"""Unrelated-domain regressions for repeated streaming intents and grounding."""
import numpy as np
import pytest

from slrag.core.schemas import RetrievedChunk, SubIntent
from slrag.core.session import SessionState
from slrag.decompose.intent_set import IntentSet
from slrag.synth.types import DraftClaim
from slrag.synth.verifier import CitationAllowlist, ClaimVerifier


class Encoder:
    def encode(self, text, **kwargs):
        return np.array([1.0, 0.0])


@pytest.mark.asyncio
async def test_explicit_requests_split_even_when_model_merges_same_topic():
    from slrag.decompose.decomposer import Decomposer
    from types import SimpleNamespace
    decomposer = object.__new__(Decomposer)
    decomposer.max_llm_calls = 2
    decomposer.facets = ["general"]
    decomposer.default_facet = "general"
    decomposer.nlp = None
    decomposer.prompt_template = SimpleNamespace(render=lambda **kw: kw["prefix"])
    async def merged(prompt):
        return {"sub_intents": [{"query_nl": prompt, "search_string": prompt}]}
    decomposer._call_llm = merged
    prefix = "List the sensor modules and what do they aim to do?"
    final = await decomposer.decompose(prefix, {}, 0)
    assert len(final) == 2
    assert final[0].query_nl.lower().startswith("list")
    assert "aim" in final[1].query_nl
    assert "they" not in final[1].query_nl.lower().split()
    assert "sensor modules" in final[1].query_nl
    narrowed = await decomposer.decompose(prefix + " Actually don't explain the purpose; just list the modules.", {}, 1)
    assert len(narrowed) == 1
    assert narrowed[0].query_nl.lower().startswith("list")


@pytest.mark.asyncio
async def test_distinct_request_operations_do_not_semantically_merge(monkeypatch):
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model", lambda _: Encoder())
    state = SessionState("heldout_operations")
    intents = IntentSet(state)
    first = SubIntent(intent_id="a", facet="general", query_nl="List sensor modules", search_string="sensor modules list")
    second = SubIntent(intent_id="b", facet="general", query_nl="What do sensor modules aim to do?", search_string="sensor modules purpose")
    assert len(await intents.add_intents([first, second])) == 2


@pytest.mark.asyncio
async def test_decomposition_uses_configured_output_and_timeout_limits(monkeypatch):
    import aiohttp
    from pathlib import Path
    from slrag.decompose.decomposer import Decomposer
    capture = {}
    class Response:
        status = 200
        async def json(self): return {"choices": [{"message": {"content": '{"sub_intents": []}'}}]}
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
    class Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def post(self, url, **kwargs):
            capture.update(kwargs)
            return Response()
    monkeypatch.setattr(aiohttp, "ClientSession", Client)
    decomposer = object.__new__(Decomposer)
    decomposer.config_dir = Path("config")
    decomposer._load_yaml = lambda path: {"generator": {"openai_compatible": {
        "decomposition_max_tokens": 768, "timeout_s": 120, "temperature": 0}}}
    assert await decomposer._call_llm("List sensor modules") == {"sub_intents": []}
    assert capture["json"]["max_tokens"] == 768
    assert capture["timeout"].total == 120


def candidate(ident, facet="sensor", **kwargs):
    return SubIntent(intent_id=ident, facet=facet, query_nl="sensor voltage limit",
                     search_string="sensor voltage limit", **kwargs)


@pytest.mark.asyncio
async def test_repeat_is_not_a_correction_even_if_model_says_supersedes(monkeypatch):
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model", lambda _: Encoder())
    state = SessionState("heldout")
    intents = IntentSet(state)
    first = candidate("first")
    await intents.add_intents([first])
    intents.mark_dispatched(first.intent_id)
    repeat = candidate("repeat", supersedes=[first.intent_id])
    assert await intents.add_intents([repeat]) == []
    assert repeat.intent_id == first.intent_id
    assert len(state.intent_set) == 1


@pytest.mark.asyncio
async def test_exact_repeat_survives_facet_jitter_without_embedding_service(monkeypatch):
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model", lambda _: Encoder())
    state = SessionState("heldout")
    intents = IntentSet(state)
    first = candidate("first")
    await intents.add_intents([first])
    intents.mark_dispatched(first.intent_id)
    def unavailable(_):
        raise RuntimeError("embedding unavailable")
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model", unavailable)
    repeat = candidate("repeat", facet="general")
    assert await intents.add_intents([repeat]) == []
    assert repeat.intent_id == first.intent_id
    assert repeat.facet == first.facet


