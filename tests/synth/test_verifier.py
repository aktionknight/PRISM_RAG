"""Verifier (roadmap 4.7 / 4.8): S-6 allowlist backstop + S-5 two-pass streaming."""

import asyncio
import copy
import math
import sys
import time
import types

import pytest

from slrag.core.schemas import RetrievedChunk
from slrag.synth.config import load_synth_config
from slrag.synth.types import DraftClaim
from slrag.synth.verifier import (
    CitationAllowlist,
    ClaimVerifier,
    CrossEncoderNLIScorer,
    LexicalEntailmentScorer,
    TwoPassStreamer,
    copy_check,
    make_entity_extractor,
    make_scorer,
    premise_windows,
    threshold_for,
    verify_all,
)
from tests.helpers import load_corpus

VENUE_A = "Venue A holds up to 40 people."
VENUE_B = "Venue B seats up to 60 people and includes a breakout room."
PRICE_A = "Venue A charges INR 45,000 per day."
REFUNDS = "Approved refunds are processed within 10 business days to the original payment method."


def _config(**verifier):
    cfg = copy.deepcopy(load_synth_config())
    cfg["verifier"].update(verifier)
    return cfg


def _draft(text, *citations, seq=0, facet="venue_capacity"):
    return DraftClaim(seq=seq, facet=facet, text=text, citations=tuple(citations), intent_id=f"i{seq}")


def scored_chunk(chunk_id, text, score=0.9):
    doc_id, section_id, _ = chunk_id.split("#")
    return RetrievedChunk(chunk_id=chunk_id, doc_id=doc_id, section_id=section_id, text=text, score=score)


@pytest.fixture
def allowlist():
    return CitationAllowlist.from_chunks(load_corpus().values())


@pytest.fixture
def verifier(allowlist):
    return ClaimVerifier(allowlist, config=load_synth_config())


class SlowScorer:
    """Lexical scorer that blocks ~delay s per call and logs when each call starts."""

    def __init__(self, delay, log=None):
        self.delay, self.log, self.inner = delay, log if log is not None else [], LexicalEntailmentScorer()

    def score(self, premise, hypothesis):
        self.log.append(("score", hypothesis))
        time.sleep(self.delay)
        return self.inner.score(premise, hypothesis)


# -- S-6 allowlist -------------------------------------------------------------
def test_allowlist_membership_and_normalisation(allowlist):
    corpus = load_corpus()
    assert "Doc_12 §2" in allowlist.labels
    assert "Doc_12  §2" in allowlist and "Doc_12 §2" in allowlist
    assert "Doc_99 §1" not in allowlist and "Source §3" not in allowlist and "garbage" not in allowlist
    assert allowlist.enum() == sorted(allowlist.labels)
    assert allowlist.chunks_for("Doc_12  §2") == [corpus["Doc_12#2#0"]]
    assert allowlist.chunks_for("Doc_99 §1") == []
    dup = CitationAllowlist.from_chunks([corpus["Doc_12#2#0"], corpus["Doc_12#2#0"], corpus["Doc_31#4#0"]])
    assert [c.chunk_id for c in dup.chunks] == ["Doc_12#2#0", "Doc_31#4#0"]
    assert dup.labels == frozenset({"Doc_12 §2", "Doc_31 §4"})


def test_strip_markers_removes_and_classifies_every_marker(allowlist):
    text = "Venue A holds up to 40 people [Doc_12 §2; Doc_99 §1]. Refunds apply [Source §3] [Doc_12  §2]."
    clean, allowed, fabricated = allowlist.strip_markers(text)
    assert clean == "Venue A holds up to 40 people. Refunds apply."
    assert allowed == ["Doc_12 §2"]
    assert fabricated == ["Doc_99 §1", "Source §3"]
    assert allowlist.strip_markers("  No markers here. ") == ("No markers here.", [], [])


def test_filter_keeps_canonical_labels_in_order_and_dedupes(allowlist):
    kept, fabricated = allowlist.filter(
        ["Doc_31 §4", "Doc_12  §2", "Doc_99 §1", "Doc_12 §2", "Doc_99 §1", "garbage", ""]
    )
    assert kept == ("Doc_31 §4", "Doc_12 §2")
    assert fabricated == ("Doc_99 §1", "garbage")


