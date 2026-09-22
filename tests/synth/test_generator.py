"""Generator + prompts (roadmap 4.6, S-6): templates, allowlist, backends, client, HC-1/2/5 guards."""

from __future__ import annotations

import ast
import copy
import json
import re
from pathlib import Path

import jinja2
import pytest

from slrag.core.schemas import Claim, SubIntent
from slrag.synth import generator as generator_module
from slrag.synth.config import load_synth_config
from slrag.synth.generator import (
    ClaimStreamParser,
    ExtractiveGenerator,
    LLMGenerator,
    LLMResponse,
    OpenAICompatibleClient,
    PromptLibrary,
    claims_json_schema,
    make_generator,
    parse_claim_objects,
)
from slrag.synth.types import DraftClaim
from tests.helpers import (
    FakeStreamTransport,
    pieces,
    scenario_turns,
    scored,
    sse,
    turn_evidence,
    turn_sub_intents,
)

LABEL_RE = re.compile(r"[^\s\[\]\"]+ §[^\s\[\]\",;]+")


def _turn(name: str, index: int = 0) -> dict:
    return scenario_turns(name)[index]


def _inputs(name: str, index: int = 0):
    turn = _turn(name, index)
    return turn_sub_intents(turn), turn_evidence(turn)


def _config(**generator_overrides) -> dict:
    cfg = copy.deepcopy(load_synth_config())
    for key, value in generator_overrides.items():
        cfg["generator"][key] = value
    return cfg


async def _collect(agen) -> list[DraftClaim]:
    return [item async for item in agen]


class FakeClient:
    def __init__(self, text: str = '{"claims": []}', *, prompt_tokens: int = 11, completion_tokens: int = 7,
                 error: Exception | None = None) -> None:
        self.text = text
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.error = error
        self.calls: list[tuple[str, dict | None]] = []

    async def complete(self, prompt: str, *, json_schema: dict | None = None) -> LLMResponse:
        self.calls.append((prompt, json_schema))
        if self.error is not None:
            raise self.error
        return LLMResponse(self.text, self.prompt_tokens, self.completion_tokens)


def _claims_json(*claims: dict) -> str:
    return json.dumps({"claims": list(claims)})


GOOD_CLAIM = {"intent_id": "i1", "facet": "venue_capacity", "text": "Venue A holds up to 40 people.",
              "citations": ["Doc_12 §2"]}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def test_all_templates_render():
    prompts = PromptLibrary()
    intents = [{"intent_id": "i1", "facet": "venue_capacity", "facet_label": "Venue capacity", "query_nl": "q"}]
    chunks = [{"label": "Doc_12 §2", "text": "Venue A holds up to 40 people."}]
    common = {"sub_intents": intents, "chunks": chunks, "allowed_ids": ["Doc_12 §2"], "constraints": {}}
    synth = prompts.render("synthesize", **common)
    refine = prompts.render("refine", **common, retained_claims=[{"text": "Old claim.", "citations": ["Doc_1 §1"]}])
    present = prompts.render(
        "present_only",
        claims=[{"claim_id": "c1", "facet": "venue_capacity", "text": "Venue A holds up to 40 people.",
                 "citations": ["Doc_12 §2"]}],
        instruction="Translate into Hindi.",
    )
    for prompt in (synth, refine, present):
        assert '{"claims": [{"intent_id": ' in prompt
        assert "background knowledge" in prompt                      # HC-1: parametric knowledge forbidden
    assert "Old claim." in refine and "Doc_1 §1" not in refine       # retained labels are not citable
    assert "Translate into Hindi." in present and "Doc_12 §2" in present


def test_strict_undefined_raises_on_missing_variable():
    with pytest.raises(jinja2.UndefinedError):
        PromptLibrary().render("synthesize", sub_intents=[], chunks=[], allowed_ids=[])   # no constraints
    with pytest.raises(KeyError):
        PromptLibrary().render("nonexistent")


