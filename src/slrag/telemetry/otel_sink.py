"""
telemetry/otel_sink.py — OpenTelemetry hierarchical span builder.

Component 5 — Observability & Telemetry (Matangi).
Translates pipeline TelemetryEvents into an OpenTelemetry span hierarchy:
  session -> turn -> chunk -> controller_decision
                          -> { retrieval(sub_query) -> rerank }
                          -> synthesis -> verification -> answer_version
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode

from slrag.core.events import (
    EVT_ANSWER_VERSION,
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_RETRIEVAL_COMPLETED,
    EVT_RETRIEVAL_STARTED,
    EVT_SESSION_ENDED,
    EVT_SESSION_STARTED,
    EVT_SYNTHESIS_STARTED,
    EVT_TURN_COMPLETED,
    EVT_TURN_STARTED,
)
from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)


class OpenTelemetrySink:
    """Consumes TelemetryEvents from TelemetryBus and builds OpenTelemetry traces."""

    def __init__(
        self,
        tracer_name: str = "slrag.engine",
        enabled: bool = True,
        configure_exporter: bool = False,
        exporter_endpoint: Optional[str] = None,
    ) -> None:
        self.enabled = enabled
        self._provider = None
        if enabled and configure_exporter:
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace import TracerProvider
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                self._provider = TracerProvider()
                exporter = OTLPSpanExporter(endpoint=exporter_endpoint)
                self._provider.add_span_processor(BatchSpanProcessor(exporter))
                trace.set_tracer_provider(self._provider)
            except Exception as exc:
                logger.warning("OTel exporter setup failed; spans remain local: %s", exc)
        self.tracer = trace.get_tracer(tracer_name)
        self._active_spans: Dict[str, Span] = {}

    def handle_event(self, event: TelemetryEvent) -> None:
        """Process incoming TelemetryEvent and map to OTel spans/attributes."""
        if not self.enabled:
            return

        ev_type = event.event_type
        sess_key = f"sess_{event.session_id}"
        turn_key = f"turn_{event.session_id}_{event.turn_id}"

        try:
            if ev_type == EVT_SESSION_STARTED:
                span = self.tracer.start_span(f"session:{event.session_id}")
                span.set_attribute("session_id", event.session_id)
                self._active_spans[sess_key] = span

            elif ev_type == EVT_TURN_STARTED:
                parent = self._active_spans.get(sess_key)
                ctx = trace.set_span_in_context(parent) if parent else None
                span = self.tracer.start_span(f"turn:{event.turn_id}", context=ctx)
                span.set_attribute("session_id", event.session_id)
                span.set_attribute("turn_id", event.turn_id)
                self._active_spans[turn_key] = span

            elif ev_type == EVT_CHUNK_RECEIVED:
                parent = self._active_spans.get(turn_key)
                ctx = trace.set_span_in_context(parent) if parent else None
                chunk_key = f"chunk_{event.session_id}_{event.turn_id}_{event.ts_stream_s}"
                span = self.tracer.start_span(f"chunk@{event.ts_stream_s:.2f}s", context=ctx)
                span.set_attribute("ts_stream_s", event.ts_stream_s)
                span.set_attribute("text", event.payload.get("text", ""))
                self._active_spans[chunk_key] = span

            elif ev_type == EVT_CONTROLLER_DECISION:
                chunk_key = f"chunk_{event.session_id}_{event.turn_id}_{event.ts_stream_s}"
                chunk = self._active_spans.get(chunk_key)
                ctx = trace.set_span_in_context(chunk) if chunk else None
                with self.tracer.start_as_current_span("controller_decision", context=ctx) as span:
                    span.set_attribute("decision", event.payload.get("decision", ""))
                    span.set_attribute("reason", event.payload.get("reason", ""))
                    span.set_attribute("confidence", event.payload.get("confidence", 0.0))
                if chunk:
                    chunk.end()
                    self._active_spans.pop(chunk_key, None)

            elif ev_type == EVT_RETRIEVAL_STARTED:
                parent = self._active_spans.get(turn_key)
                ctx = trace.set_span_in_context(parent) if parent else None
                sub_id = event.payload.get("sub_intent_id", "q")
                span = self.tracer.start_span(f"retrieval:{sub_id}", context=ctx)
                span.set_attribute("query", event.payload.get("query", ""))
                span.set_attribute("trigger", event.payload.get("trigger", ""))
                self._active_spans[f"ret_{sub_id}"] = span

            elif ev_type == EVT_RETRIEVAL_COMPLETED:
                sub_id = event.payload.get("sub_intent_id", "q")
                span = self._active_spans.pop(f"ret_{sub_id}", None)
                if span:
                    span.set_attribute("num_chunks", event.payload.get("num_chunks", 0))
                    span.end()

            elif ev_type == EVT_SYNTHESIS_STARTED:
                parent = self._active_spans.get(turn_key)
                ctx = trace.set_span_in_context(parent) if parent else None
                span = self.tracer.start_span("synthesis", context=ctx)
                self._active_spans[f"synth_{turn_key}"] = span

            elif ev_type == EVT_ANSWER_VERSION:
                span = self._active_spans.pop(f"synth_{turn_key}", None)
                if span:
                    span.set_attribute("version", event.payload.get("version", 1))
                    span.set_attribute("citations_count", len(event.payload.get("citations", [])))
                    span.end()

            elif ev_type == EVT_TURN_COMPLETED:
                span = self._active_spans.pop(turn_key, None)
                if span:
                    span.set_status(Status(StatusCode.OK))
                    span.end()

            elif ev_type == EVT_SESSION_ENDED:
                span = self._active_spans.pop(sess_key, None)
                if span:
                    span.set_status(Status(StatusCode.OK))
                    span.end()

        except Exception as e:
            logger.debug(f"Failed to record OTel span: {e}")

    def close(self) -> None:
        """End all remaining active spans."""
        for span in list(self._active_spans.values()):
            try:
                span.end()
            except Exception:
                pass
        self._active_spans.clear()
        if self._provider is not None:
            self._provider.force_flush()