def test_copy_check_numerals_and_proper_nouns():
    corpus = load_corpus()
    prices = [corpus["Doc_12#3#0"].text]
    assert copy_check(PRICE_A, prices) == ()
    assert copy_check("Venue A charges INR 50,000 per day.", prices) == ("50000",)
    assert copy_check("Venue C charges USD 45,000 per day.", prices) == ("Venue C", "USD")
    # present in ANY premise is enough
    assert copy_check("Venue B offers catering for 80 guests and seats 60.",
                      [corpus["Doc_09#1#0"].text, corpus["Doc_12#2#0"].text]) == ()


# -- ClaimVerifier ------------------------------------------------------------
def test_verbatim_sentence_with_valid_citation_commits(verifier):
    result = verifier.verify(_draft(VENUE_A, "Doc_12 §2"))
    assert result.ok and not result.reattributed
    assert result.entailment == pytest.approx(1.0)
    assert result.citations == ("Doc_12 §2",)
    assert result.fabricated == () and result.missing_values == () and result.reasons == ()
    assert result.supporting_chunk_ids == ("Doc_12#2#0",)
    assert result.text == VENUE_A and result.latency_ms >= 0.0


def test_fabricated_citation_is_stripped_and_sentence_demoted_by_default(verifier):
    """A §4.4: anything outside the allowlist is stripped and its sentence demoted to uncertainty."""
    result = verifier.verify(_draft(VENUE_A, "Doc_12 §2", "Doc_99 §1"))
    assert not result.ok and not result.reattributed
    assert result.reasons[0] == "fabricated_citation"
    assert result.fabricated == ("Doc_99 §1",) and "Doc_99 §1" not in result.citations
    assert result.supporting_chunk_ids == ()
    assert verifier.fabricated_ids_stripped == 1


def test_fabricated_citation_is_reattributed_when_demotion_disabled(allowlist):
    lenient = ClaimVerifier(allowlist, config=_config(demote_on_fabricated=False))
    result = lenient.verify(_draft(VENUE_A, "Doc_99 §1"))
    assert result.ok and result.reattributed
    assert result.citations == ("Doc_12 §2",)
    assert result.fabricated == ("Doc_99 §1",)
    assert "no_valid_citation" in result.reasons and "reattributed" in result.reasons
    assert result.supporting_chunk_ids == ("Doc_12#2#0",)
    assert lenient.fabricated_ids_stripped == 1


def test_in_text_fabricated_marker_is_stripped_from_text(verifier, allowlist):
    draft = _draft("Venue A holds up to 40 people [Doc_99 §1].", "Doc_99 §1")
    result = verifier.verify(draft)
    assert result.text == VENUE_A and not result.ok
    assert result.citations == () and result.fabricated == ("Doc_99 §1",)
    assert verifier.fabricated_ids_stripped == 1
    lenient = ClaimVerifier(allowlist, config=_config(demote_on_fabricated=False)).verify(draft)
    assert lenient.ok and lenient.text == VENUE_A and lenient.citations == ("Doc_12 §2",)


def test_in_text_valid_marker_counts_as_citation(verifier):
    result = verifier.verify(_draft("Venue A holds up to 40 people [Doc_12 §2]."))
    assert result.ok and not result.reattributed
    assert result.text == VENUE_A and result.citations == ("Doc_12 §2",)


def test_wrong_numeral_fails_copy_check_and_is_not_rescued(verifier):
    result = verifier.verify(_draft("Venue A holds up to 400 people.", "Doc_12 §2"))
    assert not result.ok and not result.reattributed
    assert result.missing_values == ("400",)
    assert any("400" in reason for reason in result.reasons)
    assert "copy_check_failed:400" in result.reasons
    assert result.supporting_chunk_ids == ()


def test_wrong_entity_fails_copy_check(verifier):
    result = verifier.verify(_draft("Venue C holds up to 40 people.", "Doc_12 §2"))
    assert not result.ok
    assert "Venue C" in result.missing_values
    assert any(reason.startswith("copy_check_failed") for reason in result.reasons)


RECEIPTS = "All reimbursement claims must include itemised receipts; card statements alone are not accepted."


