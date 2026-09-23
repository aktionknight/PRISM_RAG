"""Claim-level contradiction gate — Component 4's last line behind Component 3's S-9 gating.

Two verified sentences can each be entailed by their own chunk and still contradict
each other: "Cancellations made more than 14 days before the event receive a full
refund. [Doc_31 §4]" next to "... more than 7 days ... [Doc_08 §1]". Both pass the
verifier, so without this gate the answer asserts both.

Two committed results conflict when they cite different documents, share a frame
(content-token overlap of the two sentences, numerals excluded, at least
``conflicts.frame_overlap``) and differ in their numerals or in negation polarity.
For each conflicting pair:

* evidence scores within ``uncertainty.ambiguity_margin`` -> both are retracted and a
  clarification question is asked ("Could you clarify whether you mean 14 days or
  7 days?"), the same HC-3 branch the coverage matrix takes for bimodal evidence;
* otherwise the claim backed by the higher-ranked chunk is kept and the other retracted.

Deterministic, no LLM (HC-5); thresholds and templates from config (HC-2).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from slrag.core.citations import parse_label
from slrag.synth.text import content_tokens, extract_numerals, stopwords_from
from slrag.synth.types import VerificationResult
from slrag.synth.uncertainty import differing_options
from slrag.synth.verifier import PolarityCheck

_SCORE_EPS = 1e-9


@dataclass(frozen=True)
class Conflict:
    kept: VerificationResult | None
    dropped: tuple[VerificationResult, ...]
    question: str | None


class ContradictionGate:
    def __init__(self, config: dict[str, Any]) -> None:
        cfg = config.get("conflicts", {}) or {}
        self.enabled = bool(cfg.get("enabled", True))
        self._overlap = float(cfg.get("frame_overlap", 0.75))
        uncertainty = config.get("uncertainty", {}) or {}
        self._margin = float(uncertainty.get("ambiguity_margin", 0.05))
        self._max_words = int(uncertainty.get("clarification_max_words", 6))
        self._template = str((uncertainty.get("templates") or {}).get("clarification", ""))
        self._stopwords = stopwords_from(config)
        self._polarity = PolarityCheck(config)

    def resolve(
        self, results: Sequence[VerificationResult], scores: Mapping[str, float]
    ) -> tuple[list[VerificationResult], list[Conflict]]:
        """(results to commit, conflicts found). ``scores``: chunk_id -> rerank score."""
        if not self.enabled:
            return list(results), []
        dropped: set[int] = set()
        conflicts: list[Conflict] = []
        for i, a in enumerate(results):
            for j in range(i + 1, len(results)):
                b = results[j]
                if i in dropped or j in dropped or not self.conflicting(a, b):
                    continue
                score_a, score_b = self._score(a, scores), self._score(b, scores)
                if abs(score_a - score_b) <= self._margin + _SCORE_EPS:
                    dropped.update((i, j))
                    first, second = (a, b) if score_a >= score_b else (b, a)
                    option_a, option_b = differing_options(first.text, second.text, self._max_words,
                                                           fallback=(first.citations[0], second.citations[0]))
                    question = self._template.format(option_a=option_a, option_b=option_b) if self._template else None
                    conflicts.append(Conflict(kept=None, dropped=(first, second), question=question))
                else:
                    loser = j if score_a > score_b else i
                    dropped.add(loser)
                    conflicts.append(Conflict(kept=results[i + j - loser], dropped=(results[loser],), question=None))
        return [r for n, r in enumerate(results) if n not in dropped], conflicts

    def conflicting(self, a: VerificationResult, b: VerificationResult) -> bool:
        if not a.citations or not b.citations or _docs(a) & _docs(b):
            return False
        tokens_a = {t for t in content_tokens(a.text, self._stopwords) if not t[0].isdigit()}
        tokens_b = {t for t in content_tokens(b.text, self._stopwords) if not t[0].isdigit()}
        if not tokens_a or not tokens_b:
            return False
        frame = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
        if frame < self._overlap:
            return False
        numerals_a, numerals_b = set(extract_numerals(a.text)), set(extract_numerals(b.text))
        return (numerals_a != numerals_b) or self._polarity.negated(a.text) != self._polarity.negated(b.text)

    @staticmethod
    def _score(result: VerificationResult, scores: Mapping[str, float]) -> float:
        return max((scores.get(chunk_id, 0.0) for chunk_id in result.supporting_chunk_ids), default=0.0)


def retracted(result: VerificationResult) -> VerificationResult:
    return replace(result, ok=False, reasons=(*result.reasons, "contradiction"))


def _docs(result: VerificationResult) -> set[str]:
    return {parse_label(label)[0] for label in result.citations}
