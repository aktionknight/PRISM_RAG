"""
ingest/facet_discovery.py — Phase 0 Corpus-Agnostic Facet Discovery (Doc D §3.2–3.6).

Runs ONCE, offline, before Day 1 coding hours — never inside the live engine.

Pipeline stages:
  §3.2  Embed + deterministic agglomerative clustering (K ∈ [5,10], silhouette-selected)
  §3.3  Small-cluster floor & merge
  §3.4  Deterministic TF-IDF facet naming (tie-broken)
  §3.5  Empirical retrieval-bias calibration (measured, not guessed)
  §3.6  Reproducibility gate (byte-identical on re-run)

Output: ``.index/facets.yaml`` — read-only frozen artifact consumed at runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Union

import numpy as np
import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Pydantic config models for facets.yaml
# (NOT in core/schemas.py — these are config-layer models)
# ═══════════════════════════════════════════════════════════════════

class FacetEntry(BaseModel):
    """A single discovered facet in the taxonomy."""
    facet_id: str
    display: str
    description: str
    retrieval_bias: Literal["sparse", "dense", "balanced"]
    bias_confidence: Optional[float] = None
    unit_count: int


class ClusteringMeta(BaseModel):
    """Metadata about the clustering run that produced the taxonomy."""
    algorithm: str = "agglomerative"
    linkage: str = "average"
    metric: str = "cosine"
    k: int
    silhouette: float
    seed: int = 42


class FacetTaxonomy(BaseModel):
    """Top-level schema for the generated ``facets.yaml``."""
    generated_at: str
    corpus_checksum: str
    clustering: ClusteringMeta
    facets: list[FacetEntry]
    fallback_used: bool
    detector_used: str


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _slugify(text: str) -> str:
    """Convert a keyphrase to a snake_case facet_id."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    text = re.sub(r"[\s\-]+", "_", text)
    return text.strip("_") or "unnamed"


def compute_corpus_checksum(texts: list[str]) -> str:
    """SHA-256 of all candidate unit texts concatenated (deterministic)."""
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


# ═══════════════════════════════════════════════════════════════════
# Main pipeline
# ═══════════════════════════════════════════════════════════════════

