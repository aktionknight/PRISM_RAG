import copy

import pytest

from slrag.core.schemas import SubIntent
from slrag.synth.claims import ClaimGraph
from slrag.synth.config import load_synth_config
from slrag.synth.uncertainty import CoverageMatrix
from tests.helpers import load_corpus, scenario_turns, scored, turn_evidence, turn_sub_intents

EX1_CLAIMS = [
    ("i1", "venue_capacity", "Doc_12 §2", [
        "Venue A holds up to 40 people.",
        "In classroom layout Venue A seats 30 attendees.",
        "Venue B seats up to 60 people and includes a breakout room.",
    ]),
    ("i2", "cancellation_terms", "Doc_31 §4", [
        "Cancellations made more than 14 days before the event receive a full refund.",
        "Cancellations made within 14 days of the event forfeit the 25% booking deposit.",
    ]),
    ("i3", "catering_options", "Doc_09 §1", [
        "Venue B offers on-site catering for groups of up to 80 guests.",
        "External caterers must be registered with the venue at least 7 days before the event.",
    ]),
]
CATERING_GAP = "Catering accommodation policies for Venue A could not be verified from the retrieved corpus."
CANCEL = SubIntent(intent_id="i2", facet="cancellation_terms", query_nl="cancellation terms",
                   search_string="cancellation policy", novel=True)


@pytest.fixture(scope="module")
def matrix():
    return CoverageMatrix()


@pytest.fixture
def ex1_turn():
    return scenario_turns("example1_multi_intent")[0]


def _graph(rows, *, with_intents=True):
    graph = ClaimGraph("sess_cov")
    graph.register_evidence(load_corpus().values())
    with graph.revise() as rev:
        for intent_id, facet, label, texts in rows:
            for text in texts:
                rev.add(facet=facet, text=text, citations=[label], intent_id=intent_id if with_intents else None)
    return graph


def _claim_intents(graph):
    return {c.claim_id: graph.meta(c.claim_id).intent_id for c in graph.active() if graph.meta(c.claim_id).intent_id}


def test_golden_example1_uncertainty_sentence(matrix, ex1_turn):
    graph = _graph(EX1_CLAIMS)
    rows = matrix.build(turn_sub_intents(ex1_turn), turn_evidence(ex1_turn), graph.active(),
                        claim_intents=_claim_intents(graph))
    assert [r.state for r in rows] == ["covered", "covered", "partial"]
    assert [r.best_score for r in rows] == [0.91, 0.84, 0.66]
    assert rows[2].missing_entities == ("Venue A",)
    assert matrix.uncertainty_text(rows) == CATERING_GAP == ex1_turn["expected"]["uncertainty"]
    assert matrix.clarifications(rows) == []


def test_unmapped_claims_match_intents_by_facet(matrix, ex1_turn):
    graph = _graph(EX1_CLAIMS, with_intents=False)
    rows = matrix.build(turn_sub_intents(ex1_turn), turn_evidence(ex1_turn), graph.active())
    assert [len(r.claim_ids) for r in rows] == [3, 2, 2]
    assert matrix.uncertainty_text(rows) == CATERING_GAP


def test_intent_without_evidence_is_uncovered_never_dropped(matrix, ex1_turn):
    graph = _graph(EX1_CLAIMS)
    pricing = SubIntent(intent_id="i4", facet="venue_pricing", query_nl="venue pricing",
                        search_string="venue price", novel=True)
    rows = matrix.build(turn_sub_intents(ex1_turn) + [pricing], turn_evidence(ex1_turn), graph.active(),
                        claim_intents=_claim_intents(graph))
    assert rows[3].state == "uncovered" and rows[3].best_score is None and rows[3].claim_ids == ()
    assert rows[3].message == "Pricing details could not be verified from the retrieved corpus."
    assert matrix.uncertainty_text(rows) == f"{CATERING_GAP} {rows[3].message}"
    assert all(r.message for r in rows if r.state != "covered")


