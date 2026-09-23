"""Claim-level contradiction gate: two verified sentences that disagree are never both asserted."""

import copy

import pytest

from slrag.core.schemas import SubIntent
from slrag.synth.config import load_synth_config
from slrag.synth.conflicts import ContradictionGate
from slrag.synth.engine import SynthesisEngine, TurnInput
from slrag.synth.types import DraftClaim, VerificationResult
from tests.helpers import scored

FULL_14 = "Cancellations made more than 14 days before the event receive a full refund."
FULL_7 = "Cancellations made more than 7 days before the event receive a full refund."
DEPOSIT = "Cancellations made within 14 days of the event forfeit the 25% booking deposit."


def _result(seq, text, label, chunk_id):
    draft = DraftClaim(seq=seq, facet="cancellation_terms", text=text, citations=(label,), intent_id="i2")
    return VerificationResult(draft=draft, ok=True, text=text, citations=(label,), supporting_chunk_ids=(chunk_id,))


@pytest.fixture
def gate():
    return ContradictionGate(load_synth_config())


def test_close_scores_retract_both_and_ask(gate):
    a, b = _result(0, FULL_14, "Doc_31 §4", "Doc_31#4#0"), _result(1, FULL_7, "Doc_08 §1", "Doc_08#1#0")
    kept, conflicts = gate.resolve([a, b], {"Doc_31#4#0": 0.84, "Doc_08#1#0": 0.82})
    assert kept == []
    (conflict,) = conflicts
    assert conflict.kept is None and conflict.question == "Could you clarify whether you mean 14 days or 7 days?"


def test_clear_winner_keeps_the_higher_ranked_claim(gate):
    a, b = _result(0, FULL_14, "Doc_31 §4", "Doc_31#4#0"), _result(1, FULL_7, "Doc_08 §1", "Doc_08#1#0")
    kept, (conflict,) = gate.resolve([a, b], {"Doc_31#4#0": 0.60, "Doc_08#1#0": 0.90})
    assert kept == [b] and conflict.kept is b and conflict.dropped == (a,) and conflict.question is None


@pytest.mark.parametrize("other, label, chunk_id", [
    (DEPOSIT, "Doc_08 §1", "Doc_08#1#0"),                      # different statement: no shared frame
    (FULL_7, "Doc_31 §5", "Doc_31#5#0"),                       # same document: sections, not sources, disagree
    (FULL_14, "Doc_08 §1", "Doc_08#1#0"),                      # two sources that agree
])
def test_non_conflicts_are_left_alone(gate, other, label, chunk_id):
    a, b = _result(0, FULL_14, "Doc_31 §4", "Doc_31#4#0"), _result(1, other, label, chunk_id)
    kept, conflicts = gate.resolve([a, b], {"Doc_31#4#0": 0.84, chunk_id: 0.82})
    assert kept == [a, b] and conflicts == []


def test_opposite_polarity_is_a_conflict(gate):
    a = _result(0, "Card statements alone are accepted as receipts.", "Doc_1 §1", "Doc_1#1#0")
    b = _result(1, "Card statements alone are not accepted as receipts.", "Doc_2 §1", "Doc_2#1#0")
    assert gate.conflicting(a, b)


def test_gate_can_be_disabled():
    config = copy.deepcopy(load_synth_config())
    config["conflicts"]["enabled"] = False
    a, b = _result(0, FULL_14, "Doc_31 §4", "Doc_31#4#0"), _result(1, FULL_7, "Doc_08 §1", "Doc_08#1#0")
    assert ContradictionGate(config).resolve([a, b], {}) == ([a, b], [])


async def test_engine_retracts_contradicting_sentences_and_asks():
    cancel = SubIntent(intent_id="i2", facet="cancellation_terms", query_nl="cancellation terms and refund policies",
                       search_string="cancellation policy", novel=True)
    engine = SynthesisEngine("sess_conflict")
    result = await engine.handle_turn(TurnInput(
        turn_id=1, utterance="What are the cancellation terms?", t_s_end=1.0, sub_intents=[cancel],
        evidence={"i2": [scored("Doc_31#4#0", 0.84), scored("Doc_08#1#0", 0.82)]}))

    texts = [c["text"] for c in result.extensions["claims"]]
    assert FULL_14 not in texts and FULL_7 not in texts and DEPOSIT in texts
    assert result.output.uncertainty == "Could you clarify whether you mean 14 days or 7 days?"
    assert result.extensions["clarification_questions"] == ["Could you clarify whether you mean 14 days or 7 days?"]
    retracted = [e for e in result.stream_events if e.kind == "retracted"]
    assert {e.text for e in retracted} == {FULL_14, FULL_7}
    assert all("contradiction" in e.verification.reasons for e in retracted)
    conflicts = next(e for e in result.telemetry if e.component == "synthesis.conflicts")
    assert conflicts.payload["pairs"] == 1 and result.fabricated_id_count == 0
