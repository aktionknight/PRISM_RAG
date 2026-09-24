"""
retrieve/sparse.py — BM25 sparse retriever.

Loads a pre-built bm25s index and provides async search over
the indexed corpus chunks.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from slrag.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class SparseRetriever:
    """BM25 sparse retriever backed by bm25s.

    Loads the index from disk on init. Provides async search
    that dispatches BM25 scoring to a thread pool.
    """

    def __init__(self, index_path: str | Path, chunks_path: str | Path) -> None:
        self.index_path = Path(index_path)
        self.chunks_path = Path(chunks_path)
        self.bm25 = None
        self.chunks: list[dict] = []
        self._load_index()

    def _load_index(self) -> None:
        """Load the BM25 index and chunk metadata from disk."""
        try:
            import bm25s

            if self.index_path.exists():
                self.bm25 = bm25s.BM25.load(str(self.index_path))
                logger.info(f"BM25 index loaded from {self.index_path}")
            else:
                logger.warning(f"BM25 index not found at {self.index_path}")

            if self.chunks_path.exists():
                with open(self.chunks_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self.chunks.append(json.loads(line))
                logger.info(f"Loaded {len(self.chunks)} chunk records")
            else:
                logger.warning(f"Chunks file not found at {self.chunks_path}")
        except Exception as e:
            logger.error(f"Failed to load sparse index: {e}")

    async def search(self, query: str, top_k: int = 50) -> list[RetrievedChunk]:
        """Search the BM25 index for the given query.

        Args:
            query: Search query string.
            top_k: Number of top results to return.

        Returns:
            List of RetrievedChunk sorted by BM25 score (descending).
        """
        if not self.bm25 or not self.chunks:
            logger.warning("Sparse index not loaded — returning empty results")
            return []

        try:
            import bm25s

            def _do_search() -> tuple:
                tokenized_query = bm25s.tokenize([query])
                actual_k = min(top_k, len(self.chunks))
                results, scores = self.bm25.retrieve(
                    tokenized_query, corpus=self.chunks, k=actual_k
                )
                return results[0], scores[0]

            results, scores = await asyncio.to_thread(_do_search)

            retrieved: list[RetrievedChunk] = []
            for item, score in zip(results, scores):
                if not isinstance(item, dict):
                    continue
                doc_id = item.get("doc_id", "")
                section_id = item.get("section_id", "")
                retrieved.append(RetrievedChunk(
                    chunk_id=item.get("chunk_id", ""),
                    doc_id=doc_id,
                    section_id=section_id,
                    text=item.get("text", ""),
                    score=float(score),
                    citation_label=item.get(
                        "citation_label", f"{doc_id} §{section_id}"
                    ),
                ))

            return retrieved
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []
