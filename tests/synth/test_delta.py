import pytest

from slrag.core.citations import label_for_chunk
from slrag.core.schemas import ControllerDecision, SubIntent
from slrag.synth.claims import ClaimGraph
from slrag.synth.config import load_synth_config
from slrag.synth.constraints import values_of
from slrag.synth.delta import DeltaEngine, analyze_impact, merge_constraints
from slrag.synth.types import ConstraintDelta, DraftClaim, VerificationResult
from tests.helpers import FixtureRetriever, load_corpus, scenario_turns, turn_decisions, turn_evidence, turn_sub_intents

CORPUS = load_corpus()


@pytest.fixture(scope="module")
def engine():
    return DeltaEngine()


def _build_v1(engine, graph, facet_chunks, session):
    """One claim per chunk with its full text; preconditions derived like the generator would."""
    graph.register_evidence(chunk for _, chunk in facet_chunks)
    with graph.revise() as rev:
        ids = [
            rev.add(
                facet=facet,
                text=chunk.text,
                citations=[label_for_chunk(chunk)],
                preconditions=engine.extractor.derive_preconditions(chunk.text, facet, session),
                supporting_chunk_ids=[chunk.chunk_id],
            )
            for facet, chunk in facet_chunks
        ]
    return ids


def _results(chunks_by_intent, facets):
    """Hand-built committed VerificationResults: one verbatim sentence per delta chunk."""
    out = []
    for seq, (intent_id, chunk) in enumerate(chunks_by_intent):
        label = label_for_chunk(chunk)
        draft = DraftClaim(seq=seq, facet=facets[intent_id], text=chunk.text, citations=(label,), intent_id=intent_id)
        out.append(VerificationResult(draft=draft, ok=True, text=chunk.text, citations=(label,),
                                      supporting_chunk_ids=(chunk.chunk_id,)))
    return out


@pytest.fixture
def example2(engine):
    turn1, turn2 = scenario_turns("example2_refinement")
    facet_of = {s.intent_id: s.facet for s in turn_sub_intents(turn1)}
    facet_chunks = [(facet_of[i], chunk) for i, chunks in turn_evidence(turn1).items() for chunk in chunks]
    session = dict(engine.extractor.extract(turn1["utterance"]).slots)
    graph = ClaimGraph("sess_ex2")
    ids = _build_v1(engine, graph, facet_chunks, session)
    return graph, ids, session, turn1, turn2


@pytest.fixture
def example1_graph(engine):
    """Example-1-like V1: venue capacity (Doc_12 §2), cancellation (Doc_31 §4), catering (Doc_09 §1)."""
    (turn1,) = scenario_turns("example1_multi_intent")
    session = dict(engine.extractor.extract(turn1["utterance"]).slots)
    graph = ClaimGraph("sess_ex1")
    graph.register_evidence([CORPUS["Doc_12#2#0"], CORPUS["Doc_31#4#0"], CORPUS["Doc_09#1#0"]])
    with graph.revise() as rev:
        for facet, text, label in [
            ("venue_capacity", "Venue A holds up to 40 people.", "Doc_12 §2"),
            ("venue_capacity", "Venue B seats up to 60 people and includes a breakout room.", "Doc_12 §2"),
            ("cancellation_terms", "Cancellations made more than 14 days before the event receive a full refund.", "Doc_31 §4"),
            ("catering_options", "Venue B offers on-site catering for groups of up to 80 guests.", "Doc_09 §1"),
        ]:
            rev.add(facet=facet, text=text, citations=[label],
                    preconditions=engine.extractor.derive_preconditions(text, facet, session))
    return graph, session


# -- Example 2 (golden refinement) ---------------------------------------------------
def test_v1_preconditions_scope_only_the_domestic_advance_claim(engine, example2):
    """Scopes are read off each claim's own grammar ("Domestic trips booked in advance ...")."""
    graph, ids, session, _, _ = example2
    assert session.get("trip") == "business"                     # "my business trip"
    pre = {graph.get(cid).citations[0]: graph.get(cid).preconditions for cid in ids}
    assert pre["Doc_44 §3"]["trip"] == "domestic" and "in advance" in values_of(pre["Doc_44 §3"]["book"])
    assert all("trip" not in pre[label] and "book" not in pre[label] for label in ("Doc_44 §2", "Doc_44 §5", "Doc_44 §6"))