def test_synthesize_prompt_lists_exactly_the_context_labels():
    sub_intents, evidence = _inputs("example1_multi_intent")
    prompt, allowed = LLMGenerator(FakeClient()).render_prompt(sub_intents, evidence)
    assert allowed == ["Doc_12 §2", "Doc_12 §3", "Doc_31 §4", "Doc_09 §1"]   # all chunks passed in, first-seen
    for label in allowed:
        assert label in prompt
    assert set(LABEL_RE.findall(prompt)) == set(allowed)                    # nothing outside the context
    for intent in sub_intents:
        assert intent.intent_id in prompt and intent.query_nl in prompt


def test_claims_json_schema_constrains_citations_and_intents():
    schema = claims_json_schema(["Doc_12 §2", "Doc_31 §4"], ["i1", "i2"])
    item = schema["properties"]["claims"]["items"]
    assert item["properties"]["citations"]["items"]["enum"] == ["Doc_12 §2", "Doc_31 §4"]
    assert item["properties"]["citations"]["minItems"] == 1
    assert item["properties"]["intent_id"]["enum"] == ["i1", "i2"]
    assert item["additionalProperties"] is False and schema["additionalProperties"] is False
    assert set(item["required"]) == {"intent_id", "facet", "text", "citations"}
    assert schema["required"] == ["claims"]
    nullable = claims_json_schema(["Doc_12 §2"], [])["properties"]["claims"]["items"]["properties"]["intent_id"]
    assert nullable == {"type": ["string", "null"]}


# ---------------------------------------------------------------------------
# Extractive backend (golden replay)
# ---------------------------------------------------------------------------
async def test_extractive_example1_golden():
    generator = ExtractiveGenerator()
    drafts = await _collect(generator.generate(*_inputs("example1_multi_intent")))
    assert len(drafts) == 7
    assert [d.seq for d in drafts] == list(range(7))
    by_label = [d.citations[0] for d in drafts]
    assert by_label == ["Doc_12 §2"] * 3 + ["Doc_31 §4"] * 2 + ["Doc_09 §1"] * 2
    assert list(dict.fromkeys(by_label)) == ["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"]   # Doc_12 §3 (0.42) excluded
    assert [d.facet for d in drafts[:3]] == ["venue_capacity"] * 3
    assert drafts[0].text == "Venue A holds up to 40 people." and drafts[0].confidence == pytest.approx(0.91)
    assert all(len(d.citations) == 1 for d in drafts)
    assert generator.usage.llm_calls == 0 and generator.usage.backend == "extractive"


async def test_extractive_example2_golden():
    drafts = await _collect(ExtractiveGenerator().generate(*_inputs("example2_refinement")))
    assert [d.citations for d in drafts] == [("Doc_44 §2",), ("Doc_44 §3",), ("Doc_44 §5",), ("Doc_44 §6",)]
    assert [d.intent_id for d in drafts] == ["i1", "i1", "i2", "i2"]


async def test_extractive_is_deterministic():
    inputs = _inputs("example1_multi_intent")
    first = await _collect(ExtractiveGenerator().generate(*inputs))
    second = await _collect(ExtractiveGenerator().generate(*inputs))
    assert first == second


async def test_extractive_refine_skips_retained_sentences():
    sub_intents, evidence = _inputs("example1_multi_intent")
    retained = [Claim(claim_id="c1", facet="venue_capacity", text="Venue A holds up to 40 people.",
                      citations=["Doc_12 §2"], preconditions={}, status="active", introduced_in_version=1)]
    drafts = await _collect(
        ExtractiveGenerator().generate(sub_intents[:1], evidence, mode="refine", retained_claims=retained)
    )
    assert [d.text for d in drafts] == [
        "In classroom layout Venue A seats 30 attendees.",
        "Venue B seats up to 60 people and includes a breakout room.",
    ]