@pytest.mark.parametrize("text, citation", [
    ("Card statements alone are accepted.", "Doc_44 §5"),          # drops the chunk's "not"
    ("Venue A does not hold up to 40 people.", "Doc_12 §2"),         # adds a "not" the chunk lacks
    ("Venue A never holds up to 40 people.", "Doc_12 §2"),
])
def test_polarity_flip_is_retracted_despite_full_lexical_overlap(verifier, text, citation):
    """Audit W-4: the lexical scorer drops negations as stopwords, so these score ~1.0."""
    result = verifier.verify(_draft(text, citation))
    assert result.entailment is not None and result.entailment >= verifier.threshold
    assert not result.ok and not result.reattributed
    assert "negation_mismatch" in result.reasons
    assert result.supporting_chunk_ids == ()


@pytest.mark.parametrize("text", [
    RECEIPTS,                                                   # verbatim, negation included
    "All reimbursement claims must include itemised receipts.",  # the positive clause alone
    "Card statements alone aren't accepted.",                   # contraction keeps the polarity
])
def test_matching_polarity_commits(verifier, text):
    result = verifier.verify(_draft(text, "Doc_44 §5"))
    assert result.ok, result.reasons


def test_polarity_check_can_be_disabled(allowlist):
    lenient = ClaimVerifier(allowlist, config=_config(polarity_check=False))
    assert lenient.verify(_draft("Card statements alone are accepted.", "Doc_44 §5")).ok


def test_polarity_flip_is_not_rescued_by_reattribution():
    # Same claim text in two chunks: re-attribution must apply the polarity check too.
    chunks = [scored_chunk("Doc_1#1#0", "Deposits are not refundable."),
              scored_chunk("Doc_2#1#0", "Deposits are not refundable after booking.")]
    verifier = ClaimVerifier(CitationAllowlist.from_chunks(chunks), config=load_synth_config())
    result = verifier.verify(_draft("Deposits are refundable.", "Doc_1 §1"))
    assert not result.ok and "reattribution_failed" in result.reasons


def test_unsupported_sentence_is_retracted(verifier):
    result = verifier.verify(_draft("Parking is free for all guests.", "Doc_12 §2"))
    assert not result.ok and not result.reattributed
    assert "entailment_below_threshold" in result.reasons
    assert result.entailment is not None and result.entailment < verifier.threshold
    assert result.citations == ("Doc_12 §2",)


def test_reattribution_can_be_disabled(allowlist):
    verifier = ClaimVerifier(allowlist, config=_config(reattribute_on_failure=False, demote_on_fabricated=False))
    result = verifier.verify(_draft(VENUE_A, "Doc_99 §1"))
    assert not result.ok and result.reasons == ("no_valid_citation",)
    assert result.citations == () and result.fabricated == ("Doc_99 §1",)


def test_threshold_comes_from_config(allowlist):
    strict = ClaimVerifier(allowlist, config=_config(entailment_threshold=1.01, reattribute_on_failure=False))
    assert not strict.verify(_draft(VENUE_A, "Doc_12 §2")).ok


async def test_mixed_batch_emits_zero_fabricated_ids(verifier):
    drafts = [
        _draft(VENUE_A, "Doc_12 §2", seq=0),
        _draft(VENUE_A, "Doc_99 §1", seq=1),
        _draft("Venue A holds up to 40 people [Doc_99 §1].", seq=2),
        _draft("Venue A holds up to 400 people.", "Doc_12 §2", seq=3),
        _draft("Venue C holds up to 40 people.", "Doc_12 §2", seq=4),
        _draft("Parking is free for all guests.", "Doc_12 §2", seq=5),
        _draft(PRICE_A, "Doc_12 §3", "Doc_77 §9", seq=6),
    ]
    events, results = await verify_all(verifier, drafts)
    committed = [label for r in results if r.ok for label in r.citations]
    assert committed and verifier.output_fabricated_count(committed) == 0
    assert verifier.output_fabricated_count(label for e in events for label in e.citations) == 0
    assert [r.ok for r in results] == [True, False, False, False, False, False, False]
    assert verifier.fabricated_ids_stripped == 3
    assert (verifier.verified, verifier.committed, verifier.retracted) == (7, 1, 6)
    assert verifier.output_fabricated_count(["Doc_99 §1", "Doc_12 §2"]) == 1


