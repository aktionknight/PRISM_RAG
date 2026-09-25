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
            # Reset stub global state so Demo→Reset→Demo works correctly
            try:
                from slrag.stubs.fake_controller import reset_stub as reset_ctrl
                reset_ctrl()
            except Exception:
                pass
            return True
        return False


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
    try:
        from slrag.controller.cascade import RetrievalController
        from slrag.core.config import get_controller_config

        controller = RetrievalController(session=session.state.controller)
        decision_result = controller.process_chunk(chunk)
        decision = decision_result.decision
        reason = decision_result.reason
        confidence = decision_result.confidence
        stage = getattr(decision_result, 'stage', None)
    except Exception as e:
        logger.warning(f"Real controller failed ({e}), using stub")
        from slrag.stubs.fake_controller import fake_controller
        decision_result = fake_controller(chunk)
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
        "stage": stage,
        "latency_ms": round(latency_ms, 2),
        "prefix": session.prefix,
    }
    session.controller_decisions.append(decision_event)
    await ws.send_json(decision_event)

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
        try:
            all_candidates = await session.decomposer.decompose(
                prefix=session.prefix,
                existing_intents=session.state.intent_set,
                ts=t_s,
            )
        except Exception as e:
            logger.warning(f"Real decomposer failed ({e}), using stub")
            from slrag.stubs.fake_decomposer import fake_decompose
            all_candidates = fake_decompose(session.prefix, session.state.intent_set)

        # Diff against IntentSet — dispatch ONLY genuinely novel intents (S-2)
        try:
            novel_intents = await session.intent_set.add_intents(all_candidates)
        except Exception as e:
            logger.warning(f"IntentSet dedup failed ({e}), treating all as novel")
            novel_intents = all_candidates

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

        # Update sub-queries list (all known intents, not just novel)
        all_queries = [
            intent.query_nl
            for intent in session.state.intent_set.values()
        ]
        session.sub_queries = list(dict.fromkeys(all_queries))

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
        for intent in novel_intents:
            # Determine trigger type per 02_SOLUTION_DESIGN
            if len(session.retrieval_events) == 0:
                trigger = "provisional"
            else:
                trigger = "multi_intent"

            retrieval_event = {
                "event_id": _make_event_id(),
                "timestamp_s": t_s,
                "query": intent.search_string,
                "trigger": trigger,
                "facet": intent.facet,
                "sub_intent_id": intent.intent_id,
            }
            session.retrieval_events.append(retrieval_event)

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
    bus = get_bus()
    session.turn_id += 1
    session.answer_version += 1
    t_s = session.chunks[-1]["t_s"] if session.chunks else 0.0
    synthesis_start = time.perf_counter()

    # ── Telemetry: turn started ──
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
    try:
        from slrag.synth.engine import SynthesisEngine, TurnInput

        engine = SynthesisEngine(session.session_id)
        turn = TurnInput(
            turn_id=session.turn_id,
            utterance=session.prefix,
            t_s_end=t_s,
            sub_intents=tuple(
                SubIntent(
                    intent_id=f"i{idx}",
                    facet=q.split()[0] if q else "general",
                    query_nl=q,
                    search_string=q,
                )
                for idx, q in enumerate(session.sub_queries)
            ),
            retrieval_events=tuple(session.retrieval_events),
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

                # Extract telemetry from synthesis result
                if event.output.telemetry:
                    tel = event.output.telemetry
                    synthesis_telemetry = {
                        "latency_ms": tel.latency_ms,
                        "tokens": tel.tokens,
                        "cost_usd": tel.cost_usd,
                    }
                    # Accumulate session totals
                    session.total_tokens_prompt += tel.tokens.get("prompt", 0)
                    session.total_tokens_completion += tel.tokens.get("completion", 0)
                    session.total_cost_usd += tel.cost_usd
                    session.total_llm_calls += 1

                # Emit synthesis telemetry events
                for te in event.telemetry:
                    await bus.emit(te)

    except Exception as e:
        logger.warning(f"Synthesis engine failed ({e}), using stub")
        from slrag.stubs.fake_synthesis import fake_synthesize
        output = fake_synthesize(
            session_id=session.session_id,
            turn_id=session.turn_id,
        )
        session.answer = output.answer
        session.citations = output.citations
        session.uncertainty = output.uncertainty
        session.claims = [c.model_dump() for c in output.claims]

        # Extract stub telemetry
        if output.telemetry:
            tel = output.telemetry
            synthesis_telemetry = {
                "latency_ms": tel.latency_ms,
                "tokens": tel.tokens,
                "cost_usd": tel.cost_usd,
            }
            session.total_tokens_prompt += tel.tokens.get("prompt", 0)
            session.total_tokens_completion += tel.tokens.get("completion", 0)
            session.total_cost_usd += tel.cost_usd
            session.total_llm_calls += 1

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

    # Reset per-turn state (prefix resets for next turn; retrieval events accumulate per session)
    session.prefix = ""
    session.chunks.clear()
    session.controller_decisions.clear()
    # NOTE: retrieval_events persist across turns for session continuity (G5)


# ── WebSocket Endpoint ──────────────────────────────────────────────

@router.websocket("/ws/session")
async def websocket_session(ws: WebSocket):
    """Main WebSocket endpoint for streaming RAG sessions."""
    await ws.accept()
    mgr = get_session_manager()
    session = mgr.create()
    bus = get_bus()

    # Register WebSocket as a telemetry broadcast target
    async def ws_broadcast(payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    bus.subscribe_ws(ws_broadcast)

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
                mgr.end(session.session_id)
                session = mgr.create()
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
        bus.unsubscribe_ws(ws_broadcast)
        mgr.end(session.session_id)