async def test_generate_rejects_unknown_mode():
    with pytest.raises(ValueError):
        await _collect(ExtractiveGenerator().generate(*_inputs("example1_multi_intent"), mode="bogus"))


# ---------------------------------------------------------------------------
# LLM backend (fake client; never touches the network)
# ---------------------------------------------------------------------------
async def test_llm_generator_makes_exactly_one_call_with_schema():
    sub_intents, evidence = _inputs("example1_multi_intent")
    client = FakeClient(_claims_json(GOOD_CLAIM), prompt_tokens=900, completion_tokens=120)
    generator = LLMGenerator(client)
    drafts = await _collect(generator.generate(sub_intents, evidence))

    assert len(client.calls) == 1                                                        # HC-5
    prompt, schema = client.calls[0]
    assert schema["properties"]["claims"]["items"]["properties"]["citations"]["items"]["enum"] == [
        "Doc_12 §2", "Doc_12 §3", "Doc_31 §4", "Doc_09 §1"]
    assert "Doc_12 §2" in prompt
    assert drafts == [DraftClaim(seq=0, facet="venue_capacity", text="Venue A holds up to 40 people.",
                                 citations=("Doc_12 §2",), intent_id="i1", confidence=0.91)]
    usage = generator.usage
    assert (usage.llm_calls, usage.prompt_tokens, usage.completion_tokens, usage.backend) == (
        1, 900, 120, "openai_compatible")


async def test_llm_generator_without_schema_mode_passes_no_schema():
    cfg = _config()
    cfg["generator"]["openai_compatible"]["json_schema_mode"] = False
    client = FakeClient(_claims_json(GOOD_CLAIM))
    await _collect(LLMGenerator(client, config=cfg).generate(*_inputs("example1_multi_intent")))
    assert client.calls[0][1] is None


FENCED = "Here you go:\n```json\n" + _claims_json(GOOD_CLAIM) + "\n```\nDone."
BARE_LIST = json.dumps([GOOD_CLAIM, {**GOOD_CLAIM, "text": "Venue B seats up to 60 people."}])
JSON_LINES = "\n".join(json.dumps(c) for c in (GOOD_CLAIM, {**GOOD_CLAIM, "text": "Venue B seats up to 60 people."}))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(FENCED, 1), (BARE_LIST, 2), (JSON_LINES, 2), (json.dumps(GOOD_CLAIM), 1)],
    ids=["fenced", "bare_list", "json_lines", "single_object"],
)
async def test_llm_generator_parses_output_shapes(raw, expected):
    generator = LLMGenerator(FakeClient(raw))
    drafts = await _collect(generator.generate(*_inputs("example1_multi_intent")))
    assert len(drafts) == expected and generator.parse_errors == 0
    assert drafts[0].text == "Venue A holds up to 40 people."
    assert [d.seq for d in drafts] == list(range(expected))


async def test_llm_generator_skips_malformed_items():
    raw = _claims_json(GOOD_CLAIM, "not a claim", {"intent_id": "i1", "citations": ["Doc_12 §2"]},
                       {**GOOD_CLAIM, "text": "   "}, 42)
    generator = LLMGenerator(FakeClient(raw))
    drafts = await _collect(generator.generate(*_inputs("example1_multi_intent")))
    assert [d.text for d in drafts] == ["Venue A holds up to 40 people."]
    assert generator.parse_errors == 4


async def test_llm_generator_never_raises_on_garbage_or_truncated_output():
    generator = LLMGenerator(FakeClient("I am sorry, I cannot help with that."))
    assert await _collect(generator.generate(*_inputs("example1_multi_intent"))) == []
    assert generator.parse_errors == 1 and generator.usage.llm_calls == 1

    truncated = _claims_json(GOOD_CLAIM, {**GOOD_CLAIM, "text": "Venue B"})[:-30]
    generator = LLMGenerator(FakeClient(truncated))
    drafts = await _collect(generator.generate(*_inputs("example1_multi_intent")))
    assert [d.text for d in drafts] == ["Venue A holds up to 40 people."]      # complete objects salvaged
    assert generator.parse_errors >= 1


