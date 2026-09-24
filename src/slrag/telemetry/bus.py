"""Telemetry bus — central pub/sub for structured events (Component 5, §5.1).

Every pipeline stage emits ``TelemetryEvent`` records through the bus.
Sinks (JSONL, OpenTelemetry, Prometheus, WebSocket broadcast) subscribe
and receive events asynchronously.  The bus is always on and dependency-free;
sinks that fail never break the pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from typing import Any

from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)

Subscriber = Callable[[TelemetryEvent], Coroutine[Any, Any, None]]


class TelemetryBus:
    """Process-wide telemetry event bus (singleton per engine)."""

    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []
        self._ws_subscribers: list[Callable[[dict], Coroutine[Any, Any, None]]] = []
        self._event_count = 0

    def subscribe(self, callback: Subscriber) -> None:
        """Register a sink (JSONL, OTel, Prometheus)."""
        self._subscribers.append(callback)

    def subscribe_ws(self, callback: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        """Register a WebSocket broadcast sink (live frontend updates)."""
        self._ws_subscribers.append(callback)

    def unsubscribe_ws(self, callback: Callable[[dict], Coroutine[Any, Any, None]]) -> None:
        self._ws_subscribers = [s for s in self._ws_subscribers if s is not callback]

    async def emit(self, event: TelemetryEvent) -> None:
        """Broadcast an event to all sinks. Failures are logged but never raised."""
        self._event_count += 1
        for sub in self._subscribers:
            try:
                await sub(event)
            except Exception:
                logger.exception("Telemetry sink error")

        # WebSocket broadcast (dict serialisation for JSON)
        ws_payload = {
            "type": "telemetry_tick",
            "event_id": event.event_id,
            "session_id": event.session_id,
            "turn_id": event.turn_id,
            "component": event.component,
            "latency_ms": event.latency_ms,
            "ts_stream_s": event.ts_stream_s,
            "payload": event.payload,
        }
        for ws_sub in self._ws_subscribers:
            try:
                await ws_sub(ws_payload)
            except Exception:
                pass  # WebSocket errors are non-fatal

    async def emit_many(self, events: list[TelemetryEvent]) -> None:
        for event in events:
            await self.emit(event)

    @property
    def event_count(self) -> int:
        return self._event_count


# Process-level singleton
_bus: TelemetryBus | None = None


def get_bus() -> TelemetryBus:
    global _bus
    if _bus is None:
        _bus = TelemetryBus()
    return _bus
