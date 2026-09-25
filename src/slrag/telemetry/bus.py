"""
telemetry/bus.py — Central TelemetryBus for Streaming Live RAG.

Component 5 — Observability & Telemetry (Matangi).
Every pipeline stage emits structured events through this bus. The bus routes
events to registered sinks:
  - JSONLSink (always-on events.jsonl)
  - OpenTelemetrySink (OTel spans / Prometheus metrics)
  - WebSocket / UI streamer
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import inspect
import logging
import time
from typing import Any, Callable, Optional
import uuid

from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)


def generate_event_id() -> str:
    """Generate a unique, sortable event identifier.
    
    Uses ULID if ulid package is installed; otherwise generates a monotonic
    timestamp-prefixed hex UUID.
    """
    try:
        import ulid
        return str(ulid.new())
    except ImportError:
        ms = int(time.time() * 1000)
        rand = uuid.uuid4().hex[:12]
        return f"evt_{ms:012x}_{rand}"


class TelemetryBus:
    """Central event bus connecting all pipeline stages to sinks.
    
    Provides thread-safe / async-friendly publish-subscribe dispatch.
    Also retains in-memory events for the active session turn.
    """

    def __init__(self) -> None:
        self._subscribers: list[Callable[[TelemetryEvent], Any]] = []
        self._events: list[TelemetryEvent] = []

    def subscribe(self, callback: Callable[[TelemetryEvent], Any]) -> None:
        """Register an event listener (sync or async function)."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TelemetryEvent], Any]) -> None:
        """Unregister an event listener."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def emit(
        self,
        event_type: str,
        component: str,
        session_id: str,
        turn_id: int,
        ts_stream_s: float,
        latency_ms: float = 0.0,
        payload: Optional[dict[str, Any]] = None,
        ts_wall: Optional[str] = None,
    ) -> TelemetryEvent:
        """Create, store, and dispatch a schema-compliant TelemetryEvent."""
        if ts_wall is None:
            ts_wall = datetime.now(timezone.utc).isoformat()

        event = TelemetryEvent(
            event_id=generate_event_id(),
            session_id=session_id,
            turn_id=turn_id,
            ts_stream_s=float(ts_stream_s),
            ts_wall=ts_wall,
            component=component,
            event_type=event_type,
            latency_ms=float(latency_ms),
            payload=payload or {},
        )

        self._events.append(event)
        self._dispatch(event)
        return event

    def _dispatch(self, event: TelemetryEvent) -> None:
        """Dispatch event to all subscribers."""
        for callback in self._subscribers:
            try:
                res = callback(event)
                if inspect.isawaitable(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        asyncio.run(res)
            except Exception as e:
                logger.error(f"Error in telemetry subscriber {callback}: {e}", exc_info=True)

    def get_events(
        self,
        session_id: Optional[str] = None,
        turn_id: Optional[int] = None,
        event_type: Optional[str] = None,
        component: Optional[str] = None,
    ) -> list[TelemetryEvent]:
        """Query collected in-memory events with optional filters."""
        result = self._events
        if session_id is not None:
            result = [e for e in result if e.session_id == session_id]
        if turn_id is not None:
            result = [e for e in result if e.turn_id == turn_id]
        if event_type is not None:
            result = [e for e in result if e.event_type == event_type]
        if component is not None:
            result = [e for e in result if e.component == component]
        return list(result)

    def clear(self) -> None:
        """Clear the in-memory event buffer (scoped to active session lifecycle)."""
        self._events.clear()
