"""
retrieve/dense.py — Dense FAISS retriever.

Loads a pre-built FAISS IndexFlatIP index and the bge-small-en-v1.5
embedding model. Provides async search via thread dispatch.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from slrag.core.schemas import RetrievedChunk

logger = logging.getLogger(__name__)


class DenseRetriever:
    """Dense retriever backed by FAISS IndexFlatIP + sentence-transformers.

    Uses inner-product search on L2-normalised embeddings, giving
    cosine similarity semantics.
    """

    def __init__(
        self,
        index_path: str | Path,
        chunks_path: str | Path,
        model_name: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        self.index_path = Path(index_path)
        self.chunks_path = Path(chunks_path)
        self.model_name = model_name
        self.index = None
        self.model = None
        self.chunks: list[dict] = []
        self._load_index()

    def _load_index(self) -> None:
        """Load FAISS index, chunk metadata, and embedding model."""
        try:
            import faiss
            from sentence_transformers import SentenceTransformer

            # FAISS index
            faiss_file = self.index_path
            if faiss_file.exists():
                self.index = faiss.read_index(str(faiss_file))
                logger.info(
                    f"FAISS index loaded from {faiss_file} "
                    f"({self.index.ntotal} vectors)"
                )
            else:
                logger.warning(f"FAISS index not found at {faiss_file}")

            # Chunk metadata
            if self.chunks_path.exists():
                with open(self.chunks_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            self.chunks.append(json.loads(line))
                logger.info(f"Loaded {len(self.chunks)} chunk records")
            else:
                logger.warning(f"Chunks file not found at {self.chunks_path}")

            # Embedding model
            self.model = SentenceTransformer(self.model_name)
            logger.info(f"Embedding model loaded: {self.model_name}")

        except Exception as e:
            logger.error(f"Failed to load dense index: {e}")

    def encode_query(self, query: str) -> list[float]:
        """Encode a query string into a dense embedding vector."""
        if self.model is None:
            raise RuntimeError("Embedding model not loaded")
        embedding = self.model.encode(
            [query], normalize_embeddings=True
        )
        import numpy as np

        return np.asarray(embedding[0], dtype=float).tolist()   # ndarray from the model, list from some backends

    async def search(self, query: str, top_k: int = 50) -> list[RetrievedChunk]:
        """Search the FAISS index for the given query.

        Args:
            query: Search query string.
            top_k: Number of top results to return.

        Returns:
            List of RetrievedChunk sorted by cosine similarity (descending).
        """
        if not self.index or not self.model or not self.chunks:
            logger.warning("Dense index not loaded — returning empty results")
            return []

        try:
            import numpy as np

            def _do_search() -> tuple:
                query_vector = self.model.encode(
                    [query], normalize_embeddings=True
                )
                query_vector = np.array(query_vector, dtype=np.float32)
                actual_k = min(top_k, self.index.ntotal)
                scores, indices = self.index.search(query_vector, actual_k)
                return scores[0], indices[0]

            scores, indices = await asyncio.to_thread(_do_search)

            retrieved: list[RetrievedChunk] = []
            for score, idx in zip(scores, indices):
                idx = int(idx)
                if idx < 0 or idx >= len(self.chunks):
                    continue
                item = self.chunks[idx]
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
            logger.error(f"Dense search failed: {e}")
            return []
