"""
retrieve/pool.py — Session EvidencePool manager with near-duplicate dedup.

Manages the session-scoped evidence store.  ALL retrievals land here —
confirmed, speculative, or cancelled.  Near-duplicate chunks (cosine > 0.95)
are merged with citation-label union so provenance never drops.
"""

from __future__ import annotations

import logging

import numpy as np

from slrag.core.schemas import EvidencePoolEntry, RetrievedChunk
from slrag.core.session import SessionState

logger = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def add_to_pool(
    session: SessionState,
    chunk: RetrievedChunk,
    intent_id: str,
    ts_stream_s: float,
    chunk_embedding: list[float] | None = None,
    speculative: bool = False,
    dedup_threshold: float = 0.95,
) -> None:
    """Add a retrieved chunk to the session EvidencePool, with dedup.

    If a near-duplicate (cosine > threshold) already exists in the pool,
    the citation labels are merged (union) and the score is updated.
    Otherwise, a new entry is created.

    Args:
        session: The current session state.
        chunk: The retrieved chunk to add.
        intent_id: Which sub-intent triggered this retrieval.
        ts_stream_s: Stream time of the retrieval.
        chunk_embedding: Dense embedding of the chunk (for dedup).
        speculative: Whether this is from a speculative branch.
        dedup_threshold: Cosine similarity threshold for near-duplicate detection.
    """
    # Check for near-duplicates if embedding is available
    if chunk_embedding:
        for existing in session.evidence_pool.values():
            if existing.embedding:
                sim = _cosine_similarity(chunk_embedding, existing.embedding)
                if sim >= dedup_threshold:
                    # Near-duplicate found — merge
                    logger.debug(
                        f"Dedup merge: {chunk.chunk_id} ↔ {existing.chunk_id} "
                        f"(cos={sim:.3f})"
                    )

                    # Union citation labels
                    existing_labels = set(existing.citation_label.split(", "))
                    existing_labels.add(chunk.citation_label)
                    existing.citation_label = ", ".join(sorted(existing_labels))

                    # Update score for this intent
                    existing.scores_by_subquery[intent_id] = max(
                        existing.scores_by_subquery.get(intent_id, 0.0),
                        chunk.score,
                    )

                    # If confirmed (not speculative), upgrade
                    if not speculative:
                        existing.speculative = False

                    return

    # No duplicate found — create new entry
    entry = EvidencePoolEntry(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        section_id=chunk.section_id,
        citation_label=chunk.citation_label,
        text=chunk.text,
        embedding=chunk_embedding,
        scores_by_subquery={intent_id: chunk.score},
        first_retrieved_ts=ts_stream_s,
        used_in_versions=[],
        speculative=speculative,
    )
    session.add_evidence(entry)


def get_pool_chunks_for_intent(
    session: SessionState,
    intent_id: str,
    top_k: int = 10,
) -> list[RetrievedChunk]:
    """Retrieve the best chunks from the EvidencePool for a given intent.

    Used by the delta engine to resolve refinement from the pool
    before issuing new corpus queries.

    Args:
        session: The current session state.
        intent_id: The intent to retrieve pool chunks for.
        top_k: Maximum number of chunks to return.

    Returns:
        List of RetrievedChunk sorted by score for this intent.
    """
    scored: list[tuple[float, EvidencePoolEntry]] = []
    for entry in session.evidence_pool.values():
        score = entry.scores_by_subquery.get(intent_id, 0.0)
        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        RetrievedChunk(
            chunk_id=entry.chunk_id,
            doc_id=entry.doc_id,
            section_id=entry.section_id,
            text=entry.text,
            score=score,
            citation_label=entry.citation_label,
        )
        for score, entry in scored[:top_k]
    ]
