"""
retrieve/contradiction.py — Contradiction gating via typed slot extraction + NLI.

Detects contradictory facts within a facet:
  1. Extract typed values (durations, percentages, currency, dates, roles)
  2. Two chunks disagreeing on the same slot → candidate conflict
  3. NLI check (nli-deberta-v3-small) confirms contradiction (prob > 0.7)

Confirmed contradictions are NEVER silently resolved — they're surfaced
with both readings and citations, or routed to the uncertainty field.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from slrag.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


# ── Slot extraction patterns ──
_SLOT_PATTERNS: dict[str, re.Pattern] = {
    "currency": re.compile(
        r"(?:[$€£₹¥])\s*\d+(?:,\d{3})*(?:\.\d+)?", re.IGNORECASE
    ),
    "percentage": re.compile(r"\d+(?:\.\d+)?%"),
    "duration": re.compile(
        r"\b\d+\s*(?:day|week|month|year|hour|minute)s?\b", re.IGNORECASE
    ),
    "date": re.compile(
        r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b", re.IGNORECASE
    ),
    "approval_role": re.compile(
        r"\b(?:manager|director|VP|CEO|CFO|CTO|senior\s+\w+|head\s+of\s+\w+)\b",
        re.IGNORECASE,
    ),
}


def extract_typed_slots(text: str) -> dict[str, list[str]]:
    """Extract typed values from chunk text.

    Returns:
        Dict mapping slot type → list of extracted values.
    """
    slots: dict[str, list[str]] = {}
    for slot_type, pattern in _SLOT_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            slots[slot_type] = [m.strip() for m in matches]
    return slots


class ContradictionGating:
    """Detects contradictions between chunks within the same facet.

    Uses typed slot extraction for cheap candidate detection,
    then confirms with NLI cross-encoder.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-small",
        threshold: float = 0.7,
    ) -> None:
        self.threshold = threshold
        self.model_name = model_name
        self.nli_pipeline = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the NLI pipeline for contradiction detection."""
        try:
            from transformers import pipeline

            self.nli_pipeline = pipeline(
                "text-classification",
                model=self.model_name,
                device=-1,  # CPU
            )
            logger.info(f"NLI model loaded: {self.model_name}")
        except Exception as e:
            logger.warning(f"NLI model not available ({e}) — contradiction gating disabled")

    async def detect_contradictions(
        self,
        chunks: list[RetrievedChunk],
        facet: str | None = None,
    ) -> list[dict[str, Any]]:
        """Detect contradictions among a set of chunks.

        Args:
            chunks: Chunks to check for internal contradictions.
            facet: Optional facet label for logging.

        Returns:
            List of contradiction records:
            [{facet, chunk_a, chunk_b, slot, values, nli_score}]
        """
        if len(chunks) < 2:
            return []

        contradictions: list[dict[str, Any]] = []

        # Pairwise slot comparison
        for i in range(len(chunks)):
            slots_i = extract_typed_slots(chunks[i].text)
            for j in range(i + 1, len(chunks)):
                slots_j = extract_typed_slots(chunks[j].text)

                # Find slot types present in both chunks
                common_types = set(slots_i.keys()) & set(slots_j.keys())

                for slot_type in common_types:
                    # Check if values differ
                    vals_i = set(slots_i[slot_type])
                    vals_j = set(slots_j[slot_type])

                    if vals_i != vals_j:
                        # Candidate conflict — confirm with NLI if available
                        nli_score = await self._nli_check(
                            chunks[i].text, chunks[j].text
                        )

                        if nli_score >= self.threshold:
                            contradiction = {
                                "facet": facet or "unknown",
                                "chunk_a": chunks[i].chunk_id,
                                "chunk_b": chunks[j].chunk_id,
                                "citation_a": chunks[i].citation_label,
                                "citation_b": chunks[j].citation_label,
                                "slot": slot_type,
                                "values": [list(vals_i), list(vals_j)],
                                "nli_score": nli_score,
                            }
                            contradictions.append(contradiction)
                            logger.info(
                                f"Contradiction detected in {facet}: "
                                f"{slot_type} = {vals_i} vs {vals_j} "
                                f"(NLI={nli_score:.2f})"
                            )

        return contradictions

    async def _nli_check(self, text_a: str, text_b: str) -> float:
        """Run NLI contradiction check between two texts.

        Returns:
            Contradiction probability [0, 1]. Returns 1.0 if NLI model
            is unavailable (fail-open: assume conflict for manual review).
        """
        if not self.nli_pipeline:
            # Without NLI model, conservatively assume contradiction
            # so it gets surfaced for review
            return 1.0

        try:
            def _run():
                result = self.nli_pipeline(
                    f"{text_a} [SEP] {text_b}",
                    top_k=None,
                )
                # Find the contradiction label score
                for item in result:
                    if item["label"].lower() in ("contradiction", "contradict"):
                        return item["score"]
                return 0.0

            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.error(f"NLI check failed: {e}")
            return 0.0
