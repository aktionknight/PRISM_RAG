"""
api/ws_server.py — FastAPI WebSocket and REST server for Streaming Live RAG.

Component 5 & Demo Surface (Matangi).
Exposes /ws/session for real-time streaming transcripts and broadcasts
intermediate controller decisions, retrieval events, citations, and answers.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict

from slrag.core.schemas import TelemetryEvent, TranscriptChunk
from slrag.core.session import SessionState
from slrag.core.orchestrator import Orchestrator
from slrag.telemetry.bus import TelemetryBus

logger = logging.getLogger(__name__)

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from fastapi.responses import Response
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def create_app() -> Any:
    """Create and configure the FastAPI application."""
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is not installed. Run 'pip install fastapi uvicorn websockets' "
            "to enable the WebSocket serving surface."
        )

    app = FastAPI(
        title="Streaming Live RAG Engine",
        description="Real-time incremental retrieval, multi-intent decomposition, and refinement.",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "streaming-live-rag", "version": "0.1.0"}

    @app.get("/metrics")
    async def metrics():
        from slrag.telemetry.metrics import metrics_payload

        return Response(content=metrics_payload(), media_type="text/plain; version=0.0.4")

    @app.websocket("/ws/session")
    async def session_websocket(websocket: WebSocket):
        await websocket.accept()
        session_id = f"sess_ws_{int(asyncio.get_event_loop().time() * 1000)}"
        session = SessionState(session_id=session_id)
        bus = TelemetryBus()
        event_queue: asyncio.Queue[TelemetryEvent] = asyncio.Queue()
        from slrag.telemetry.metrics import observe_event

        bus.subscribe(observe_event)

        # Serialize telemetry sends so concurrent pipeline events cannot race.
        def queue_event(event: TelemetryEvent) -> None:
            event_queue.put_nowait(event)

        async def forward_events() -> None:
            while True:
                event = await event_queue.get()
                await websocket.send_text(event.model_dump_json())
                event_queue.task_done()

        bus.subscribe(queue_event)
        orchestrator = Orchestrator(session=session, bus=bus)
        sender_task = asyncio.create_task(forward_events())
        logger.info(f"WebSocket client connected: {session_id}")

        try:
            while True:
                raw_msg = await websocket.receive_text()
                try:
                    payload = json.loads(raw_msg)
                except json.JSONDecodeError:
                    await websocket.send_json({"error": "Invalid JSON format"})
                    continue

                msg_type = payload.get("type", "chunk")

                if msg_type == "chunk":
                    chunk = TranscriptChunk(
                        t_s=float(payload.get("t_s", 0.0)),
                        text=str(payload.get("text", "")),
                        is_final=bool(payload.get("is_final", False)),
                    )
                    decision = await orchestrator.process_chunk(chunk)
                    
                    if chunk.is_final:
                        output = await orchestrator.finalize_turn(last_ts=chunk.t_s)
                        await event_queue.join()
                        await websocket.send_json({
                            "type": "turn_completed",
                            "answer_output": output.model_dump(),
                        })

                elif msg_type == "finalize":
                    last_ts = float(payload.get("t_s", 2.1))
                    output = await orchestrator.finalize_turn(last_ts=last_ts)
                    await event_queue.join()
                    await websocket.send_json({
                        "type": "turn_completed",
                        "answer_output": output.model_dump(),
                    })

                elif msg_type == "reset":
                    session = SessionState(session_id=session_id)
                    orchestrator = Orchestrator(session=session, bus=bus)
                    await websocket.send_json({"type": "session_reset", "session_id": session_id})

        except WebSocketDisconnect:
            logger.info(f"WebSocket client disconnected: {session_id}")
        except Exception as e:
            logger.error(f"WebSocket error in {session_id}: {e}", exc_info=True)
        finally:
            sender_task.cancel()

    return app


if FASTAPI_AVAILABLE:
    app = create_app()
else:
    app = None