# -- TwoPassStreamer (S-5) -----------------------------------------------------
def _assert_two_pass_order(events, n):
    assert len(events) == 2 * n
    provisional = [e.seq for e in events if e.kind == "provisional"]
    final = [e for e in events if e.kind != "provisional"]
    assert sorted(provisional) == list(range(n))
    assert [e.seq for e in final] == list(range(n))           # committed/retracted in arrival order
    for seq in range(n):
        kinds = [(i, e.kind) for i, e in enumerate(events) if e.seq == seq]
        assert len(kinds) == 2 and kinds[0][1] == "provisional" and kinds[1][1] in ("committed", "retracted")
    assert all(e.verification is None for e in events if e.kind == "provisional")
    assert all(e.verification is not None for e in final)


async def test_streamer_orders_provisional_then_final_per_draft(verifier):
    drafts = [
        _draft(VENUE_A, "Doc_12 §2", seq=0),
        _draft("Venue A holds up to 400 people [Doc_99 §1].", "Doc_12 §2", seq=1),
        _draft(VENUE_B, "Doc_12 §2", seq=2),
        _draft("Parking is free for all guests.", "Doc_12 §2", seq=3),
    ]

    async def generate():
        for i, draft in enumerate(drafts):
            if i:
                await asyncio.sleep(0.02)
            yield draft

    streamer = TwoPassStreamer(verifier)
    events = [event async for event in streamer.run(generate())]
    _assert_two_pass_order(events, len(drafts))
    kinds = {e.seq: e.kind for e in events if e.kind != "provisional"}
    assert kinds == {0: "committed", 1: "retracted", 2: "committed", 3: "retracted"}
    provisional_1 = next(e for e in events if e.seq == 1 and e.kind == "provisional")
    assert provisional_1.text == "Venue A holds up to 400 people." and provisional_1.citations == ("Doc_12 §2",)
    assert [r.draft.seq for r in streamer.results] == [0, 1, 2, 3]
    assert [r.draft.seq for r in streamer.committed_results()] == [0, 2]


async def test_streamer_verifies_concurrently_with_generation(allowlist):
    log = []
    scorer = SlowScorer(0.05, log)
    verifier = ClaimVerifier(allowlist, config=load_synth_config(), scorer=scorer)
    texts = [(VENUE_A, "Doc_12 §2"), (VENUE_B, "Doc_12 §2"), (PRICE_A, "Doc_12 §3"), (REFUNDS, "Doc_31 §5")]
    drafts = [_draft(text, label, seq=i) for i, (text, label) in enumerate(texts)]
    gap = 0.03

    async def generate():
        for i, draft in enumerate(drafts):
            if i:
                await asyncio.sleep(gap)
            log.append(("yield", i))
            yield draft

    started = time.perf_counter()
    events, results = await verify_all(verifier, generate())
    elapsed = time.perf_counter() - started

    _assert_two_pass_order(events, len(drafts))
    assert all(r.ok for r in results)
    sequential = gap * (len(drafts) - 1) + scorer.delay * len(drafts)
    assert elapsed < 0.8 * sequential
    assert log.index(("score", VENUE_A)) < log.index(("yield", 1))   # N verified while N+1 generated


async def test_streamer_accepts_plain_iterable(verifier):
    drafts = [_draft(VENUE_A, "Doc_12 §2", seq=0), _draft("Venue C holds up to 40 people.", "Doc_12 §2", seq=1)]
    events, results = await verify_all(verifier, drafts)
    _assert_two_pass_order(events, 2)
    assert [r.ok for r in results] == [True, False]


async def test_streamer_cancels_pending_tasks_on_early_stop(allowlist):
    verifier = ClaimVerifier(allowlist, config=load_synth_config(), scorer=SlowScorer(0.1))
    agen = TwoPassStreamer(verifier).run([_draft(VENUE_A, "Doc_12 §2", seq=i) for i in range(3)])
    first = await agen.__anext__()
    assert first.kind == "provisional" and first.seq == 0
    await agen.aclose()
    await asyncio.sleep(0.01)
    current = asyncio.current_task()
    assert [t for t in asyncio.all_tasks() if t is not current and not t.done()] == []


