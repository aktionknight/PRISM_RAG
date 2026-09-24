"""Turn classifier + delta engine (S-4, roadmap 4.3 / 4.4).

Refinement is a ``ClaimGraph`` mutation, never string editing (Rule 3)::

    classify turn -> extract constraint delta -> impact analysis (retain | affect)
      -> pool-first resolution -> targeted queries (affected facet x new constraint)
      -> merge (one Revision: add new claims, supersede affected) -> version++

Deterministic and side-effect free: no LLM calls, no retrieval calls (HC-5) — the
caller dispatches ``DeltaPlan.queries`` through Component 3. No module-level
mutable state (HC-4). Constraints are read off a dependency parse
(``synth/constraints.py``), never off a list of domain slots, so the engine works on any
corpus; templates, cues and thresholds come from ``config/synth.yaml`` (HC-2), and
``config/facets.yaml`` is only used for display labels (unknown facets are fine).

Mixed turns (audit W-8): a refinement whose question clause asks about content
the answer does not carry ("make it 40 people, and is AV equipment included?") is
still a CONSTRAINT_REFINEMENT, flagged ``mixed`` so the harness runs Components 2-3
for the new question while Component 4 applies the constraint as a delta.

Known limitations (D3 edge cases):
  * additive phrasing ("also for Mumbai") is treated as a replacement of the slot;
  * a lexical translate request naming the target language ("into Hindi") sees the
    language as a new proper noun; the controller's NO_RETRIEVAL decision covers it.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from slrag.core.citations import label_for_chunk
from slrag.core.schemas import Claim, ControllerDecision, RetrievedChunk, SubIntent
from slrag.synth.claims import ClaimGraph
from slrag.synth.config import facet_label, load_facets, load_synth_config
from slrag.synth.constraints import ConstraintExtractor, values_of
from slrag.synth.text import content_tokens, extract_numerals, extract_proper_nouns, overlap, stopwords_from, tokenize
from slrag.synth.types import (
    ConstraintDelta,
    DeltaPlan,
    DeltaTarget,
    RefinementReport,
    TurnClassification,
    VerificationResult,
    VersionLineage,
)

# Fallbacks only, used when a key is missing from config/synth.yaml.
_DEFAULT_TEMPLATES = {"query_nl": "{facet_label} for {value_phrase}", "search_string": "{value_phrase} {facet_label}"}
_DEFAULT_PRESENTATION_REASON = "presentation_restructure"


def merge_constraints(session: Mapping[str, str], delta: ConstraintDelta) -> dict[str, str]:
    """Session constraints after applying ``delta`` (delta values win)."""
    return {**{k: str(v) for k, v in session.items()}, **delta.slots}


def _conflicting_slots(preconditions: Mapping[str, Any], delta: ConstraintDelta) -> list[str]:
    """Delta keys the claim is scoped to with *other* values (absent key = general claim)."""
    return [slot for slot, value in delta.slots.items()
            if slot in preconditions and value not in values_of(preconditions[slot])]


def analyze_impact(graph: ClaimGraph, delta: ConstraintDelta) -> tuple[list[str], list[str]]:
    """(retained ids, affected ids) over active claims in graph order (S-4 step 3)."""
    retained: list[str] = []
    affected: list[str] = []
    for claim in graph.active():
        (affected if _conflicting_slots(claim.preconditions, delta) else retained).append(claim.claim_id)
    return retained, affected


class TurnClassifier:
    """NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY (S-4 step 1, Example 3).

    A refinement that also asks a new question is flagged ``mixed`` (audit W-8).
    """

    def __init__(
        self,
        config: dict | None = None,
        facets: dict | None = None,
        *,
        extractor: ConstraintExtractor | None = None,
    ) -> None:
        self.config = load_synth_config() if config is None else config
        self.facets = load_facets() if facets is None else facets
        self.extractor = extractor or ConstraintExtractor(self.config, self.facets)
        pres = self.config.get("presentation", {}) or {}
        verbs = [str(v) for v in pres.get("verbs", ())]
        self._verbs = frozenset(tokenize(" ".join(verbs)))
        reasons = dict(pres.get("reasons", {}) or {})
        self._default_reason = str(reasons.pop("default", _DEFAULT_PRESENTATION_REASON))
        self._reason_keys = [(frozenset(tokenize(str(key))), str(reason)) for key, reason in reasons.items()]
        self._presentation_reasons = frozenset([self._default_reason, *(r for _, r in self._reason_keys)])
        self._neutral = frozenset(
            tokenize(" ".join([*stopwords_from(self.config), *verbs, *map(str, pres.get("number_words", {}) or {})]))
        )
        # "3 bullets" is a format count, not a content numeral.
        self._format_count_re = (
            re.compile(r"\b\d+\s+(?:" + "|".join(map(re.escape, verbs)) + r")\b", re.IGNORECASE) if verbs else None
        )
        delta_cfg = self.config.get("delta", {}) or {}
        self._cues = tuple(re.compile(p, re.IGNORECASE) for p in delta_cfg.get("refinement_cues", ()))
        question = [str(p) for p in delta_cfg.get("question_cues", ())]
        self._question_re = re.compile("|".join(question), re.IGNORECASE) if question else None
        self._clause_re = re.compile("|".join(map(str, delta_cfg.get("question_clause_splitters", ()) or [r"(?!)"])),
                                     re.IGNORECASE)
        self._follow_up_neutral = frozenset(tokenize(" ".join(map(str, delta_cfg.get("follow_up_neutral", ()) or ()))))

    def classify(
        self,
        utterance: str,
        graph: ClaimGraph,
        *,
        session_constraints: Mapping[str, str] | None = None,
        controller_decisions: Sequence[ControllerDecision] = (),
        sub_intents: Sequence[SubIntent] = (),
    ) -> TurnClassification:
        session = {k: str(v) for k, v in (session_constraints or {}).items()}
        active = graph.active()
        extracted = self._user_constraints(utterance, active, session)
        if not active:
            return TurnClassification("NEW_INTENT", "no_prior_answer", extracted)

        changed = {slot: value for slot, value in extracted.slots.items() if session.get(slot) != value}
        reason = self._presentation_reason(utterance, active, changed, controller_decisions, sub_intents)
        if reason is not None:
            return TurnClassification("PRESENTATION_ONLY", reason, ConstraintDelta(raw_text=utterance))

        # Only a constraint the answer depends on is a delta; a cue ("actually", "make it")
        # makes any changed constraint one.
        relevant = {slot: value for slot, value in changed.items() if self._depends_on(active, slot, session)}
        if not relevant and changed and any(c.search(utterance) for c in self._cues):
            relevant = dict(changed)
        phrases = {slot: extracted.phrases.get(slot, "") for slot in (relevant or changed)}
        delta = ConstraintDelta(slots=relevant or changed, raw_text=utterance, phrases=phrases)
        if relevant:
            if self.asks_new_question(utterance, active, sub_intents, delta):
                return TurnClassification("CONSTRAINT_REFINEMENT", "constraint_delta_with_new_question", delta,
                                          mixed=True)
            return TurnClassification("CONSTRAINT_REFINEMENT", "constraint_delta", delta)
        return TurnClassification("NEW_INTENT", "new_intent", delta)

    def _user_constraints(self, utterance: str, active: Sequence[Claim], session: Mapping[str, str]) -> ConstraintDelta:
        """Parsed constraints minus two kinds of non-constraints: phrases made of presentation
        vocabulary ("repeat that in two bullets") and counts that only point at a number the
        answer already states ("the part about the 14 days")."""
        parsed = self.extractor.extract(utterance)
        claim_numerals = set(extract_numerals(" ".join(c.text for c in active)))
        slots, phrases = {}, {}
        for key, value in parsed.slots.items():
            head = set(tokenize(key.split(":", 1)[-1]))
            words = (head | set(tokenize(value))) - {t for t in tokenize(value) if t[0].isdigit()}
            if (head and head <= self._neutral) or (words and words <= self._neutral):
                continue
            if self.extractor.is_numeric(key) and key not in session and value in claim_numerals:
                continue
            slots[key], phrases[key] = value, parsed.phrases.get(key, "")
        return ConstraintDelta(slots=slots, raw_text=utterance, phrases=phrases)

    def asks_new_question(self, utterance: str, active: Sequence[Claim], sub_intents: Sequence[SubIntent] = (),
                          delta: ConstraintDelta | None = None) -> bool:
        """Does a refinement turn also ask about something the answer does not cover (W-8)?

        After decomposition: a novel sub-intent on a facet the answer lacks. Before it
        (``classify()`` at utterance end): a question clause (``delta.question_cues``)
        with a content word that is not in the active claims, not part of a constraint
        phrase, not a refinement cue and not a ``delta.follow_up_neutral`` word
        ("does that change anything?" is about the constraint, not a new topic).
        """
        active_facets = {c.facet for c in active}
        if any(s.novel and s.facet not in active_facets for s in sub_intents):
            return True
        if self._question_re is None:
            return False
        known = set(tokenize(" ".join(c.text for c in active))) | self._neutral | self._follow_up_neutral
        for clause in self._clause_re.split(utterance):
            if not clause or not self._question_re.search(clause):
                continue
            for phrase in (delta.phrases.values() if delta is not None else ()):
                if phrase:
                    clause = re.sub(re.escape(phrase), " ", clause, flags=re.IGNORECASE)
            for pattern in self._cues:
                clause = pattern.sub(" ", clause)
            if any(tok not in known and not tok[0].isdigit() and len(tok) > 1 for tok in tokenize(clause)):
                return True
        return False

    def new_content_anchors(
        self,
        utterance: str,
        active: Sequence[Claim],
        changed_slots: Mapping[str, str],
        sub_intents: Sequence[SubIntent] = (),
    ) -> list[str]:
        """Content the prior answer does not already carry: numerals, new/changed constraints,
        proper nouns absent from active claims, and novel sub-intents on facets the answer
        lacks. Empty => the turn can be presentation-only."""
        claim_text = " ".join(c.text for c in active)
        claim_lower = claim_text.lower()
        claim_numerals = set(extract_numerals(claim_text))
        active_facets = {c.facet for c in active}

        body = self._format_count_re.sub(" ", utterance) if self._format_count_re else utterance
        anchors = [n for n in extract_numerals(body) if n not in claim_numerals]
        anchors += [f"{slot}={value}" for slot, value in changed_slots.items()]
        for noun in extract_proper_nouns(utterance):
            if all(tok in self._neutral for tok in tokenize(noun)):
                continue
            if not re.search(r"\b" + re.escape(noun.lower()) + r"\b", claim_lower):
                anchors.append(noun)
        anchors += [s.intent_id for s in sub_intents if s.novel and s.facet not in active_facets]
        return anchors

    def _presentation_reason(
        self,
        utterance: str,
        active: Sequence[Claim],
        changed: Mapping[str, str],
        controller_decisions: Sequence[ControllerDecision],
        sub_intents: Sequence[SubIntent],
    ) -> str | None:
        for decision in controller_decisions:
            if decision.decision == "NO_RETRIEVAL" and decision.reason in self._presentation_reasons:
                return decision.reason
        tokens = set(tokenize(utterance))
        if not tokens & self._verbs or self.new_content_anchors(utterance, active, changed, sub_intents):
            return None
        for keys, reason in self._reason_keys:
            if keys & tokens:
                return reason
        return self._default_reason

    def _depends_on(self, active: Sequence[Claim], slot: str, session: Mapping[str, str]) -> bool:
        """The answer depends on ``slot`` if a session constraint, a claim's scope or a claim's
        text already involves it (its noun / verb / unit class / a role / a place)."""
        if slot in session or any(slot in claim.preconditions for claim in active):
            return True
        return any(self.extractor.mentions_key(slot, claim.text) for claim in active)


class DeltaEngine:
    """Plans and applies a CONSTRAINT_REFINEMENT as one ClaimGraph revision (S-4 steps 3-6)."""

    merge_constraints = staticmethod(merge_constraints)

    def __init__(self, config: dict | None = None, facets: dict | None = None) -> None:
        self.config = load_synth_config() if config is None else config
        self.facets = load_facets() if facets is None else facets
        self.extractor = ConstraintExtractor(self.config, self.facets)
        self.classifier = TurnClassifier(self.config, self.facets, extractor=self.extractor)
        delta_cfg = self.config.get("delta", {}) or {}
        self._min_score = float(delta_cfg.get("pool_resolution_min_score", 0.5))
        self._additive = bool(delta_cfg.get("additive_targets", True))
        self._keep_unreplaced = bool(delta_cfg.get("keep_unreplaced_session_scoped", True))
        self._templates = {**_DEFAULT_TEMPLATES, **(delta_cfg.get("query_templates") or {})}
        self._stopwords = stopwords_from(self.config)

    # -- plan ------------------------------------------------------------------
    def plan(
        self,
        graph: ClaimGraph,
        delta: ConstraintDelta,
        *,
        pool: Iterable[RetrievedChunk] = (),
        turn_id: int = 0,
    ) -> DeltaPlan:
        retained, affected = analyze_impact(graph, delta)
        claims = {c.claim_id: c for c in graph.active()}

        grouped: dict[tuple[str, str, str], list[str]] = {}
        for claim_id in affected:
            claim = claims[claim_id]
            for slot in _conflicting_slots(claim.preconditions, delta):
                value = delta.slots[slot]
                ids = grouped.setdefault((claim.facet, slot, value), [])
                if claim_id not in ids:
                    ids.append(claim_id)
        if self._additive:
            # A new constraint can add rules without contradicting any claim (only the general
            # rule was in V1): target (active facet x new constraint) for facets whose claims talk
            # about what the constraint restricts, superseding nothing. Dedupes onto conflict targets.
            for slot, value in delta.slots.items():
                for facet in dict.fromkeys(c.facet for c in claims.values()):
                    if any(self.extractor.mentions_key(slot, c.text) for c in claims.values() if c.facet == facet):
                        grouped.setdefault((facet, slot, value), [])

        cited = {label for c in claims.values() for label in c.citations}
        candidates = list({c.chunk_id: c for c in pool if label_for_chunk(c) not in cited}.values())
        targets = []
        for n, ((facet, slot, value), ids) in enumerate(grouped.items(), start=1):
            sub_intent = self._sub_intent(f"d{turn_id}_{n}", facet, slot, value, delta)
            targets.append(
                DeltaTarget(
                    facet=facet,
                    slot=slot,
                    value=value,
                    affected_claim_ids=tuple(ids),
                    sub_intent=sub_intent,
                    pool_chunks=self._resolve_from_pool(sub_intent, slot, value, candidates),
                )
            )
        return DeltaPlan(delta=delta, retained=retained, affected=affected, targets=targets)

    def _sub_intent(self, intent_id: str, facet: str, slot: str, value: str, delta: ConstraintDelta) -> SubIntent:
        """Targeted delta query scoped to (affected facet x new constraint) — never a full re-run.
        Worded from the user's own phrase ("international trip", "40 people") and the facet label."""
        fields = {"facet_label": facet_label(self.facets, facet),
                  "value_phrase": self.extractor.value_phrase(slot, value, delta)}
        return SubIntent(
            intent_id=intent_id,
            facet=facet,
            query_nl=self._templates["query_nl"].format(**fields),
            search_string=self._templates["search_string"].format(**fields),
            novel=True,
        )

    def _resolve_from_pool(
        self, sub_intent: SubIntent, slot: str, value: str, candidates: Sequence[RetrievedChunk]
    ) -> tuple[RetrievedChunk, ...]:
        """Pool-first resolution (S-4 step 4): eligible chunks mention the new value and are not
        cited by any active claim. Relevance = fraction of the targeted query's content tokens
        the chunk covers, where the target facet's label counts as one synonym class once the
        chunk hits any of it. Chunks >= ``pool_resolution_min_score`` resolve the target,
        score-desc, with ``score`` set to that relevance."""
        query = set(content_tokens(f"{sub_intent.query_nl} {sub_intent.search_string}", self._stopwords))
        vocab = set(content_tokens(facet_label(self.facets, sub_intent.facet), self._stopwords))
        hits = []
        for chunk in candidates:
            if not self.extractor.mentions(slot, value, chunk.text):
                continue
            tokens = set(content_tokens(chunk.text, self._stopwords))
            score = overlap(query, tokens | vocab) if tokens & vocab else overlap(query, tokens)
            if score >= self._min_score:
                hits.append(chunk.model_copy(update={"score": score}))
        hits.sort(key=lambda c: -c.score)
        return tuple(hits)

    # -- apply -----------------------------------------------------------------
    def apply(
        self,
        graph: ClaimGraph,
        plan: DeltaPlan,
        committed: Sequence[VerificationResult],
        *,
        session_constraints: Mapping[str, str],
        delta_queries_issued: int,
        latency_ms: float = 0.0,
    ) -> tuple[VersionLineage | None, RefinementReport]:
        """ONE revision: add a claim per committed result, supersede every affected claim.

        ``session_constraints`` are the already-merged constraints (see ``merge_constraints``).
        Evidence cited by ``committed`` must already be registered on ``graph``. Results with
        ``ok=False`` are ignored. Retained claims are never touched (byte-for-byte identical).
        """
        from_version = graph.version
        by_intent = {t.sub_intent.intent_id: t for t in plan.targets}
        new_ids: dict[str, list[str]] = {}
        kept: list[str] = []
        with graph.revise() as rev:
            for result in committed:
                if not result.ok:
                    continue
                target = by_intent.get(result.draft.intent_id or "")
                facet = target.facet if target else result.draft.facet
                claim_id = rev.add(
                    facet=facet,
                    text=result.text,
                    citations=result.citations,
                    preconditions=self.extractor.derive_preconditions(result.text, facet, session_constraints),
                    confidence=result.draft.confidence,
                    intent_id=result.draft.intent_id,
                    supporting_chunk_ids=result.supporting_chunk_ids,
                )
                if target:
                    new_ids.setdefault(target.sub_intent.intent_id, []).append(claim_id)
            for claim_id in plan.affected:
                by = [cid for t in plan.targets if claim_id in t.affected_claim_ids
                      for cid in new_ids.get(t.sub_intent.intent_id, ())]
                if not by and self._keep_unreplaced and not self.content_scoped(graph.get(claim_id), plan.delta):
                    # The targeted query found nothing, and the claim only inherited the old value
                    # from the session ("on-site catering for up to 80 guests" under headcount=30):
                    # it is still true, so it stays rather than silently vanishing.
                    kept.append(claim_id)
                    continue
                rev.supersede(claim_id, superseded_by=list(dict.fromkeys(by)))
        lineage = rev.lineage

        retained = list(lineage.retained) if lineage else [c.claim_id for c in graph.active()]
        added = list(lineage.added) if lineage else []
        preserved = self._citations(graph, retained)
        report = RefinementReport(
            from_version=from_version,
            to_version=graph.version,
            claims_retained=len(retained),
            claims_superseded=len(lineage.superseded) if lineage else 0,
            claims_added=len(added),
            delta_queries_issued=delta_queries_issued,
            citations_preserved=preserved,
            citations_added=[label for label in self._citations(graph, added) if label not in preserved],
            pool_resolved_targets=sum(t.resolved_from_pool for t in plan.targets),
            latency_ms=latency_ms,
            affected_kept=len(kept),
        )
        return lineage, report

    def content_scoped(self, claim: Claim, delta: ConstraintDelta) -> bool:
        """Does the claim's own text state the old value of a key the delta changes?"""
        return any(
            self.extractor.mentions(slot, old, claim.text)
            for slot in _conflicting_slots(claim.preconditions, delta)
            for old in values_of(claim.preconditions[slot])
        )

    @staticmethod
    def _citations(graph: ClaimGraph, claim_ids: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(label for cid in claim_ids for label in graph.get(cid).citations))
