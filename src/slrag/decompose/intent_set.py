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

        Implements deterministic supersession rule:
        If a candidate has the same facet as an active intent, shares >= 1 slot key,
        and has a different value, mark the older one superseded unless an additive
        marker appears in the current window.
        """
        model = _get_embedding_model(self.embedding_model_name)
        novel_intents = []
        
        from slrag.core.config import get_controller_config
        config = get_controller_config()
        additive_markers = config.get("additive_markers", ["also", "as well", "too", "in addition", "and for"])
        
        has_additive = any(m in prefix.lower() for m in additive_markers)

        async with self._lock:
            for candidate in new_candidates:
                candidate_emb = self._get_embedding(candidate.search_string, model)
                is_duplicate = False
                
                # Check for LLM-emitted supersedes
                for old_id in candidate.supersedes:
                    if old_id in self.session.intent_set:
                        old_intent = self.session.intent_set[old_id]
                        if old_intent.status != IntentStatus.superseded:
                            old_intent.status = IntentStatus.superseded
                            old_intent.superseded_by = candidate.intent_id
                            candidate.facet = old_intent.facet  # Inherit facet

                for existing_intent in self.session.intent_set.values():
                    if existing_intent.status == IntentStatus.superseded:
                        continue
                        
                    # Deterministic Slot Conflict
                    if existing_intent.facet == candidate.facet:
                        shared_keys = set(candidate.slots.keys()) & set(existing_intent.slots.keys())
                        conflict = False
                        for k in shared_keys:
                            if candidate.slots[k] != existing_intent.slots[k]:
                                conflict = True
                                break
                                
                        if conflict:
                            if not has_additive:
                                existing_intent.status = IntentStatus.superseded
                                # candidate hasn't got an ID yet, we'll set superseded_by later
                                existing_intent.superseded_by = "pending_" + str(len(novel_intents))
                                candidate.facet = existing_intent.facet
                            continue # Don't deduplicate if conflicting, either it supersedes or both live
                    
                    # Deduplication
                    if existing_intent.facet == candidate.facet:
                        existing_emb = self._get_embedding(
                            existing_intent.search_string, model
                        )
                        sim = self._compute_similarity(candidate_emb, existing_emb)

                        if sim > self.similarity_threshold:
                            cand_nums = set(re.findall(r'\d+', candidate.search_string))
                            exist_nums = set(re.findall(r'\d+', existing_intent.search_string))
                            if cand_nums != exist_nums:
                                logger.info(f"Skipping dedup for changed numbers: {cand_nums} vs {exist_nums}")
                                continue

                            is_duplicate = True
                            candidate.intent_id = existing_intent.intent_id
                            candidate.novel = False
                            candidate.status = existing_intent.status
                            logger.info(
                                f"Intent deduplicated (sim={sim:.3f}): "
                                f"'{candidate.search_string}' matches existing "
                                f"'{existing_intent.search_string}'"
                            )
                            break

                if not is_duplicate:
                    new_id = self._generate_intent_id()
                    candidate.intent_id = new_id
                    candidate.novel = True
                    candidate.status = IntentStatus.pending

                    self.session.intent_set[new_id] = candidate
                    novel_intents.append(candidate)
                    logger.debug(
                        f"Added novel intent: {new_id} ({candidate.search_string})"
                    )
                    
            # Fix up pending superseded_by
            for intent in self.session.intent_set.values():
                if intent.superseded_by and intent.superseded_by.startswith("pending_"):
                    idx = int(intent.superseded_by.split("_")[1])
                    if idx < len(novel_intents):
                        intent.superseded_by = novel_intents[idx].intent_id
                        
                        # Telemetry: intent_superseded
                        from slrag.telemetry.bus import get_bus
                        import time
                        from slrag.core.events import EVT_INTENT_ADDED
                        
                        bus = get_bus()
                        try:
                            # Actually we don't have a specific EVT_INTENT_SUPERSEDED in events.py, we can just emit it
                            # Instruction says "Emit an intent_superseded telemetry event with old/new ids, slot diff, and the triggering text window."
                            import asyncio
                            from slrag.api.ws_server import _emit_telemetry
                            
                            diff = {
                                "old": intent.slots,
                                "new": novel_intents[idx].slots
                            }
                            
                            te = _emit_telemetry(
                                session_id=self.session.session_id,
                                turn_id=self.session.turn_id,
                                ts_stream_s=time.time(), # approximate
                                component="intent_set",
                                event_type="intent_superseded",
                                payload={
                                    "old_id": intent.intent_id,
                                    "new_id": novel_intents[idx].intent_id,
                                    "slot_diff": diff,
                                    "text_window": prefix
                                }
                            )
                            # Create task so it doesn't block
                            asyncio.create_task(bus.emit(te))
                        except Exception as e:
                            logger.warning(f"Failed to emit intent_superseded telemetry: {e}")

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