def test_unsupported_value_remains_rejected():
    evidence = RetrievedChunk(chunk_id="sensors#1#0", doc_id="sensors", section_id="1",
                              text="The sensor limit is 12 volts.", score=1)
    verifier = ClaimVerifier(CitationAllowlist([evidence]))
    result = verifier.verify(DraftClaim(0, "sensor", "The sensor limit is 900 volts.",
                                       (evidence.citation_label,)))
    assert not result.ok
    assert "900" in result.missing_values


@pytest.mark.asyncio
async def test_overlap_merge_preserves_all_evidence_and_canonical_identity(monkeypatch):
    from slrag.decompose.overlap import OverlapMerger
    from slrag.retrieve.pool import add_to_pool
    state = SessionState("heldout")
    a, b = candidate("a"), candidate("b")
    state.intent_set = {"a": a, "b": b}
    rows = [RetrievedChunk(chunk_id=f"sensor#{n}#0", doc_id="sensor", section_id=str(n),
                           text=f"Sensor measurement {n}.", score=1) for n in range(5)]
    for row in rows[:4]:
        add_to_pool(state, row, "a", 0)
    for row in rows:
        add_to_pool(state, row, "b", 0)
    assert OverlapMerger().check_and_merge(state, "a", "b", rows[:4], rows)
    assert b.superseded_by == "a"
    assert "a" in state.evidence_pool[rows[-1].chunk_id].scores_by_subquery


@pytest.mark.asyncio
async def test_same_question_with_jittered_slots_is_dispatched_once():
    state = SessionState("heldout")
    intents = IntentSet(state)
    first = candidate("a", slots={"requested_format": "bullets"})
    await intents.add_intents([first])
    intents.mark_dispatched(first.intent_id)
    repeat = candidate("b", slots={"requested_format": "list"})
    assert await intents.add_intents([repeat]) == []
    assert first.status.value == "dispatched"


def test_empty_final_marker_confirms_evidence_without_embedding_drift(monkeypatch):
    from slrag.controller.cascade import RetrievalController
    from slrag.core.schemas import TranscriptChunk
    from slrag.retrieve.pool import add_to_pool
    state = SessionState("heldout")
    row = RetrievedChunk(chunk_id="sensor#1#0", doc_id="sensor", section_id="1",
                         text="The sensor limit is 12 volts.", score=1)
    add_to_pool(state, row, "a", 0, speculative=True)
    state.controller.active_speculations["branch"] = {"retrieved_chunks": [row.model_dump()]}
    state.controller.last_embedding = np.array([1.0, 0.0])
    class NoEmptyEncoder:
        def encode(self, text):
            assert text.strip(), "end markers must not be embedded"
            return np.array([1.0, 0.0])
    controller = RetrievalController(state.controller, encoder_mock=NoEmptyEncoder())
    controller.process_chunk(TranscriptChunk(t_s=1, text="", is_final=True))
    assert not state.evidence_pool[row.chunk_id].speculative
    controller.reset_turn()
    assert state.controller.last_retrieve_time == float("-inf")


@pytest.mark.asyncio
async def test_decomposition_reserves_synthesis_call_and_does_not_count_phantom_retry():
    from slrag.decompose.decomposer import Decomposer
    from types import SimpleNamespace
    decomposer = object.__new__(Decomposer)
    decomposer.max_llm_calls = 2
    decomposer.facets = ["general"]
    decomposer.default_facet = "general"
    decomposer.prompt_template = SimpleNamespace(render=lambda **kw: "prompt")
    decomposer._syntactic_split = lambda text: [text]
    calls = []
    async def failed_call(prompt):
        calls.append(prompt)
        return None
    decomposer._call_llm = failed_call
    state = SessionState("heldout")
    await decomposer.decompose("sensor voltage limit", {}, 0, session_state=state)
    assert len(calls) == state.turn_llm_calls == 2
    await decomposer.decompose("sensor voltage range", {}, 1, session_state=state)
    assert len(calls) == state.turn_llm_calls == 2


