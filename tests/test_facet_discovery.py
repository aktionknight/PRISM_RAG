"""
tests/test_facet_discovery.py — Tests for the Phase 0 Facet Discovery pipeline.

Verifies Doc D §6 requirements:
  - test_reproducibility
  - test_detector_cascade_order
  - test_small_cluster_merge
  - test_general_facet_always_present
  - test_retrieval_bias_measured_not_guessed
  - test_facets_yaml_schema
  - test_edge_cases
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from slrag.ingest.facet_discovery import (
    ClusteringMeta,
    FacetDiscoveryPipeline,
    FacetEntry,
    FacetTaxonomy,
    run_facet_discovery,
)
from slrag.ingest.segmenter import CandidateUnit, StructureAgnosticSegmenter

# ═══════════════════════════════════════════════════════════════════
# Fixtures & Mocks
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_embedding_model():
    """Mock sentence-transformers model returning stable random vectors."""
    model = MagicMock()
    # Always return deterministic embeddings for a given input size
    def mock_encode(texts, **kwargs):
        np.random.seed(42)
        return np.random.rand(len(texts), 384).astype(np.float32)
    model.encode.side_effect = mock_encode
    return model


@pytest.fixture
def temp_corpus(tmp_path):
    """Creates a temporary corpus structure for segmenter tests."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    return corpus_dir


# ═══════════════════════════════════════════════════════════════════
# Test Segmenter Cascade (Doc D §6)
# ═══════════════════════════════════════════════════════════════════

class TestDetectorCascadeOrder:
    
    def test_markdown_detector_d(self, temp_corpus):
        (temp_corpus / "doc1.md").write_text("# H1\nText\n## H2\nText\n### H3\nText")
        segmenter = StructureAgnosticSegmenter()
        units, detector = segmenter.segment(temp_corpus)
        assert detector == "D"
        assert len(units) >= 3

    def test_numbered_sections_detector_b(self, temp_corpus):
        content = "1. First\ntext\n2. Second\ntext\n3. Third\ntext"
        (temp_corpus / "doc1.txt").write_text(content)
        segmenter = StructureAgnosticSegmenter()
        units, detector = segmenter.segment(temp_corpus)
        assert detector == "B"
        assert len(units) >= 3
        
    def test_typographic_heuristic_detector_c(self, temp_corpus):
        content = "Short Title\nHere is a much longer paragraph that provides context.\nAnother Short Title\nAnd more text here that spans multiple words.\nA Third Title\nFollowed by its body text.\n"
        (temp_corpus / "doc1.txt").write_text(content)
        segmenter = StructureAgnosticSegmenter()
        units, detector = segmenter.segment(temp_corpus)
        assert detector == "C"
        assert len(units) >= 3

    def test_plain_text_fallback_detector_e(self, temp_corpus):
        # Just a huge block of text, no structure
        content = "word " * 2000
        (temp_corpus / "doc1.txt").write_text(content)
        segmenter = StructureAgnosticSegmenter()
        units, detector = segmenter.segment(temp_corpus)
        assert detector == "E"
        assert len(units) > 0


# ═══════════════════════════════════════════════════════════════════
# Test Pipeline Core (Doc D §6)
# ═══════════════════════════════════════════════════════════════════

