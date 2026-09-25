"""Prometheus metrics derived from TelemetryBus events."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest

from slrag.core.schemas import TelemetryEvent

EVENTS_TOTAL = Counter(
    "slrag_events_total", "Telemetry events emitted", ["component", "event_type"]
)
EVENT_LATENCY_MS = Histogram(
    "slrag_event_latency_ms", "Pipeline event latency", ["component", "event_type"]
)


def observe_event(event: TelemetryEvent) -> None:
    EVENTS_TOTAL.labels(event.component, event.event_type).inc()
    EVENT_LATENCY_MS.labels(event.component, event.event_type).observe(event.latency_ms)


def metrics_payload() -> bytes:
    return generate_latest()