@pytest.mark.asyncio
async def test_early_decomposition_preserves_final_correction_budget():
    from slrag.decompose.decomposer import Decomposer
    from types import SimpleNamespace
    decomposer = object.__new__(Decomposer)
    decomposer.max_llm_calls = 3
    decomposer.facets = ["general"]
    decomposer.default_facet = "general"
    decomposer.prompt_template = SimpleNamespace(render=lambda **kw: kw["prefix"])
    decomposer._syntactic_split = lambda text: [text]
    calls = []
    async def respond(prompt):
        calls.append(prompt)
        return {"sub_intents": [{"query_nl": prompt, "search_string": prompt}]}
    decomposer._call_llm = respond
    state = SessionState("heldout")
    await decomposer.decompose("sensor voltage and calibration", {}, 0, state, is_final=False)
    await decomposer.decompose("sensor voltage and calibration please", {}, 1, state, is_final=False)
    final = await decomposer.decompose("Only explain calibration", {}, 2, state, is_final=True)
    assert len(calls) == state.turn_llm_calls == 2
    assert final[0].query_nl == "explain calibration"
    assert decomposer.last_source == "reconciled"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["llm", "reconciled", "fallback"])
async def test_final_snapshot_removes_withdrawn_provisional_question(monkeypatch, source):
    from slrag.api.ws_server import PipelineSession, _process_chunk
    from slrag.core.schemas import ControllerDecision
    import slrag.api.ws_server as api
    import slrag.controller.cascade as cascade
    queries = ["sensor voltage limit", "sensor calibration purpose"]
    class Decomposer:
        last_source = source
        async def decompose(self, **kwargs):
            selected = queries[1:] if kwargs["is_final"] else queries
            return [SubIntent(intent_id=f"candidate{n}", facet="general", query_nl=q, search_string=q)
                    for n, q in enumerate(selected)]
    class Retriever:
        async def search(self, intent): return []
    class Socket:
        async def send_json(self, message): pass
    monkeypatch.setattr(api, "get_retriever", lambda: Retriever())
    monkeypatch.setattr(cascade.RetrievalController, "process_chunk", lambda self, chunk:
        ControllerDecision(t_s=chunk.t_s, decision="RETRIEVE", reason="sentence_boundary", confidence=1, stage=1))
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model",
                        lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    session = PipelineSession("heldout_correction", SessionState("heldout_correction"))
    session._decomposer = Decomposer()
    await _process_chunk(session, {"text": "Explain voltage and calibration", "t_s": 0, "is_final": False}, Socket())
    await _process_chunk(session, {"text": ". Actually, only explain calibration.", "t_s": 1, "is_final": True}, Socket())
    assert session.sub_queries == queries[1:]
    assert len(session.current_candidates) == 1
    removed = next(intent for intent in session.state.intent_set.values() if intent.query_nl == queries[0])
    assert removed.status == "superseded"


@pytest.mark.asyncio
async def test_explicit_exclusion_filters_model_ignored_withdrawal():
    from slrag.decompose.decomposer import Decomposer
    from types import SimpleNamespace
    decomposer = object.__new__(Decomposer)
    decomposer.max_llm_calls = 2
    decomposer.facets = ["general"]
    decomposer.default_facet = "general"
    decomposer.prompt_template = SimpleNamespace(render=lambda **kw: kw["prefix"])
    decomposer._syntactic_split = lambda text: [text]
    async def respond(prompt):
        return {"sub_intents": [{"query_nl": q, "search_string": q}
                                for q in ["Explain the sensor voltage limit", "Explain calibration purpose"]]}
    decomposer._call_llm = respond
    final = await decomposer.decompose("Explain voltage limit and calibration purpose. actual dont list the voltage limit.", {}, 0)
    assert [intent.query_nl for intent in final] == ["Explain calibration purpose"]


@pytest.mark.asyncio
async def test_exclusive_late_request_overrides_broad_model_output():
    from slrag.decompose.decomposer import Decomposer
    from types import SimpleNamespace
    decomposer = object.__new__(Decomposer)
    decomposer.max_llm_calls = 2
    decomposer.facets = ["general"]
    decomposer.default_facet = "general"
    decomposer.prompt_template = SimpleNamespace(render=lambda **kw: kw["prefix"])
    decomposer._syntactic_split = lambda text: [text]
    async def respond(prompt):
        return {"sub_intents": [{"query_nl": "Explain the instrument project", "search_string": "instrument project"},
                                {"query_nl": "Describe the instrument features", "search_string": "instrument features"}]}
    decomposer._call_llm = respond
    final = await decomposer.decompose("Explain the instrument project and list the techniques. actually dont explain the project just list the techniques", {}, 0)
    assert len(final) == 1
    assert "technique" in final[0].query_nl
    assert "instrument" in final[0].search_string
    assert decomposer.last_source == "reconciled"


