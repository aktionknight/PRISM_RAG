import pytest

from slrag.synth.claims import ClaimGraph
from slrag.synth.types import CitationNotAllowedError, ClaimGraphError
from tests.helpers import load_corpus


@pytest.fixture
def graph():
    corpus = load_corpus()
    g = ClaimGraph("sess_test")
    g.register_evidence([corpus["Doc_44#2#0"], corpus["Doc_44#3#0"], corpus["Doc_44#7#0"]])
    return g


def _v1(graph):
    with graph.revise() as rev:
        a = rev.add(facet="travel_reimbursement", text="Standard rule applies.", citations=["Doc_44 §2"])
        b = rev.add(
            facet="travel_reimbursement",
            text="Domestic advance bookings are reimbursed in full.",
            citations=["Doc_44 §3"],
            preconditions={"trip_type": "domestic", "booking_timing": "advance"},
        )
    return a, b


def test_first_revision_creates_version_1_with_lineage(graph):
    a, b = _v1(graph)
    assert graph.version == 1
    assert [c.claim_id for c in graph.active()] == [a, b]
    assert all(c.introduced_in_version == 1 and c.status == "active" for c in graph.active())
    lineage = graph.latest_lineage()
    assert lineage.to_dict() == {"from": 0, "to": 1, "retained": [], "superseded": [], "added": [a, b]}


def test_supersede_keeps_retained_claims_byte_for_byte(graph):
    a, b = _v1(graph)
    before = graph.get(a).model_dump_json()
    with graph.revise() as rev:
        c = rev.add(facet="travel_reimbursement", text="International trips need pre-approval.", citations=["Doc_44 §7"])
        rev.supersede(b, superseded_by=[c])
    assert graph.version == 2
    assert graph.get(a).model_dump_json() == before
    assert graph.get(b).status == "superseded"
    assert graph.meta(b).superseded_by == (c,) and graph.meta(b).superseded_in_version == 2
    assert graph.get(c).introduced_in_version == 2
    assert graph.latest_lineage().to_dict() == {"from": 1, "to": 2, "retained": [a], "superseded": [b], "added": [c]}
    assert graph.citations() == ["Doc_44 §2", "Doc_44 §7"]
    assert graph.citations(version=1) == ["Doc_44 §2", "Doc_44 §3"]
    assert [x.claim_id for x in graph.snapshot(1)] == [a, b]


def test_fabricated_citation_cannot_enter_graph(graph):
    rev = graph.revise()
    with pytest.raises(CitationNotAllowedError):
        rev.add(facet="x", text="Made up.", citations=["Doc_99 §1"])
    with pytest.raises(CitationNotAllowedError):
        rev.add(facet="x", text="Uncited.", citations=[])
    rev.abort()
    assert graph.version == 0 and len(graph) == 0


def test_empty_revision_does_not_bump_version(graph):
    _v1(graph)
    with graph.revise() as rev:
        pass
    assert rev.lineage is None and graph.version == 1 and len(graph.lineage) == 1


def test_exception_inside_revision_aborts_atomically(graph):
    with pytest.raises(RuntimeError):
        with graph.revise() as rev:
            rev.add(facet="travel_reimbursement", text="Partial.", citations=["Doc_44 §2"])
            raise RuntimeError("boom")
    assert graph.version == 0 and len(graph) == 0
    graph.revise().abort()  # a fresh revision can be opened again


def test_single_open_revision_and_illegal_supersede(graph):
    a, _ = _v1(graph)
    rev = graph.revise()
    with pytest.raises(ClaimGraphError):
        graph.revise()
    with pytest.raises(ClaimGraphError):
        rev.supersede("c404")
    rev.supersede(a)
    rev.commit()
    with graph.revise() as rev2:
        with pytest.raises(ClaimGraphError):
            rev2.supersede(a)


def test_returned_claims_are_copies(graph):
    a, _ = _v1(graph)
    leaked = graph.get(a)
    leaked.text = "mutated"
    leaked.citations.append("Doc_99 §1")
    assert graph.get(a).text == "Standard rule applies."
    assert graph.get(a).citations == ["Doc_44 §2"]


def test_destroy_is_ephemeral_session_end(graph):
    _v1(graph)
    graph.destroy()
    assert graph.version == 0 and len(graph) == 0 and not graph.known_labels() and not graph.lineage


def test_sessions_are_isolated():
    corpus = load_corpus()
    g1, g2 = ClaimGraph("s1"), ClaimGraph("s2")
    g1.register_evidence([corpus["Doc_12#2#0"]])
    with g1.revise() as rev:
        rev.add(facet="venue_capacity", text="Venue A holds up to 40 people.", citations=["Doc_12 §2"])
    assert len(g2) == 0 and not g2.known_labels()
    with pytest.raises(CitationNotAllowedError):
        with g2.revise() as rev:
            rev.add(facet="venue_capacity", text="Venue A holds up to 40 people.", citations=["Doc_12 §2"])
