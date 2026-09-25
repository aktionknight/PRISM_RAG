"""
tests/test_coverage_invariants.py — Unit tests for TraceCoverageSuite (Gate G6).

Component 5 — Observability & Telemetry (Matangi).
"""

import pytest

from slrag.core.events import (
    EVT_ANSWER_VERSION,
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_COST_RECORD,
    EVT_LLM_CALL,
    EVT_RETRIEVAL_STARTED,
)
from slrag.core.schemas import TelemetryEvent
from slrag.telemetry.coverage import TraceCoverageSuite


def make_clean_event_stream() -> list[TelemetryEvent]:
    """Assemble an artificial events stream satisfying all 6 invariants."""
    return [
        TelemetryEvent(
            event_id="e1", session_id="s1", turn_id=1, ts_stream_s=0.0,
            component="stream", event_type=EVT_CHUNK_RECEIVED, payload={"text": "chunk1"}
        ),
        TelemetryEvent(
            event_id="e2", session_id="s1", turn_id=1, ts_stream_s=0.0,
            component="controller", event_type=EVT_CONTROLLER_DECISION,
            payload={"decision": "WAIT", "reason": "intent_unstable"}
        ),
        TelemetryEvent(
            event_id="e3", session_id="s1", turn_id=1, ts_stream_s=0.8,
            component="stream", event_type=EVT_CHUNK_RECEIVED, payload={"text": "chunk2"}
        ),
        TelemetryEvent(
            event_id="e4", session_id="s1", turn_id=1, ts_stream_s=0.8,
            component="controller", event_type=EVT_CONTROLLER_DECISION,
            payload={"decision": "RETRIEVE", "reason": "corpus_discriminative"}
        ),
        TelemetryEvent(
            event_id="e5", session_id="s1", turn_id=1, ts_stream_s=0.8,
            component="retriever", event_type=EVT_RETRIEVAL_STARTED,
            payload={"query": "workshop pune", "trigger": "provisional"}
        ),
        TelemetryEvent(
            event_id="e6", session_id="s1", turn_id=1, ts_stream_s=2.1,
            component="synthesizer", event_type=EVT_LLM_CALL,
            payload={"call_id": "call-1", "prompt_tokens": 500, "completion_tokens": 100}
        ),
        TelemetryEvent(
            event_id="e7", session_id="s1", turn_id=1, ts_stream_s=2.1,
            component="synthesizer", event_type=EVT_COST_RECORD,
            payload={"call_id": "call-1", "cost_usd": 0.0004, "item_type": "llm"}
        ),
        TelemetryEvent(
            event_id="e8", session_id="s1", turn_id=1, ts_stream_s=2.1,
            component="synthesizer", event_type=EVT_ANSWER_VERSION,
            payload={
                "version": 1,
                "citations": ["Doc_12 §2", "Doc_31 §4"],
                "answer": "Test answer",
            }
        ),
    ]


class TestTraceCoverageSuite:
    def test_clean_stream_passes_all_invariants(self):
        suite = TraceCoverageSuite(indexed_citation_labels={"Doc_12 §2", "Doc_31 §4"})
        events = make_clean_event_stream()
        report = suite.evaluate_events(events)

        assert report.is_clean is True
        assert report.passed == 6
        assert report.total == 6
        assert report.coverage_pct == 100.0

    def test_invariant_1_chunk_decision_mismatch(self):
        suite = TraceCoverageSuite()
        events = make_clean_event_stream()
        # Drop decision e4 -> 2 chunks, 1 decision
        events = [e for e in events if e.event_id != "e4"]
        report = suite.evaluate_events(events)

        assert report.is_clean is False
        assert report.details["chunk_decision_parity"]["passed"] is False

    def test_invariant_2_retrieval_without_parent(self):
        suite = TraceCoverageSuite()
        events = make_clean_event_stream()
        # Change decision e4 from RETRIEVE to WAIT -> retrieval e5 has no RETRIEVE parent
        for e in events:
            if e.event_id == "e4":
                e.payload["decision"] = "WAIT"
        report = suite.evaluate_events(events)

        assert report.is_clean is False
        assert report.details["retrieval_parentage"]["passed"] is False

    def test_invariant_3_citation_format_violation(self):
        suite = TraceCoverageSuite()
        events = make_clean_event_stream()
        # Insert a malformed citation
        for e in events:
            if e.event_type == EVT_ANSWER_VERSION:
                e.payload["citations"].append("invalid_citation_marker")
        report = suite.evaluate_events(events)

        assert report.is_clean is False
        assert report.details["citation_resolution"]["passed"] is False

    def test_invariant_6_timestamp_regress(self):
        suite = TraceCoverageSuite()
        events = make_clean_event_stream()
        # Set last event timestamp backward
        events[-1].ts_stream_s = 0.5  # occurred after 2.1s
        report = suite.evaluate_events(events)

        assert report.is_clean is False
        assert report.details["monotonic_timestamps"]["passed"] is False