@pytest.mark.parametrize("evidence", [[("Doc_09#1#0", 0.31)], [("Doc_09#1#0", 0.66)]])
def test_no_claim_below_floor_or_single_reading_is_uncovered(matrix, evidence):
    catering = SubIntent(intent_id="i3", facet="catering_options", query_nl="catering options",
                         search_string="catering", novel=True)
    rows = matrix.build([catering], {"i3": [scored(cid, s) for cid, s in evidence]}, [])
    assert rows[0].state == "uncovered" and rows[0].best_score == evidence[0][1]
    assert matrix.uncertainty_text(rows) == "Catering accommodation policies could not be verified from the retrieved corpus."


def test_bimodal_evidence_asks_for_clarification_instead_of_uncertainty(matrix):
    evidence = {"i2": [scored("Doc_31#4#0", 0.72), scored("Doc_08#1#0", 0.70)]}
    rows = matrix.build([CANCEL], evidence, [])
    assert rows[0].state == "ambiguous" and rows[0].is_clarification
    assert rows[0].message == "Could you clarify whether you mean 14 days or 7 days?"
    assert matrix.clarifications(rows) == [rows[0].message]
    assert matrix.uncertainty_text(rows) == ""


@pytest.mark.parametrize("pair", [
    (("Doc_31#4#0", 0.84), ("Doc_08#1#0", 0.60)),   # scores not close
    (("Doc_31#4#0", 0.72), ("Doc_31#5#0", 0.70)),   # same document
    (("Doc_31#4#0", 0.35), ("Doc_08#1#0", 0.34)),   # below the coverage floor
])
def test_clarification_needs_close_scores_distinct_docs_above_floor(matrix, pair):
    rows = matrix.build([CANCEL], {"i2": [scored(cid, s) for cid, s in pair]}, [])
    assert rows[0].state == "uncovered" and not rows[0].is_clarification
    assert matrix.uncertainty_text(rows) == "Cancellation and refund terms could not be verified from the retrieved corpus."


def test_clarification_falls_back_to_labels_when_readings_share_no_frame(matrix):
    rows = matrix.build([CANCEL], {"i2": [scored("Doc_12#2#0", 0.70), scored("Doc_09#1#0", 0.69)]}, [])
    assert rows[0].message == "Could you clarify whether you mean Doc_12 §2 or Doc_09 §1?"


def test_full_coverage_gives_empty_uncertainty(matrix, ex1_turn):
    graph = _graph(EX1_CLAIMS[:2])
    rows = matrix.build(turn_sub_intents(ex1_turn)[:2], turn_evidence(ex1_turn), graph.active(),
                        claim_intents=_claim_intents(graph))
    assert [r.state for r in rows] == ["covered", "covered"]
    assert all(r.message is None for r in rows)
    assert matrix.uncertainty_text(rows) == ""


def test_full_coverage_caveat_and_templates_come_from_config():
    cfg = copy.deepcopy(load_synth_config())
    cfg["uncertainty"]["templates"]["full_coverage_caveat"] = "Coverage is limited to the indexed corpus."
    assert CoverageMatrix(cfg).uncertainty_text([]) == "Coverage is limited to the indexed corpus."
    del cfg["uncertainty"]["templates"]["uncovered"]
    with pytest.raises(ValueError, match="uncovered"):
        CoverageMatrix(cfg)


def test_to_telemetry_counts_states(matrix, ex1_turn):
    graph = _graph(EX1_CLAIMS)
    rows = matrix.build(turn_sub_intents(ex1_turn), turn_evidence(ex1_turn), graph.active(),
                        claim_intents=_claim_intents(graph))
    tele = matrix.to_telemetry(rows)
    assert tele["intents"] == 3
    assert tele["counts"] == {"covered": 2, "partial": 1, "ambiguous": 0, "uncovered": 0}
    assert tele["rows"][2]["missing_entities"] == ["Venue A"] and tele["rows"][2]["state"] == "partial"
