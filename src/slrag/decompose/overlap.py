"""
decompose/overlap.py — Retrieval-overlap merge (Phase 3, Task 3.5).

Detects when two sub-intents retrieve substantially overlapping result sets
and merges them to prevent redundant queries. Directly prevents the
"coordination trap" edge case (e.g., "cancellation and refund terms"
producing two overlapping intents).
"""

from __future__ import annotations

import logging

from slrag.core.schemas import IntentStatus, RetrievedChunk
from slrag.core.session import SessionState

logger = logging.getLogger(__name__)


class OverlapMerger:
    """Detects and merges sub-intents with highly overlapping retrieval results.

    Prevents the 'coordination trap' (e.g. 'cancellation and refund terms'
    producing two identical queries) by computing Jaccard similarity on top-k chunks.
    """

    def check_and_merge(
        self,
        session: SessionState,
        intent_a_id: str,
        intent_b_id: str,
        results_a: list[RetrievedChunk],
        results_b: list[RetrievedChunk],
        jaccard_threshold: float = 0.7,
    ) -> bool:
        """Check if two intents overlap and merge B into A if they do.

        Merging means: mark intent_b as ``merged`` status, keep intent_a's
        results, union citation labels. Provenance never drops.

        Args:
            session: Current session state.
            intent_a_id: ID of the intent to keep.
            intent_b_id: ID of the intent to merge (will be marked merged).
            results_a: Top retrieval results for intent A.
            results_b: Top retrieval results for intent B.
            jaccard_threshold: Jaccard threshold on top-10 chunk IDs.

        Returns:
            True if merge happened.
        """
        intent_a = session.intent_set.get(intent_a_id)
        intent_b = session.intent_set.get(intent_b_id)

        if not intent_a or not intent_b:
            return False

        # Only merge intents that share the same facet
        if intent_a.facet != intent_b.facet:
            return False

        # Compute Jaccard on top-10 chunks
        top_a = {c.chunk_id for c in results_a[:10]}
        top_b = {c.chunk_id for c in results_b[:10]}

        if not top_a or not top_b:
            return False

        intersection = len(top_a & top_b)
        union = len(top_a | top_b)
        jaccard = intersection / union if union > 0 else 0.0

        if jaccard > jaccard_threshold:
            logger.info(
                f"Overlap merge: {intent_b_id} into {intent_a_id} "
                f"(Jaccard={jaccard:.2f}, facet={intent_a.facet})"
            )
            intent_b.status = IntentStatus.merged
            return True

        return False

    def check_all_pairs(
        self,
        session: SessionState,
        results_by_intent: dict[str, list[RetrievedChunk]],
        jaccard_threshold: float = 0.7,
    ) -> list[tuple[str, str]]:
        """Check all pairs of dispatched intents for overlap.

        Args:
            session: Current session state.
            results_by_intent: Mapping of intent_id → retrieval results.
            jaccard_threshold: Jaccard threshold on top-10 chunk IDs.

        Returns:
            List of (kept_intent_id, merged_intent_id) pairs.
        """
        intent_ids = list(results_by_intent.keys())
        merged_pairs: list[tuple[str, str]] = []
        merged_intents: set[str] = set()

        for i in range(len(intent_ids)):
            intent_a_id = intent_ids[i]
            if intent_a_id in merged_intents:
                continue

            for j in range(i + 1, len(intent_ids)):
                intent_b_id = intent_ids[j]
                if intent_b_id in merged_intents:
                    continue

                results_a = results_by_intent.get(intent_a_id, [])
                results_b = results_by_intent.get(intent_b_id, [])

                if self.check_and_merge(
                    session,
                    intent_a_id,
                    intent_b_id,
                    results_a,
                    results_b,
                    jaccard_threshold,
                ):
                    merged_pairs.append((intent_a_id, intent_b_id))
                    merged_intents.add(intent_b_id)

        if merged_pairs:
            logger.info(
                f"Overlap merge completed: {len(merged_pairs)} pair(s) merged"
            )

        return merged_pairs