@pytest.mark.parametrize("score", [-8.2, 0.0, 2.1])
def test_raw_reranker_logits_reach_context(score):
    from slrag.retrieve.pool import add_to_pool, get_pool_chunks_for_intent
    from slrag.retrieve.quota import assemble_context
    state = SessionState("heldout")
    row = RetrievedChunk(chunk_id="sensor#1#0", doc_id="sensor", section_id="1",
                         text="The sensor limit is 12 volts.", score=score)
    add_to_pool(state, row, "sensor", 0)
    chunks = get_pool_chunks_for_intent(state, "sensor")
    assert len(chunks) == 1
    assert chunks[0].score == score
    assert not get_pool_chunks_for_intent(state, "unrelated")
    assert assemble_context({"sensor": chunks}, {}).chunks


@pytest.mark.asyncio
async def test_negative_scored_evidence_invokes_llm_and_commits_verified_fact():
    from slrag.synth.generator import LLMGenerator
    from slrag.synth.engine import SynthesisEngine, TurnInput, SynthesisResult
    from slrag.synth.config import load_synth_config
    from types import SimpleNamespace
    row = RetrievedChunk(chunk_id="sensor#1#0", doc_id="sensor", section_id="1",
                         text="The sensor limit is 12 volts.", score=-8.2)
    calls = []
    class Client:
        last_usage = None
        async def complete(self, prompt, json_schema=None):
            calls.append(prompt)
            import json
            from slrag.synth.generator import LLMResponse
            return LLMResponse(prompt_tokens=10, completion_tokens=10, text=json.dumps({"claims": [{"intent_id": "sensor", "facet": "general",
                     "text": row.text, "citations": [row.citation_label]}]}))
    cfg = load_synth_config()
    cfg["generator"]["openai_compatible"]["stream"] = False
    generator = LLMGenerator(Client(), config=cfg)
    engine = SynthesisEngine("heldout", generator=generator, config=cfg)
    intent = SubIntent(intent_id="sensor", facet="general", query_nl="sensor limit",
                       search_string="sensor limit")
    events = [e async for e in engine.stream_turn(TurnInput(
        turn_id=1, t_s_end=1, utterance="list the sensor limit in bullets", sub_intents=(intent,),
        evidence={"sensor": [row]}))]
    result = next(e for e in events if isinstance(e, SynthesisResult))
    assert len(calls) == 1
    assert "12 volts" in result.output.answer
    assert result.output.citations
    # A distinct next question must not keep the previous answer active.
    other = SubIntent(intent_id="other", facet="general", query_nl="calibration purpose", search_string="calibration purpose")
    events = [e async for e in engine.stream_turn(TurnInput(
        turn_id=2, t_s_end=2, utterance="What is the calibration purpose?", sub_intents=(other,), evidence={}))]
    result = next(e for e in events if isinstance(e, SynthesisResult))
    assert "12 volts" not in result.output.answer


@pytest.mark.asyncio
async def test_stability_can_fire_before_sentence_end_after_floor_wait(monkeypatch):
    from slrag.controller.cascade import RetrievalController
    from slrag.core.schemas import TranscriptChunk
    import slrag.controller.cascade as cascade
    class GrowingEncoder:
        def encode(self, text):
            return np.array([1.0, 0.0]) if len(text.split()) <= 2 else np.array([0.0, 1.0])
    monkeypatch.setattr(cascade, "evaluate_probe", lambda *args: None)
    monkeypatch.setattr(cascade, "evaluate_suppression", lambda *args: None)
    monkeypatch.setattr(cascade, "evaluate_sentence_boundary", lambda *args: None)
    state = SessionState("heldout")
    controller = RetrievalController(state.controller, encoder_mock=GrowingEncoder())
    controller.process_chunk(TranscriptChunk(t_s=0, text="sensor voltage", is_final=False))
    decision = controller.process_chunk(TranscriptChunk(t_s=0.8, text="in", is_final=False))
    assert decision.decision == "WAIT"
    decision = controller.process_chunk(TranscriptChunk(t_s=1.6, text="the control circuit", is_final=False))
    assert decision.decision == "RETRIEVE"
    assert decision.reason == "intent_stabilised"
    controller.reset_turn()