def test_classify_example2_turn2_is_constraint_refinement(engine, example2):
    graph, _, session, _, turn2 = example2
    result = engine.classifier.classify(turn2["utterance"], graph, session_constraints=session,
                                        controller_decisions=turn_decisions(turn2))
    assert result.turn_type == turn2["expected"]["turn_type"] == "CONSTRAINT_REFINEMENT"
    assert result.reason == "constraint_delta"
    assert dict(result.delta.slots) == turn2["expected"]["constraint_delta"]
    assert result.delta.raw_text == turn2["utterance"]


def test_plan_example2_targets_affected_facet_x_new_constraint(engine, example2):
    graph, ids, session, _, turn2 = example2
    delta = engine.classifier.classify(turn2["utterance"], graph, session_constraints=session).delta
    plan = engine.plan(graph, delta, pool=graph.evidence(), turn_id=2)
    assert plan.retained == [ids[0], ids[2], ids[3]] and plan.affected == [ids[1]]
    assert [(t.facet, t.slot, t.value) for t in plan.targets] == [
        ("travel_reimbursement", "trip", "international"),
        ("travel_reimbursement", "book", "after travel"),
    ]
    assert all(t.affected_claim_ids == (ids[1],) and not t.resolved_from_pool for t in plan.targets)
    # Generic template over the user's own phrase + facet label; no hand-written query strings.
    assert [q.search_string for q in plan.queries] == turn2["expected"]["delta_search_strings"]
    assert [q.query_nl for q in plan.queries] == turn2["expected"]["sub_queries"]
    assert [q.intent_id for q in plan.queries] == ["d2_1", "d2_2"] and all(q.novel for q in plan.queries)


def test_apply_example2_reproduces_golden_refinement(engine, example2):
    graph, ids, session, turn1, turn2 = example2
    expected = turn2["expected"]
    before = {cid: graph.get(cid).model_dump_json() for cid in ids}
    delta = engine.classifier.classify(turn2["utterance"], graph, session_constraints=session).delta
    plan = engine.plan(graph, delta, pool=graph.evidence(), turn_id=2)

    retriever = FixtureRetriever(turn2["delta_evidence"])
    dispatched = [(q.intent_id, chunk) for q in plan.queries for chunk in retriever(q)]
    graph.register_evidence(chunk for _, chunk in dispatched)
    committed = _results(dispatched, {q.intent_id: q.facet for q in plan.queries})
    merged = merge_constraints(session, delta)
    lineage, report = engine.apply(graph, plan, committed, session_constraints=merged,
                                   delta_queries_issued=len(retriever.calls), latency_ms=12.5)

    # Only the targeted delta queries were issued — never a turn-1 (full-corpus) re-run.
    turn1_queries = {s.search_string for s in turn_sub_intents(turn1)}
    assert [c.search_string for c in retriever.calls] == list(turn2["delta_evidence"])
    assert not turn1_queries & {c.search_string for c in retriever.calls}

    event = report.to_event()
    assert {k: event[k] for k in expected["refinement"]} == expected["refinement"]
    assert report.citations_preserved == expected["citations_preserved"]
    assert report.citations_added == expected["citations_added"]
    assert report.pool_resolved_targets == 0 and report.latency_ms == 12.5
    assert graph.version == expected["answer_version"] == 2

    c1, c2, c3, c4 = ids
    new = list(lineage.added)
    assert lineage.to_dict() == {"from": 1, "to": 2, "retained": [c1, c3, c4], "superseded": [c2], "added": new}
    assert len(new) == 2
    assert all(graph.get(cid).model_dump_json() == before[cid] for cid in (c1, c3, c4))
    assert graph.get(c2).status == "superseded" and graph.meta(c2).superseded_by == tuple(new)
    assert [graph.get(cid).facet for cid in new] == ["travel_reimbursement", "travel_reimbursement"]
    assert "international" in values_of(graph.get(new[0]).preconditions["trip"])
    assert graph.citations() == expected["citations_preserved"] + expected["citations_added"]


def test_pool_first_resolution_skips_the_retrieval(engine, example2):
    graph, ids, session, _, turn2 = example2
    delta = engine.classifier.classify(turn2["utterance"], graph, session_constraints=session).delta
    plan = engine.plan(graph, delta, pool=[*graph.evidence(), CORPUS["Doc_44#7#0"]], turn_id=2)
    international, post_travel = plan.targets
    assert international.resolved_from_pool and not post_travel.resolved_from_pool
    assert [c.chunk_id for c in international.pool_chunks] == ["Doc_44#7#0"]
    assert engine._min_score <= international.pool_chunks[0].score <= 1.0
    assert [q.search_string for q in plan.queries] == turn2["expected"]["delta_search_strings"][1:]

    retriever = FixtureRetriever(turn2["delta_evidence"])
    dispatched = [(international.sub_intent.intent_id, international.pool_chunks[0])]
    dispatched += [(q.intent_id, chunk) for q in plan.queries for chunk in retriever(q)]
    graph.register_evidence(chunk for _, chunk in dispatched)
    committed = _results(dispatched, {t.sub_intent.intent_id: t.facet for t in plan.targets})
    _, report = engine.apply(graph, plan, committed, session_constraints=merge_constraints(session, delta),
                             delta_queries_issued=len(retriever.calls))
    assert (report.delta_queries_issued, report.pool_resolved_targets, report.claims_added) == (1, 1, 2)
    assert report.citations_added == ["Doc_44 §7", "Doc_47 §2"] and report.full_corpus_searches == 0