async def test_llm_generator_passes_fabricated_labels_and_drops_non_strings():
    claim = {"intent_id": "i1", "facet": "venue_capacity", "text": "Venue B seats up to 60 people.",
             "citations": ["Doc_77 §9", 12, None, {"x": 1}, "Doc_12 §2"]}
    drafts = await _collect(LLMGenerator(FakeClient(_claims_json(claim))).generate(*_inputs("example1_multi_intent")))
    assert drafts[0].citations == ("Doc_77 §9", "Doc_12 §2")        # verifier (layer 3) strips Doc_77, not us
    assert drafts[0].confidence == pytest.approx(0.91)


async def test_llm_generator_facet_falls_back_to_intent():
    claim = {"intent_id": "i2", "text": "Cancellations made within 14 days forfeit the deposit.",
             "citations": ["Doc_31 §4"]}
    drafts = await _collect(LLMGenerator(FakeClient(_claims_json(claim))).generate(*_inputs("example1_multi_intent")))
    assert drafts[0].facet == "cancellation_terms" and drafts[0].intent_id == "i2"


async def test_llm_generator_refine_mode_uses_refine_template():
    retained = [Claim(claim_id="c1", facet="travel_reimbursement", text="Economy airfare is reimbursed.",
                      citations=["Doc_44 §2"], preconditions={}, status="active", introduced_in_version=1)]
    target = SubIntent(intent_id="d2_0", facet="travel_reimbursement", novel=True,
                       query_nl="international travel reimbursement exception",
                       search_string="international travel reimbursement exception")
    evidence = {"d2_0": [scored("Doc_44#7#0", 0.86)]}
    client = FakeClient(_claims_json({"intent_id": "d2_0", "facet": "travel_reimbursement",
                                      "text": "International trips are reimbursed only when pre-approved.",
                                      "citations": ["Doc_44 §7"]}))
    generator = LLMGenerator(client)
    drafts = await _collect(generator.generate([target], evidence, constraints={"trip_type": "international"},
                                               mode="refine", retained_claims=retained))
    prompt, schema = client.calls[0]
    assert "RETAINED CLAIMS" in prompt and "Economy airfare is reimbursed." in prompt
    assert "trip_type: international" in prompt                                # new constraint delta shown
    assert schema["properties"]["claims"]["items"]["properties"]["intent_id"]["enum"] == ["d2_0"]
    assert [d.citations for d in drafts] == [("Doc_44 §7",)] and len(client.calls) == 1


async def test_llm_generator_spends_no_call_without_evidence():
    sub_intents, _ = _inputs("example1_multi_intent")
    client = FakeClient(_claims_json(GOOD_CLAIM))
    generator = LLMGenerator(client)
    assert await _collect(generator.generate(sub_intents, {})) == []
    assert client.calls == [] and generator.usage.llm_calls == 0


async def test_llm_generator_degrades_on_transport_failure_without_retry():
    client = FakeClient(error=ConnectionRefusedError("ollama down"))
    generator = LLMGenerator(client)
    assert await _collect(generator.generate(*_inputs("example1_multi_intent"))) == []
    assert len(client.calls) == 1 and generator.usage.llm_calls == 1               # no retry (HC-5)
    assert "ConnectionRefusedError" in (generator.last_error or "")