class TestFacetDiscoveryPipeline:

    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._get_model")
    def test_small_cluster_merge(self, mock_get_model, mock_embedding_model, tmp_path):
        """test_small_cluster_merge: tiny clusters must merge into neighbors."""
        mock_get_model.return_value = mock_embedding_model
        
        pipeline = FacetDiscoveryPipeline()
        # Generate 100 texts to make min_units_per_facet = max(3, 3) = 3
        units = [f"Text {i}" for i in range(100)]
        
        # Override the _cluster method to explicitly return a tiny cluster
        original_cluster = pipeline._cluster
        def mock_cluster(embeds, num_units):
            # 3 clusters: size 90, size 9, size 1 (should merge)
            labels = np.array([0]*90 + [1]*9 + [2]*1)
            return 3, 0.5, labels
            
        with patch.object(pipeline, "_cluster", side_effect=mock_cluster):
            taxonomy = pipeline.run(units, "E", "checksum123", tmp_path, tmp_path)
            
            # The cluster of size 1 should have been merged
            # Plus general facet -> total facets should be 3
            assert len(taxonomy.facets) == 3
            sizes = [f.unit_count for f in taxonomy.facets if f.facet_id != "general"]
            assert all(size >= 3 for size in sizes)

    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._get_model")
    def test_general_facet_always_present(self, mock_get_model, mock_embedding_model, tmp_path):
        mock_get_model.return_value = mock_embedding_model
        pipeline = FacetDiscoveryPipeline()
        units = [f"Text {i}" for i in range(20)]
        
        taxonomy = pipeline.run(units, "E", "checksum123", tmp_path, tmp_path)
        
        assert any(f.facet_id == "general" for f in taxonomy.facets)
        general_facet = next(f for f in taxonomy.facets if f.facet_id == "general")
        assert general_facet.retrieval_bias == "balanced"
        assert general_facet.bias_confidence is None


    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._get_model")
    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._calibrate_bias")
    def test_retrieval_bias_measured_not_guessed(self, mock_calibrate, mock_get_model, mock_embedding_model, tmp_path):
        mock_get_model.return_value = mock_embedding_model
        
        # Mock calibration to return "sparse" with confidence 0.15 for all non-general
        def mock_calib(facet, indices, texts, index_dir, chunks_path):
            if facet.facet_id == "general":
                return "balanced", None
            return "sparse", 0.15
            
        mock_calibrate.side_effect = mock_calib
        
        pipeline = FacetDiscoveryPipeline()
        units = [f"Text {i}" for i in range(20)]
        taxonomy = pipeline.run(units, "E", "checksum123", tmp_path, tmp_path)
        
        for facet in taxonomy.facets:
            if facet.facet_id != "general":
                assert facet.retrieval_bias == "sparse"
                assert facet.bias_confidence is not None
                assert facet.bias_confidence > 0

    def test_facets_yaml_schema(self):
        """Output validates against the Pydantic model for facets.yaml."""
        # Valid taxonomy
        data = {
            "generated_at": "2026-09-24T04:12:00Z",
            "corpus_checksum": "sha256:9f2a",
            "clustering": {"algorithm": "agglomerative", "linkage": "average", "metric": "cosine", "k": 7, "silhouette": 0.41, "seed": 42},
            "facets": [
                {
                    "facet_id": "cancellation_terms",
                    "display": "Cancellation & Refund Terms",
                    "description": "Policy language governing cancellation windows.",
                    "retrieval_bias": "sparse",
                    "bias_confidence": 0.83,
                    "unit_count": 14
                }
            ],
            "fallback_used": False,
            "detector_used": "B"
        }
        
        taxonomy = FacetTaxonomy.model_validate(data)
        assert taxonomy.facets[0].facet_id == "cancellation_terms"
        
        # Invalid bias
        data["facets"][0]["retrieval_bias"] = "invalid_bias"
        with pytest.raises(ValidationError):
            FacetTaxonomy.model_validate(data)

    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._get_model")
    def test_edge_case_few_units(self, mock_get_model, mock_embedding_model, tmp_path):
        mock_get_model.return_value = mock_embedding_model
        pipeline = FacetDiscoveryPipeline()
        units = ["Text 1", "Text 2"] # < 5
        
        taxonomy = pipeline.run(units, "E", "checksum123", tmp_path, tmp_path)
        
        assert len(taxonomy.facets) == 1
        assert taxonomy.facets[0].facet_id == "general"
        assert taxonomy.facets[0].unit_count == 2
        assert taxonomy.clustering.k == 0

    @patch("slrag.ingest.facet_discovery.FacetDiscoveryPipeline._get_model")
    def test_reproducibility(self, mock_get_model, mock_embedding_model, tmp_path):
        mock_get_model.return_value = mock_embedding_model
        pipeline = FacetDiscoveryPipeline(seed=42)
        units = [f"This is a sample text number {i} about some topic." for i in range(20)]
        
        tax1 = pipeline.run(units, "D", "checksum", tmp_path, tmp_path)
        
        # Run again
        pipeline2 = FacetDiscoveryPipeline(seed=42)
        tax2 = pipeline2.run(units, "D", "checksum", tmp_path, tmp_path)
        
        # Ensure they are byte-identical when dumped
        import yaml
        dump1 = yaml.dump(tax1.model_dump(), default_flow_style=False, sort_keys=False)
        # Update generated_at to match for equality check
        tax2.generated_at = tax1.generated_at
        dump2 = yaml.dump(tax2.model_dump(), default_flow_style=False, sort_keys=False)
        
        assert dump1 == dump2
