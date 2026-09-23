"""Golden replay for Component 4: brief Examples 1–3 reproduced end-to-end.

Upstream components are replaced by fixture data (what the stubs/real Component
1–3 would hand over), so this is the contract test the walking skeleton's CI
runs against ``SynthesisEngine`` before Matangi's harness wires it in.
"""

from __future__ import annotations

import copy
import dataclasses
import json

import pytest

from slrag.core.citations import find_markers
from slrag.core.schemas import AnswerOutput, TelemetryEvent
from slrag.core.session import SessionStore
from slrag.synth.config import load_synth_config
from slrag.synth.engine import SynthesisEngine, TurnInput
from slrag.synth.generator import LLMGenerator, LLMResponse, OpenAICompatibleClient
from slrag.synth.renderer import render_claims
from tests.helpers import (
    FakeStreamTransport,
    FixtureRetriever,
    load_scenarios,
    pieces,
    scenario_turns,
    sse,
    turn_decisions,
    turn_evidence,
    turn_sub_intents,
)


def _turn_input(turn: dict) -> TurnInput:
    return TurnInput(
        turn_id=turn["turn_id"],
        utterance=turn["utterance"],
        t_s_end=turn["t_s_end"],
        sub_intents=turn_sub_intents(turn),
        evidence=turn_evidence(turn),
        retrieval_events=turn["retrieval_events"],
        controller_decisions=turn_decisions(turn),
    )


async def _run(name: str, *, retriever=None, **engine_kwargs):
    turns = scenario_turns(name)
    if retriever is None:
        delta_evidence = {}
        for turn in turns:
            delta_evidence.update(turn.get("delta_evidence", {}))
        retriever = FixtureRetriever(delta_evidence)
    engine = SynthesisEngine(f"sess_{name}", retrieve_fn=retriever, **engine_kwargs)
    results = [await engine.handle_turn(_turn_input(turn)) for turn in turns]
    return engine, retriever, turns, results


def _assert_contract(result) -> None:
    """Schema-valid output, closed allowlist, every marker in the answer is a listed citation."""
    AnswerOutput.model_validate(json.loads(result.output.model_dump_json()))
    assert result.fabricated_id_count == 0
    marked = {label for _, labels in find_markers(result.output.answer) for label in labels}
    assert marked <= set(result.output.citations)
    assert all(isinstance(event, TelemetryEvent) for event in result.telemetry)
    rendered = result.to_json()
    assert list(rendered)[:5] == ["retrieval_events", "sub_queries", "answer", "citations", "uncertainty"]


def _assert_two_pass_order(events) -> None:
    seen_provisional, resolved = set(), []
    for event in events:
        if event.kind == "provisional":
            seen_provisional.add(event.seq)
        else:
            assert event.seq in seen_provisional, "committed/retracted before provisional"
            resolved.append(event.seq)
    assert resolved == sorted(resolved) and set(resolved) == seen_provisional


async def test_example1_multi_intent_reproduces_brief_output():
    _, _, turns, (result,) = await _run("example1_multi_intent")
    turn, expected = turns[0], turns[0]["expected"]

    assert result.turn_type == expected["turn_type"]
    out = result.output
    assert out.answer_version == expected["answer_version"]
    assert out.sub_queries == expected["sub_queries"]
    assert out.retrieval_events == turn["retrieval_events"]
    assert out.citations == expected["citations"]
    assert out.uncertainty == expected["uncertainty"]
    assert [c["facet"] for c in result.extensions["claims"]][:1] == ["venue_capacity"]
    assert {c["facet"] for c in result.extensions["claims"]} == set(expected["facets_covered"])
    assert result.extensions["version_lineage"]["to"] == 1
    assert result.extensions["retrieval_required"] is True
    _assert_contract(result)
    _assert_two_pass_order(result.stream_events)