async def test_llm_generator_restyle_uses_present_only_template():
    claims = [Claim(claim_id="c1", facet="venue_capacity", text="Venue A holds up to 40 people.",
                    citations=["Doc_12 §2"], preconditions={}, status="active", introduced_in_version=1)]
    client = FakeClient(_claims_json({"intent_id": None, "facet": "venue_capacity",
                                      "text": "Venue A mein 40 log aa sakte hain.", "citations": ["Doc_12 §2"]}))
    generator = LLMGenerator(client)
    drafts = await _collect(generator.restyle(claims, "Translate into Hinglish."))
    prompt, schema = client.calls[0]
    assert "Translate into Hinglish." in prompt and "c1" in prompt
    assert schema["properties"]["claims"]["items"]["properties"]["citations"]["items"]["enum"] == ["Doc_12 §2"]
    assert drafts[0].intent_id is None and drafts[0].citations == ("Doc_12 §2",)


def test_parse_claim_objects_counts_broken_fragments():
    items, broken = parse_claim_objects(json.dumps(GOOD_CLAIM) + '\n{"text": "cut off", "citat')
    assert items == [GOOD_CLAIM] and broken == 1
    assert parse_claim_objects("") == ([], 0)


# ---------------------------------------------------------------------------
# OpenAI-compatible client (fake transport; HC-1 guard)
# ---------------------------------------------------------------------------
class FakeTransport:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.requests: list[tuple[str, dict, dict, float]] = []

    def __call__(self, url: str, body: dict, headers: dict, timeout: float) -> dict:
        self.requests.append((url, body, headers, timeout))
        return self.response


def _client_config(**overrides) -> dict:
    cfg = _config()
    cfg["generator"]["openai_compatible"].update(overrides)
    return cfg


async def test_client_request_shape_and_usage(monkeypatch):
    monkeypatch.setenv("SLRAG_LLM_API_KEY", "sekret")
    transport = FakeTransport({"choices": [{"message": {"content": '{"claims": []}'}}],
                               "usage": {"prompt_tokens": 321, "completion_tokens": 45}})
    client = OpenAICompatibleClient(_client_config(), transport=transport)
    schema = claims_json_schema(["Doc_12 §2"], ["i1"])
    response = await client.complete("PROMPT", json_schema=schema)

    url, body, headers, timeout = transport.requests[0]
    assert url == "http://localhost:11434/v1/chat/completions" and timeout == 30.0
    assert body["model"] == "qwen2.5:7b-instruct"
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert body["temperature"] == 0.0 and body["max_tokens"] == 700
    assert body["response_format"] == {"type": "json_schema",
                                       "json_schema": {"name": "claims", "schema": schema, "strict": True}}
    assert headers["Authorization"] == "Bearer sekret"
    assert response == LLMResponse(text='{"claims": []}', prompt_tokens=321, completion_tokens=45)


async def test_client_without_schema_or_key_and_usage_fallback(monkeypatch):
    monkeypatch.delenv("SLRAG_LLM_API_KEY", raising=False)
    transport = FakeTransport({"choices": [{"message": {"content": "one two three"}}]})
    client = OpenAICompatibleClient(_client_config(), transport=transport)
    response = await client.complete("a b c d")
    _, body, headers, _ = transport.requests[0]
    assert "response_format" not in body and "Authorization" not in headers
    assert (response.prompt_tokens, response.completion_tokens) == (4, 3)       # word-count estimate
    assert (await OpenAICompatibleClient(_client_config(), transport=FakeTransport({})).complete("x")).text == ""


@pytest.mark.parametrize("url", ["http://localhost:11434/v1", "http://127.0.0.1:8000/v1", "http://[::1]:8000/v1",
                                 "http://host.docker.internal:11434/v1", "http://ollama:11434/v1"])
def test_client_accepts_local_endpoints(url):
    assert OpenAICompatibleClient(_client_config(base_url=url), transport=FakeTransport({})).base_url == url


@pytest.mark.parametrize("url", ["https://api.openai.com/v1", "http://10.0.0.5:8000/v1", "http://llm.example.com"])
def test_client_refuses_remote_endpoints(url):
    with pytest.raises(ValueError, match="HC-1"):
        OpenAICompatibleClient(_client_config(base_url=url), transport=FakeTransport({}))
    assert OpenAICompatibleClient(_client_config(base_url=url, allow_remote=True), transport=FakeTransport({}))


