"""
tests/test_schemas.py — Validate frozen schemas against architectural requirements.

These tests ensure the frozen Pydantic schemas in core/schemas.py
are compliant with:
  - A_FINAL_ARCHITECTURE.md §6 (Output Schema — Contractual)
  - C_TEAM_COORDINATION.md §2 (Contract Freeze)
"""

import json

import pytest

from slrag.core.schemas import (
    AnswerOutput,
    Claim,
    ClaimStatus,
    ControllerDecision,
    ControllerDecisionType,
    ControllerReason,
    EvidencePoolEntry,
    FusedContext,
    RetrievalEvent,
    RetrievalTrigger,
    RetrievedChunk,
    SubIntent,
    TelemetryEvent,
    TelemetrySummary,
    TranscriptChunk,
    VersionLineage,
)


class TestTranscriptChunk:
    def test_basic_creation(self):
        chunk = TranscriptChunk(t_s=0.8, text="hello world", is_final=False)
        assert chunk.t_s == 0.8
        assert chunk.text == "hello world"
        assert chunk.is_final is False

    def test_utterance_end(self):
        chunk = TranscriptChunk(t_s=2.1, text="", is_final=True)
        assert chunk.is_final is True


class TestControllerDecision:
    def test_wait_decision(self):
        d = ControllerDecision(
            t_s=0.0,
            decision=ControllerDecisionType.WAIT,
            reason=ControllerReason.intent_unstable,
            confidence=0.31,
            stage=1,
        )
        assert d.decision == ControllerDecisionType.WAIT

    def test_retrieve_decision(self):
        d = ControllerDecision(
            t_s=0.8,
            decision=ControllerDecisionType.RETRIEVE,
            reason=ControllerReason.corpus_discriminative,
            confidence=0.78,
            stage=2,
        )
        assert d.decision == ControllerDecisionType.RETRIEVE

    def test_no_retrieval_decision(self):
        d = ControllerDecision(
            t_s=1.0,
            decision=ControllerDecisionType.NO_RETRIEVAL,
            reason=ControllerReason.presentation_restructure,
            confidence=0.95,
        )
        assert d.decision == ControllerDecisionType.NO_RETRIEVAL


class TestSubIntent:
    def test_creation(self):
        si = SubIntent(
            intent_id="i1",
            facet="venue_capacity",
            query_nl="venue capacity for 30 in Pune",
            search_string="Pune venue capacity 30",
            novel=True,
        )
        assert si.intent_id == "i1"
        assert si.novel is True
        assert si.dispatched is False


class TestRetrievedChunk:
    def test_creation(self):
        rc = RetrievedChunk(
            chunk_id="Doc_12#2#0",
            doc_id="Doc_12",
            section_id="2",
            text="Venue A holds up to 40 people.",
            score=0.92,
            citation_label="Doc_12 §2",
        )
        assert rc.citation_label == "Doc_12 §2"
        assert rc.chunk_id == "Doc_12#2#0"


class TestClaim:
    def test_active_claim(self):
        c = Claim(
            claim_id="c1",
            facet="venue_capacity",
            text="Venue A holds up to 40 people.",
            citations=["Doc_12 §2"],
            confidence=0.92,
            introduced_in_version=1,
            status=ClaimStatus.active,
        )
        assert c.status == ClaimStatus.active

    def test_superseded_claim(self):
        c = Claim(
            claim_id="c2",
            facet="cancellation_terms",
            text="Full refund if cancelled 14 days before.",
            citations=["Doc_31 §4"],
            status=ClaimStatus.superseded,
            superseded_by="c5",
        )
        assert c.superseded_by == "c5"


class TestAnswerOutput:
    """Test the full output schema matches the brief's five required keys."""

    def test_five_required_keys(self):
        """The five keys mandated by the brief must exist."""
        out = AnswerOutput()
        data = out.model_dump()
        for key in ["retrieval_events", "sub_queries", "answer", "citations", "uncertainty"]:
            assert key in data, f"Required key '{key}' missing from AnswerOutput"

    def test_golden_example_output(self):
        """Reproduce the architecture doc's §6 example output."""
        out = AnswerOutput(
            retrieval_events=[
                RetrievalEvent(
                    event_id="re1", timestamp_s=0.8,
                    query="Pune workshop venue capacity 30",
                    trigger=RetrievalTrigger.provisional, sub_intent_id="i1",
                ),
                RetrievalEvent(
                    event_id="re2", timestamp_s=1.6,
                    query="cancellation policy workshop venues Pune",
                    trigger=RetrievalTrigger.multi_intent, sub_intent_id="i2",
                ),
                RetrievalEvent(
                    event_id="re3", timestamp_s=1.6,
                    query="catering service options workshop Pune",
                    trigger=RetrievalTrigger.multi_intent, sub_intent_id="i3",
                ),
            ],
            sub_queries=[
                "venue capacity for 30 attendees in Pune",
                "cancellation terms and refund policies",
                "on-site and external catering options",
            ],
            answer="For a 30-person workshop in Pune...",
            citations=["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"],
            uncertainty="Catering accommodation policies for Venue A could not be verified.",
            session_id="sess_a91c",
            turn_id=3,
            answer_version=2,
            retrieval_required=True,
            controller_decisions=[
                ControllerDecision(
                    t_s=0.0, decision=ControllerDecisionType.WAIT,
                    reason=ControllerReason.intent_unstable, confidence=0.31,
                ),
                ControllerDecision(
                    t_s=0.8, decision=ControllerDecisionType.RETRIEVE,
                    reason=ControllerReason.corpus_discriminative, confidence=0.78,
                ),
            ],
        )

        data = out.model_dump()
        assert len(data["retrieval_events"]) == 3
        assert len(data["sub_queries"]) == 3
        assert data["retrieval_events"][0]["timestamp_s"] == 0.8
        assert data["retrieval_events"][0]["trigger"] == "provisional"
        assert data["retrieval_events"][1]["trigger"] == "multi_intent"

    def test_json_serialization_roundtrip(self):
        """Schema must survive JSON serialization roundtrip."""
        out = AnswerOutput(
            answer="Test answer",
            citations=["Doc_1 §1"],
            uncertainty="",
        )
        json_str = out.model_dump_json()
        loaded = json.loads(json_str)
        roundtripped = AnswerOutput.model_validate(loaded)
        assert roundtripped.answer == "Test answer"


class TestVersionLineage:
    def test_lineage(self):
        vl = VersionLineage(
            from_version=1,
            to_version=2,
            retained=["c1"],
            superseded=["c2"],
            added=["c5"],
        )
        assert vl.from_version == 1
        assert vl.to_version == 2


class TestTelemetryEvent:
    def test_creation(self):
        evt = TelemetryEvent(
            event_id="evt_001",
            session_id="sess_01",
            turn_id=1,
            ts_stream_s=0.8,
            component="controller",
            event_type="controller_decision",
            latency_ms=2.3,
            payload={"decision": "RETRIEVE"},
        )
        assert evt.component == "controller"
        assert evt.payload["decision"] == "RETRIEVE"