# -- scorers -------------------------------------------------------------------
def test_make_scorer_defaults_to_lexical():
    scorer = make_scorer(load_synth_config())
    assert isinstance(scorer, LexicalEntailmentScorer)
    corpus = load_corpus()
    assert scorer.score(corpus["Doc_12#2#0"].text, VENUE_A) == pytest.approx(1.0)
    assert scorer.score(corpus["Doc_12#2#0"].text, "Parking is free for all guests.") == 0.0


def test_make_scorer_rejects_unknown_backend():
    with pytest.raises(ValueError):
        make_scorer(_config(entailment_backend="magic"))


def test_cross_encoder_missing_model_raises_without_importing_dependency(monkeypatch):
    monkeypatch.delitem(sys.modules, "sentence_transformers", raising=False)   # another test may have loaded it
    cfg = _config(entailment_backend="cross_encoder",
                  cross_encoder={"model_path": "models/definitely-not-baked", "labels": ["contradiction",
                                 "entailment", "neutral"], "max_length": 256})
    with pytest.raises(FileNotFoundError, match="never downloaded"):
        make_scorer(cfg)
    assert "sentence_transformers" not in sys.modules


def test_cross_encoder_softmax_follows_configured_label_order(tmp_path, monkeypatch):
    class FakeCrossEncoder:
        def __init__(self, path, **kwargs):
            self.path, self.kwargs = path, kwargs

        def predict(self, pairs, **kwargs):
            return [[0.0, 2.0, 0.0] for _ in pairs]

    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    cfg = _config(entailment_backend="cross_encoder",
                  cross_encoder={"model_path": str(tmp_path), "labels": ["neutral", "entailment", "contradiction"],
                                 "max_length": 128})
    scorer = make_scorer(cfg)
    assert isinstance(scorer, CrossEncoderNLIScorer)
    assert scorer._model.kwargs == {"max_length": 128}
    denom = math.exp(2.0) + 2.0
    assert scorer.score("p", "h") == pytest.approx(math.exp(2.0) / denom)
    assert scorer.contradiction("p", "h") == pytest.approx(1.0 / denom)
    assert scorer.score_batch([("p", "h"), ("p2", "h2")]) == pytest.approx([math.exp(2.0) / denom] * 2)


# -- Audit N-1: antonym swaps, exempt cue phrases, finer clause alignment -----------------
@pytest.mark.parametrize("text, citation", [
    ("Rejected refunds are processed within 10 business days to the original payment method.", "Doc_31 §5"),
    ("Venue B seats up to 60 people and excludes a breakout room.", "Doc_12 §2"),
    ("Itemised receipts are optional for reimbursement claims.", "Doc_44 §5"),
    ("Card statements alone are rejected, and itemised receipts are excluded from claims.", "Doc_44 §5"),
])
def test_antonym_swaps_are_retracted_despite_full_lexical_overlap(verifier, text, citation):
    result = verifier.verify(_draft(text, citation))
    assert not result.ok and "negation_mismatch" in result.reasons


def test_refund_versus_forfeit_is_retracted():
    chunk = scored_chunk("Doc_31#4#0", load_corpus()["Doc_31#4#0"].text)
    verifier = ClaimVerifier(CitationAllowlist.from_chunks([chunk]), config=load_synth_config())
    result = verifier.verify(_draft(
        "Cancellations made within 14 days of the event get the 25% booking deposit refunded.", "Doc_31 §4"))
    assert not result.ok and "negation_mismatch" in result.reasons


@pytest.mark.parametrize("text, citation", [
    ("Card statements alone are rejected.", "Doc_44 §5"),       # antonym of a negated premise: same meaning
    ("Venue B seats up to 60 people and includes a breakout room.", "Doc_12 §2"),
])
def test_antonym_that_restates_the_premise_commits(verifier, text, citation):
    result = verifier.verify(_draft(text, citation))
    assert result.ok, result.reasons


@pytest.mark.parametrize("premise, text", [
    ("Venue A offers catering and also hosts breakout sessions.",
     "Venue A not only offers catering but also hosts breakout sessions."),
    ("Venue A holds up to 40 people.", "Venue A holds no more than 40 people."),
])
def test_exempt_cue_phrases_are_not_negations(premise, text):
    verifier = ClaimVerifier(CitationAllowlist.from_chunks([scored_chunk("Doc_1#1#0", premise)]),
                             config=load_synth_config())
    result = verifier.verify(_draft(text, "Doc_1 §1"))
    assert "negation_mismatch" not in result.reasons, result.reasons