def test_client_refuses_non_http_schemes():
    with pytest.raises(ValueError):
        OpenAICompatibleClient(_client_config(base_url="file:///etc/passwd", allow_remote=True))


# ---------------------------------------------------------------------------
# Factory + HC-2 guard
# ---------------------------------------------------------------------------
def test_make_generator_factory():
    assert isinstance(make_generator(), ExtractiveGenerator)
    client = FakeClient()
    llm = make_generator(_config(backend="openai_compatible"), client=client)
    assert isinstance(llm, LLMGenerator) and llm.client is client
    built = make_generator(_config(backend="openai_compatible"))
    assert isinstance(built.client, OpenAICompatibleClient)                     # constructs, never connects
    with pytest.raises(ValueError):
        make_generator(_config(backend="gpt-in-the-cloud"))


def test_hc2_no_prompt_text_in_generator_source():
    tree = ast.parse(Path(generator_module.__file__).read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
    }
    long_literals = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in docstrings and len(node.value) > 120
    ]
    assert long_literals == []


# ---------------------------------------------------------------------------
# Streaming (audit W-1): SSE client + incremental claim parsing
# ---------------------------------------------------------------------------
OTHER_CLAIM = {"intent_id": "i2", "facet": "cancellation_terms",
               "text": "Cancellations made more than 14 days before the event receive a full refund.",
               "citations": ["Doc_31 §4"]}
TRICKY_CLAIM = {"intent_id": "i1", "facet": "venue_capacity",
                "text": 'Venue A {main hall} holds "up to" 40 people}.', "citations": ["Doc_12 §2"]}


@pytest.mark.parametrize("size", [1, 7, 0])
@pytest.mark.parametrize("raw", [
    _claims_json(GOOD_CLAIM, OTHER_CLAIM),
    json.dumps([GOOD_CLAIM, TRICKY_CLAIM]),
    json.dumps(GOOD_CLAIM) + "\n" + json.dumps(OTHER_CLAIM),
    "```json\n" + _claims_json(TRICKY_CLAIM) + "\n```",
    _claims_json({**GOOD_CLAIM, "meta": {"k": 1}}),
    '{"claims": [{"text": "cut off", "citat',
    '{"claims": []}',
    '{"claims": [{"facet": "venue_capacity"}]}',
    "Sorry, I cannot help with that.",
])
def test_stream_parser_matches_the_whole_text_parser(raw, size):
    parser = ClaimStreamParser()
    items = [item for piece in pieces(raw, size) for item in parser.feed(piece)]
    items += parser.finish()
    assert (items, parser.broken) == parse_claim_objects(raw)


@pytest.mark.parametrize("size", [1, 7, 0])
def test_stream_parser_counts_one_broken_claim_for_truncated_output(size):
    raw = _claims_json(GOOD_CLAIM)[:-2] + ', {"text": "cut off", "citat'
    parser = ClaimStreamParser()
    items = [item for piece in pieces(raw, size) for item in parser.feed(piece)] + parser.finish()
    assert items == [GOOD_CLAIM] and parser.broken == 1
    whole_items, whole_broken = parse_claim_objects(raw)      # the whole-text parser also counts the
    assert whole_items == items and whole_broken >= 1         # unclosed wrapper; streaming is exact


def test_stream_parser_yields_each_claim_as_its_object_closes():
    raw = _claims_json(GOOD_CLAIM, OTHER_CLAIM)
    cut = raw.index("}") + 1                       # end of the first claim object
    parser = ClaimStreamParser()
    assert parser.feed(raw[:cut]) == [GOOD_CLAIM]
    assert parser.feed(raw[cut:cut + 20]) == []
    assert parser.feed(raw[cut + 20:]) == [OTHER_CLAIM]
    assert parser.finish() == [] and parser.broken == 0


