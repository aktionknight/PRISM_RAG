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

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.config = _load_config("retrieval")
        self.project_root = Path(__file__).resolve().parents[3]

        idx = self.config["index"]
        self.sparse_path = self.project_root / idx["sparse_path"]
        self.dense_path = self.project_root / idx["dense_path"]
        self.metadata_path = self.project_root / idx["metadata_path"]
        self.chunks_path = self.project_root / idx["chunks_path"]

        import os
        if output_dir is not None or os.environ.get("SLRAG_INDEX_DIR"):
            from slrag.core.paths import index_dir
            output = Path(output_dir) if output_dir is not None else index_dir()
            self.sparse_path = output / "bm25"
            self.dense_path = output / "faiss"
            self.metadata_path = output / "metadata.json"
            self.chunks_path = output / "chunks.jsonl"

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
            import torch
            from sentence_transformers import SentenceTransformer
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"Loading embedding model on {device}: {self.model_name}")
            self.embedding_model = SentenceTransformer(self.model_name, device=device)
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

        # ── 5. Probe Threshold Calibration (Index-Time Per-Corpus Tuning) ──
        logger.info("Calibrating probe thresholds from corpus prefix margin distribution...")
        self.calibrate_probe_thresholds(chunks, bm25_retriever)

        logger.info(
            f"Indexing complete: {len(chunks)} chunks, "
            f"sparse={self.sparse_path}, dense={self.dense_path}"
        )

    def calibrate_probe_thresholds(self, chunks: list[ChunkRecord], bm25_retriever: Any) -> dict[str, float]:
        """Calibrate tau_hi and tau_lo per corpus at index time.
        
        Samples prefixes from the corpus's own chunks, queries BM25 to compute
        empirical margin and entropy distributions, and sets tau_hi (75th percentile)
        and tau_lo (25th percentile).
        """
        import re
        import numpy as np
        import bm25s

        sampled_prefixes: list[str] = []
        for chunk in chunks:
            text = chunk.text.strip()
            if not text:
                continue
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            for line in lines:
                clean = re.sub(r'[*_#`\[\]]', '', line).strip()
                words = clean.split()
                if len(words) >= 4:
                    sampled_prefixes.append(" ".join(words[:min(5, len(words))]))
                if len(words) >= 8:
                    sampled_prefixes.append(" ".join(words[:min(9, len(words))]))
                if 4 <= len(words) <= 15:
                    sampled_prefixes.append(clean)
            if len(sampled_prefixes) >= 120:
                break

        sampled_prefixes = list(dict.fromkeys(sampled_prefixes))
        margins: list[float] = []
        entropies: list[float] = []

        if sampled_prefixes:
            for pref in sampled_prefixes:
                try:
                    q_tokens = bm25s.tokenize([pref], show_progress=False)
                    docs, scores = bm25_retriever.retrieve(q_tokens, k=10, show_progress=False)
                    s = scores[0]
                    if len(s) > 0 and s[0] > 0:
                        s1 = float(s[0])
                        s_rest = s[1:5]
                        mean_rest = float(np.mean(s_rest)) if len(s_rest) > 0 else 0.0
                        margin = (s1 - mean_rest) / s1 if s1 > 0 else 0.0
                        margins.append(margin)

                        total = float(np.sum(s))
                        if total > 0:
                            p = s / total
                            p = p[p > 0]
                            h_raw = -float(np.sum(p * np.log(p)))
                            h_norm = h_raw / float(np.log(len(s))) if len(s) > 1 else 0.0
                            entropies.append(h_norm)
                except Exception as e:
                    logger.debug(f"Prefix calibration probe skipped '{pref}': {e}")

        if len(margins) >= 5:
            tau_hi = float(np.percentile(margins, 75))
            tau_lo = float(np.percentile(margins, 25))
            tau_lo = max(0.04, min(tau_lo, 0.25))
            tau_hi = max(tau_lo + 0.05, min(tau_hi, 0.85))
            h_lo = float(np.percentile(entropies, 65)) if entropies else 0.65
            h_lo = max(0.40, min(h_lo, 0.85))
        else:
            tau_hi = 0.35
            tau_lo = 0.10
            h_lo = 0.65

        calib_data = {
            "tau_hi": round(tau_hi, 4),
            "tau_lo": round(tau_lo, 4),
            "h_lo": round(h_lo, 4),
            "sample_count": len(margins),
        }

        calib_file = self.chunks_path.parent / "probe_calibration.json"
        calib_file.parent.mkdir(parents=True, exist_ok=True)
        with open(calib_file, "w", encoding="utf-8") as f:
            json.dump(calib_data, f, indent=2)

        logger.info(
            f"Calibrated probe thresholds: tau_hi={tau_hi:.4f}, tau_lo={tau_lo:.4f}, "
            f"h_lo={h_lo:.4f} (from {len(margins)} sampled prefixes saved to {calib_file})"
        )
        return calib_data

    @classmethod
    def run_pipeline(cls, corpus_dir: Path, output_dir: str | Path | None = None) -> None:
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

        indexer = cls(output_dir=output_dir)
        indexer.build_and_save(chunks)
        
        # ── Run Phase 0 Facet Discovery ──
        from slrag.ingest.facet_discovery import run_facet_discovery
        logger.info("Starting Phase 0 Facet Discovery...")
        run_facet_discovery(
            corpus_dir=corpus_dir,
            index_dir=indexer.sparse_path.parent
        )
        
        logger.info("Ingest pipeline complete.")
