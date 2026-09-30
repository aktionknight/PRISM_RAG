"""Corpus-independent regressions using sensor maintenance as held-out vocabulary."""

import numpy as np
import pytest

from slrag.controller import cascade
from slrag.core.schemas import ControllerDecision, SubIntent, TranscriptChunk
from slrag.core.session import ControllerState, SessionState
from slrag.decompose import intent_set


class Encoder:
    def encode(self, text, **kwargs):
        return np.array([1.0, 0.0])


@pytest.mark.asyncio
@pytest.mark.parametrize("new_interval,expected_count", [(12, 0), (24, 1)])
async def test_near_duplicate_preserves_numeric_changes(monkeypatch, new_interval, expected_count):
    monkeypatch.setattr(intent_set, "_get_embedding_model", lambda _: Encoder())
    session = SessionState(session_id="held-out")
    intents = intent_set.IntentSet(session)

    def candidate(interval):
        return SubIntent(intent_id="", facet="maintenance", query_nl="sensor calibration",
                         search_string=f"sensor calibration every {interval} months")

    await intents.add_intents([candidate(12)])
    novel = await intents.add_intents([candidate(new_interval)])
    assert len(novel) == expected_count
    assert len(session.intent_set) == 1 + expected_count


@pytest.mark.asyncio
async def test_duplicate_candidate_reuses_evidence_identity(monkeypatch):
    monkeypatch.setattr(intent_set, "_get_embedding_model", lambda _: Encoder())
    session = SessionState(session_id="held-out")
    intents = intent_set.IntentSet(session)
    original = SubIntent(intent_id="initial", facet="maintenance", query_nl="sensor calibration",
                         search_string="sensor calibration every 12 months")
    await intents.add_intents([original])
    intents.mark_dispatched(original.intent_id)
    duplicate = original.model_copy(update={"intent_id": "fresh-candidate", "novel": True})
    assert await intents.add_intents([duplicate]) == []
    assert duplicate.intent_id == original.intent_id
    assert duplicate.novel is False
    assert duplicate.status == original.status


def test_final_suppression_precedes_safety_and_clears_prefix(monkeypatch):
    seen = []

    def suppress(prefix, t_s):
        seen.append(prefix)
        return ControllerDecision(t_s=t_s, decision="NO_RETRIEVAL",
                                  reason="presentation_restructure", confidence=0.9, stage=0)

    monkeypatch.setattr(cascade, "evaluate_suppression", suppress)
    state = ControllerState()
    state.current_prefix = "summarize"
    state.last_retrieve_time = 950.0  # Final suppression also survives cooldown.
    controller = cascade.RetrievalController(state, encoder_mock=Encoder())
    decision = controller.process_chunk(TranscriptChunk(t_s=1.0, text="that briefly", is_final=True))
    assert decision.decision == "NO_RETRIEVAL"
    assert seen == ["summarize that briefly"]
    assert state.current_prefix == ""
    assert state.last_retrieve_time == 950.0


def test_final_new_information_keeps_safety_retrieval(monkeypatch):
    monkeypatch.setattr(cascade, "evaluate_suppression", lambda *args: None)
    state = ControllerState()
    controller = cascade.RetrievalController(state, encoder_mock=Encoder())
    decision = controller.process_chunk(TranscriptChunk(t_s=1.0, text="sensor calibration", is_final=True))
    assert decision.decision == "RETRIEVE"
    assert decision.reason == "utterance_end_safety"
    assert state.current_prefix == ""
    assert state.last_retrieve_time == 1000.0


@pytest.mark.parametrize("text,expected", [
    ("repeat that in two bullets", "NO_RETRIEVAL"),
    ("repeat that in 3 bullets", "NO_RETRIEVAL"),
    ("summarize sensor calibration in two bullets", "RETRIEVE"),
])
def test_final_presentation_controls_are_not_corpus_anchors(text, expected):
    controller = cascade.RetrievalController(ControllerState(), encoder_mock=Encoder())
    assert controller.process_chunk(TranscriptChunk(t_s=1.0, text=text, is_final=True)).decision == expected
