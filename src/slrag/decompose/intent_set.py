"""
decompose/intent_set.py — Monotonic IntentSet manager for Phase 3 (Task 3.4).

Manages the session-scoped store of sub-intents. Intents are only ever added,
never removed. Ensures novelty via facet and embedding-based deduplication.
"""

from __future__ import annotations

import asyncio
import logging
import re
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
        import torch
        from sentence_transformers import SentenceTransformer

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading embedding model on {device}: {model_name}")
        _EMBEDDING_MODEL = SentenceTransformer(model_name, device=device)
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
        self._intent_turns: dict[str, int] = {}

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

    async def add_intents(self, new_candidates: list[SubIntent], prefix: str = "") -> list[SubIntent]:
        """Add genuinely new intents to the session, returning only the novel ones.

        Apply supersession only for user corrections. A changing model slot or
        supersedes hint alone must not discard another information need.
        Exact identity is checked before corrections, with semantic dedup
        restricted to the current turn.
        """
        from slrag.core.config import get_controller_config
        controller_config = get_controller_config()
        markers = controller_config.get("additive_markers", [])
        correcting = any(re.search(r"\b" + re.escape(m) + r"\b", prefix, re.I)
                         for m in controller_config.get("self_correction_markers", []))
        additive = any(re.search(r"\b" + re.escape(m) + r"\b", prefix, re.I) for m in markers)
        novel_intents = []
        model = None
        model_unavailable = False

        def key(text):
            return " ".join(re.findall(r"\w+", text.casefold()))

        async with self._lock:
            for candidate in new_candidates:
                if not candidate.search_string.strip():
                    continue
                active = [i for i in self.session.intent_set.values()
                          if i.status not in (IntentStatus.superseded, IntentStatus.merged)]
                duplicate = None
                replaced = []
                for existing in active:
                    if (key(candidate.search_string) == key(existing.search_string) or
                            (candidate.query_nl.strip() and key(candidate.query_nl) == key(existing.query_nl))):
                        duplicate = existing
                        break
                    shared = candidate.slots.keys() & existing.slots.keys()
                    conflict = any(candidate.slots[k] != existing.slots[k] for k in shared)
                    if conflict:
                        if existing.facet == candidate.facet and correcting and not additive:
                            replaced.append(existing)
                        continue
                    # Exact identity is independent of an LLM's changing facet label
                    # and is available even when the embedding service is down.
                    if key(candidate.search_string) == key(existing.search_string):
                        duplicate = existing
                        break
                    if existing.facet != candidate.facet:
                        continue
                    # Exact identity may reuse session evidence, but fuzzy matches
                    # must not substitute an unrelated earlier-turn question.
                    if self._intent_turns.get(existing.intent_id) != self.session.turn_id:
                        continue
                    operators = set(controller_config.get("intent_request_operators", ()))
                    if (set(key(candidate.query_nl).split()) & operators) != (set(key(existing.query_nl).split()) & operators):
                        continue
                    if set(re.findall(r"\d+", candidate.search_string)) != set(re.findall(r"\d+", existing.search_string)):
                        continue
                    if not model_unavailable:
                        try:
                            if model is None:
                                model = await asyncio.to_thread(_get_embedding_model, self.embedding_model_name)
                            ce = await asyncio.to_thread(self._get_embedding, candidate.search_string, model)
                            ee = await asyncio.to_thread(self._get_embedding, existing.search_string, model)
                            if self._compute_similarity(ce, ee) > self.similarity_threshold:
                                duplicate = existing
                                break
                        except Exception:
                            logger.exception("Semantic intent dedup unavailable; retaining exact-query dedup")
                            model_unavailable = True
                if duplicate is not None:
                    candidate.intent_id = duplicate.intent_id
                    candidate.facet = duplicate.facet
                    candidate.status = duplicate.status
                    candidate.dispatched = duplicate.dispatched
                    candidate.novel = False
                    self._intent_turns[duplicate.intent_id] = self.session.turn_id
                    # A repeated pending intent may still need its first dispatch.
                    if not duplicate.dispatched and all(i.intent_id != duplicate.intent_id for i in novel_intents):
                        novel_intents.append(duplicate)
                    continue

                candidate.intent_id = self._generate_intent_id()
                candidate.novel = True
                candidate.status = IntentStatus.pending
                self.session.intent_set[candidate.intent_id] = candidate
                self._intent_turns[candidate.intent_id] = self.session.turn_id
                novel_intents.append(candidate)
                # Apply model correction hints only after identity checks and ID allocation.
                for old_id in candidate.supersedes:
                    old = self.session.intent_set.get(old_id)
                    if old and old.intent_id != candidate.intent_id and old.facet == candidate.facet and old not in replaced and correcting and not additive:
                        replaced.append(old)
                for old in replaced:
                    old.status = IntentStatus.superseded
                    old.superseded_by = candidate.intent_id
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
