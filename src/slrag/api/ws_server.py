"""WebSocket server — /ws/session endpoint (Roadmap §1.2).

Client sends:
  {type: "chunk", t_s: float, text: string}
  {type: "utterance_end"}
  {type: "new_session"}
  {type: "end_session"}

Server streams back:
  controller_decision, retrieval_started, subqueries_updated,
  answer_token (provisional/committed), citation_attached,
  answer_version, uncertainty, telemetry_tick
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from slrag.core.schemas import (
    AnswerOutput,
    ControllerDecision,
    ControllerDecisionType,
    RetrievalEvent,
    RetrievalTrigger,
    SubIntent,
    TelemetryEvent,
    TranscriptChunk,
)
from slrag.core.session import SessionState
from slrag.core.events import (
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_DECOMPOSITION_STARTED,
    EVT_DECOMPOSITION_COMPLETED,
    EVT_INTENT_ADDED,
    EVT_RETRIEVAL_STARTED,
    EVT_RETRIEVAL_COMPLETED,
    EVT_SYNTHESIS_STARTED,
    EVT_ANSWER_VERSION,
    EVT_SESSION_STARTED,
    EVT_SESSION_ENDED,
    EVT_TURN_STARTED,
    EVT_TURN_COMPLETED,
    EVT_COST_RECORD,
    EVT_LLM_CALL,
)
from slrag.telemetry.bus import get_bus

logger = logging.getLogger(__name__)

router = APIRouter()

_RETRIEVER = None

def get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        from slrag.retrieve.dense import DenseRetriever
        from slrag.retrieve.sparse import SparseRetriever
        from slrag.retrieve.rerank import Reranker
        from pathlib import Path
        
        class RetrievalStack:
            def __init__(self):
                from slrag.core.paths import index_dir
                selected_index = index_dir()
                self.dense = DenseRetriever(index_path=selected_index / "faiss", chunks_path=selected_index / "chunks.jsonl")
                self.sparse = SparseRetriever(index_path=selected_index / "bm25", chunks_path=selected_index / "chunks.jsonl")
                self.reranker = Reranker()
                from slrag.synth.config import _load_yaml
                self.config = _load_yaml(Path("config/retrieval.yaml"))
                
            async def search(self, intent):
                import asyncio
                sparse_res, dense_res = await asyncio.gather(
                    self.sparse.search(intent.search_string, top_k=30),
                    self.dense.search(intent.search_string, top_k=30)
                )
                from slrag.retrieve.rrf import apply_rrf
                fused = apply_rrf(sparse_res, dense_res, intent.facet, self.config)
                reranked = await self.reranker.rerank(intent.search_string, fused, top_k=8)
                return reranked
                
        _RETRIEVER = RetrievalStack()
    return _RETRIEVER

def reset_retriever():
    global _RETRIEVER
    _RETRIEVER = None
    try:
        from slrag.controller.probe import reset_probe_cache
        reset_probe_cache()
        from slrag.controller.suppression import reset_suppression_cache
        reset_suppression_cache()
    except Exception:
        pass
    logger.info("Retriever instance and probe cache reset.")


# ── Telemetry helpers ────────────────────────────────────────────────

def _make_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


def _ts_wall() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_telemetry(
    session_id: str,
    turn_id: int,
    ts_stream_s: float,
    component: str,
    event_type: str,
    latency_ms: float = 0.0,
    payload: dict | None = None,
) -> TelemetryEvent:
    """Build a TelemetryEvent; caller is responsible for emitting via the bus."""
    return TelemetryEvent(
        event_id=_make_event_id(),
        session_id=session_id,
        turn_id=turn_id,
        ts_stream_s=ts_stream_s,
        component=component,
        event_type=event_type,
        latency_ms=latency_ms,
        ts_wall=_ts_wall(),
        payload=payload or {},
    )


# ── Pipeline Session ────────────────────────────────────────────────

@dataclass
class PipelineSession:
    """One active user session with full pipeline state.
    
    Persists Decomposer and IntentSet across chunks so that the
    monotonic IntentSet diffing (S-2) works correctly: intents are
    only added, never re-issued.
    """
    session_id: str
    state: SessionState
    prefix: str = ""
    turn_id: int = 0
    chunks: list[dict] = field(default_factory=list)
    controller_decisions: list[dict] = field(default_factory=list)
    controller_results: list[ControllerDecision] = field(default_factory=list)
    retrieval_events: list[dict] = field(default_factory=list)
    sub_queries: list[str] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    answer: str = ""
    answer_version: int = 0
    uncertainty: str = ""
    citations: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    # Persistent decomposer + intent set — NOT recreated per chunk
    _decomposer: Any = field(default=None, repr=False)
    _intent_set: Any = field(default=None, repr=False)
    # Track total telemetry
    total_tokens_prompt: int = 0
    total_tokens_completion: int = 0
    total_cost_usd: float = 0.0
    total_llm_calls: int = 0
    active_tasks: set[asyncio.Task] = field(default_factory=set)

    @property
    def decomposer(self):
        if self._decomposer is None:
            from slrag.decompose.decomposer import Decomposer
            self._decomposer = Decomposer()
        return self._decomposer

    @property
    def intent_set(self):
        if self._intent_set is None:
            from slrag.decompose.intent_set import IntentSet
            self._intent_set = IntentSet(session=self.state)
        return self._intent_set


class SessionManager:
    """Manages WebSocket sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, PipelineSession] = {}

    def create(self, session_id: str | None = None) -> PipelineSession:
        sid = session_id or f"sess_{uuid.uuid4().hex[:8]}"
        state = SessionState(session_id=sid)
        session = PipelineSession(session_id=sid, state=state)
        self.sessions[sid] = session
        return session

    def get(self, session_id: str) -> PipelineSession | None:
        return self.sessions.get(session_id)

    def end(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session:
            session.state.destroy()
            if hasattr(session, 'engine') and session.engine is not None:
                session.engine.destroy()
            return True
        return False

    def reset_all(self) -> None:
        """End and destroy all active sessions."""
        for sid in list(self.sessions.keys()):
            self.end(sid)



_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


# ── Chunk Processing ────────────────────────────────────────────────

async def _process_chunk(session: PipelineSession, chunk_data: dict, ws: WebSocket) -> None:
    """Process a single transcript chunk through the pipeline.
    
    Design pattern (02_SOLUTION_DESIGN §C2):
    - On every RETRIEVE, decompose the *current full prefix* (not just the new chunk)
    - Diff the candidate intents against the existing IntentSet
    - Dispatch retrieval *only for genuinely new intents*
    
    This reproduces the brief's event pattern:
    - At 0.8s the set holds {venue_capacity}
    - At 1.6s two more are added (cancellation_terms, catering_options)
    - Only those 2 new intents generate new retrieval_events
    """
    bus = get_bus()
    t_s = chunk_data.get("t_s", 0.0)
    text = chunk_data.get("text", "")
    is_final = chunk_data.get("is_final", False)

    if not session.chunks:
        session.turn_id = session.state.new_turn()
        await bus.emit(_emit_telemetry(
            session_id=session.session_id,
            turn_id=session.turn_id,
            ts_stream_s=t_s,
            component="orchestrator",
            event_type=EVT_TURN_STARTED,
            payload={
                "turn_id": session.turn_id,
                "answer_version": session.answer_version,
                "prefix_len": len(session.prefix),
                "retrieval_events_count": len(session.retrieval_events),
                "sub_queries_count": len(session.sub_queries),
            },
        ))

    session.prefix += text
    chunk = TranscriptChunk(t_s=t_s, text=text, is_final=is_final)

    # Store chunk for telemetry
    session.chunks.append({"t_s": t_s, "text": text, "is_final": is_final})

    # ── Telemetry: chunk received ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=session.turn_id,
        ts_stream_s=t_s,
        component="controller",
        event_type=EVT_CHUNK_RECEIVED,
        payload={"text": text, "is_final": is_final, "prefix_len": len(session.prefix)},
    ))

    # ── Stage 1: Controller Decision ──
    started = time.perf_counter()
    from slrag.controller.cascade import RetrievalController
    from slrag.core.config import get_controller_config

    controller = RetrievalController(session=session.state.controller)
    decision_result = controller.process_chunk(chunk)
    decision = decision_result.decision
    reason = decision_result.reason
    confidence = decision_result.confidence
    stage = getattr(decision_result, 'stage', None)

    latency_ms = (time.perf_counter() - started) * 1000

    # ── Telemetry: controller decision ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=session.turn_id,
        ts_stream_s=t_s,
        component="controller",
        event_type=EVT_CONTROLLER_DECISION,
        latency_ms=round(latency_ms, 2),
        payload={
            "decision": str(decision),
            "reason": str(reason),
            "confidence": confidence,
            "stage": stage,
            "prefix_len": len(session.prefix),
        },
    ))

    # Record Prometheus metrics
    try:
        from slrag.telemetry.metrics import record_controller_decision
        record_controller_decision(str(decision), str(reason), latency_ms / 1000)
    except Exception:
        pass

    decision_event = {
        "type": "controller_decision",
        "t_s": t_s,
        "decision": str(decision),
        "reason": str(reason),
        "confidence": confidence,
        "stage": decision_result.stage,
        "stage_name": getattr(decision_result, "stage_name", None),
        "margin": getattr(decision_result, "margin", None),
        "entropy": getattr(decision_result, "entropy", None),
        "threshold": getattr(decision_result, "threshold", None),
        "latency_ms": round(latency_ms, 2),
        "prefix": session.prefix,
    }
    session.controller_decisions.append(decision_event)
    session.controller_results.append(decision_result)
    await ws.send_json(decision_event)

    # ── Stage 3: Synthesis Engine Init ──
    if not hasattr(session, "engine") or session.engine is None:
        from slrag.synth.engine import SynthesisEngine
        
        class PoolView:
            def chunks(self):
                from slrag.core.schemas import RetrievedChunk
                for entry in session.state.evidence_pool.values():
                    if not entry.speculative:
                        yield RetrievedChunk(
                            chunk_id=entry.chunk_id, doc_id=entry.doc_id,
                            section_id=entry.section_id, text=entry.text,
                            score=max(entry.scores_by_subquery.values()) if entry.scores_by_subquery else 0.0,
                            citation_label=entry.citation_label
                        )
        
        async def _retrieve_fn(intent):
            retriever = get_retriever()
            chunks = await retriever.search(intent)
            from slrag.retrieve.pool import add_to_pool
            for chunk in chunks:
                add_to_pool(
                    session=session.state,
                    chunk=chunk,
                    intent_id=intent.intent_id,
                    ts_stream_s=time.time(),
                    speculative=False
                )
            return chunks

        session.engine = SynthesisEngine(
            session.session_id,
            retrieve_fn=_retrieve_fn,
            pool=PoolView()
        )

    # ── Stage 2: Decompose + Retrieve on RETRIEVE ──
    if decision == ControllerDecisionType.RETRIEVE or decision == "RETRIEVE":
        await ws.send_json({"type": "retrieval_started", "t_s": t_s})

        # ── Telemetry: decomposition started ──
        decomp_start = time.perf_counter()
        await bus.emit(_emit_telemetry(
            session_id=session.session_id,
            turn_id=session.turn_id,
            ts_stream_s=t_s,
            component="decomposer",
            event_type=EVT_DECOMPOSITION_STARTED,
            payload={"prefix_len": len(session.prefix)},
        ))

        # Decompose the FULL prefix (not just the chunk — 02_SOLUTION_DESIGN §C2)
        if getattr(session, "_last_decomposition_prefix", None) == session.prefix and not is_final:
            all_candidates = session._last_decomposition_candidates
        else:
            context_classification = session.engine.classify(
                utterance=session.prefix, controller_decisions=session.controller_results,
                sub_intents=getattr(session, "current_candidates", []),
            )
            context_ids = {intent.intent_id for intent in getattr(session, "current_candidates", [])}
            if context_classification.turn_type != "NEW_INTENT":
                context_ids.update(session.engine._intents)
            decomposition_context = {iid: intent for iid, intent in session.state.intent_set.items()
                                     if iid in context_ids and intent.status not in ("merged", "superseded")}
            all_candidates = await session.decomposer.decompose(
                prefix=session.prefix,
                existing_intents=decomposition_context,
                ts=t_s,
                session_state=session.state,
                is_final=is_final,
            )
            session._last_decomposition_prefix = session.prefix
            session._last_decomposition_candidates = all_candidates

        # Diff against IntentSet — dispatch ONLY genuinely novel intents (S-2)
        try:
            if is_final and getattr(session.decomposer, "last_source", None) == "reconciled":
                questions = {intent.query_nl.casefold().strip() for intent in all_candidates}
                for intent in getattr(session, "current_candidates", []):
                    if intent.query_nl.casefold().strip() not in questions:
                        intent.status = "superseded"
            novel_intents = await session.intent_set.add_intents(all_candidates, prefix=session.prefix)
        except Exception as e:
            logger.exception("Intent deduplication failed; refusing duplicate dispatch")
            raise

        decomp_latency_ms = (time.perf_counter() - decomp_start) * 1000

        # ── Telemetry: decomposition completed ──
        await bus.emit(_emit_telemetry(
            session_id=session.session_id,
            turn_id=session.turn_id,
            ts_stream_s=t_s,
            component="decomposer",
            event_type=EVT_DECOMPOSITION_COMPLETED,
            latency_ms=round(decomp_latency_ms, 2),
            payload={
                "total_candidates": len(all_candidates),
                "novel_intents": len(novel_intents),
                "existing_intents": len(session.state.intent_set),
            },
        ))

        logger.info("Intent post-process: session=%s candidates=%d novel=%d canonical=%d calls=%d",
                    session.session_id, len(all_candidates), len(novel_intents),
                    len(session.state.intent_set), session.state.turn_llm_calls)

        # Store current candidates for the synthesis engine later
        previous_ids = {i.intent_id for i in getattr(session, "current_candidates", [])}
        if is_final:
            final_ids = {i.intent_id for i in all_candidates}
            for intent_id in previous_ids - final_ids:
                session.state.intent_set[intent_id].status = "superseded"
            previous_ids = set()
        previous_ids.update(i.intent_id for i in all_candidates)
        session.current_candidates = [i for i in session.state.intent_set.values()
                                      if i.intent_id in previous_ids and i.status not in ("merged", "superseded")]
        session.sub_queries = list(dict.fromkeys(intent.query_nl for intent in session.current_candidates))

        session.classification = session.engine.classify(
            utterance=session.prefix,
            controller_decisions=session.controller_results,
            sub_intents=session.current_candidates
        )

        await ws.send_json({
            "type": "subqueries_updated",
            "t_s": t_s,
            "sub_queries": session.sub_queries,
            "new_intents": [
                {"facet": i.facet, "query_nl": i.query_nl, "intent_id": i.intent_id}
                for i in novel_intents
            ],
            "total_intents": len(session.state.intent_set),
        })

        # ── Retrieval: only for genuinely novel intents ──
        retrieval_start = time.perf_counter()

        async def _retrieve_and_pool(intent):
            # Determine trigger type per 02_SOLUTION_DESIGN
            if len(session.retrieval_events) == 0:
                trigger = "provisional"
            else:
                trigger = "multi_intent"

            retrieval_event = {
                "timestamp_s": t_s,
                "query": intent.search_string,
                "trigger": trigger,
            }
            session.retrieval_events.append(retrieval_event)

            # Do actual retrieval and add to pool
            retriever = get_retriever()
            retrieved_chunks = await retriever.search(intent)

            from slrag.retrieve.pool import add_to_pool
            is_speculative = not is_final and stage in (2, 3)
            
            branch_id = None
            if is_speculative:
                branch_id = f"spec_{uuid.uuid4().hex[:8]}"
                session.state.controller.active_speculations[branch_id] = {
                    "status": "pending",
                    "retrieved_chunks": []
                }
                
            for chunk in retrieved_chunks:
                if is_speculative:
                    session.state.controller.active_speculations[branch_id]["retrieved_chunks"].append(
                        chunk.model_dump()
                    )
                add_to_pool(
                    session=session.state,
                    chunk=chunk,
                    intent_id=intent.intent_id,
                    ts_stream_s=t_s,
                    speculative=is_speculative
                )

            # Mark intent as dispatched
            session.intent_set.mark_dispatched(intent.intent_id)

            # ── Telemetry: intent added ──
            await bus.emit(_emit_telemetry(
                session_id=session.session_id,
                turn_id=session.turn_id,
                ts_stream_s=t_s,
                component="decomposer",
                event_type=EVT_INTENT_ADDED,
                payload={
                    "intent_id": intent.intent_id,
                    "facet": intent.facet,
                    "query_nl": intent.query_nl,
                    "search_string": intent.search_string,
                    "trigger": trigger,
                },
            ))

            try:
                from slrag.telemetry.metrics import record_retrieval
                record_retrieval(trigger, 0.0)
            except Exception:
                pass

        dispatch = {intent.intent_id: intent for intent in novel_intents}
        if is_final:
            from slrag.retrieve.pool import get_pool_chunks_for_intent
            recovered = []
            for intent in session.current_candidates:
                if not get_pool_chunks_for_intent(session.state, intent.intent_id, top_k=1):
                    if intent.intent_id not in dispatch:
                        recovered.append(intent.intent_id)
                    dispatch[intent.intent_id] = intent
            if recovered:
                logger.info("Final retrieval recovery: session=%s intents=%s (no confirmed grounding)",
                            session.session_id, recovered)
        if dispatch and (session.classification.turn_type != "CONSTRAINT_REFINEMENT" or session.classification.mixed):
            import asyncio
            await asyncio.gather(*[_retrieve_and_pool(intent) for intent in dispatch.values()])
        # --- Overlap Merge (Anti-fragmentation) ---
        from slrag.decompose.overlap import OverlapMerger
        from slrag.core.schemas import RetrievedChunk
        overlap_merger = OverlapMerger()
        results_by_intent = {}
        current_ids = {i.intent_id for i in session.current_candidates}
        for entry in session.state.evidence_pool.values():
            for i_id, score in entry.scores_by_subquery.items():
                if i_id not in current_ids:
                    continue
                if i_id not in results_by_intent:
                    results_by_intent[i_id] = []
                results_by_intent[i_id].append(
                    RetrievedChunk(
                        chunk_id=entry.chunk_id, doc_id=entry.doc_id,
                        section_id=entry.section_id, text=entry.text,
                        score=score, citation_label=entry.citation_label
                    )
                )
        for i_id in results_by_intent:
            results_by_intent[i_id].sort(key=lambda x: x.score, reverse=True)

        merged_pairs = overlap_merger.check_all_pairs(
            session.state,
            results_by_intent,
            jaccard_threshold=0.7,
        )
        
        # Update triggers to resolve speculation on merged intents
        for kept_id, merged_id in merged_pairs:
            session.intent_set.mark_merged(merged_id, kept_id)
            kept_intent = session.state.intent_set.get(kept_id)
            merged_intent = session.state.intent_set.get(merged_id)
            for event in session.retrieval_events:
                if kept_intent and event.get("query") == kept_intent.search_string:
                    if event.get("trigger") == "provisional":
                        event["trigger"] = "final_confirm"
                if merged_intent and event.get("query") == merged_intent.search_string:
                    if event.get("trigger") == "provisional":
                        event["trigger"] = "final_confirm"

        retrieval_latency_ms = (time.perf_counter() - retrieval_start) * 1000

        # ── Telemetry: retrieval completed ──
        await bus.emit(_emit_telemetry(
            session_id=session.session_id,
            turn_id=session.turn_id,
            ts_stream_s=t_s,
            component="retriever",
            event_type=EVT_RETRIEVAL_COMPLETED,
            latency_ms=round(retrieval_latency_ms, 2),
            payload={
                "events_count": len(session.retrieval_events),
                "novel_dispatched": len(novel_intents),
            },
        ))

        await ws.send_json({
            "type": "retrieval_complete",
            "t_s": t_s,
            "events": session.retrieval_events,
        })


