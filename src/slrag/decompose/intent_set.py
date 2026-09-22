"""
decompose/intent_set.py — Monotonic IntentSet manager for Phase 3 (Task 3.4).

Manages the session-scoped store of sub-intents. Intents are only ever added,
never removed. Ensures novelty via facet and embedding-based deduplication.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import numpy as np
import ulid

from slrag.core.schemas import IntentStatus, SubIntent
from slrag.core.session import SessionState

logger = logging.getLogger(__name__)

# Lazy-loaded embedding model to avoid blocking on import
_EMBEDDING_MODEL = None


def _get_embedding_model(model_name: str):
    """Lazy load the sentence-transformers model."""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        logger.info(f"Loading embedding model: {model_name}")
        from sentence_transformers import SentenceTransformer

        _EMBEDDING_MODEL = SentenceTransformer(model_name)
    return _EMBEDDING_MODEL


class IntentSet:
    """Monotonic session-scoped store of sub-intents.

    Intents can change status but are never removed. Handles novelty detection
    using facet-matching and semantic similarity of the search string.
    """

    def __init__(
        self,
        session: SessionState,
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",
        similarity_threshold: float = 0.88,
    ):
        self.session = session
        self.embedding_model_name = embedding_model_name
        self.similarity_threshold = similarity_threshold
        self._lock = asyncio.Lock()
        self._embedding_cache: dict[str, np.ndarray] = {}

    def _generate_intent_id(self) -> str:
        """Generate a unique ID for a new intent."""
        # Handle different common Python ULID libraries (e.g. python-ulid vs ulid-py)
        if hasattr(ulid, "new"):
            return str(ulid.new())
        return str(ulid.ULID())

    def _get_embedding(self, text: str, model) -> np.ndarray:
        """Get or compute the normalized embedding for a text."""
        if text not in self._embedding_cache:
            # normalize_embeddings=True allows dot product for cosine similarity
            emb = model.encode(text, normalize_embeddings=True)
            self._embedding_cache[text] = emb
        return self._embedding_cache[text]

    def _compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two normalized embeddings."""
        return float(np.dot(emb1, emb2))

    async def add_intents(self, new_candidates: list[SubIntent]) -> list[SubIntent]:
        """Add genuinely new intents to the session, returning only the novel ones.

        Two intents are duplicates if:
          a) They share the same facet key
          b) Cosine similarity of their search_string embeddings > similarity_threshold
        """
        model = _get_embedding_model(self.embedding_model_name)
        novel_intents = []

        async with self._lock:
            for candidate in new_candidates:
                candidate_emb = self._get_embedding(candidate.search_string, model)
                is_duplicate = False

                for existing_intent in self.session.intent_set.values():
                    if existing_intent.facet == candidate.facet:
                        existing_emb = self._get_embedding(
                            existing_intent.search_string, model
                        )
                        sim = self._compute_similarity(candidate_emb, existing_emb)

                        if sim > self.similarity_threshold:
                            is_duplicate = True
                            logger.info(
                                f"Intent deduplicated (sim={sim:.3f}): "
                                f"'{candidate.search_string}' matches existing "
                                f"'{existing_intent.search_string}'"
                            )
                            break

                if not is_duplicate:
                    # Assign a new ULID and add to the authoritative session store
                    new_id = self._generate_intent_id()
                    candidate.intent_id = new_id
                    candidate.novel = True
                    candidate.status = IntentStatus.pending

                    self.session.intent_set[new_id] = candidate
                    novel_intents.append(candidate)
                    logger.debug(
                        f"Added novel intent: {new_id} ({candidate.search_string})"
                    )

        return novel_intents

    def get_pending(self) -> list[SubIntent]:
        """Return all undispatched intents."""
        return self.session.get_pending_intents()

    def get_dispatched(self) -> list[SubIntent]:
        """Return all already-dispatched intents."""
        return self.session.get_dispatched_intents()

    def mark_dispatched(self, intent_id: str) -> None:
        """Mark an intent as dispatched."""
        intent = self.session.intent_set.get(intent_id)
        if intent:
            intent.dispatched = True
            intent.status = IntentStatus.dispatched
            logger.debug(f"Marked intent {intent_id} as dispatched.")
        else:
            logger.warning(
                f"Attempted to mark unknown intent {intent_id} as dispatched."
            )

    def mark_merged(self, intent_id: str, merged_into: str) -> None:
        """Mark an intent as merged into another intent."""
        intent = self.session.intent_set.get(intent_id)
        if intent:
            intent.status = IntentStatus.merged
            logger.debug(f"Marked intent {intent_id} as merged into {merged_into}.")
        else:
            logger.warning(
                f"Attempted to mark unknown intent {intent_id} as merged."
            )