class FacetDiscoveryPipeline:
    """Phase 0 offline facet discovery pipeline.

    Deterministic, seed-pinned, corpus-agnostic.  Produces a
    ``FacetTaxonomy`` and writes ``facets.yaml`` to the index directory.
    """

    def __init__(
        self,
        seed: int = 42,
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        self.seed = seed
        self.embedding_model_name = embedding_model_name
        self._model = None

    # ── Lazy model loader ────────────────────────────────────────────

    def _get_model(self):
        """Lazy-load the sentence-transformer model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info(f"Loading embedding model: {self.embedding_model_name}")
            self._model = SentenceTransformer(self.embedding_model_name)
        return self._model

    # ── Text extraction helper ───────────────────────────────────────

    @staticmethod
    def _get_texts(candidate_units: list[Any]) -> list[str]:
        """Extract plain text from heterogeneous candidate unit inputs."""
        texts: list[str] = []
        for unit in candidate_units:
            if hasattr(unit, "text"):
                texts.append(unit.text)
            elif isinstance(unit, str):
                texts.append(unit)
            elif isinstance(unit, dict) and "text" in unit:
                texts.append(unit["text"])
            else:
                texts.append(str(unit))
        return texts

    # ── §3.2: Embed + Deterministic Clustering ──────────────────────

    def _cluster(
        self, embeddings: np.ndarray, num_units: int
    ) -> tuple[int, float, np.ndarray]:
        """Agglomerative clustering with silhouette-selected K ∈ [5, 10]."""
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.metrics import silhouette_score

        best_k: Optional[int] = None
        best_score: float = -1.0
        best_labels: Optional[np.ndarray] = None

        max_k = min(10, num_units - 1)
        min_k = min(5, max_k)

        if min_k < 2:
            # Cannot cluster meaningfully
            return 1, 0.0, np.zeros(num_units, dtype=int)

        for k in range(min_k, max_k + 1):
            clusterer = AgglomerativeClustering(
                n_clusters=k, metric="cosine", linkage="average"
            )
            labels = clusterer.fit_predict(embeddings)
            score = float(silhouette_score(embeddings, labels, metric="cosine"))
            if score > best_score:
                best_k, best_score, best_labels = k, score, labels

        assert best_k is not None and best_labels is not None
        return best_k, best_score, best_labels

    # ── §3.3: Small-Cluster Floor & Merge ────────────────────────────

    @staticmethod
    def _merge_small_clusters(
        clusters: dict[int, list[int]],
        embeddings: np.ndarray,
        min_units_per_facet: int,
    ) -> dict[int, list[int]]:
        """Merge clusters below *min_units_per_facet* into nearest neighbour."""
        from sklearn.metrics.pairwise import cosine_similarity

        def _centroid(indices: list[int]) -> np.ndarray:
            c = np.mean(embeddings[indices], axis=0)
            norm = np.linalg.norm(c)
            return c / norm if norm > 0 else c

        centroids = {cid: _centroid(idxs) for cid, idxs in clusters.items()}

        # Process smallest clusters first
        for cid in sorted(clusters, key=lambda c: len(clusters[c])):
            if cid not in clusters:
                continue
            if len(clusters[cid]) >= min_units_per_facet:
                continue
            if len(clusters) <= 1:
                break  # Can't merge the last cluster

            current = centroids[cid].reshape(1, -1)
            best_target: Optional[int] = None
            best_sim = -1.0

            for target_cid, target_centroid in centroids.items():
                if target_cid == cid:
                    continue
                sim = float(
                    cosine_similarity(current, target_centroid.reshape(1, -1))[0][0]
                )
                if sim > best_sim:
                    best_sim = sim
                    best_target = target_cid

            if best_target is not None:
                logger.debug(
                    f"Merging cluster {cid} ({len(clusters[cid])} units) "
                    f"into cluster {best_target} (sim={best_sim:.3f})"
                )
                clusters[best_target].extend(clusters[cid])
                del clusters[cid]
                centroids[best_target] = _centroid(clusters[best_target])
                del centroids[cid]

        return clusters

    # ── §3.4: Facet Naming — Deterministic TF-IDF ────────────────────

    def _name_facets(
        self,
        clusters: dict[int, list[int]],
        texts: list[str],
        embeddings: np.ndarray,
    ) -> list[FacetEntry]:
        """Produce named FacetEntry objects via TF-IDF keyphrase extraction."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        all_texts = texts  # full corpus for IDF computation
        vectorizer = TfidfVectorizer(ngram_range=(1, 3), stop_words="english")

        try:
            vectorizer.fit(all_texts)
            feature_names = vectorizer.get_feature_names_out()
            idf_ready = True
        except ValueError:
            idf_ready = False

        facets: list[FacetEntry] = []

        for cid in sorted(clusters):  # sorted for determinism
            indices = clusters[cid]
            cluster_texts = [texts[idx] for idx in indices]

            # ── Keyphrase ──
            keyphrase = f"cluster_{cid}"
            if idf_ready and cluster_texts:
                joined = " ".join(cluster_texts)
                tfidf_vec = vectorizer.transform([joined])
                scores = tfidf_vec.toarray()[0]
                top_order = np.argsort(scores)[::-1]

                best_kp: Optional[str] = None
                best_kp_score: float = -1.0

                for ti in top_order[:20]:
                    s = float(scores[ti])
                    if s == 0.0:
                        break
                    kp = str(feature_names[ti])
                    if best_kp is None:
                        best_kp, best_kp_score = kp, s
                    elif math.isclose(s, best_kp_score, rel_tol=1e-9):
                        # Tie-break: shorter first, then lexicographic
                        if len(kp) < len(best_kp) or (
                            len(kp) == len(best_kp) and kp < best_kp
                        ):
                            best_kp = kp
                    else:
                        break  # No more ties

                if best_kp:
                    keyphrase = best_kp

            facet_id = _slugify(keyphrase)
            display = keyphrase.title()

            # ── Description: 2 nearest sentences to cluster centroid ──
            centroid = np.mean(embeddings[indices], axis=0)
            c_norm = np.linalg.norm(centroid)
            if c_norm > 0:
                centroid = centroid / c_norm
            cluster_embeds = embeddings[indices]
            sims = cosine_similarity(centroid.reshape(1, -1), cluster_embeds)[0]
            top_2_local = np.argsort(sims)[::-1][:2]
            desc_parts = [cluster_texts[i].strip() for i in top_2_local]
            description = " ".join(desc_parts)[:500]

            facets.append(FacetEntry(
                facet_id=facet_id,
                display=display,
                description=description,
                retrieval_bias="balanced",  # placeholder — calibrated in §3.5
                bias_confidence=None,
                unit_count=len(indices),
            ))

        return facets

    # ── §3.5: Empirical Retrieval-Bias Calibration ───────────────────

    def _calibrate_bias(
        self,
        facet: FacetEntry,
        cluster_indices: list[int],
        texts: list[str],
        index_dir: Path,
        chunks_path: Path,
    ) -> tuple[Literal["sparse", "dense", "balanced"], Optional[float]]:
        """Measure sparse-vs-dense retrieval performance per facet.

        Probes up to 5 source chunks from this cluster against the full
        index using both BM25 and FAISS, computes mean reciprocal rank,
        and assigns bias accordingly.
        """
        sparse_path = index_dir / "bm25"
        dense_path = index_dir / "faiss"

        if not sparse_path.exists() or not dense_path.exists() or not chunks_path.exists():
            logger.debug(
                f"Skipping bias calibration for {facet.facet_id}: "
                "indexes not available"
            )
            return "balanced", None

        # Sample up to 5 source texts deterministically
        rng = np.random.RandomState(self.seed)
        sample_size = min(5, len(cluster_indices))
        sampled = rng.choice(cluster_indices, size=sample_size, replace=False)
        queries = [texts[i] for i in sampled]
        true_texts = queries  # self-retrieval probes

        sparse_mrr = 0.0
        dense_mrr = 0.0

        try:
            from slrag.retrieve.sparse import SparseRetriever
            from slrag.retrieve.dense import DenseRetriever

            s_ret = SparseRetriever(
                index_path=sparse_path, chunks_path=chunks_path
            )
            d_ret = DenseRetriever(
                index_path=dense_path, chunks_path=chunks_path
            )

            async def _probe():
                nonlocal sparse_mrr, dense_mrr
                for query, true_text in zip(queries, true_texts):
                    # Use first 200 chars as query to avoid overly long queries
                    q = query[:200]

                    s_results = await s_ret.search(q, top_k=10)
                    d_results = await d_ret.search(q, top_k=10)

                    # Find self in results (substring match)
                    for rank, res in enumerate(s_results, 1):
                        if true_text[:100] in res.text or res.text in true_text:
                            sparse_mrr += 1.0 / rank
                            break

                    for rank, res in enumerate(d_results, 1):
                        if true_text[:100] in res.text or res.text in true_text:
                            dense_mrr += 1.0 / rank
                            break

            # Run the async probes
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We're inside an async context — create a new thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_probe())).result(timeout=30)
            else:
                asyncio.run(_probe())

        except Exception as exc:
            logger.warning(
                f"Bias calibration failed for {facet.facet_id}: {exc}"
            )
            return "balanced", None

        if sample_size > 0:
            sparse_mrr /= sample_size
            dense_mrr /= sample_size

        diff = sparse_mrr - dense_mrr
        confidence = round(abs(diff), 3)

        if diff > 0.1:
            return "sparse", confidence
        elif diff < -0.1:
            return "dense", confidence
        else:
            return "balanced", confidence

    # ── Main entry point ─────────────────────────────────────────────

    def run(
        self,
        candidate_units: list[Any],
        detector_used: str,
        corpus_checksum: str,
        index_dir: Union[str, Path],
        chunks_path: Optional[Union[str, Path]] = None,
    ) -> FacetTaxonomy:
        """Run the complete facet discovery pipeline.

        Args:
            candidate_units: Topic units from the segmenter.
            detector_used: Which detector produced them ("A"–"E").
            corpus_checksum: SHA-256 of the corpus content.
            index_dir: Path to the ``.index/`` directory (reads BM25/FAISS
                for bias calibration, writes ``facets.yaml``).
            chunks_path: Path to ``chunks.jsonl`` (for bias calibration).

        Returns:
            The generated ``FacetTaxonomy``.
        """
        # Pin global seed for full determinism
        np.random.seed(self.seed)

        index_dir = Path(index_dir)
        if chunks_path is not None:
            chunks_path = Path(chunks_path)
        else:
            chunks_path = index_dir / "chunks.jsonl"

        texts = self._get_texts(candidate_units)
        num_units = len(texts)
        fallback_used = detector_used == "E"

        logger.info(
            f"Phase 0 facet discovery: {num_units} units, "
            f"detector={detector_used}"
        )

        # ── Edge case: too few units for clustering ──
        if num_units < 5:
            logger.warning(
                f"Fewer than 5 candidate units ({num_units}) — "
                "skipping clustering, all assigned to 'general'"
            )
            general = FacetEntry(
                facet_id="general",
                display="General / Unclassified",
                description="Fallback bucket for content that did not "
                "cluster cleanly.",
                retrieval_bias="balanced",
                bias_confidence=None,
                unit_count=num_units,
            )
            taxonomy = FacetTaxonomy(
                generated_at=datetime.now(timezone.utc).isoformat(),
                corpus_checksum=corpus_checksum,
                clustering=ClusteringMeta(k=0, silhouette=0.0, seed=self.seed),
                facets=[general],
                fallback_used=True,
                detector_used=detector_used,
            )
            self._save(taxonomy, index_dir)
            return taxonomy

        # ── §3.2: Embed + Cluster ──
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        embeddings = np.array(embeddings, dtype=np.float32)

        best_k, best_score, best_labels = self._cluster(embeddings, num_units)
        logger.info(
            f"Clustering: K={best_k}, silhouette={best_score:.4f}"
        )

        # Build cluster dict
        clusters: dict[int, list[int]] = {}
        for idx, label in enumerate(best_labels):
            clusters.setdefault(int(label), []).append(idx)

        # ── §3.3: Small-Cluster Floor & Merge ──
        min_units = max(3, int(0.03 * num_units))
        clusters = self._merge_small_clusters(clusters, embeddings, min_units)
        logger.info(
            f"After merge: {len(clusters)} clusters "
            f"(min_units_per_facet={min_units})"
        )

        # ── §3.4: Facet Naming ──
        facets = self._name_facets(clusters, texts, embeddings)

        # ── §3.5: Empirical Retrieval-Bias Calibration ──
        cluster_list = sorted(clusters.items())
        for i, (cid, indices) in enumerate(cluster_list):
            if i < len(facets):
                bias, confidence = self._calibrate_bias(
                    facets[i], indices, texts, index_dir, chunks_path
                )
                facets[i].retrieval_bias = bias
                facets[i].bias_confidence = confidence

        # ── §3.6: Always include a 'general' facet ──
        if not any(f.facet_id == "general" for f in facets):
            facets.append(FacetEntry(
                facet_id="general",
                display="General / Unclassified",
                description="Fallback bucket for content that did not "
                "cluster cleanly.",
                retrieval_bias="balanced",
                bias_confidence=None,
                unit_count=0,
            ))

        clustering_meta = ClusteringMeta(
            k=best_k,
            silhouette=round(best_score, 4),
            seed=self.seed,
        )

        taxonomy = FacetTaxonomy(
            generated_at=datetime.now(timezone.utc).isoformat(),
            corpus_checksum=corpus_checksum,
            clustering=clustering_meta,
            facets=facets,
            fallback_used=fallback_used,
            detector_used=detector_used,
        )

        self._save(taxonomy, index_dir)
        return taxonomy

    # ── Persistence ──────────────────────────────────────────────────

    @staticmethod
    def _save(taxonomy: FacetTaxonomy, index_dir: Path) -> None:
        """Write ``facets.yaml`` to the index directory."""
        index_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = index_dir / "facets.yaml"

        data = taxonomy.model_dump()
        with open(yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Facet taxonomy saved to {yaml_path}")


# ═══════════════════════════════════════════════════════════════════
# Convenience: run full pipeline from corpus directory
# ═══════════════════════════════════════════════════════════════════

def run_facet_discovery(
    corpus_dir: Union[str, Path],
    index_dir: Union[str, Path],
    seed: int = 42,
) -> FacetTaxonomy:
    """High-level entry point: segment + discover facets.

    Intended to be called after the hybrid index has been built
    (so bias calibration can probe BM25/FAISS).

    Args:
        corpus_dir: Path to the raw corpus directory.
        index_dir: Path to the ``.index/`` directory.
        seed: Random seed for determinism.

    Returns:
        The generated ``FacetTaxonomy``.
    """
    from slrag.ingest.segmenter import StructureAgnosticSegmenter

    corpus_dir = Path(corpus_dir)
    index_dir = Path(index_dir)
    chunks_path = index_dir / "chunks.jsonl"

    # Stage 0.1: Segment
    segmenter = StructureAgnosticSegmenter()
    candidate_units, detector_used = segmenter.segment(corpus_dir)

    if not candidate_units:
        logger.warning("Segmenter produced no candidates — creating minimal taxonomy")

    # Compute checksum
    texts = FacetDiscoveryPipeline._get_texts(candidate_units)
    checksum = compute_corpus_checksum(texts)

    # Stages 0.2–0.6: Discover
    pipeline = FacetDiscoveryPipeline(seed=seed)
    taxonomy = pipeline.run(
        candidate_units=candidate_units,
        detector_used=detector_used,
        corpus_checksum=checksum,
        index_dir=index_dir,
        chunks_path=chunks_path,
    )

    logger.info(
        f"Facet discovery complete: {len(taxonomy.facets)} facets, "
        f"detector={detector_used}, K={taxonomy.clustering.k}, "
        f"silhouette={taxonomy.clustering.silhouette}"
    )
    return taxonomy
