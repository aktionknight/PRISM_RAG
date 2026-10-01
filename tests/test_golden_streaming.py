"""Held-out golden correction: real intent store, extractive synthesis and verifier.

Embeddings alone are deterministic. This is a component integration regression,
not a live-LLM or streaming latency benchmark.
"""
import numpy as np
import pytest

from slrag.core.schemas import AnswerOutput, IntentStatus, RetrievedChunk, SubIntent
from slrag.core.session import SessionState
from slrag.decompose import intent_set
from slrag.synth.config import load_synth_config
from slrag.synth.engine import SynthesisEngine, TurnInput


class Encoder:
    def encode(self, text, **kwargs):
        return np.array([1.0, 0.0])


@pytest.fixture
def intents(monkeypatch):
    monkeypatch.setattr(intent_set, "_get_embedding_model", lambda _: Encoder())
    return intent_set.IntentSet(SessionState(session_id="golden-self-correction"))


def candidate(interval):
    return SubIntent(
        intent_id="", facet="maintenance",
        query_nl=f"Explain sensor calibration every {interval} months",
        search_string=f"sensor calibration every {interval} months",
        slots={"interval_months": interval},
    )


@pytest.mark.asyncio
async def test_golden_replay_chunk_sequence(intents):
    original = candidate(12)
    await intents.add_intents([original], prefix="Explain sensor calibration every 12 months")
    intents.mark_dispatched(original.intent_id)
    corrected = candidate(24)
    await intents.add_intents([corrected], prefix="Actually, I meant every 24 months")
    intents.mark_dispatched(corrected.intent_id)

    assert original.status == IntentStatus.superseded
    assert original.superseded_by == corrected.intent_id
    active = [i for i in intents.session.intent_set.values() if i.status != IntentStatus.superseded]
    assert active == [corrected]
    assert set(intents.session.intent_set) == {original.intent_id, corrected.intent_id}

    old_chunk = RetrievedChunk(
        chunk_id="sensor_manual#1#0", doc_id="sensor_manual", section_id="1",
        text="The old sensor requires calibration every 12 months.", score=1.0,
    )
    new_chunk = RetrievedChunk(
        chunk_id="sensor_manual#2#0", doc_id="sensor_manual", section_id="2",
        text="The replacement sensor requires calibration every 24 months.", score=1.0,
    )
    config = load_synth_config()
    config["generator"]["backend"] = "extractive"
    engine = SynthesisEngine("golden-self-correction", config=config, facets={})
    result = await engine.handle_turn(TurnInput(
        turn_id=1, utterance="Explain sensor calibration every 12 months. Actually, every 24 months.",
        t_s_end=2.0, sub_intents=active,
        evidence={original.intent_id: [old_chunk], corrected.intent_id: [new_chunk]},
    ))
    output = AnswerOutput.model_validate(result.output.model_dump())
    assert output.sub_queries == [corrected.query_nl]
    assert new_chunk.text in output.answer
    assert "12 months" not in output.answer
    assert output.citations == [new_chunk.citation_label]
    assert [claim.text for claim in output.claims] == [new_chunk.text]
    assert result.fabricated_id_count == 0
    assert output.uncertainty == ""
    required = {"retrieval_events", "sub_queries", "answer", "citations", "uncertainty"}
    assert required <= output.model_dump().keys()


@pytest.mark.asyncio
async def test_additive_case(intents):
    original, additional = candidate(12), candidate(24)
    await intents.add_intents([original])
    intents.mark_dispatched(original.intent_id)
    await intents.add_intents([additional], prefix="and also every 24 months as well")
    assert original.status == IntentStatus.dispatched
    assert additional.status == IntentStatus.pending
    assert original.superseded_by is None
    assert len(intents.session.intent_set) == 2


@pytest.mark.asyncio
async def test_no_conflict_case(intents):
    original = candidate(12)
    await intents.add_intents([original])
    intents.mark_dispatched(original.intent_id)
    duplicate = candidate(12)
    assert await intents.add_intents([duplicate]) == []
    assert duplicate.intent_id == original.intent_id
    assert intents.get_dispatched() == [original]


@pytest.mark.asyncio
async def test_marker_case_different_facet(intents):
    original = candidate(12)
    await intents.add_intents([original])
    intents.mark_dispatched(original.intent_id)
    unrelated = candidate(24)
    unrelated.facet = "inspection"
    await intents.add_intents([unrelated], prefix="Actually, explain inspection")
    assert original.status == IntentStatus.dispatched
    assert original.superseded_by is None
    assert len(intents.session.intent_set) == 2
