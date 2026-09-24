"""
retrieve/rerank.py — Cross-encoder reranker.

Uses bge-reranker-base to rerank the fused top-30 candidates
down to top-8 per sub-query.  Dispatched to a thread pool for
non-blocking async operation.
"""

from __future__ import annotations

import asyncio
import logging

from slrag.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-encoder reranker using bge-reranker-base (or compatible).

    Scores query-document pairs and returns the top-k by reranker score.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-base") -> None:
        self.model_name = model_name
        self.model = None
        self.tokenizer = None
        self._load_model()

    def _load_model(self) -> None:
        """Load the cross-encoder model and tokenizer."""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name
            )
            self.model.eval()

            # Move to GPU if available
            try:
                import torch
                if torch.cuda.is_available():
                    self.model = self.model.cuda()
                    logger.info(f"Reranker on CUDA: {self.model_name}")
                else:
                    logger.info(f"Reranker on CPU: {self.model_name}")
            except ImportError:
                logger.info(f"Reranker loaded (torch not available for GPU): {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load reranker model {self.model_name}: {e}")

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        """Rerank chunks by cross-encoder relevance to the query.

        Args:
            query: The search query.
            chunks: Candidate chunks to rerank.
            top_k: Number of top results to return after reranking.

        Returns:
            Top-k chunks sorted by reranker score (descending).
        """
        if not self.model or not self.tokenizer or not chunks:
            logger.warning("Reranker not available — returning original order")
            return chunks[:top_k]

        try:
            import torch

            def _do_rerank() -> list[float]:
                pairs = [[query, chunk.text] for chunk in chunks]
                with torch.no_grad():
                    inputs = self.tokenizer(
                        pairs,
                        padding=True,
                        truncation=True,
                        return_tensors="pt",
                        max_length=512,
                    )
                    if torch.cuda.is_available():
                        inputs = {k: v.cuda() for k, v in inputs.items()}

                    logits = self.model(**inputs, return_dict=True).logits
                    scores = logits.view(-1).float()

                if torch.cuda.is_available():
                    scores = scores.cpu()
                return scores.numpy().tolist()

            scores = await asyncio.to_thread(_do_rerank)

            # Pair chunks with new scores
            reranked: list[RetrievedChunk] = []
            for chunk, score in zip(chunks, scores):
                reranked.append(RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    section_id=chunk.section_id,
                    text=chunk.text,
                    score=float(score),
                    citation_label=chunk.citation_label,
                ))

            reranked.sort(key=lambda c: c.score, reverse=True)
            logger.debug(
                f"Reranked {len(chunks)} → top-{top_k} "
                f"(score range: {reranked[0].score:.3f}–{reranked[-1].score:.3f})"
            )
            return reranked[:top_k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return chunks[:top_k]
