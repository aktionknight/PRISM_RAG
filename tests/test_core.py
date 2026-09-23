import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from slrag.core.clock import RealTimeClock, VirtualClock
from slrag.core.events import (
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_SESSION_STARTED,
)
from slrag.core.orchestrator import Orchestrator
from slrag.core.schemas import (
    Claim,
    ClaimStatus,
    ControllerDecision,
    ControllerDecisionType,
    ControllerReason,
    EvidencePoolEntry,
    SubIntent,
    TranscriptChunk,
)
from slrag.core.session import SessionState


# --- Tests for session.py ---
def test_session_state_initialization():
    session = SessionState(session_id="test_sess", ttl_seconds=10.0)
    assert session.session_id == "test_sess"
    assert session.turn_id == 0
    assert session.answer_version == 0
    assert not session.is_expired
    assert session.active_claims == []
    assert session.all_citation_labels == set()


def test_session_state_ttl_expiration():
    session = SessionState(ttl_seconds=0.1)
    time.sleep(0.15)
    assert session.is_expired


def test_session_state_counters():
    session = SessionState()
    assert session.new_turn() == 1
    assert session.new_turn() == 2
    assert session.new_version() == 1
    assert session.new_version() == 2


def test_session_state_add_evidence():
    session = SessionState()
    entry1 = EvidencePoolEntry(
        chunk_id="chunk_1",
        text="some text",
        doc_id="doc1",
        section_id="sec1",
        citation_label="[doc1]",
        scores_by_subquery={"intent1": 0.9},
        used_in_versions=[1],
        first_retrieved_ts=10.0,
        speculative=True,
        embedding=[0.0] * 384
    )
    session.add_evidence(entry1)
    assert len(session.evidence_pool) == 1
    assert session.all_citation_labels == {"[doc1]"}

    # Update with the same chunk_id
    entry2 = EvidencePoolEntry(
        chunk_id="chunk_1",
        text="some text",
        doc_id="doc1",
        section_id="sec1",
        citation_label="[doc1]",
        scores_by_subquery={"intent2": 0.8},
        used_in_versions=[2],
        first_retrieved_ts=5.0,
        speculative=False,
        embedding=[0.0] * 384
    )
    session.add_evidence(entry2)
    
    updated = session.evidence_pool["chunk_1"]
    assert updated.scores_by_subquery == {"intent1": 0.9, "intent2": 0.8}
    assert set(updated.used_in_versions) == {1, 2}
    assert updated.first_retrieved_ts == 5.0
    assert not updated.speculative


def test_session_state_destroy():
    session = SessionState()
    session.intent_set["intent1"] = SubIntent(intent_id="intent1", facet="test", query_nl="t", search_string="t")
    session.evidence_pool["chunk1"] = EvidencePoolEntry(chunk_id="chunk1", text="a", doc_id="b", section_id="s", citation_label="c", embedding=[0.0]*384, first_retrieved_ts=1.0)
    session.claims.append(Claim(claim_id="c1", text="claim text"))
    session.prev_prefix_embedding = [0.1, 0.2]
    
    session.destroy()
    
    assert len(session.intent_set) == 0
    assert len(session.evidence_pool) == 0
    assert len(session.claims) == 0
    assert session.prev_prefix_embedding is None


# --- Tests for events.py ---
def test_events_constants():
    assert EVT_CHUNK_RECEIVED == "chunk_received"
    assert EVT_CONTROLLER_DECISION == "controller_decision"
    assert EVT_SESSION_STARTED == "session_started"


# --- Tests for clock.py ---
@pytest.mark.asyncio
async def test_virtual_clock():
    clock = VirtualClock()
    assert clock.stream_time() == 0.0
    
    clock.advance_to(5.0)
    assert clock.stream_time() == 5.0
    
    await clock.wait_until(10.0)
    assert clock.stream_time() == 10.0
    
    # Backward advance shouldn't decrease time
    clock.advance_to(2.0)
    assert clock.stream_time() == 10.0
    
    clock.reset()
    assert clock.stream_time() == 0.0


@pytest.mark.asyncio
async def test_real_time_clock():
    clock = RealTimeClock()
    start_time = clock.stream_time()
    assert start_time >= 0.0
    
    await clock.wait_until(0.1)
    assert clock.stream_time() >= 0.1
    
    clock.reset()
    assert clock.stream_time() < 0.1


# --- Tests for orchestrator.py ---
@pytest.mark.asyncio
@patch("slrag.core.orchestrator.fake_controller")
@patch("slrag.core.orchestrator.Decomposer", autospec=True)
@patch("slrag.core.orchestrator.IntentSet", autospec=True)
@patch("slrag.core.orchestrator.fake_retrieve")
@patch("slrag.core.orchestrator.add_to_pool")
async def test_orchestrator_process_chunk(
    mock_add_to_pool, mock_fake_retrieve, mock_intent_set_cls, mock_decomposer_cls, mock_fake_controller
):
    session = SessionState()
    
    # Mocking decomposer
    mock_decomposer_instance = mock_decomposer_cls.return_value
    mock_decomposer_instance.decompose = AsyncMock(return_value=[SubIntent(intent_id="i1", facet="test facet", query_nl="t", search_string="t")])
    
    # Mocking IntentSet
    mock_intent_set_instance = mock_intent_set_cls.return_value
    mock_intent_set_instance.add_intents = AsyncMock(return_value=[SubIntent(intent_id="i1", facet="test facet", query_nl="t", search_string="t")])
    mock_intent_set_instance.mark_dispatched = MagicMock()
    
    # Mocking fake_controller to return RETRIEVE
    mock_fake_controller.return_value = ControllerDecision(
        decision=ControllerDecisionType.RETRIEVE,
        reason=ControllerReason.new_intent,
        confidence=0.9
    )
    
    dummy_retrieved_chunk = MagicMock()
    mock_fake_retrieve.return_value = [dummy_retrieved_chunk]

    orchestrator = Orchestrator(session=session)
    orchestrator.decomposer = mock_decomposer_instance
    orchestrator.intent_set = mock_intent_set_instance

    chunk = TranscriptChunk(text="hello ", t_s=1.0)
    decision = await orchestrator.process_chunk(chunk)
    
    assert orchestrator.prefix == "hello "
    assert decision.decision == ControllerDecisionType.RETRIEVE
    
    mock_fake_controller.assert_called_once_with(chunk)
    mock_decomposer_instance.decompose.assert_awaited_once_with(
        prefix="hello ",
        existing_intents=session.intent_set,
        ts=1.0
    )
    mock_intent_set_instance.add_intents.assert_awaited_once()
    mock_fake_retrieve.assert_called_once()
    mock_add_to_pool.assert_called_once_with(
        session=session,
        chunk=dummy_retrieved_chunk,
        intent_id="i1",
        ts_stream_s=1.0,
        speculative=False
    )
    mock_intent_set_instance.mark_dispatched.assert_called_once_with("i1")


@pytest.mark.asyncio
async def test_orchestrator_process_stream():
    session = SessionState()
    orchestrator = Orchestrator(session=session)
    
    orchestrator.process_chunk = AsyncMock(return_value=ControllerDecision(
        decision=ControllerDecisionType.WAIT, reason=ControllerReason.intent_unstable, confidence=1.0
    ))

    async def mock_stream():
        yield TranscriptChunk(text="hello", t_s=1.0)
        yield TranscriptChunk(text=" world", t_s=2.0)

    await orchestrator.process_stream(mock_stream())
    
    assert orchestrator.process_chunk.call_count == 2
