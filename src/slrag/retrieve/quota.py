"""
retrieve/quota.py — Facet-quota context assembly with MMR diversity.

Assembles the final evidence bundle from reranked candidates:
  1. Guaranteed 2 chunks per active sub-intent (no facet starves another)
  2. Remainder allocated by factual density score
  3. MMR (λ≈0.7) applied within each facet for diversity
  4. Total budget: 3000 tokens

Directly prevents a dominant facet from crowding out thin ones —
the brief's "diluting context windows" risk, solved by quota.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from slrag.core.schemas import FusedContext, RetrievedChunk
from slrag.retrieve.density import score_factual_density

logger = logging.getLogger(__name__)


def _approx_token_count(text: str) -> int:
    """Approximate token count (roughly 1.33 tokens per whitespace-word)."""
    return max(1, int(len(text.split()) * 1.33))


def _mmr_select(
    candidates: list[RetrievedChunk],
    selected_texts: list[str],
    n: int,
    lambda_param: float = 0.7,
) -> list[RetrievedChunk]:
    """Maximal Marginal Relevance selection within a facet.

    Balances relevance (score) against diversity (dissimilarity
    to already-selected chunks).  Uses word-overlap Jaccard as
    a cheap proxy for semantic similarity.
    """
    if not candidates:
        return []

    result: list[RetrievedChunk] = []
    remaining = list(candidates)

    for _ in range(min(n, len(remaining))):
        best_score = -1.0
        best_idx = 0

        for i, cand in enumerate(remaining):
            relevance = cand.score

            # Max similarity to already-selected chunks
            cand_words = set(cand.text.lower().split())
            max_sim = 0.0
            for sel_text in selected_texts + [c.text for c in result]:
                sel_words = set(sel_text.lower().split())
                if cand_words or sel_words:
                    jaccard = len(cand_words & sel_words) / max(
                        len(cand_words | sel_words), 1
                    )
                    max_sim = max(max_sim, jaccard)

            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = i

        result.append(remaining.pop(best_idx))

    return result


def assemble_context(
    candidates_by_intent: dict[str, list[RetrievedChunk]],
    config: dict[str, Any],
) -> FusedContext:
    """Assemble the final context bundle with facet-quota allocation.

    Args:
        candidates_by_intent: Mapping of intent_id → reranked chunks.
        config: Retrieval config dict.

    Returns:
        FusedContext with chunks, token budget tracking, and facet coverage.
    """
    ctx_config = config.get("context", {})
    budget = ctx_config.get("budget_tokens", 3000)
    guaranteed = ctx_config.get("guaranteed_chunks_per_intent", 2)
    mmr_lambda = ctx_config.get("mmr_lambda", 0.7)

    selected_chunks: list[RetrievedChunk] = []
    total_tokens = 0
    facet_coverage: dict[str, int] = {}

    # ── Phase 1: Guaranteed quota — 2 chunks per intent ──
    remainder_candidates: list[RetrievedChunk] = []

    for intent_id, chunks in candidates_by_intent.items():
        facet_coverage[intent_id] = 0
        added = 0

        for chunk in chunks:
            if added < guaranteed:
                tokens = _approx_token_count(chunk.text)
                if total_tokens + tokens <= budget:
                    selected_chunks.append(chunk)
                    total_tokens += tokens
                    facet_coverage[intent_id] += 1
                    added += 1
                else:
                    remainder_candidates.append(chunk)
            else:
                remainder_candidates.append(chunk)

    # ── Phase 2: Remainder by factual density + MMR diversity ──
    # Sort remainder by factual density (descending)
    remainder_candidates.sort(
        key=lambda c: score_factual_density(c.text), reverse=True
    )

    # Apply MMR to avoid redundancy
    selected_texts = [c.text for c in selected_chunks]
    diverse_remainder = _mmr_select(
        remainder_candidates, selected_texts, len(remainder_candidates), mmr_lambda
    )

    for chunk in diverse_remainder:
        tokens = _approx_token_count(chunk.text)
        if total_tokens + tokens > budget:
            break

        # Prevent exact duplicate additions
        if any(c.chunk_id == chunk.chunk_id for c in selected_chunks):
            continue

        selected_chunks.append(chunk)
        total_tokens += tokens

    logger.info(
        f"Context assembled: {len(selected_chunks)} chunks, "
        f"{total_tokens}/{budget} tokens, "
        f"coverage={facet_coverage}"
    )

    return FusedContext(
        chunks=selected_chunks,
        total_tokens=total_tokens,
        facet_coverage=facet_coverage,
        contradictions=[],  # Populated by contradiction.py separately
    )