def test_pool_chunk_must_mention_new_value_and_not_be_cited_already(engine):
    graph = ClaimGraph("sess_pool")
    _build_v1(engine, graph, [("travel_reimbursement", CORPUS["Doc_44#3#0"]),
                              ("travel_reimbursement", CORPUS["Doc_44#7#0"])], {})
    delta = ConstraintDelta(slots={"trip": "international"})
    plan = engine.plan(graph, delta, pool=[CORPUS["Doc_44#7#0"], CORPUS["Doc_44#2#0"]], turn_id=3)
    (target,) = plan.targets
    # Doc_44 §7 is already cited by a retained claim; Doc_44 §2 never mentions "international".
    assert not target.resolved_from_pool and len(plan.queries) == 1


# -- Presentation-only (Example 3) / new intent ------------------------------------
@pytest.mark.parametrize("utterance, reason", [
    ("Can you repeat that in two bullets?", "presentation_restructure"),
    ("Shorten it to 3 bullets please.", "presentation_restructure"),
    ("Can you repeat the part about the 14 days?", "presentation_restructure"),
    ("Could you translate that?", "translation"),
    ("Make the tone of that more formal.", "tone_change"),
])
def test_presentation_only_lexical_path(engine, example1_graph, utterance, reason):
    graph, session = example1_graph
    result = engine.classifier.classify(utterance, graph, session_constraints=session)
    assert (result.turn_type, result.reason) == ("PRESENTATION_ONLY", reason)
    assert not result.delta


def test_presentation_only_via_controller_decision(engine, example1_graph):
    graph, session = example1_graph
    (turn,) = scenario_turns("example3_presentation")[1:]
    decisions = turn_decisions(turn)
    result = engine.classifier.classify(turn["utterance"], graph, session_constraints=session,
                                        controller_decisions=decisions)
    assert (result.turn_type, result.reason) == (turn["expected"]["turn_type"], turn["expected"]["suppression_reason"])
    nudge = [ControllerDecision(t_s=0.4, decision="NO_RETRIEVAL", reason="presentation_restructure", confidence=0.9)]
    assert engine.classifier.classify("Okay go on.", graph, controller_decisions=nudge).turn_type == "PRESENTATION_ONLY"


@pytest.mark.parametrize("utterance", [
    "Repeat that, and also for Mumbai",
    "Can you repeat that for 50 people?",
    "Can you list that with the parking details?",
])
def test_presentation_verb_with_new_content_is_not_presentation_only(engine, example1_graph, utterance):
    graph, session = example1_graph
    assert engine.classifier.classify(utterance, graph, session_constraints=session).turn_type != "PRESENTATION_ONLY"


def test_novel_sub_intent_on_unanswered_facet_blocks_presentation(engine, example1_graph):
    graph, session = example1_graph
    sub = SubIntent(intent_id="i9", facet="venue_pricing", query_nl="q", search_string="q", novel=True)
    result = engine.classifier.classify("Repeat that briefly.", graph, session_constraints=session, sub_intents=[sub])
    assert result.turn_type == "NEW_INTENT"


def test_new_intent_without_prior_answer_or_constraint(engine, example1_graph):
    (turn1,) = scenario_turns("example1_multi_intent")
    empty = engine.classifier.classify(turn1["utterance"], ClaimGraph("sess_new"))
    assert (empty.turn_type, empty.reason) == ("NEW_INTENT", "no_prior_answer")
    assert {k: empty.delta.slots[k] for k in ("count:person", "location")} == {"count:person": "30", "location": "pune"}

    graph, session = example1_graph
    parking = engine.classifier.classify("And what about parking options?", graph, session_constraints=session)
    assert (parking.turn_type, parking.reason) == ("NEW_INTENT", "new_intent")