def test_discriminative_probe_fires_without_punctuation(monkeypatch):
    import slrag.controller.probe as probe
    monkeypatch.setattr(probe, "_load_calibration", lambda: {"tau_hi": .35, "h_lo": .65})
    class Corpus:
        def query(self, text, k):
            return np.array([10., .1, .1, .1])
    decision = probe.evaluate_probe("sensor voltage limit", .8, Corpus())
    assert decision.decision == "RETRIEVE"
    assert decision.reason == "corpus_discriminative"


@pytest.mark.asyncio
async def test_different_percentages_are_not_confirmed_conflicts_without_nli():
    from slrag.retrieve.contradiction import ContradictionGating
    gate = object.__new__(ContradictionGating)
    gate.nli_pipeline = None
    gate.threshold = .7
    rows = [RetrievedChunk(chunk_id=f"sensor#{n}#0", doc_id="sensor", section_id=str(n),
                           text=text, score=1) for n, text in enumerate([
                           "The sensor error rate is 1%.",
                           "The controller accuracy is 97.61%."])]
    assert await gate.detect_contradictions(rows, "general") == []


@pytest.mark.asyncio
async def test_distinct_questions_sharing_all_evidence_do_not_merge_or_repeat(monkeypatch):
    from slrag.decompose.overlap import OverlapMerger
    from slrag.retrieve.pool import add_to_pool
    state = SessionState("heldout")
    intents = IntentSet(state)
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    a = SubIntent(intent_id="a", facet="general", query_nl="sensor voltage limit", search_string="sensor voltage limit")
    b = SubIntent(intent_id="b", facet="general", query_nl="sensor calibration purpose", search_string="sensor calibration purpose")
    await intents.add_intents([a,b])
    intents.mark_dispatched(a.intent_id); intents.mark_dispatched(b.intent_id)
    row = RetrievedChunk(chunk_id="sensor#1#0",doc_id="sensor",section_id="1",text="The sensor limit is 12 volts.",score=1)
    add_to_pool(state,row,a.intent_id,0); add_to_pool(state,row,b.intent_id,0)
    assert not OverlapMerger().check_and_merge(state,a.intent_id,b.intent_id,[row],[row])
    repeat = SubIntent(intent_id="c",facet="general",query_nl=b.query_nl,search_string=b.search_string)
    assert await intents.add_intents([repeat]) == []
    assert repeat.intent_id == b.intent_id


@pytest.mark.asyncio
async def test_new_question_does_not_report_previous_failed_question_coverage():
    import json
    from slrag.synth.generator import LLMGenerator, LLMResponse
    from slrag.synth.engine import SynthesisEngine, TurnInput, SynthesisResult
    from slrag.synth.config import load_synth_config
    class Client:
        async def complete(self, prompt, json_schema=None):
            return LLMResponse(text=json.dumps({"claims": []}),prompt_tokens=1,completion_tokens=1)
    cfg=load_synth_config(); cfg["generator"]["openai_compatible"]["stream"]=False
    engine=SynthesisEngine("heldout",generator=LLMGenerator(Client(),config=cfg),config=cfg)
    for n,q in enumerate(["sensor voltage limit", "controller calibration purpose"]):
        intent=SubIntent(intent_id=str(n),facet="general",query_nl=q,search_string=q)
        events=[e async for e in engine.stream_turn(TurnInput(turn_id=n+1,t_s_end=1,utterance=q,sub_intents=(intent,),evidence={}))]
    result=next(e for e in events if isinstance(e,SynthesisResult))
    assert "sensor voltage limit" not in result.output.uncertainty
    assert "controller calibration purpose" in result.output.uncertainty


