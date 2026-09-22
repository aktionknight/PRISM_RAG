"""
ingest/indexer.py — Hybrid index builder (BM25 + FAISS).

Builds both sparse (bm25s) and dense (bge-small-en-v1.5 → FAISS IndexFlatIP)
indexes from chunked corpus documents.  Persists:
  - BM25 index at .index/bm25/
  - FAISS index at .index/faiss
  - metadata.json (chunk_id → citation_label mapping)
  - chunks.jsonl (full chunk records)

Invoked via `slrag index` CLI command — never shipped baked (HC-2).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from slrag.ingest.chunker import IngestChunk

logger = logging.getLogger(__name__)


def _load_config(name: str) -> dict:
    """Load a YAML config file from the project config/ directory."""
    path = Path(__file__).resolve().parents[3] / "config" / f"{name}.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class HybridIndexer:
    """Builds and persists BM25 + FAISS indexes from IngestChunks.

    Configuration read from config/retrieval.yaml:
      - index.sparse_path, index.dense_path, index.metadata_path, index.chunks_path
      - embedding.model_name, embedding.dimension
    """

    def __init__(self) -> None:
        self.config = _load_config("retrieval")
        self.project_root = Path(__file__).resolve().parents[3]

        idx = self.config["index"]
        self.sparse_path = self.project_root / idx["sparse_path"]
        self.dense_path = self.project_root / idx["dense_path"]
        self.metadata_path = self.project_root / idx["metadata_path"]
        self.chunks_path = self.project_root / idx["chunks_path"]

        emb = self.config["embedding"]
        self.model_name: str = emb["model_name"]
        self.dimension: int = emb["dimension"]

        self.embedding_model = None  # lazy-loaded

    def _ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        for p in [self.sparse_path, self.dense_path, self.metadata_path, self.chunks_path]:
            p.parent.mkdir(parents=True, exist_ok=True)

    def _load_embedding_model(self):
        """Lazy-load the sentence transformer model."""
        if self.embedding_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self.model_name}")
            self.embedding_model = SentenceTransformer(self.model_name)
        return self.embedding_model

    def build_and_save(self, chunks: list[IngestChunk]) -> None:
        """Build both indexes and persist all artifacts."""
        if not chunks:
            logger.warning("No chunks provided to indexer — skipping.")
            return

        self._ensure_dirs()
        corpus_texts = [chunk.text for chunk in chunks]
        logger.info(f"Building indexes for {len(chunks)} chunks")

        # ── 1. Sparse Index (BM25s) ──
        logger.info("Building BM25 sparse index...")
        import bm25s

        corpus_tokens = bm25s.tokenize(corpus_texts)
        bm25_retriever = bm25s.BM25()
        bm25_retriever.index(corpus_tokens)

        # Ensure sparse_path directory exists
        self.sparse_path.mkdir(parents=True, exist_ok=True)
        bm25_retriever.save(str(self.sparse_path))
        logger.info(f"BM25 index saved to {self.sparse_path}")

        # ── 2. Dense Index (FAISS IndexFlatIP) ──
        logger.info("Building FAISS dense index...")
        import faiss
        import numpy as np

        model = self._load_embedding_model()
        embeddings = model.encode(
            corpus_texts,
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=64,
        )
        embeddings = np.array(embeddings, dtype=np.float32)

        # IndexFlatIP with normalized embeddings gives cosine similarity
        faiss_index = faiss.IndexFlatIP(self.dimension)
        faiss_index.add(embeddings)
        faiss.write_index(faiss_index, str(self.dense_path))
        logger.info(f"FAISS index saved to {self.dense_path} ({faiss_index.ntotal} vectors)")

        # ── 3. Metadata (chunk_id → citation_label) ──
        logger.info("Saving metadata...")
        metadata = {chunk.chunk_id: chunk.citation_label for chunk in chunks}
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # ── 4. Chunks JSONL (full records) ──
        logger.info("Saving chunks JSONL...")
        with open(self.chunks_path, "w", encoding="utf-8") as f:
            for chunk in chunks:
                record = {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "section_id": chunk.section_id,
                    "ordinal": chunk.ordinal,
                    "citation_label": chunk.citation_label,
                    "text": chunk.text,
                }
                f.write(json.dumps(record) + "\n")

        logger.info(
            f"Indexing complete: {len(chunks)} chunks, "
            f"sparse={self.sparse_path}, dense={self.dense_path}"
        )

    @classmethod
    def run_pipeline(cls, corpus_dir: Path) -> None:
        """Run the full ingest pipeline: load → chunk → index."""
        from slrag.ingest.loader import MarkdownLoader
        from slrag.ingest.chunker import StructureAwareChunker

        logger.info(f"Running ingest pipeline on corpus: {corpus_dir}")

        loader = MarkdownLoader(corpus_dir)
        sections = loader.load_all()
        if not sections:
            logger.error("No sections found in corpus — aborting.")
            return

        chunker = StructureAwareChunker()
        chunks = chunker.chunk_documents(sections)
        if not chunks:
            logger.error("Chunker produced no chunks — aborting.")
            return

        indexer = cls()
        indexer.build_and_save(chunks)
        logger.info("Ingest pipeline complete.")