def test_new_slot_the_answer_does_not_depend_on_needs_a_cue(engine, example2):
    graph, _, session, _, _ = example2
    assert engine.classifier.classify("What about venues in Mumbai?", graph, session_constraints=session).turn_type \
        == "NEW_INTENT"
    assert engine.classifier.classify("Actually, it was in Mumbai.", graph, session_constraints=session).turn_type \
        == "CONSTRAINT_REFINEMENT"


# -- Numeric refinement ---------------------------------------------------------------
def test_numeric_headcount_refinement_builds_templated_query(engine):
    graph = ClaimGraph("sess_num")
    session = {"count:person": "30"}
    (cid,) = _build_v1(engine, graph, [("venue_capacity", CORPUS["Doc_12#2#0"])], session)
    # The count comes from the session, never from the claim's own numbers ("holds up to 40 people").
    assert graph.get(cid).preconditions["count:person"] == "30"

    result = engine.classifier.classify("Actually make it 50 people", graph, session_constraints=session)
    assert result.turn_type == "CONSTRAINT_REFINEMENT" and dict(result.delta.slots) == {"count:person": "50"}
    assert analyze_impact(graph, result.delta) == ([], [cid])

    plan = engine.plan(graph, result.delta, pool=graph.evidence(), turn_id=4)
    (query,) = plan.queries
    templates = load_synth_config()["delta"]["query_templates"]
    fields = {"facet_label": "Venue capacity", "value_phrase": "50 people"}
    assert (query.intent_id, query.facet) == ("d4_1", "venue_capacity")
    assert query.query_nl == templates["query_nl"].format(**fields)
    assert query.search_string == templates["search_string"].format(**fields)

    # The claim's own text states the old count ("seats 30 attendees"): superseded even without a replacement.
    lineage, report = engine.apply(graph, plan, [], session_constraints=merge_constraints(session, result.delta),
                                   delta_queries_issued=1)
    assert lineage.superseded == (cid,) and lineage.added == () and graph.meta(cid).superseded_by == ()
    assert (report.claims_retained, report.claims_superseded, report.claims_added) == (0, 1, 0)


# -- Extraction / preconditions ----------------------------------------------------
def test_derive_preconditions_reads_the_claim_and_inherits_only_counts(engine):
    derive = engine.extractor.derive_preconditions
    venue = "Venue A holds up to 40 people."
    assert derive(venue, "venue_capacity", {}) == {}                                   # its own 40 is a fact
    assert derive(venue, "venue_capacity", {"count:person": "30"}) == {"count:person": "30"}
    assert derive(venue, "venue_capacity", {"location": "pune", "trip": "business"}) == {}  # only counts inherit
    assert derive("Refunds are processed within 10 business days.", "x", {"count:person": "30"}) \
        .get("count:person") is None                                                  # no person noun
    scope = derive("Domestic trips booked in advance.", "travel_reimbursement", {"trip": "international"})
    assert scope["trip"] == "domestic" and "in advance" in values_of(scope["book"])


def test_extract_slots_restriction_and_merge(engine):
    text = "It was booked after travel, for 40 people in Bangalore."
    slots = dict(engine.extractor.extract(text).slots)
    assert slots["count:person"] == "40" and slots["location"] == "bangalore" and slots["book"] == "after travel"
    assert dict(engine.extractor.extract(text, slots=["count:person"]).slots) == {"count:person": "40"}
    delta = ConstraintDelta(slots={"count:person": "50"})
    assert merge_constraints({"count:person": "30", "location": "pune"}, delta) == {"count:person": "50",
                                                                                    "location": "pune"}
    assert DeltaEngine.merge_constraints is merge_constraints


def test_additive_target_when_no_claim_conflicts(engine):
    """V1 held only the general rule: a new constraint still fetches its specific rule, superseding nothing.
    The claim says "travel", the user says "trip": WordNet relates them (trip -> journey -> travel)."""
    graph = ClaimGraph("sess_additive")
    (c1,) = _build_v1(engine, graph, [("travel_reimbursement", CORPUS["Doc_44#2#0"])], {})
    classification = engine.classifier.classify("The trip was international.", graph, session_constraints={})
    assert classification.turn_type == "CONSTRAINT_REFINEMENT"
    plan = engine.plan(graph, classification.delta, pool=graph.evidence(), turn_id=2)
    assert plan.retained == [c1] and plan.affected == []
    (target,) = plan.targets
    assert target.affected_claim_ids == () and target.facet == "travel_reimbursement"
    assert [q.search_string for q in plan.queries] == ["international trip Travel reimbursement"]

    chunk = CORPUS["Doc_44#7#0"]
    graph.register_evidence([chunk])
    committed = _results([(target.sub_intent.intent_id, chunk)], {target.sub_intent.intent_id: target.facet})
    lineage, report = engine.apply(graph, plan, committed,
                                   session_constraints=merge_constraints({}, classification.delta),
                                   delta_queries_issued=1)
    assert (report.claims_retained, report.claims_superseded, report.claims_added) == (1, 0, 1)
    assert lineage.retained == (c1,) and graph.version == 2


