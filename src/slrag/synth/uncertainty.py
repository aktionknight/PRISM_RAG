"""Coverage matrix -> principled uncertainty (S-10, roadmap 4.9, A_FINAL_ARCHITECTURE §4.6).

For every sub-intent the matrix records the best rerank score and whether a
committed claim exists (claims reach the graph only after verification, so a
committed claim *is* an entailed claim), then derives one state per row:

  covered    >=1 claim; its claims name every anchor entity, or none (a general facet)
  partial    covered, but its claims name a non-empty proper subset of the session's
             anchor entities -> one entity x facet gap sentence per missing anchor
  ambiguous  no claim, credible evidence split between two documents with near-equal
             scores -> a targeted clarification question instead (HC-3's permitted
             alternate branch)
  uncovered  no claim otherwise -> an uncertainty sentence

An uncovered sub-intent is never silently dropped: every non-covered row carries a
message. Thresholds, anchor patterns and sentence templates come from
``config/synth.yaml`` ``uncertainty:`` (HC-2); facet phrasing from
``config/facets.yaml`` ``uncertainty_label``. Deterministic, no LLM (HC-5).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from slrag.core.citations import label_for_chunk
from slrag.core.schemas import Claim, RetrievedChunk, SubIntent
from slrag.synth.config import facet_label, load_facets, load_synth_config
from slrag.synth.text import split_sentences
from slrag.synth.types import CoverageRow, CoverageState

_STATES: tuple[CoverageState, ...] = ("covered", "partial", "ambiguous", "uncovered")
_REQUIRED_TEMPLATES = ("uncovered", "entity_gap", "clarification")
_SCORE_EPS = 1e-9          # float tolerance on the ambiguity margin, not a threshold


class CoverageMatrix:
    """Builds the sub_intent x evidence matrix and projects it to ``uncertainty``."""

    def __init__(self, config: dict | None = None, facets: dict | None = None) -> None:
        self.config = config if config is not None else load_synth_config()
        self.facets = facets if facets is not None else load_facets()
        cfg = self.config.get("uncertainty", {})
        self._floor = float(cfg.get("coverage_floor", 0.4))
        self._margin = float(cfg.get("ambiguity_margin", 0.05))
        self._max_option_words = int(cfg.get("clarification_max_words", 6))
        self._entity_res = tuple(re.compile(p) for p in cfg.get("entity_patterns", ()))
        self._templates = dict(cfg.get("templates", {}))
        missing = [key for key in _REQUIRED_TEMPLATES if not self._templates.get(key)]
        if missing:
            raise ValueError(f"config uncertainty.templates is missing {missing} (HC-2: no templates in code)")

    # -- matrix ----------------------------------------------------------------
    def build(
        self,
        sub_intents: Sequence[SubIntent],
        evidence: Mapping[str, Sequence[RetrievedChunk]],
        claims: Sequence[Claim],
        *,
        claim_intents: Mapping[str, str] | None = None,
    ) -> list[CoverageRow]:
        """One row per sub-intent, in order. ``claims`` = active committed claims."""
        active = [claim for claim in claims if claim.status == "active"]
        anchors = self._entities(claim.text for claim in active)
        assigned = _assign(sub_intents, active, claim_intents or {})
        rows = []
        for intent in sub_intents:
            ranked = _ranked(evidence.get(intent.intent_id, ()))
            best = ranked[0].score if ranked else None
            mine = assigned[intent.intent_id]
            if mine:
                rows.append(self._covered_row(intent, best, mine, anchors))
            elif (pair := self._ambiguous_pair(ranked)) is not None:
                option_a, option_b = self._options(*pair)
                message = self._fmt("clarification", intent, option_a=option_a, option_b=option_b)
                rows.append(_row(intent, best, (), "ambiguous", message, is_clarification=True))
            else:
                rows.append(_row(intent, best, (), "uncovered", self._fmt("uncovered", intent)))
        return rows

    # -- projections -----------------------------------------------------------
    def uncertainty_text(self, rows: Sequence[CoverageRow]) -> str:
        """Non-clarification messages, row order, de-duplicated; else the full-coverage caveat."""
        messages = dict.fromkeys(row.message for row in rows if row.message and not row.is_clarification)
        if messages:
            return " ".join(messages)
        return str(self._templates.get("full_coverage_caveat") or "")

    def clarifications(self, rows: Sequence[CoverageRow]) -> list[str]:
        return list(dict.fromkeys(row.message for row in rows if row.is_clarification and row.message))

    def to_telemetry(self, rows: Sequence[CoverageRow]) -> dict[str, Any]:
        counts = {state: 0 for state in _STATES}
        for row in rows:
            counts[row.state] += 1
        return {
            "intents": len(rows),
            "counts": counts,
            "rows": [
                {
                    "intent_id": row.intent_id,
                    "facet": row.facet,
                    "state": row.state,
                    "best_score": row.best_score,
                    "claim_ids": list(row.claim_ids),
                    "missing_entities": list(row.missing_entities),
                    "is_clarification": row.is_clarification,
                }
                for row in rows
            ],
        }

    # -- internals -------------------------------------------------------------
    def _covered_row(
        self, intent: SubIntent, best: float | None, mine: list[Claim], anchors: list[str]
    ) -> CoverageRow:
        claim_ids = tuple(claim.claim_id for claim in mine)
        mentioned = set(self._entities(claim.text for claim in mine))
        missing = tuple(anchor for anchor in anchors if anchor not in mentioned)
        if not mentioned or not missing:     # general facet, or every anchor named
            return _row(intent, best, claim_ids, "covered", None)
        message = " ".join(self._fmt("entity_gap", intent, entity=entity) for entity in missing)
        return _row(intent, best, claim_ids, "partial", message, missing_entities=missing)

    def _ambiguous_pair(self, ranked: list[RetrievedChunk]) -> tuple[RetrievedChunk, RetrievedChunk] | None:
        if len(ranked) < 2:
            return None
        first, second = ranked[0], ranked[1]
        if first.score < self._floor or first.doc_id == second.doc_id:
            return None
        if first.score - second.score > self._margin + _SCORE_EPS:
            return None
        return first, second

    def _options(self, first: RetrievedChunk, second: RetrievedChunk) -> tuple[str, str]:
        """The phrase that tells the two readings apart ("14 days" / "7 days").

        Common leading and trailing words of the two lead sentences are stripped and
        one word of trailing context is kept so a numeral keeps its unit. Falls back
        to the citation labels when the readings share no frame or the differing
        span is longer than ``clarification_max_words``.
        """
        words_a, words_b = _lead_sentence(first.text).split(), _lead_sentence(second.text).split()
        shortest = min(len(words_a), len(words_b))
        start = 0
        while start < shortest and words_a[start] == words_b[start]:
            start += 1
        tail = 0
        while tail < shortest - start and words_a[-1 - tail] == words_b[-1 - tail]:
            tail += 1
        end_a, end_b = len(words_a) - tail, len(words_b) - tail
        context = 1 if tail else 0
        span = max(end_a, end_b) - start + context
        if start >= end_a or start >= end_b or span > self._max_option_words:
            return label_for_chunk(first), label_for_chunk(second)
        return " ".join(words_a[start:end_a + context]), " ".join(words_b[start:end_b + context])

    def _entities(self, texts: Iterable[str]) -> list[str]:
        """Anchor-entity matches of ``uncertainty.entity_patterns``, ordered and unique."""
        found: dict[str, None] = {}
        for text in texts:
            for pattern in self._entity_res:
                for match in pattern.finditer(text):
                    found.setdefault(match.group(0), None)
        return list(found)

    def _fmt(self, key: str, intent: SubIntent, **values: str) -> str:
        label = facet_label(self.facets, intent.facet, key="uncertainty_label")
        return self._templates[key].format(facet_label=label, facet=intent.facet, query=intent.query_nl, **values)


def _assign(
    sub_intents: Sequence[SubIntent], claims: Sequence[Claim], claim_intents: Mapping[str, str]
) -> dict[str, list[Claim]]:
    """claim -> intent via ``claim_intents``; unmapped claims match intents by facet."""
    assigned: dict[str, list[Claim]] = {intent.intent_id: [] for intent in sub_intents}
    for claim in claims:
        target = claim_intents.get(claim.claim_id)
        if target in assigned:
            assigned[target].append(claim)
            continue
        for intent in sub_intents:
            if intent.facet == claim.facet:
                assigned[intent.intent_id].append(claim)
    return assigned


def _ranked(chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    """Evidence de-duplicated by chunk_id (max score), best first; ties keep input order."""
    best: dict[str, RetrievedChunk] = {}
    for chunk in chunks:
        if chunk.chunk_id not in best or chunk.score > best[chunk.chunk_id].score:
            best[chunk.chunk_id] = chunk
    return sorted(best.values(), key=lambda chunk: -chunk.score)


def _lead_sentence(text: str) -> str:
    return (split_sentences(text) or [text])[0].rstrip(" .!?;:")


def _row(
    intent: SubIntent,
    best: float | None,
    claim_ids: tuple[str, ...],
    state: CoverageState,
    message: str | None,
    *,
    is_clarification: bool = False,
    missing_entities: tuple[str, ...] = (),
) -> CoverageRow:
    return CoverageRow(
        intent_id=intent.intent_id,
        facet=intent.facet,
        query=intent.query_nl,
        best_score=best,
        claim_ids=claim_ids,
        state=state,
        message=message,
        is_clarification=is_clarification,
        missing_entities=missing_entities,
    )