async def test_example2_refinement_is_a_delta_not_a_restart():
    engine, retriever, turns, (v1, v2) = await _run("example2_refinement")
    exp1, exp2 = turns[0]["expected"], turns[1]["expected"]

    assert v1.turn_type == "NEW_INTENT" and v1.output.answer_version == 1
    assert v1.output.citations == exp1["citations"]
    assert len(v1.extensions["claims"]) == exp1["claims_active"]

    assert v2.turn_type == exp2["turn_type"]
    assert dict(v2.classification.delta.slots) == exp2["constraint_delta"]
    event = v2.refinement.to_event()
    assert {k: event[k] for k in exp2["refinement"]} == exp2["refinement"]
    assert v2.refinement.citations_preserved == exp2["citations_preserved"]
    assert v2.refinement.citations_added == exp2["citations_added"]
    assert v2.output.answer_version == 2
    assert v2.output.citations == exp2["citations_preserved"] + exp2["citations_added"]
    assert v2.output.sub_queries == exp2["sub_queries"]
    assert [e["trigger"] for e in v2.output.retrieval_events] == exp2["retrieval_triggers"]
    assert [q.search_string for q in retriever.calls] == exp2["sub_queries"]

    lineage = v2.extensions["version_lineage"]
    assert (lineage["from"], lineage["to"]) == (1, 2)
    v1_claims = {c["claim_id"]: c for c in v1.extensions["claims"]}
    v2_claims = {c["claim_id"]: c for c in v2.extensions["claims"]}
    for claim_id in lineage["retained"]:                      # retained byte-for-byte
        assert v2_claims[claim_id] == v1_claims[claim_id]
    assert set(lineage["superseded"]).isdisjoint(v2_claims)   # superseded no longer active
    assert any("reimbursed for economy airfare" in c["text"] for c in v2_claims.values())
    _assert_contract(v1)
    _assert_contract(v2)


class ExplodingRetriever:
    def __call__(self, sub_intent):
        raise AssertionError("presentation-only turns must never reach retrieval")


async def test_example3_presentation_only_never_retrieves():
    engine, _, turns, (v1, v2) = await _run("example3_presentation", retriever=ExplodingRetriever())
    expected = turns[-1]["expected"]

    assert v2.turn_type == expected["turn_type"]
    assert v2.output.retrieval_events == []
    assert v2.output.answer_version == expected["answer_version"] == v1.output.answer_version
    assert set(v2.output.citations) <= set(v1.output.citations)
    assert v2.extensions["retrieval_required"] is expected["retrieval_required"]
    assert v2.extensions["suppression_reason"] == expected["suppression_reason"]
    bullets = [line for line in v2.output.answer.splitlines() if line.strip()]
    assert len(bullets) == expected["bullet_count"]
    assert all(line.startswith("- ") for line in bullets)
    assert v2.usage.llm_calls == 0
    _assert_contract(v2)


