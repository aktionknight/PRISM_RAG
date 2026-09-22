"""Turn classifier + delta engine (S-4, roadmap 4.3 / 4.4).

Refinement is a ``ClaimGraph`` mutation, never string editing (Rule 3)::

    classify turn -> extract constraint delta -> impact analysis (retain | affect)
      -> pool-first resolution -> targeted queries (affected facet x new constraint)
      -> merge (one Revision: add new claims, supersede affected) -> version++

Deterministic and side-effect free: no LLM calls, no retrieval calls (HC-5) — the
caller dispatches ``DeltaPlan.queries`` through Component 3. No module-level
mutable state (HC-4). Slots, patterns, templates, cues and thresholds come from
``config/synth.yaml`` ``delta:`` / ``presentation:`` and ``config/facets.yaml`` (HC-2).

Known limitations (D3 edge cases):
  * a turn mixing a constraint with a brand-new facet ("international, and what
    about visas?") is classified CONSTRAINT_REFINEMENT — turn splitting is not done;
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
    """Delta slots the claim is scoped to with a *different* value (absent slot = general claim)."""
    return [slot for slot, value in delta.slots.items() if slot in preconditions and str(preconditions[slot]) != value]


def analyze_impact(graph: ClaimGraph, delta: ConstraintDelta) -> tuple[list[str], list[str]]:
    """(retained ids, affected ids) over active claims in graph order (S-4 step 3)."""
    retained: list[str] = []
    affected: list[str] = []
    for claim in graph.active():
        (affected if _conflicting_slots(claim.preconditions, delta) else retained).append(claim.claim_id)
    return retained, affected


class ConstraintExtractor:
    """Regex slot filling over ``delta.slots`` (categorical ``values`` or ``numeric_patterns``)."""

    def __init__(self, config: dict | None = None, facets: dict | None = None) -> None:
        self.config = load_synth_config() if config is None else config
        self.facets = load_facets() if facets is None else facets
        self._slots: dict[str, dict[str, Any]] = dict(self.config.get("delta", {}).get("slots", {}) or {})
        self._categorical: dict[str, tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]] = {}
        self._numeric: dict[str, tuple[re.Pattern[str], ...]] = {}
        for slot, spec in self._slots.items():
            if spec.get("values"):
                self._categorical[slot] = tuple(
                    (str(value), tuple(re.compile(p, re.IGNORECASE) for p in (vspec or {}).get("patterns", ())))
                    for value, vspec in spec["values"].items()
                )
            elif spec.get("numeric_patterns"):
                self._numeric[slot] = tuple(re.compile(p, re.IGNORECASE) for p in spec["numeric_patterns"])

    # -- extraction --------------------------------------------------------------
    def extract(self, text: str, slots: Iterable[str] | None = None) -> ConstraintDelta:
        wanted = None if slots is None else set(slots)
        found: dict[str, str] = {}
        for slot in self._slots:
            if wanted is not None and slot not in wanted:
                continue
            value = self._match_categorical(slot, text) if slot in self._categorical else self._match_numeric(slot, text)
            if value is not None:
                found[slot] = value
        return ConstraintDelta(slots=found, raw_text=text)

    def derive_preconditions(self, claim_text: str, facet: str, session_constraints: Mapping[str, str]) -> dict[str, str]:
        """Claim scope over the facet's ``constraint_slots``: a categorical value in the claim's own
        text wins, else the session constraint. Numeric slots come from the session only."""
        out: dict[str, str] = {}
        for slot in self.facets.get(facet, {}).get("constraint_slots") or ():
            value = self._match_categorical(slot, claim_text) if slot in self._categorical else None
            if value is None and session_constraints.get(slot) is not None:
                value = str(session_constraints[slot])
            if value is not None:
                out[slot] = value
        return out

    # -- slot metadata (used by the delta engine) --------------------------------
    def is_numeric(self, slot: str) -> bool:
        return slot in self._numeric

    def value_spec(self, slot: str, value: str) -> Mapping[str, Any]:
        """Config for ``slot=value``: the categorical value's spec, or the numeric slot's spec."""
        spec = self._slots.get(slot, {})
        if slot in self._numeric:
            return spec
        return (spec.get("values") or {}).get(value) or {}

    def value_phrase(self, slot: str, value: str) -> str:
        phrase = self.value_spec(slot, value).get("value_phrase")
        return str(phrase).format(value=value) if phrase else value

    def mentions(self, slot: str, value: str, text: str) -> bool:
        """Does ``text`` mention ``slot=value`` (a value pattern matches / the number appears)?"""
        if slot in self._numeric:
            return value in extract_numerals(text)
        for candidate, patterns in self._categorical.get(slot, ()):
            if candidate == value:
                return any(p.search(text) for p in patterns)
        return False

    def _match_categorical(self, slot: str, text: str) -> str | None:
        for value, patterns in self._categorical.get(slot, ()):
            if any(p.search(text) for p in patterns):
                return value
        return None

    def _match_numeric(self, slot: str, text: str) -> str | None:
        for pattern in self._numeric.get(slot, ()):
            match = pattern.search(text)
            if match:
                return match.group(1).replace(",", "")
        return None


class TurnClassifier:
    """NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY (S-4 step 1, Example 3).

    Known limitation: a turn mixing a constraint and a brand-new facet is classified
    CONSTRAINT_REFINEMENT (turn splitting is a D3 edge case).
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
        self._cues = tuple(re.compile(p, re.IGNORECASE) for p in self.config.get("delta", {}).get("refinement_cues", ()))
        self._keywords = {
            facet: frozenset(tokenize(" ".join(map(str, spec.get("keywords", ()) or ()))))
            for facet, spec in self.facets.items()
        }

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
        extracted = self.extractor.extract(utterance)
        active = graph.active()
        if not active:
            return TurnClassification("NEW_INTENT", "no_prior_answer", extracted)

        changed = {slot: value for slot, value in extracted.slots.items() if session.get(slot) != value}
        reason = self._presentation_reason(utterance, active, changed, controller_decisions, sub_intents)
        if reason is not None:
            return TurnClassification("PRESENTATION_ONLY", reason, ConstraintDelta(raw_text=utterance))

        delta = ConstraintDelta(slots=changed, raw_text=utterance)
        # A new slot the current answer does not depend on only counts as a refinement with a cue.
        if changed and (self._depends_on(active, changed) or any(c.search(utterance) for c in self._cues)):
            return TurnClassification("CONSTRAINT_REFINEMENT", "constraint_delta", delta)
        return TurnClassification("NEW_INTENT", "new_intent", delta)

    def new_content_anchors(
        self,
        utterance: str,
        active: Sequence[Claim],
        changed_slots: Mapping[str, str],
        sub_intents: Sequence[SubIntent] = (),
    ) -> list[str]:
        """Content the prior answer does not already carry: numerals, new/changed slot values,
        proper nouns absent from active claims, keywords of facets absent from the answer,
        and novel sub-intents on such facets. Empty => the turn can be presentation-only."""
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
        answered = set().union(*(self._keywords.get(f, frozenset()) for f in active_facets))
        unanswered = set().union(*(kw for f, kw in self._keywords.items() if f not in active_facets))
        anchors += sorted((set(tokenize(utterance)) & unanswered) - answered)
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

    def _depends_on(self, active: Sequence[Claim], slots: Mapping[str, str]) -> bool:
        relevant: set[str] = set()
        for claim in active:
            relevant.update(self.facets.get(claim.facet, {}).get("constraint_slots") or ())
            relevant.update(claim.preconditions)
        return any(slot in relevant for slot in slots)


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
                facet = self.extractor.value_spec(slot, value).get("facet") or claim.facet
                ids = grouped.setdefault((str(facet), slot, value), [])
                if claim_id not in ids:
                    ids.append(claim_id)
        if self._additive:
            # A new constraint can add rules without contradicting any claim (only the general
            # rule was in V1): target (active facet x new constraint) for facets that declare
            # the slot, superseding nothing. Dedupes onto conflict targets with the same key.
            for slot, value in delta.slots.items():
                for facet in dict.fromkeys(c.facet for c in claims.values()):
                    if slot in (self.facets.get(facet, {}).get("constraint_slots") or ()):
                        target_facet = self.extractor.value_spec(slot, value).get("facet") or facet
                        grouped.setdefault((str(target_facet), slot, value), [])

        cited = {label for c in claims.values() for label in c.citations}
        candidates = list({c.chunk_id: c for c in pool if label_for_chunk(c) not in cited}.values())
        targets = []
        for n, ((facet, slot, value), ids) in enumerate(grouped.items(), start=1):
            sub_intent = self._sub_intent(f"d{turn_id}_{n}", facet, slot, value)
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

    def _sub_intent(self, intent_id: str, facet: str, slot: str, value: str) -> SubIntent:
        """Targeted delta query scoped to (affected facet x new constraint) — never a full re-run."""
        spec = self.extractor.value_spec(slot, value)
        fields = {"facet_label": facet_label(self.facets, facet), "value_phrase": self.extractor.value_phrase(slot, value)}
        query_nl = spec.get("query_nl") if not self.extractor.is_numeric(slot) else None
        search = spec.get("search_string") if not self.extractor.is_numeric(slot) else None
        return SubIntent(
            intent_id=intent_id,
            facet=facet,
            query_nl=str(query_nl or self._templates["query_nl"].format(**fields)),
            search_string=str(search or self._templates["search_string"].format(**fields)),
            novel=True,
        )

    def _resolve_from_pool(
        self, sub_intent: SubIntent, slot: str, value: str, candidates: Sequence[RetrievedChunk]
    ) -> tuple[RetrievedChunk, ...]:
        """Pool-first resolution (S-4 step 4): eligible chunks mention the new value and are not
        cited by any active claim. Relevance = fraction of the targeted query's content tokens
        the chunk covers, where the target facet's vocabulary (label + keywords) counts as one
        synonym class once the chunk hits any of it. Chunks >= ``pool_resolution_min_score``
        resolve the target, score-desc, with ``score`` set to that relevance."""
        query = set(content_tokens(f"{sub_intent.query_nl} {sub_intent.search_string}", self._stopwords))
        spec = self.facets.get(sub_intent.facet, {})
        vocab = set(
            content_tokens(" ".join([facet_label(self.facets, sub_intent.facet), *map(str, spec.get("keywords", ()) or ())]),
                           self._stopwords)
        )
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
        )
        return lineage, report

    @staticmethod
    def _citations(graph: ClaimGraph, claim_ids: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(label for cid in claim_ids for label in graph.get(cid).citations))
