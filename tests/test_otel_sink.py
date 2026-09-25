"""
tests/test_otel_sink.py — Unit tests for OpenTelemetrySink span builder.

Component 5 — Observability & Telemetry (Matangi).
"""

import pytest

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
from slrag.telemetry.otel_sink import OpenTelemetrySink


class TestOpenTelemetrySink:
    def test_otel_sink_lifecycle_events(self):
        sink = OpenTelemetrySink(tracer_name="test.slrag", enabled=True)

        events = [
            TelemetryEvent(
                event_id="e1", session_id="s1", turn_id=1, ts_stream_s=0.0,
                component="orchestrator", event_type=EVT_SESSION_STARTED, payload={}
            ),
            TelemetryEvent(
                event_id="e2", session_id="s1", turn_id=1, ts_stream_s=0.0,
                component="orchestrator", event_type=EVT_TURN_STARTED, payload={}
            ),
            TelemetryEvent(
                event_id="e3", session_id="s1", turn_id=1, ts_stream_s=0.8,
                component="stream", event_type=EVT_CHUNK_RECEIVED, payload={"text": "chunk1"}
            ),
            TelemetryEvent(
                event_id="e4", session_id="s1", turn_id=1, ts_stream_s=0.8,
                component="controller", event_type=EVT_CONTROLLER_DECISION,
                payload={"decision": "RETRIEVE", "reason": "corpus_discriminative", "confidence": 0.9}
            ),
            TelemetryEvent(
                event_id="e5", session_id="s1", turn_id=1, ts_stream_s=0.8,
                component="retriever", event_type=EVT_RETRIEVAL_STARTED,
                payload={"sub_intent_id": "i1", "query": "workshop pune", "trigger": "provisional"}
            ),
            TelemetryEvent(
                event_id="e6", session_id="s1", turn_id=1, ts_stream_s=1.0,
                component="retriever", event_type=EVT_RETRIEVAL_COMPLETED,
                payload={"sub_intent_id": "i1", "num_chunks": 4}
            ),
            TelemetryEvent(
                event_id="e7", session_id="s1", turn_id=1, ts_stream_s=2.1,
                component="synthesizer", event_type=EVT_SYNTHESIS_STARTED, payload={}
            ),
            TelemetryEvent(
                event_id="e8", session_id="s1", turn_id=1, ts_stream_s=2.1,
                component="synthesizer", event_type=EVT_ANSWER_VERSION,
                payload={"version": 1, "citations": ["Doc_12 §2"]}
            ),
            TelemetryEvent(
                event_id="e9", session_id="s1", turn_id=1, ts_stream_s=2.1,
                component="orchestrator", event_type=EVT_TURN_COMPLETED, payload={}
            ),
            TelemetryEvent(
                event_id="e10", session_id="s1", turn_id=1, ts_stream_s=2.1,
                component="orchestrator", event_type=EVT_SESSION_ENDED, payload={}
            ),
        ]

        for ev in events:
            sink.handle_event(ev)

        assert len(sink._active_spans) == 0
        sink.close()

    def test_otel_sink_disabled(self):
        sink = OpenTelemetrySink(enabled=False)
        ev = TelemetryEvent(
            event_id="e1", session_id="s1", turn_id=1, ts_stream_s=0.0,
            component="orchestrator", event_type=EVT_SESSION_STARTED, payload={}
        )
        sink.handle_event(ev)
        assert len(sink._active_spans) == 0