class FakeLLM:
    """Local-LLM stand-in: cites one real label and one fabricated label per call."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str, *, json_schema=None) -> LLMResponse:
        self.calls += 1
        claims = [
            {"intent_id": "i1", "facet": "venue_capacity",
             "text": "Venue A holds up to 40 people.", "citations": ["Doc_12 §2"]},
            {"intent_id": "i1", "facet": "venue_capacity",
             "text": "Venue B seats up to 60 people and includes a breakout room.",
             "citations": ["Doc_77 §9"]},
            {"intent_id": "i2", "facet": "cancellation_terms",
             "text": "Cancellations are free up to 90 days before the event.", "citations": ["Doc_31 §4"]},
        ]
        return LLMResponse(text=json.dumps({"claims": claims}), prompt_tokens=900, completion_tokens=120)


async def test_llm_backend_respects_budget_and_allowlist():
    client = FakeLLM()
    generator = LLMGenerator(client)
    _, _, _, (result,) = await _run("example1_multi_intent", generator=generator)

    assert client.calls == 1 and result.usage.llm_calls == 1            # HC-5: one synthesis call/turn
    assert result.fabricated_id_count == 0                                # Doc_77 never reaches output
    assert "Doc_77 §9" not in result.output.answer
    texts = [c["text"] for c in result.extensions["claims"]]
    assert texts == ["Venue A holds up to 40 people."]
    assert "Cancellations are free up to 90 days before the event." not in texts   # copy check retracts
    demoted = [r for r in result.verification if "fabricated_citation" in r.reasons]
    assert [r.fabricated for r in demoted] == [("Doc_77 §9",)]               # A §4.4: demoted, not rescued
    assert "Cancellation and refund terms could not be verified" in result.output.uncertainty
    _assert_contract(result)


async def test_sessions_are_isolated_and_destroyable():
    engine_a, _, _, _ = await _run("example1_multi_intent")
    engine_b = SynthesisEngine("sess_other")
    assert len(engine_b.graph) == 0 and not engine_b.graph.known_labels()
    engine_a.destroy()
    assert len(engine_a.graph) == 0 and engine_a.session_constraints == {}


async def test_stream_turn_emits_provisional_events_before_the_result():
    turn = scenario_turns("example1_multi_intent")[0]
    engine = SynthesisEngine("sess_stream")
    items = [item async for item in engine.stream_turn(_turn_input(turn))]
    assert items[0].kind == "provisional"
    assert items[-1].output.answer_version == 1
    _assert_two_pass_order(items[:-1])


@pytest.mark.parametrize("name", sorted(load_scenarios()))
async def test_every_golden_scenario_has_zero_fabricated_ids(name):
    _, _, _, results = await _run(name, retriever=None if name != "example3_presentation" else ExplodingRetriever())
    assert all(r.fabricated_id_count == 0 for r in results)


async def _run_routed(name: str):
    """Harness order (audit C-3): classify at utterance end; run Components 2-3 only when told to."""
    turns = scenario_turns(name)
    delta_evidence = {k: v for turn in turns for k, v in turn.get("delta_evidence", {}).items()}
    retriever = FixtureRetriever(delta_evidence)
    store = SessionStore(lambda sid: SynthesisEngine(sid, retrieve_fn=retriever), ttl_s=60)
    results, upstream_passes = [], 0
    for turn in turns:
        async with store.turn(f"sess_{name}") as engine:
            classification = engine.classify(turn["utterance"], turn_decisions(turn))
            routed = TurnInput(turn_id=turn["turn_id"], utterance=turn["utterance"], t_s_end=turn["t_s_end"],
                               controller_decisions=turn_decisions(turn), classification=classification)
            if classification.needs_upstream_retrieval:
                upstream_passes += 1
                routed = dataclasses.replace(routed, sub_intents=turn_sub_intents(turn),
                                             evidence=turn_evidence(turn), retrieval_events=turn["retrieval_events"])
            results.append(await engine.handle_turn(routed))
    return turns, results, retriever, upstream_passes


@pytest.mark.parametrize("name", sorted(load_scenarios()))
async def test_pre_decomposition_routing_reproduces_every_golden_scenario(name):
    _, _, turns, golden = await _run(name)
    _, routed, retriever, upstream_passes = await _run_routed(name)

    assert [r.output.model_dump() for r in routed] == [r.output.model_dump() for r in golden]
    assert upstream_passes == sum(t["expected"]["turn_type"] == "NEW_INTENT" for t in turns if "expected" in t)
    assert all(r.telemetry[0].payload["precomputed"] for r in routed)
    assert not any(r.telemetry[0].payload["stale"] for r in routed)
    if name == "example2_refinement":
        # The refinement turn skipped upstream entirely: its only searches are the 2 targeted ones.
        assert [q.search_string for q in retriever.calls] == turns[1]["expected"]["sub_queries"]


async def test_a_stale_precomputed_classification_is_redone():
    """Audit N-3: another turn ran between classify() and handle_turn(); the stale route is not trusted."""
    first, second = scenario_turns("example2_refinement")
    retriever = FixtureRetriever(second["delta_evidence"])
    engine = SynthesisEngine("sess_stale", retrieve_fn=retriever)
    early = engine.classify(second["utterance"])                       # empty session: NEW_INTENT
    assert early.turn_type == "NEW_INTENT" and early.session_epoch == 0
    await engine.handle_turn(_turn_input(first))
    result = await engine.handle_turn(
        TurnInput(turn_id=2, utterance=second["utterance"], t_s_end=second["t_s_end"], classification=early)
    )
    assert result.turn_type == "CONSTRAINT_REFINEMENT"
    classify = result.telemetry[0].payload
    assert classify["precomputed"] is True and classify["stale"] is True
    assert result.refinement.delta_queries_issued == 2


class RestyleLLM:
    """Local-LLM stand-in for the present_only call; ``make`` builds the reply from the active claims."""

    def __init__(self, make) -> None:
        self.make, self.calls = make, 0

    async def complete(self, prompt: str, *, json_schema=None) -> LLMResponse:
        self.calls += 1
        claims = self.make(self.active)
        text = claims if isinstance(claims, str) else json.dumps({"claims": claims})
        return LLMResponse(text=text, prompt_tokens=300, completion_tokens=80)


def _restated(claims, edit=lambda text: f"{text[:-1]} (translated)."):
    return [{"intent_id": None, "facet": c.facet, "text": edit(c.text), "citations": list(c.citations)}
            for c in claims]


async def _presentation_turn(llm: RestyleLLM, utterance: str, reason: str):
    engine, _, _, (v1,) = await _run("example1_multi_intent")
    llm.active = engine.graph.active()
    engine.generator = LLMGenerator(llm)
    engine.retrieve_fn = ExplodingRetriever()
    decision = {"t_s": 0.9, "decision": "NO_RETRIEVAL", "reason": reason, "confidence": 0.95}
    turn = {"turn_id": 2, "utterance": utterance, "t_s_end": 0.9, "retrieval_events": [],
            "controller_decisions": [decision]}
    v2 = await engine.handle_turn(_turn_input(turn))
    render = next(e for e in v2.telemetry if e.component == "synthesis.render")
    return engine, llm, v1, v2, render.payload


async def test_translation_turn_uses_one_verified_llm_restyle():
    engine, llm, v1, v2, render = await _presentation_turn(
        RestyleLLM(_restated), "Can you translate that into Hindi?", "translation")

    assert v2.turn_type == "PRESENTATION_ONLY" and render["restyle"] == "llm"
    assert llm.calls == 1 and v2.usage.llm_calls == 1                         # HC-5: one call
    assert v2.output.answer.count("(translated)") == len(engine.graph.active())
    assert v2.output.citations == v1.output.citations                        # same sources, subset by construction
    assert v2.output.retrieval_events == [] and v2.extensions["suppression_reason"] == "translation"
    assert v2.output.answer_version == 1 and v2.extensions["claims"] == v1.extensions["claims"]  # graph untouched
    assert v2.extensions["restyle_fallback"] is None
    _assert_contract(v2)


async def test_translation_without_an_llm_backend_reports_the_fallback():
    engine, _, _, _ = await _run("example1_multi_intent")          # extractive backend: cannot restyle
    decision = {"t_s": 0.9, "decision": "NO_RETRIEVAL", "reason": "translation", "confidence": 0.95}
    turn = {"turn_id": 2, "utterance": "Can you translate that into Hindi?", "t_s_end": 0.9,
            "retrieval_events": [], "controller_decisions": [decision]}
    v2 = await engine.handle_turn(_turn_input(turn))
    assert v2.extensions["suppression_reason"] == "translation"
    assert v2.extensions["restyle_fallback"] == "no_llm_backend"
    assert v2.output.answer == render_claims(engine.graph.active(), config=engine.config)
    _assert_contract(v2)


@pytest.mark.parametrize("make, outcome", [
    (lambda active: _restated(active[:1]) + [{**row, "citations": ["Doc_77 §9"]} for row in _restated(active[1:])],
     "fallback:citation_outside_prior"),
    (lambda active: _restated(active, lambda t: t.replace("40", "400")), "fallback:copy_check_failed"),
    (lambda active: _restated(active[:1]), "fallback:content_dropped"),
    (lambda active: "Sorry, I cannot help with that.", "fallback:no_output"),
])
async def test_ungrounded_restyle_falls_back_to_the_deterministic_render(make, outcome):
    engine, llm, _, v2, render = await _presentation_turn(
        RestyleLLM(make), "Say that again in a friendlier tone.", "tone_change")

    assert render["restyle"] == outcome and llm.calls == 1
    assert v2.extensions["restyle_fallback"] == outcome.split(":", 1)[1]      # I-11: the UI can say so
    assert v2.output.answer == render_claims(engine.graph.active(), config=engine.config)
    assert "(translated)" not in v2.output.answer and "Doc_77" not in v2.output.answer
    _assert_contract(v2)


async def test_restructure_requests_never_call_the_llm():
    _, llm, _, v2, render = await _presentation_turn(
        RestyleLLM(_restated), "Can you repeat that in two bullets?", "presentation_restructure")
    assert llm.calls == 0 and v2.usage.llm_calls == 0 and render["restyle"] is None
    assert v2.extensions["restyle_fallback"] is None
    assert len(v2.output.answer.splitlines()) == 2


async def test_streaming_llm_shows_the_first_sentence_before_generation_ends():
    """Audit W-1: with stream: true the first PROVISIONAL event precedes the end of the LLM stream."""
    claims = [
        {"intent_id": "i1", "facet": "venue_capacity", "text": "Venue A holds up to 40 people.",
         "citations": ["Doc_12 §2"]},
        {"intent_id": "i2", "facet": "cancellation_terms",
         "text": "Cancellations made more than 14 days before the event receive a full refund.",
         "citations": ["Doc_31 §4"]},
    ]
    log: list[str] = []
    transport = FakeStreamTransport(sse(pieces(json.dumps({"claims": claims}), 6)), log=log)
    config = copy.deepcopy(load_synth_config())
    config["generator"]["openai_compatible"]["stream"] = True
    client = OpenAICompatibleClient(config, stream_transport=transport)
    engine = SynthesisEngine("sess_stream_llm", generator=LLMGenerator(client, config=config))
    turn = scenario_turns("example1_multi_intent")[0]
    async for item in engine.stream_turn(_turn_input(turn)):
        if getattr(item, "kind", None) == "provisional":
            log.append(f"provisional:{item.seq}")
        result = item

    last_content = max(n for n, line in enumerate(transport.lines) if '"content"' in line and "late" not in line)
    assert log.index("provisional:0") < log.index(f"sent:{last_content}")
    assert [c["text"] for c in result.extensions["claims"]] == [c["text"] for c in claims]
    generation = next(e for e in result.telemetry if e.component == "synthesis.generation")
    assert generation.payload["llm_calls"] == 1 and generation.payload["first_draft_ms"] is not None
    _assert_contract(result)
