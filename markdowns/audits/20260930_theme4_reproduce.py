"""Offline audit probes. Run from repository root; no production files changed."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import numpy as np
from slrag.core.schemas import RetrievedChunk, SubIntent, TelemetryEvent
from slrag.core.session import SessionState
from slrag.synth.config import load_synth_config
from slrag.synth.types import DraftClaim, TurnClassification
from slrag.synth.verifier import CitationAllowlist, ClaimVerifier

RESULTS = {}

def chunk(text="The sensor limit is 12 volts.", ident="Doc_sensor#1#0"):
    return RetrievedChunk(chunk_id=ident, doc_id=ident.split("#")[0],
                          section_id="1", text=text, score=0.9)

def intent(ident, query="sensor voltage limit"):
    return SubIntent(intent_id=ident, facet="sensor", query_nl=query, search_string=query)

class Encoder:
    def encode(self, text, **kwargs):
        return np.array([1.0, 0.0])

class Socket:
    def __init__(self):
        self.messages = []
    async def send_json(self, value):
        self.messages.append(value)

async def main():
    cfg = load_synth_config()
    evidence = chunk()
    verifier = ClaimVerifier(CitationAllowlist([evidence]), config=cfg)
    for name, text, citations in [
        ("unsupported_number", "The sensor limit is 900 volts.", (evidence.citation_label,)),
        ("mixed_fabricated_citation", "The sensor limit is 12 volts.", (evidence.citation_label, "Doc_missing §9")),
    ]:
        r = verifier.verify(DraftClaim(0, "sensor", text, citations))
        RESULTS[name] = {"ok": r.ok, "reasons": r.reasons, "missing_values": r.missing_values,
                         "fabricated": r.fabricated, "supporting_chunk_ids": r.supporting_chunk_ids}

    from slrag.synth.generator import ExtractiveGenerator, LLMResponse
    from slrag.synth.engine import SynthesisEngine, TurnInput
    class RewriteClient:
        async def complete(self, prompt):
            return LLMResponse(text="The sensor limit is 900 volts [Doc_missing §9].",
                               prompt_tokens=10, completion_tokens=10)
    gen = ExtractiveGenerator(config=cfg, facets={})
    gen.client = RewriteClient()
    engine = SynthesisEngine("audit-rewrite", config=cfg, facets={}, generator=gen)
    result = await engine.handle_turn(TurnInput(1, "sensor voltage limit", 1.0,
        sub_intents=[intent("i1")], evidence={"i1": [evidence]},
        classification=TurnClassification("NEW_INTENT", "audit")))
    RESULTS["unverified_rewrite"] = {"answer": result.output.answer,
        "citations": result.output.citations, "claims": [c.text for c in result.output.claims],
        "fabricated_id_count": result.fabricated_id_count}

    from slrag.decompose.intent_set import IntentSet
    from slrag.retrieve.pool import add_to_pool, get_pool_chunks_for_intent
    from slrag.controller.speculation import process_speculation
    state = SessionState("audit-dedup")
    ids = IntentSet(state)
    with patch("slrag.decompose.intent_set._get_embedding_model", return_value=Encoder()):
        first = intent("candidate-a")
        await ids.add_intents([first])
        add_to_pool(state, evidence, first.intent_id, 0.5)
        later = intent("candidate-b")
        novel = await ids.add_intents([later])
    RESULTS["dedup_id_disconnect"] = {"novel_count": len(novel),
        "latest_candidate_id": later.intent_id, "stored_ids": list(state.intent_set),
        "candidate_evidence": len(get_pool_chunks_for_intent(state, later.intent_id)),
        "original_evidence": len(get_pool_chunks_for_intent(state, first.intent_id))}

    state2 = SessionState("audit-cancel")
    add_to_pool(state2, evidence, "i1", 0.5, speculative=True)
    state2.controller.active_speculations["branch"] = {
        "status": "pending", "retrieved_chunks": [evidence.model_dump()]}
    process_speculation("actually use a different sensor", 1.0, state2.controller)
    RESULTS["cancelled_evidence_selected"] = {
        "active_branches": len(state2.controller.active_speculations),
        "speculative": state2.evidence_pool[evidence.chunk_id].speculative,
        "selected_chunks": len(get_pool_chunks_for_intent(state2, "i1"))}

    from slrag.retrieve.quota import assemble_context
    a = chunk("alpha " * 100, "Doc_alpha#1#0")
    b = chunk("beta " * 100, "Doc_beta#1#0")
    fused = assemble_context({"i1": [a], "i2": [a], "i3": [b]},
        {"context": {"budget_tokens": 270, "guaranteed_chunks_per_intent": 2}})
    RESULTS["quota_duplicates_starve_intent"] = {
        "chunk_ids": [c.chunk_id for c in fused.chunks], "coverage": fused.facet_coverage,
        "tokens": fused.total_tokens}

    from slrag.telemetry.bus import TelemetryBus
    bus = TelemetryBus()
    received_a, received_b = [], []
    async def a_sink(payload): received_a.append(payload)
    async def b_sink(payload): received_b.append(payload)
    bus.subscribe_ws(a_sink)
    bus.subscribe_ws(b_sink)
    await bus.emit(TelemetryEvent(event_id="audit", session_id="A", turn_id=1,
        ts_stream_s=0.5, component="controller", payload={"text": "private session A transcript"}))
    RESULTS["cross_session_broadcast"] = {"a_received": len(received_a),
        "b_received": len(received_b), "b_saw_session": received_b[0]["session_id"]}

    from slrag.telemetry.cost import make_cost_accumulator
    acc = make_cost_accumulator()
    RESULTS["pricing_schema_mismatch"] = {"cost_for_1000_prompt_and_completion": acc.add_llm_call(1000, 1000)}

    from bench.metrics import summarise, gate_failures
    empty = summarise([], {}, judge=SimpleNamespace(score=lambda p, h: 0), threshold=0.6)
    RESULTS["empty_benchmark_passes"] = {"turns": empty["turns"],
        "citation_support_rate": empty["g4"]["citation_support_rate"],
        "refinements": empty["g5"]["refinements"], "gate_failures": gate_failures(empty)}

    from slrag.ingest.loader import MarkdownLoader
    from slrag.ingest.chunker import StructureAwareChunker
    doc = ROOT / "scratch/theme4_audit/collision.md"
    doc.write_text("# 1.1 Input\nInput limit is 12 volts.\n# 1.2 Output\nOutput limit is 5 volts.\n", encoding="utf-8")
    sections = MarkdownLoader(doc.parent).load_file(doc)
    chunks = StructureAwareChunker().chunk_documents(sections)
    RESULTS["citation_id_collision"] = {"sections": [s.section_id for s in sections],
        "chunk_ids": [c.chunk_id for c in chunks]}

    # Exercise the API adapter while avoiding any network/model loading.
    from slrag.api import ws_server
    import slrag.synth.engine as engine_module
    class CapturingEngine:
        def __init__(self): self.turns = []
        async def stream_turn(self, turn):
            self.turns.append(turn)
            if False: yield None
    class NoConflicts:
        async def detect_contradictions(self, *args): return []
    api_session = ws_server.PipelineSession("audit-api", SessionState("audit-api"))
    api_session.prefix = "explain the sensor"
    api_session.state.controller.current_prefix = "unretrieved prefix from prior turn"
    api_session.chunks = [{"t_s": 0.8, "text": api_session.prefix, "is_final": False}]
    api_session.cg = NoConflicts()
    captured = CapturingEngine()
    socket = Socket()
    with patch.object(ws_server, "get_bus", return_value=TelemetryBus()), \
         patch.object(engine_module, "SynthesisEngine", return_value=captured) as constructor, \
         patch.object(ws_server, "_process_chunk") as chunk_handler:
        await ws_server._process_utterance_end(api_session, socket)
        RESULTS["api_end_adapter"] = {
            "engine_constructor_args": str(constructor.call_args),
            "controller_chunk_handler_calls": chunk_handler.call_count,
            "sub_intents": len(captured.turns[0].sub_intents),
            "controller_prefix_after_turn": api_session.state.controller.current_prefix}

    # Show upstream retrieval happens before any existing synthesis engine classification.
    from slrag.controller.cascade import RetrievalController
    from slrag.core.schemas import ControllerDecision
    from slrag.decompose.overlap import OverlapMerger
    order = []
    class FakeDecomposer:
        async def decompose(self, **kwargs):
            order.append("decompose")
            return [intent("next", "actually use the external sensor")]
    class FakeIntents:
        async def add_intents(self, candidates, **kwargs):
            api_session.state.intent_set[candidates[0].intent_id] = candidates[0]
            return candidates
        def mark_dispatched(self, ident): pass
    class FakeRetriever:
        async def search(self, candidate):
            order.append("full-prefix retrieval")
            return [evidence]
    api_session._decomposer, api_session._intent_set = FakeDecomposer(), FakeIntents()
    with patch.object(ws_server, "get_bus", return_value=TelemetryBus()), \
         patch.object(RetrievalController, "process_chunk", return_value=ControllerDecision(
             t_s=0.8, decision="RETRIEVE", reason="audit", confidence=1.0, stage=5)), \
         patch.object(ws_server, "get_retriever", return_value=FakeRetriever()), \
         patch.object(OverlapMerger, "check_all_pairs", return_value=[]):
        await ws_server._process_chunk(api_session, {"t_s": 0.8, "text": "actually use the external sensor"}, socket)
    RESULTS["api_refinement_upstream_retrieval"] = {"actions_before_classification": order}

    output = ROOT / "scratch/theme4_audit/reproduction_results.json"
    output.write_text(json.dumps(RESULTS, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(RESULTS, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