@pytest.mark.asyncio
@pytest.mark.parametrize("followup_text,cancel_speculation", [
    ("Repeat that in bullets.", False),
    ("describe the previous answer in short (summarize it)", False),
    ("describe the previous answer in short (summarize it)", True),
    ("summarize the previous answer in one line", False),
])
async def test_streaming_api_reuses_ids_and_returns_verified_llm_answer(monkeypatch, followup_text, cancel_speculation):
    import json
    from slrag.api.ws_server import PipelineSession, _process_chunk, _process_utterance_end
    from slrag.core.schemas import ControllerDecision
    from slrag.synth.generator import LLMGenerator, LLMResponse
    from slrag.synth.engine import SynthesisEngine
    from slrag.synth.config import load_synth_config
    import slrag.api.ws_server as api
    import slrag.controller.cascade as cascade
    queries=["What is the sensor voltage limit?", "What is the sensor calibration purpose?"]
    facts=["The sensor limit is 12 volts.", "Sensor calibration corrects measurement drift."]
    rows=[RetrievedChunk(chunk_id=f"sensor#{n}#0", doc_id="sensor",section_id=str(n),text=text,score=-2)
          for n,text in enumerate(facts)]
    searches=[]; calls=[]; decomposition_contexts=[]
    class Decomposer:
        async def decompose(self, **kwargs):
            decomposition_contexts.append(dict(kwargs["existing_intents"]))
            return [SubIntent(intent_id=f"candidate{n}",facet="general",query_nl=q,search_string=q)
                    for n,q in enumerate(queries)]
    class Retriever:
        async def search(self, intent):
            searches.append(intent.search_string)
            return rows
    class Socket:
        def __init__(self): self.messages=[]
        async def send_json(self, msg): self.messages.append(msg)
    class Gate:
        async def detect_contradictions(self,*args): return []
    class Client:
        async def complete(self,prompt,json_schema=None):
            calls.append(prompt)
            ids=json_schema["properties"]["claims"]["items"]["properties"]["intent_id"]["enum"]
            return LLMResponse(text=json.dumps({"claims": [
                {"intent_id":iid,"facet":"general","text":facts[n],"citations":[rows[n].citation_label]}
                for n,iid in enumerate(ids)]}),prompt_tokens=100,completion_tokens=50)
    monkeypatch.setattr(api,"get_retriever",lambda: Retriever())
    real_controller_process = cascade.RetrievalController.process_chunk
    def controller_decision(self, chunk):
        if cancel_speculation and chunk.t_s > 0:
            from slrag.controller.speculation import process_speculation
            process_speculation(chunk.text, 1.0, self.session)
        return ControllerDecision(t_s=chunk.t_s, decision="RETRIEVE", reason="sentence_boundary",
                                  confidence=1, stage=3 if cancel_speculation and chunk.t_s == 0 else 1)
    monkeypatch.setattr(cascade.RetrievalController,"process_chunk",controller_decision)
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model",lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    cfg=load_synth_config(); cfg["generator"]["openai_compatible"]["stream"]=False
    session=PipelineSession(session_id="heldout_api",state=SessionState("heldout_api"))
    session._decomposer=Decomposer(); session.cg=Gate()
    session.engine=SynthesisEngine("heldout_api",generator=LLMGenerator(Client(),config=cfg),config=cfg)
    ws=Socket()
    for n,part in enumerate(["What is the sensor voltage limit", " and the calibration purpose", "?"]):
        await _process_chunk(session,{"text":part,"t_s":n*.8,"is_final":n==2},ws)
    await _process_utterance_end(session,ws)
    final=next(m for m in ws.messages if m["type"]=="answer_version")
    expected_searches = queries * (2 if cancel_speculation else 1)
    assert searches == expected_searches

    assert len(calls)==1
    assert len(final["claims"])==2
    assert len(final["citations"])==2
    assert final["llm_diagnostics"]["calls"]==1
    assert final["llm_diagnostics"]["error"] is None
    assert "12 volts" in final["answer"]
    updates=[m for m in ws.messages if m["type"]=="subqueries_updated"]
    assert [i["intent_id"] for i in updates[0]["new_intents"]] == list(session.state.intent_set)
    assert all(not m["new_intents"] for m in updates[1:])
    # The classifier inspects controller decisions only once an answer exists.
    # Exercise a real follow-up through the API boundary, not just the first turn.
    monkeypatch.setattr(cascade.RetrievalController,"process_chunk",real_controller_process)
    followup_parts = ["summarize the previous answer", " in one", " line"] if "one line" in followup_text else [followup_text]
    for n, part in enumerate(followup_parts):
        await _process_chunk(session,{"text":part,"t_s":n*.8,"is_final":n==len(followup_parts)-1},ws)
    await _process_utterance_end(session,ws)
    followup=[m for m in ws.messages if m["type"]=="answer_version"][-1]
    assert followup["turn_id"] == 2
    assert followup["answer"]
    assert set(followup["citations"]) <= set(final["citations"])
    assert len(calls) == 1
    assert followup["suppression"] == "presentation_restructure"
    assert followup["retrieval_events"] == []
    if "one line" in followup_text:
        assert "\n" not in followup["answer"]
        assert not followup["answer"].startswith("- ")
    assert searches == expected_searches
    queries[:] = ["What is the controller reset procedure?"]
    monkeypatch.setattr(cascade.RetrievalController,"process_chunk",lambda self,chunk:
        ControllerDecision(t_s=chunk.t_s,decision="RETRIEVE",reason="sentence_boundary",confidence=1,stage=1))
    await _process_chunk(session,{"text":queries[0],"t_s":0,"is_final":True},ws)
    assert decomposition_contexts[-1] == {}
    assert session.sub_queries == queries


