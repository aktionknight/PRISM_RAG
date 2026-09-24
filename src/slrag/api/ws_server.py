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
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from slrag.core.schemas import (
    AnswerOutput,
    ControllerDecision,
    ControllerDecisionType,
    SubIntent,
    TranscriptChunk,
)
from slrag.core.session import SessionState
from slrag.telemetry.bus import get_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@dataclass
class PipelineSession:
    """One active user session with full pipeline state."""
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
            return True
        return False


_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _manager
    if _manager is None:
        _manager = SessionManager()
    return _manager


async def _process_chunk(session: PipelineSession, chunk_data: dict, ws: WebSocket) -> None:
    """Process a single transcript chunk through the pipeline."""
    t_s = chunk_data.get("t_s", 0.0)
    text = chunk_data.get("text", "")
    is_final = chunk_data.get("is_final", False)

    session.prefix += text
    chunk = TranscriptChunk(t_s=t_s, text=text, is_final=is_final)

    # Store chunk for telemetry
    session.chunks.append({"t_s": t_s, "text": text, "is_final": is_final})

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

    # Record metrics
    try:
        from slrag.telemetry.metrics import record_controller_decision
        record_controller_decision(decision, reason, latency_ms / 1000)
    except Exception:
        pass

    decision_event = {
        "type": "controller_decision",
        "t_s": t_s,
        "decision": decision,
        "reason": reason,
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

        # Decompose
        try:
            from slrag.decompose.decomposer import Decomposer
            decomposer = Decomposer()
            intents = await decomposer.decompose(
                prefix=session.prefix,
                existing_intents=session.state.intent_set,
                ts=t_s,
            )
        except Exception as e:
            logger.warning(f"Real decomposer failed ({e}), using stub")
            from slrag.stubs.fake_decomposer import fake_decompose
            intents = fake_decompose(session.prefix, t_s)

        # Update sub-queries
        sub_queries = [intent.query_nl for intent in intents]
        session.sub_queries = list(dict.fromkeys([*session.sub_queries, *sub_queries]))

        await ws.send_json({
            "type": "subqueries_updated",
            "t_s": t_s,
            "sub_queries": session.sub_queries,
            "new_intents": [
                {"facet": i.facet, "query_nl": i.query_nl, "intent_id": i.intent_id}
                for i in intents
            ],
        })

        # Retrieval (per intent)
        for intent in intents:
            retrieval_event = {
                "timestamp_s": t_s,
                "query": intent.search_string,
                "trigger": "provisional" if len(session.retrieval_events) == 0 else "multi_intent",
                "facet": intent.facet,
            }
            session.retrieval_events.append(retrieval_event)

            try:
                from slrag.telemetry.metrics import record_retrieval
                record_retrieval(retrieval_event["trigger"], 0.0)
            except Exception:
                pass

        await ws.send_json({
            "type": "retrieval_complete",
            "t_s": t_s,
            "events": session.retrieval_events,
        })


async def _process_utterance_end(session: PipelineSession, ws: WebSocket) -> None:
    """Process utterance end — synthesize the answer."""
    session.turn_id += 1
    session.answer_version += 1
    t_s = session.chunks[-1]["t_s"] if session.chunks else 0.0

    await ws.send_json({"type": "synthesis_started", "turn_id": session.turn_id})

    # ── Stage 3: Synthesis ──
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

                # Emit telemetry
                bus = get_bus()
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

    # Emit answer version
    await ws.send_json({
        "type": "answer_version",
        "turn_id": session.turn_id,
        "version": session.answer_version,
        "answer": session.answer,
        "citations": session.citations,
        "sub_queries": session.sub_queries,
        "claims": session.claims,
        "retrieval_events": session.retrieval_events,
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

    # Reset per-turn state
    session.prefix = ""
    session.chunks.clear()
    session.controller_decisions.clear()
    session.retrieval_events.clear()


@router.websocket("/ws/session")
async def websocket_session(ws: WebSocket):
    """Main WebSocket endpoint for streaming RAG sessions."""
    await ws.accept()
    mgr = get_session_manager()
    session = mgr.create()

    # Register WebSocket as a telemetry broadcast target
    bus = get_bus()

    async def ws_broadcast(payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            pass

    bus.subscribe_ws(ws_broadcast)

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
                mgr.end(session.session_id)
                session = mgr.create()
                await ws.send_json({
                    "type": "session_created",
                    "session_id": session.session_id,
                })

            elif msg_type == "end_session":
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