# ── Utterance End → Synthesis ────────────────────────────────────────

async def _process_utterance_end(session: PipelineSession, ws: WebSocket) -> None:
    """Process utterance end — synthesize the answer."""
    t_s = session.chunks[-1]["t_s"] if session.chunks else 0.0

    # ── Explicit End-Turn Transition: Final Decision Safety Net ──
    if not session.chunks or not session.chunks[-1].get("is_final"):
        await _process_chunk(session, {"t_s": t_s, "text": "", "is_final": True}, ws)
    from slrag.controller.speculation import process_speculation
    process_speculation("", 0.0, session.state.controller)
    session.current_candidates = [i for i in getattr(session, "current_candidates", [])
                                  if i.status not in ("merged", "superseded")]

    bus = get_bus()
    
    synthesis_start = time.perf_counter()

    # Resolve any remaining provisional events to CONFIRMED since utterance ended
    for event in session.retrieval_events:
        if event.get("trigger") == "provisional":
            event["trigger"] = "final_confirm"

    await ws.send_json({"type": "synthesis_started", "turn_id": session.turn_id})

    # ── Telemetry: synthesis started ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=session.turn_id,
        ts_stream_s=t_s,
        component="synthesis",
        event_type=EVT_SYNTHESIS_STARTED,
        payload={"turn_id": session.turn_id},
    ))

    # ── Stage 3: Synthesis ──
    synthesis_telemetry = {}
    if not hasattr(session, "engine") or session.engine is None:
        from slrag.synth.engine import SynthesisEngine
        session.engine = SynthesisEngine(session.session_id)
    engine = session.engine
    session.classification = engine.classify(
        utterance=session.prefix, controller_decisions=session.controller_results,
        sub_intents=session.current_candidates,
    )
    current_ids = {intent.intent_id for intent in session.current_candidates}
    if session.classification.turn_type == "PRESENTATION_ONLY":
        current_ids.clear()

    from slrag.retrieve.pool import get_pool_chunks_for_intent
    from slrag.core.schemas import IntentStatus
    candidates_by_intent = {
        intent.intent_id: get_pool_chunks_for_intent(session.state, intent.intent_id, top_k=10)
        for intent in session.state.intent_set.values()
        if intent.intent_id in current_ids and intent.status not in (IntentStatus.merged, IntentStatus.superseded)
    }
    
    from pathlib import Path
    from slrag.synth.config import _load_yaml
    retrieval_config = _load_yaml(Path("config/retrieval.yaml"))
    
    from slrag.retrieve.quota import assemble_context
    fused_context = assemble_context(candidates_by_intent, retrieval_config)
    
    from slrag.retrieve.contradiction import ContradictionGating
    if fused_context.chunks and not hasattr(session, "cg"):
        session.cg = ContradictionGating()
    
    # Group chunks by intent for the SynthesisEngine
    turn_evidence = {}
    for chunk in fused_context.chunks:
        for intent_id, chunks in candidates_by_intent.items():
            if any(c.chunk_id == chunk.chunk_id for c in chunks):
                turn_evidence.setdefault(intent_id, []).append(chunk)

    logger.info("Synthesis context: session=%s pooled_chunks=%d eligible_chunks=%d context_chunks=%d intents=%d",
                session.session_id, len(session.state.evidence_pool),
                sum(len(rows) for rows in candidates_by_intent.values()),
                len(fused_context.chunks), len(turn_evidence))
    await ws.send_json({"type": "pipeline_status", "stage": "context",
                        "message": f"Grounding context: {len(fused_context.chunks)} chunks for {len(turn_evidence)} intents"})

    # Detect contradictions per facet
    contradictions = []
    for intent_id, chunks in turn_evidence.items():
        intent = session.state.intent_set.get(intent_id)
        facet = intent.facet if intent else None
        res = await session.cg.detect_contradictions(chunks, facet)
        for conflict in res:
            vals_a, vals_b = conflict["values"]
            slot = conflict["slot"]
            contradictions.append(
                f"Conflicting {slot} found for {facet}: {vals_a} vs {vals_b}."
            )

    from slrag.synth.engine import TurnInput
    turn = TurnInput(
        turn_id=session.turn_id,
        utterance=session.prefix,
        t_s_end=t_s,
        sub_intents=tuple(getattr(session, 'current_candidates', [])),
        contradictions=contradictions,
        retrieval_events=tuple(session.retrieval_events),
        controller_decisions=tuple(session.controller_results),
        evidence=turn_evidence,
        classification=getattr(session, 'classification', None),
    )

    # Stream results
    async for event in engine.stream_turn(turn):
        from slrag.synth.types import StreamEvent
        from slrag.synth.engine import SynthesisResult

        if isinstance(event, StreamEvent):
            await ws.send_json({
                "type": "answer_token",
                "kind": event.kind,
                "seq": event.seq,
                "text": event.text,
                "citations": event.citations,
                "facet": event.facet,
            })
        elif isinstance(event, SynthesisResult):
            session.answer = event.output.answer
            session.citations = event.output.citations
            session.uncertainty = event.output.uncertainty
            session.claims = [c.model_dump() for c in event.output.claims]
            session.answer_version = event.output.answer_version
            session.suppression_reason = event.output.suppression_reason
            session.lineage = event.output.version_lineage.to_dict() if event.output.version_lineage else (event.lineage.to_dict() if event.lineage else None)

            # Extract telemetry from synthesis result
            synthesis_telemetry = {}
            if event.output.telemetry:
                tel = event.output.telemetry
                synthesis_telemetry = {
                    "latency_ms": tel.latency_ms,
                    "tokens": tel.tokens,
                    "cost_usd": tel.cost_usd,
                    "llm_calls": tel.llm_calls,
                }
                # Accumulate session totals
                session.total_tokens_prompt += tel.tokens.get("prompt", 0)
                session.total_tokens_completion += tel.tokens.get("completion", 0)
                session.total_cost_usd += tel.cost_usd
                session.total_llm_calls += tel.llm_calls

            # Emit synthesis telemetry events
            for te in event.telemetry:
                await bus.emit(te)

    synthesis_latency_ms = (time.perf_counter() - synthesis_start) * 1000

    # ── Telemetry: answer version ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=session.turn_id,
        ts_stream_s=t_s,
        component="synthesis",
        event_type=EVT_ANSWER_VERSION,
        latency_ms=round(synthesis_latency_ms, 2),
        payload={
            "answer_version": session.answer_version,
            "claims_count": len(session.claims),
            "citations_count": len(session.citations),
            "has_uncertainty": bool(session.uncertainty),
            **synthesis_telemetry,
        },
    ))

    # ── Telemetry: cost record ──
    if synthesis_telemetry:
        await bus.emit(_emit_telemetry(
            session_id=session.session_id,
            turn_id=session.turn_id,
            ts_stream_s=t_s,
            component="synthesis",
            event_type=EVT_COST_RECORD,
            payload={
                "tokens_prompt": synthesis_telemetry.get("tokens", {}).get("prompt", 0),
                "tokens_completion": synthesis_telemetry.get("tokens", {}).get("completion", 0),
                "cost_usd": synthesis_telemetry.get("cost_usd", 0),
                "session_total_prompt": session.total_tokens_prompt,
                "session_total_completion": session.total_tokens_completion,
                "session_total_cost_usd": round(session.total_cost_usd, 6),
            },
        ))

    # Emit answer version to client (includes telemetry data)
    await ws.send_json({
        "type": "answer_version",
        "turn_id": session.turn_id,
        "version": session.answer_version,
        "answer": session.answer,
        "citations": session.citations,
        "sub_queries": session.sub_queries,
        "claims": session.claims,
        "retrieval_events": session.retrieval_events,
        "suppression": getattr(session, 'suppression_reason', None),
        "lineage": getattr(session, 'lineage', None),
        "llm_diagnostics": {"calls": synthesis_telemetry.get("llm_calls", 0),
                            "context_chunks": len(fused_context.chunks),
                            "parse_errors": getattr(engine.generator, "parse_errors", 0),
                            "error": getattr(engine.generator, "last_error", None)},
        # Telemetry data for the UI
        "telemetry": {
            **synthesis_telemetry,
            "synthesis_latency_ms": round(synthesis_latency_ms, 2),
            "total_tokens_prompt": session.total_tokens_prompt,
            "total_tokens_completion": session.total_tokens_completion,
            "total_cost_usd": round(session.total_cost_usd, 6),
            "total_llm_calls": session.total_llm_calls,
        },
    })

    # Emit uncertainty
    if session.uncertainty:
        await ws.send_json({
            "type": "uncertainty",
            "text": session.uncertainty,
        })

    # Emit citation details
    for citation in session.citations:
        await ws.send_json({
            "type": "citation_attached",
            "label": citation,
        })

    # ── Telemetry: turn completed ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=session.turn_id,
        ts_stream_s=t_s,
        component="orchestrator",
        event_type=EVT_TURN_COMPLETED,
        latency_ms=round(synthesis_latency_ms, 2),
        payload={
            "turn_id": session.turn_id,
            "answer_version": session.answer_version,
            "claims_count": len(session.claims),
            "citations_count": len(session.citations),
            "retrieval_events_count": len(session.retrieval_events),
            "controller_decisions_count": len(session.controller_decisions),
        },
    ))

    # Reset per-turn state (prefix resets for next turn)
    session.prefix = ""
    session.chunks.clear()
    session.controller_decisions.clear()
    session.controller_results.clear()
    session.retrieval_events.clear()
    session.sub_queries.clear()
    session.suppression_reason = None
    session.lineage = None
    
    # Task cleanup and reset on controller
    from slrag.controller.cascade import RetrievalController
    controller = RetrievalController(session=session.state.controller)
    controller.reset_turn()
    
    session.state.controller.has_retrieved_this_intent = False
    if hasattr(session, 'current_candidates'):
        session.current_candidates.clear()
    session._last_decomposition_prefix = None
    session._last_decomposition_candidates = []
    if hasattr(session, 'classification'):
        session.classification = None