@pytest.mark.asyncio
async def test_semantic_dedup_does_not_alias_a_new_turn_to_an_old_question(monkeypatch):
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model",lambda _: Encoder())
    state=SessionState("heldout")
    intents=IntentSet(state)
    state.new_turn()
    old=SubIntent(intent_id="a",facet="general",query_nl="sensor voltage limit",search_string="sensor voltage limit")
    await intents.add_intents([old]); intents.mark_dispatched(old.intent_id)
    state.new_turn()
    new=SubIntent(intent_id="b",facet="general",query_nl="controller calibration purpose",search_string="controller calibration purpose")
    assert await intents.add_intents([new]) == [new]
    assert new.intent_id != old.intent_id
    repeat=SubIntent(intent_id="c",facet="general",query_nl=new.query_nl,search_string=new.search_string)
    intents.mark_dispatched(new.intent_id)
    assert await intents.add_intents([repeat]) == []
    assert repeat.intent_id == new.intent_id


@pytest.mark.asyncio
async def test_extractive_llm_schema_limits_claims_to_retrieved_sentences():
    import json
    from slrag.synth.generator import LLMGenerator, LLMResponse
    from slrag.synth.config import load_synth_config
    cfg=load_synth_config(); opts=cfg["generator"]["openai_compatible"]
    opts.update(stream=False,claim_text_mode="extractive",max_claims_per_intent=2)
    captured=[]
    class Client:
        async def complete(self,prompt,json_schema=None):
            captured.append(json_schema)
            return LLMResponse(text='{"claims": []}',prompt_tokens=1,completion_tokens=1)
    row=RetrievedChunk(chunk_id="sensor#1#0",doc_id="sensor",section_id="1",text="The sensor limit is 12 volts.",score=-1)
    intent=SubIntent(intent_id="s",facet="general",query_nl="What is the sensor limit?",search_string="sensor limit")
    generator=LLMGenerator(Client(),config=cfg)
    assert [d async for d in generator.generate([intent],{"s":[row]})] == []
    claims=captured[0]["properties"]["claims"]
    assert claims["maxItems"] == 2
    assert claims["items"]["properties"]["text"]["enum"] == [row.text]
    assert intent.query_nl not in claims["items"]["properties"]["text"]["enum"]
    selection=claims["items"]["anyOf"][0]["properties"]
    assert selection["text"]["const"] == row.text
    assert selection["citations"]["const"] == [row.citation_label]
    assert selection["intent_id"]["const"] == intent.intent_id


@pytest.mark.asyncio
async def test_added_question_does_not_obey_unjustified_model_supersession(monkeypatch):
    monkeypatch.setattr("slrag.decompose.intent_set._get_embedding_model",lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    state=SessionState("heldout"); intents=IntentSet(state)
    first=SubIntent(intent_id="a",facet="general",query_nl="sensor voltage limit",search_string="sensor voltage limit",slots={"task":"limits"})
    await intents.add_intents([first]); intents.mark_dispatched(first.intent_id)
    second=SubIntent(intent_id="b",facet="general",query_nl="sensor calibration purpose",search_string="sensor calibration purpose",slots={"task":"purpose"},supersedes=[first.intent_id])
    await intents.add_intents([second],prefix="sensor voltage limit and sensor calibration purpose")
    assert first.status.value == "dispatched"
    assert first.superseded_by is None
    assert second.intent_id != first.intent_id