def test_comma_clause_carries_its_own_polarity():
    premise = "Venue A includes a projector, and the fee covers parking."
    verifier = ClaimVerifier(CitationAllowlist.from_chunks([scored_chunk("Doc_1#1#0", premise)]),
                             config=load_synth_config())
    result = verifier.verify(_draft("Venue A includes a projector, but the fee does not cover parking.", "Doc_1 §1"))
    assert not result.ok and "negation_mismatch" in result.reasons


def test_cross_encoder_scores_the_best_sentence_window(tmp_path, monkeypatch):
    """A claim entailed by one sentence of a multi-sentence chunk must not be diluted by the rest."""
    class FakeCrossEncoder:
        def __init__(self, path, **kwargs):
            self.calls = []

        def predict(self, pairs, **kwargs):
            self.calls.append([tuple(p) for p in pairs])
            return [[0.0, 4.0, 0.0] if premise == "B is 2." else [4.0, 0.0, 0.0] for premise, _ in pairs]

    fake = types.ModuleType("sentence_transformers")
    fake.CrossEncoder = FakeCrossEncoder
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)
    cfg = _config(entailment_backend="cross_encoder",
                  cross_encoder={"model_path": str(tmp_path), "labels": ["contradiction", "entailment", "neutral"],
                                 "premise_window_sentences": 1, "entailment_threshold": 0.5})
    scorer = make_scorer(cfg)
    assert scorer.score_batch([("A is 1. B is 2. C is 3.", "B is 2."), ("A is 1.", "B is 2.")]) == pytest.approx(
        [math.exp(4) / (math.exp(4) + 2), 1 / (math.exp(4) + 2)])
    assert len(scorer._model.calls) == 1                        # one predict call for every window of every pair
    assert premise_windows("A is 1. B is 2. C is 3.", 2) == [
        "A is 1. B is 2. C is 3.", "A is 1.", "B is 2.", "C is 3.", "A is 1. B is 2.", "B is 2. C is 3."]
    assert premise_windows("A is 1.", 0) == ["A is 1."]


def test_spacy_entities_extend_the_copy_check(tmp_path, monkeypatch):
    """Audit W-6: NER adds names the regex skips (a lone sentence-initial word)."""
    class Doc:
        def __init__(self, text):
            self.ents = [types.SimpleNamespace(text=w, label_="ORG") for w in text.split() if w == "Marriott"]

    fake = types.ModuleType("spacy")
    fake.load = lambda path, **kwargs: Doc
    monkeypatch.setitem(sys.modules, "spacy", fake)
    cfg = _config(entity_backend="spacy", spacy={"model_path": str(tmp_path), "labels": ["ORG"]})
    entities = make_entity_extractor(cfg)
    assert entities("Marriott holds up to 40 people.") == ["Marriott"]
    assert copy_check("Marriott holds up to 40 people.", [VENUE_A]) == ()             # regex alone misses it
    assert copy_check("Marriott holds up to 40 people.", [VENUE_A], entities) == ("Marriott",)
    verifier = ClaimVerifier(CitationAllowlist.from_chunks([scored_chunk("Doc_12#2#0", VENUE_A)]), config=cfg)
    result = verifier.verify(_draft("Marriott holds up to 40 people.", "Doc_12 §2"))
    assert not result.ok and "Marriott" in result.missing_values


def test_spacy_backend_needs_a_baked_model():
    cfg = _config(entity_backend="spacy", spacy={"model_path": "models/definitely-not-baked"})
    with pytest.raises(FileNotFoundError, match="never downloaded|bake_nli_model"):
        make_entity_extractor(cfg)
    with pytest.raises(ValueError):
        make_entity_extractor(_config(entity_backend="magic"))


def test_threshold_is_per_backend():
    assert threshold_for(_config(entailment_backend="lexical", entailment_threshold=0.6)) == 0.6
    nli = _config(entailment_backend="cross_encoder", entailment_threshold=0.6,
                  cross_encoder={"entailment_threshold": 0.5})
    assert threshold_for(nli) == 0.5
    assert threshold_for(_config(entailment_backend="cross_encoder", entailment_threshold=0.6,
                                 cross_encoder={})) == 0.6