# ── WebSocket Endpoint ──────────────────────────────────────────────

@router.websocket("/ws/session")
async def websocket_session(ws: WebSocket):
    """Main WebSocket endpoint for streaming RAG sessions."""
    await ws.accept()
    mgr = get_session_manager()
    session = mgr.create()
    bus = get_bus()

    # Register WebSocket as a telemetry broadcast target
    queue = asyncio.Queue(maxsize=100)

    async def ws_broadcast(payload: dict) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass

    async def queue_worker():
        while True:
            try:
                payload = await queue.get()
                await ws.send_json(payload)
                queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                pass
                
    worker_task = asyncio.create_task(queue_worker())

    bus.subscribe_ws(session.session_id, ws_broadcast)

    # ── Telemetry: session started ──
    await bus.emit(_emit_telemetry(
        session_id=session.session_id,
        turn_id=0,
        ts_stream_s=0.0,
        component="orchestrator",
        event_type=EVT_SESSION_STARTED,
        payload={"session_id": session.session_id},
    ))

    try:
        await ws.send_json({
            "type": "session_created",
            "session_id": session.session_id,
        })

        logger.info(f"WebSocket session started: {session.session_id}")

        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            if msg_type == "chunk":
                await _process_chunk(session, msg, ws)

            elif msg_type == "utterance_end":
                await _process_utterance_end(session, ws)

            elif msg_type == "new_session":
                # End old session telemetry
                await bus.emit(_emit_telemetry(
                    session_id=session.session_id,
                    turn_id=session.turn_id,
                    ts_stream_s=0.0,
                    component="orchestrator",
                    event_type=EVT_SESSION_ENDED,
                    payload={"session_id": session.session_id},
                ))
                bus.unsubscribe_ws(session.session_id, ws_broadcast)
                mgr.end(session.session_id)
                session = mgr.create()
                bus.subscribe_ws(session.session_id, ws_broadcast)
                reset_retriever()
                # New session telemetry
                await bus.emit(_emit_telemetry(
                    session_id=session.session_id,
                    turn_id=0,
                    ts_stream_s=0.0,
                    component="orchestrator",
                    event_type=EVT_SESSION_STARTED,
                    payload={"session_id": session.session_id},
                ))
                await ws.send_json({
                    "type": "session_created",
                    "session_id": session.session_id,
                })

            elif msg_type == "end_session":
                await bus.emit(_emit_telemetry(
                    session_id=session.session_id,
                    turn_id=session.turn_id,
                    ts_stream_s=0.0,
                    component="orchestrator",
                    event_type=EVT_SESSION_ENDED,
                    payload={"session_id": session.session_id},
                ))
                mgr.end(session.session_id)
                await ws.send_json({"type": "session_ended", "session_id": session.session_id})

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            else:
                await ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session.session_id}")
    except Exception:
        logger.exception(f"WebSocket error: {session.session_id}")
    finally:
        worker_task.cancel()
        bus.unsubscribe_ws(session.session_id, ws_broadcast)
        mgr.end(session.session_id)