def _streaming_client(transport: FakeStreamTransport, **overrides) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(_client_config(stream=True, **overrides), transport=FakeTransport({}),
                                  stream_transport=transport)


async def test_client_stream_request_shape_deltas_and_usage():
    transport = FakeStreamTransport(sse(["{\"cla", "ims\": []}"], usage={"prompt_tokens": 50, "completion_tokens": 4}))
    client = _streaming_client(transport)
    deltas = [delta async for delta in client.stream("PROMPT", json_schema=claims_json_schema(["Doc_12 §2"], ["i1"]))]

    _, body, _, _ = transport.requests[0]
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}
    assert body["response_format"]["type"] == "json_schema"
    assert deltas == ['{"cla', 'ims": []}']                     # comments, blanks and post-[DONE] lines ignored
    assert client.last_usage == LLMResponse('{"claims": []}', 50, 4)


async def test_client_stream_estimates_usage_without_a_usage_chunk():
    client = _streaming_client(FakeStreamTransport(sse(["one two", " three"])), stream_usage=False)
    assert [d async for d in client.stream("a b c d")] == ["one two", " three"]
    assert (client.last_usage.prompt_tokens, client.last_usage.completion_tokens) == (4, 3)
    assert "stream_options" not in client.build_request("x", stream=True)[1]


async def test_llm_generator_streams_drafts_before_the_response_finishes():
    raw = _claims_json(GOOD_CLAIM, OTHER_CLAIM)
    log: list[str] = []
    transport = FakeStreamTransport(sse(pieces(raw, 8), usage={"prompt_tokens": 900, "completion_tokens": 60}),
                                    log=log)
    generator = LLMGenerator(_streaming_client(transport))
    drafts = []
    async for draft in generator.generate(*_inputs("example1_multi_intent")):
        log.append(f"draft:{draft.seq}")
        drafts.append(draft)

    assert [d.text for d in drafts] == [GOOD_CLAIM["text"], OTHER_CLAIM["text"]]
    last_content_line = max(i for i, line in enumerate(transport.lines) if '"content"' in line and "late" not in line)
    assert log.index("draft:0") < log.index(f"sent:{last_content_line}")       # TTFT: before the stream ends
    assert len(transport.requests) == 1 and generator.usage.llm_calls == 1     # still one call (HC-5)
    assert (generator.usage.prompt_tokens, generator.usage.completion_tokens) == (900, 60)
    assert 0 <= generator.usage.first_draft_ms <= generator.usage.latency_ms
    assert generator.parse_errors == 0


async def test_llm_generator_keeps_streamed_drafts_when_the_connection_drops():
    raw = _claims_json(GOOD_CLAIM, OTHER_CLAIM)
    lines = sse(pieces(raw, 8))
    inside_second = raw.index('{"intent_id": "i2"') + 10
    drop = 2 + 2 * (inside_second // 8)             # 2 preamble lines, then a data line + blank per piece
    generator = LLMGenerator(_streaming_client(FakeStreamTransport(lines, fail_at=drop)))
    drafts = await _collect(generator.generate(*_inputs("example1_multi_intent")))

    assert [d.text for d in drafts] == [GOOD_CLAIM["text"]]
    assert "ConnectionResetError" in (generator.last_error or "")
    assert generator.usage.llm_calls == 1 and generator.parse_errors == 1      # truncated second claim, no retry


async def test_streaming_off_uses_one_blocking_completion():
    transport = FakeTransport({"choices": [{"message": {"content": _claims_json(GOOD_CLAIM)}}]})
    stream = FakeStreamTransport([])
    client = OpenAICompatibleClient(_client_config(stream=False), transport=transport, stream_transport=stream)
    drafts = await _collect(LLMGenerator(client).generate(*_inputs("example1_multi_intent")))
    assert [d.text for d in drafts] == [GOOD_CLAIM["text"]]
    assert len(transport.requests) == 1 and stream.requests == []
