"""
retrieve/rrf.py — Reciprocal Rank Fusion with facet-routed weighting (S-8).

Combines sparse and dense retrieval results using weighted RRF where
the BM25/dense weight ratio is determined by the sub-intent's facet.

  score(d) = w_sparse / (k + rank_sparse(d)) + w_dense / (k + rank_dense(d))

Facet weights from config/retrieval.yaml → facet_weights.
"""

from __future__ import annotations

import logging
from typing import Any

from slrag.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


def apply_rrf(
    sparse_results: list[RetrievedChunk],
    dense_results: list[RetrievedChunk],
    facet: str,
    config: dict[str, Any],
) -> list[RetrievedChunk]:
    """Apply facet-routed weighted Reciprocal Rank Fusion.

    Args:
        sparse_results: BM25 results sorted by score descending.
        dense_results: Dense retrieval results sorted by score descending.
        facet: The facet key determining BM25/dense weight balance.
        config: Retrieval config dict (from config/retrieval.yaml).

    Returns:
        Fused results sorted by RRF score descending.
    """
    k = config.get("rrf", {}).get("k", 60)

    # ── Load dynamic weights from facets.yaml (Phase 0 output) ──
    from pathlib import Path
    import yaml

    project_root = Path(__file__).resolve().parents[3]
    index_facets = project_root / ".index" / "facets.yaml"
    
    w_sparse, w_dense = 0.5, 0.5
    found_facet = False

    if index_facets.exists():
        try:
            with open(index_facets, "r", encoding="utf-8") as f:
                facets_data = yaml.safe_load(f)
                
            for f_data in facets_data.get("facets", []):
                if f_data.get("facet_id") == facet:
                    bias = f_data.get("retrieval_bias", "balanced")
                    bias_config = config.get("rrf", {}).get("bias_weights", {})
                    if bias == "sparse":
                        sparse_cfg = bias_config.get("sparse", {"bm25": 0.8, "dense": 0.2})
                        w_sparse, w_dense = sparse_cfg.get("bm25", 0.8), sparse_cfg.get("dense", 0.2)
                    elif bias == "dense":
                        dense_cfg = bias_config.get("dense", {"bm25": 0.2, "dense": 0.8})
                        w_sparse, w_dense = dense_cfg.get("bm25", 0.2), dense_cfg.get("dense", 0.8)
                    found_facet = True
                    break
        except Exception as e:
            logger.warning(f"Failed to read dynamic facet weights: {e}")
            
    if not found_facet:
        # Fallback to hardcoded retrieval.yaml config
        facet_weights = config.get("facet_weights", {})
        weights = facet_weights.get(
            facet, facet_weights.get("default", {"bm25": 0.5, "dense": 0.5})
        )
        w_sparse = weights.get("bm25", 0.5)
        w_dense = weights.get("dense", 0.5)

    # Build rank maps (1-indexed)
    sparse_ranks: dict[str, int] = {
        chunk.chunk_id: rank + 1
        for rank, chunk in enumerate(sparse_results)
    }
    dense_ranks: dict[str, int] = {
        chunk.chunk_id: rank + 1
        for rank, chunk in enumerate(dense_results)
    }

    # Merge into a single chunk map (keep the richer metadata from whichever source)
    chunk_map: dict[str, RetrievedChunk] = {}
    for chunk in sparse_results:
        chunk_map[chunk.chunk_id] = chunk
    for chunk in dense_results:
        if chunk.chunk_id not in chunk_map:
            chunk_map[chunk.chunk_id] = chunk

    # Compute fused RRF scores
    fused_scores: dict[str, float] = {}
    for chunk_id in chunk_map:
        score = 0.0
        if chunk_id in sparse_ranks:
            score += w_sparse / (k + sparse_ranks[chunk_id])
        if chunk_id in dense_ranks:
            score += w_dense / (k + dense_ranks[chunk_id])
        fused_scores[chunk_id] = score

    # Sort by fused score and update the score field
    sorted_ids = sorted(fused_scores, key=fused_scores.get, reverse=True)  # type: ignore[arg-type]
    result: list[RetrievedChunk] = []
    for chunk_id in sorted_ids:
        original = chunk_map[chunk_id]
        fused = RetrievedChunk(
            chunk_id=original.chunk_id,
            doc_id=original.doc_id,
            section_id=original.section_id,
            text=original.text,
            score=fused_scores[chunk_id],
            citation_label=original.citation_label,
        )
        result.append(fused)

    logger.debug(
        f"RRF fused {len(sparse_results)} sparse + {len(dense_results)} dense "
        f"→ {len(result)} candidates (facet={facet}, w_bm25={w_sparse}, w_dense={w_dense})"
    )
    return result
