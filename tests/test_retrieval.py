"""
tests/test_retrieval.py — Tests for retrieval pipeline components.
"""

import pytest

from slrag.core.schemas import RetrievedChunk
from slrag.retrieve.rrf import apply_rrf
from slrag.retrieve.density import score_factual_density


class TestRRF:
    def test_basic_fusion(self):
        """RRF should combine sparse and dense results."""
        sparse = [
            RetrievedChunk(chunk_id="c1", doc_id="D1", section_id="1",
                           text="text1", score=10.0, citation_label="D1 §1"),
            RetrievedChunk(chunk_id="c2", doc_id="D2", section_id="2",
                           text="text2", score=8.0, citation_label="D2 §2"),
        ]
        dense = [
            RetrievedChunk(chunk_id="c2", doc_id="D2", section_id="2",
                           text="text2", score=0.95, citation_label="D2 §2"),
            RetrievedChunk(chunk_id="c3", doc_id="D3", section_id="1",
                           text="text3", score=0.85, citation_label="D3 §1"),
        ]
        config = {
            "rrf": {"k": 60},
            "facet_weights": {"default": {"bm25": 0.5, "dense": 0.5}},
        }

        fused = apply_rrf(sparse, dense, "venue_capacity", config)

        # c2 should be ranked highest (appears in both)
        assert fused[0].chunk_id == "c2"
        assert len(fused) == 3  # c1, c2, c3

    def test_facet_weight_routing(self):
        """Policy facets should boost sparse weight."""
        sparse = [
            RetrievedChunk(chunk_id="c1", doc_id="D1", section_id="1",
                           text="t1", score=10.0, citation_label="D1 §1"),
        ]
        dense = [
            RetrievedChunk(chunk_id="c2", doc_id="D2", section_id="2",
                           text="t2", score=0.95, citation_label="D2 §2"),
        ]

        config = {
            "rrf": {"k": 60},
            "facet_weights": {
                "cancellation_terms": {"bm25": 0.7, "dense": 0.3},
                "default": {"bm25": 0.5, "dense": 0.5},
            },
        }

        fused = apply_rrf(sparse, dense, "cancellation_terms", config)
        # With higher BM25 weight, c1 (sparse-only) should score higher
        assert fused[0].chunk_id == "c1"


class TestFactualDensity:
    def test_dense_text(self):
        """Text with many factual markers should score high."""
        text = ("The Grand Hall costs $5,000 per day on weekdays. "
                "A 50% non-refundable deposit is required. "
                "Late payments will incur a 5% weekly penalty.")
        score = score_factual_density(text)
        assert score > 0.1  # Should be relatively high

    def test_sparse_text(self):
        """Text with few factual markers should score low."""
        text = ("The venue is a nice place to hold events. "
                "It has good facilities and friendly staff.")
        score = score_factual_density(text)
        assert score < 0.1  # Should be relatively low

    def test_empty_text(self):
        """Empty text should score 0."""
        assert score_factual_density("") == 0.0
