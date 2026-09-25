"""
tests/test_telemetry_bus.py — Unit tests for TelemetryBus and JSONLSink.

Component 5 — Observability & Telemetry (Matangi).
"""

import json
from pathlib import Path
import pytest

from slrag.core.events import EVT_CHUNK_RECEIVED, EVT_CONTROLLER_DECISION
from slrag.core.schemas import TelemetryEvent
from slrag.telemetry.bus import TelemetryBus, generate_event_id
from slrag.telemetry.jsonl_sink import JSONLSink


class TestTelemetryBus:
    def test_generate_event_id_unique(self):
        id1 = generate_event_id()
        id2 = generate_event_id()
        assert id1 != id2
        assert len(id1) >= 8

    def test_bus_emit_and_retrieve(self):
        bus = TelemetryBus()
        evt = bus.emit(
            event_type=EVT_CHUNK_RECEIVED,
            component="stream",
            session_id="s1",
            turn_id=1,
            ts_stream_s=0.8,
            payload={"text": "hello"},
        )

        assert isinstance(evt, TelemetryEvent)
        assert evt.event_type == EVT_CHUNK_RECEIVED
        assert evt.component == "stream"
        assert evt.ts_stream_s == 0.8
        assert evt.payload == {"text": "hello"}

        all_evts = bus.get_events()
        assert len(all_evts) == 1
        assert all_evts[0].event_id == evt.event_id

    def test_bus_filters(self):
        bus = TelemetryBus()
        bus.emit(EVT_CHUNK_RECEIVED, "stream", "s1", 1, 0.0)
        bus.emit(EVT_CONTROLLER_DECISION, "controller", "s1", 1, 0.0)
        bus.emit(EVT_CHUNK_RECEIVED, "stream", "s2", 2, 0.8)

        assert len(bus.get_events(session_id="s1")) == 2
        assert len(bus.get_events(session_id="s2")) == 1
        assert len(bus.get_events(event_type=EVT_CONTROLLER_DECISION)) == 1
        assert len(bus.get_events(component="stream")) == 2

    def test_bus_subscription_dispatch(self):
        bus = TelemetryBus()
        received = []

        def listener(event: TelemetryEvent):
            received.append(event)

        bus.subscribe(listener)
        bus.emit(EVT_CHUNK_RECEIVED, "stream", "s1", 1, 0.5)

        assert len(received) == 1
        assert received[0].ts_stream_s == 0.5

        bus.unsubscribe(listener)
        bus.emit(EVT_CONTROLLER_DECISION, "controller", "s1", 1, 0.5)
        assert len(received) == 1


class TestJSONLSink:
    def test_jsonl_sink_write_and_read(self, tmp_path: Path):
        file_path = tmp_path / "test_events.jsonl"
        sink = JSONLSink(file_path=file_path)

        bus = TelemetryBus()
        bus.subscribe(sink.write)

        evt1 = bus.emit(EVT_CHUNK_RECEIVED, "stream", "s1", 1, 0.0, payload={"text": "chunk1"})
        evt2 = bus.emit(EVT_CONTROLLER_DECISION, "controller", "s1", 1, 0.8, payload={"decision": "RETRIEVE"})

        sink.close()

        assert file_path.exists()
        lines = file_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        parsed1 = json.loads(lines[0])
        parsed2 = json.loads(lines[1])

        event_obj1 = TelemetryEvent(**parsed1)
        event_obj2 = TelemetryEvent(**parsed2)

        assert event_obj1.event_type == EVT_CHUNK_RECEIVED
        assert event_obj2.event_type == EVT_CONTROLLER_DECISION
        assert event_obj2.payload["decision"] == "RETRIEVE"