def test_additive_targets_can_be_disabled_for_ablation():
    config = load_synth_config()
    config["delta"]["additive_targets"] = False
    engine = DeltaEngine(config)
    graph = ClaimGraph("sess_no_additive")
    _build_v1(engine, graph, [("travel_reimbursement", CORPUS["Doc_44#2#0"])], {})
    delta = ConstraintDelta(slots={"trip": "international"})
    assert engine.plan(graph, delta, pool=graph.evidence()).targets == []


# -- Audit W-8: mixed turns + self-correction ------------------------------------------
@pytest.mark.parametrize("utterance", [
    "Make it 40 people, and is AV equipment included?",
    "Make it 40 people - what about parking?",
])
def test_refinement_with_a_new_question_is_mixed(engine, example1_graph, utterance):
    graph, session = example1_graph
    result = engine.classifier.classify(utterance, graph, session_constraints=session)
    assert result.turn_type == "CONSTRAINT_REFINEMENT" and result.mixed
    assert dict(result.delta.slots) == {"count:person": "40"}
    assert result.needs_upstream_retrieval                       # the new question goes through Components 2-3


@pytest.mark.parametrize("utterance", [
    "Actually make it 40 people.",
    "Actually it's 40 people, does that change anything?",
    "Can you make it for 40 people?",
])
def test_pure_refinement_is_not_mixed(engine, example1_graph, utterance):
    graph, session = example1_graph
    result = engine.classifier.classify(utterance, graph, session_constraints=session)
    assert result.turn_type == "CONSTRAINT_REFINEMENT" and not result.mixed
    assert not result.needs_upstream_retrieval


def test_novel_sub_intent_on_an_unanswered_facet_makes_a_refinement_mixed(engine, example1_graph):
    graph, session = example1_graph
    novel = SubIntent(intent_id="i9", facet="logistics", query_nl="parking", search_string="parking", novel=True)
    old = SubIntent(intent_id="i8", facet="venue_capacity", query_nl="capacity", search_string="capacity", novel=True)
    assert engine.classifier.classify("Make it 40 people.", graph, session_constraints=session,
                                      sub_intents=[novel]).mixed
    assert not engine.classifier.classify("Make it 40 people.", graph, session_constraints=session,
                                          sub_intents=[old]).mixed


def test_unreplaced_session_scoped_claims_are_kept(engine, example1_graph):
    """Self-correction 30 -> 40: a claim that only inherited headcount=30 is not dropped when its query finds nothing."""
    graph, session = example1_graph
    catering = next(c for c in graph.active() if c.facet == "catering_options")
    delta = ConstraintDelta(slots={"count:person": "40"})
    assert catering.preconditions.get("count:person") == "30" and not engine.content_scoped(catering, delta)
    plan = engine.plan(graph, delta, pool=(), turn_id=2)
    assert catering.claim_id in plan.affected
    lineage, report = engine.apply(graph, plan, [], session_constraints=merge_constraints(session, delta),
                                   delta_queries_issued=len(plan.queries))
    assert lineage is None or catering.claim_id not in lineage.superseded
    assert graph.get(catering.claim_id).status == "active" and report.affected_kept >= 1


def test_content_scoped_claims_are_still_superseded(engine):
    graph = ClaimGraph("sess_scoped")
    (cid,) = _build_v1(engine, graph, [("venue_capacity", CORPUS["Doc_12#2#0"])], {"count:person": "30"})
    claim = graph.get(cid)
    assert engine.content_scoped(claim, ConstraintDelta(slots={"count:person": "40"}))   # text says "30 attendees"


def test_keeping_unreplaced_claims_can_be_disabled(example1_graph):
    config = load_synth_config()
    config["delta"]["keep_unreplaced_session_scoped"] = False
    strict = DeltaEngine(config)
    graph, session = example1_graph
    delta = ConstraintDelta(slots={"count:person": "40"})
    plan = strict.plan(graph, delta, pool=(), turn_id=2)
    lineage, report = strict.apply(graph, plan, [], session_constraints=merge_constraints(session, delta),
                                   delta_queries_issued=len(plan.queries))
    assert set(lineage.superseded) == set(plan.affected) and report.affected_kept == 0
