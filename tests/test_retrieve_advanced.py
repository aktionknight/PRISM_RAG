import pytest
import os
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import numpy as np

from slrag.core.schemas import RetrievedChunk, EvidencePoolEntry, FusedContext
from slrag.core.session import SessionState

# Patch density
mock_density = MagicMock()
mock_density.score_factual_density = lambda text: len(text.split())

from slrag.retrieve.sparse import SparseRetriever
from slrag.retrieve.dense import DenseRetriever
from slrag.retrieve.pool import add_to_pool, get_pool_chunks_for_intent, _cosine_similarity
from slrag.retrieve.quota import assemble_context, _approx_token_count, _mmr_select
from slrag.retrieve.rerank import Reranker
from slrag.retrieve.contradiction import ContradictionGating, extract_typed_slots

@pytest.fixture
def mock_bm25s():
    with patch.dict("sys.modules", {"bm25s": MagicMock()}):
        import bm25s
        yield bm25s

@pytest.fixture
def mock_faiss_and_st():
    with patch.dict("sys.modules", {"faiss": MagicMock(), "sentence_transformers": MagicMock()}):
        import faiss
        import sentence_transformers
        yield faiss, sentence_transformers

@pytest.fixture
def mock_transformers():
    with patch.dict("sys.modules", {"transformers": MagicMock(), "torch": MagicMock()}):
        import transformers
        import torch
        yield transformers, torch


# Sparse tests
@pytest.mark.asyncio
async def test_sparse_retriever(tmp_path, mock_bm25s):
    index_path = tmp_path / "index"
    index_path.mkdir()
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps({"chunk_id": "c1", "doc_id": "d1", "section_id": "s1", "citation_label": "c1", "text": "hello world", "ordinal": 0}) + "\n")
    
    mock_bm25_instance = MagicMock()
    mock_bm25s.BM25.load.return_value = mock_bm25_instance
    mock_bm25s.tokenize.return_value = "tokenized"
    
    # simulate search returning results and scores
    doc = MagicMock()
    doc.get.side_effect = lambda k, d=None: {"chunk_id": "c1", "text": "hello world"}.get(k, d)
    # the retrieve function in bm25s usually returns (documents, scores)
    mock_bm25_instance.retrieve.return_value = ([[{"chunk_id": "c1", "text": "hello world", "doc_id": "d1", "section_id": "s1", "citation_label": "c1"}]], [[0.9]])
    
    retriever = SparseRetriever(index_path, chunks_path)
    assert len(retriever.chunks) == 1
    
    results = await retriever.search("hello")
    assert len(results) == 1
    assert results[0].chunk_id == "c1"
    assert results[0].score == 0.9

@pytest.mark.asyncio
async def test_sparse_retriever_empty(tmp_path, mock_bm25s):
    index_path = tmp_path / "empty_index"
    chunks_path = tmp_path / "empty_chunks.jsonl"
    chunks_path.write_text("")
    retriever = SparseRetriever(index_path, chunks_path)
    results = await retriever.search("hello")
    assert results == []

# Dense tests
@pytest.mark.asyncio
async def test_dense_retriever(tmp_path, mock_faiss_and_st):
    faiss, st = mock_faiss_and_st
    
    index_path = tmp_path / "index.faiss"
    index_path.write_text("dummy")
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps({"chunk_id": "c1", "doc_id": "d1", "section_id": "s1", "citation_label": "c1", "text": "hello world", "ordinal": 0}) + "\n")
    
    mock_index = MagicMock()
    mock_index.ntotal = 1
    mock_index.search.return_value = (np.array([[0.9]]), np.array([[0]]))
    faiss.read_index.return_value = mock_index
    
    mock_model = MagicMock()
    mock_model.encode.return_value = [[0.1, 0.2, 0.3]]
    st.SentenceTransformer.return_value = mock_model
    
    retriever = DenseRetriever(index_path, chunks_path)
    
    # Test encode
    emb = retriever.encode_query("hello")
    assert list(emb) == [0.1, 0.2, 0.3]
    
    # Test search
    results = await retriever.search("hello")
    assert len(results) == 1
    assert results[0].chunk_id == "c1"

@pytest.mark.asyncio
async def test_dense_retriever_empty(tmp_path, mock_faiss_and_st):
    index_path = tmp_path / "empty_index.faiss"
    chunks_path = tmp_path / "empty_chunks.jsonl"
    chunks_path.write_text("")
    faiss, st = mock_faiss_and_st
    mock_index = MagicMock()
    mock_index.ntotal = 0
    faiss.read_index.return_value = mock_index

    retriever = DenseRetriever(index_path, chunks_path)
    results = await retriever.search("hello")
    assert results == []

# Pool tests
def test_cosine_similarity():
    sim = _cosine_similarity([1.0, 0.0], [1.0, 0.0])
    assert abs(sim - 1.0) < 1e-6
    sim2 = _cosine_similarity([1.0, 0.0], [0.0, 1.0])
    assert abs(sim2 - 0.0) < 1e-6

def test_pool_operations():
    session = SessionState(session_id="test")
    chunk = RetrievedChunk(chunk_id="c1", doc_id="d1", section_id="s1", text="text", score=0.8, citation_label="d1 s1")
    
    add_to_pool(session, chunk, "intent1", 10.0, chunk_embedding=[1.0, 0.0], speculative=False)
    
    assert len(session.evidence_pool) == 1
    
    # add near duplicate
    chunk2 = RetrievedChunk(chunk_id="c2", doc_id="d1", section_id="s2", text="text2", score=0.9, citation_label="d1 s2")
    add_to_pool(session, chunk2, "intent1", 11.0, chunk_embedding=[0.99, 0.0], speculative=False)
    
    assert len(session.evidence_pool) == 1
    entry = list(session.evidence_pool.values())[0]
    assert "d1 s1" in entry.citation_label
    assert "d1 s2" in entry.citation_label
    assert entry.scores_by_subquery["intent1"] == 0.9
    
    results = get_pool_chunks_for_intent(session, "intent1")
    assert len(results) == 1
    assert results[0].score == 0.9


# Quota tests
def test_approx_token_count():
    assert _approx_token_count("hello world") == int(2 * 1.33)

def test_mmr_select():
    c1 = RetrievedChunk(chunk_id="c1", doc_id="d1", section_id="s1", text="hello world", score=0.9, citation_label="c1")
    c2 = RetrievedChunk(chunk_id="c2", doc_id="d2", section_id="s2", text="hello world", score=0.8, citation_label="c2")
    c3 = RetrievedChunk(chunk_id="c3", doc_id="d3", section_id="s3", text="foo bar", score=0.7, citation_label="c3")
    
    candidates = [c1, c2, c3]
    selected = _mmr_select(candidates, [], 2, lambda_param=0.5)
    
    assert len(selected) == 2
    assert selected[0].chunk_id == "c1"

def test_quota_assemble_context():
    candidates = {
        "intent1": [
            RetrievedChunk(chunk_id="c1", doc_id="d1", section_id="s1", text="word " * 10, score=0.9, citation_label="c1"),
            RetrievedChunk(chunk_id="c2", doc_id="d2", section_id="s2", text="different text here", score=0.8, citation_label="c2"),
            RetrievedChunk(chunk_id="c3", doc_id="d3", section_id="s3", text="more different things", score=0.7, citation_label="c3"),
        ],
        "intent2": [
            RetrievedChunk(chunk_id="c4", doc_id="d4", section_id="s4", text="unique content", score=0.95, citation_label="c4"),
        ]
    }
    
    config = {"context": {"budget_tokens": 100, "guaranteed_chunks_per_intent": 2}}
    ctx = assemble_context(candidates, config)
    
    assert len(ctx.chunks) == 4
    assert ctx.facet_coverage["intent1"] == 3  # 2 guaranteed + 1 remainder
    assert ctx.facet_coverage["intent2"] == 1  # 1 guaranteed


# Rerank tests
@pytest.mark.asyncio
async def test_reranker(mock_transformers):
    transformers, torch = mock_transformers
    mock_model = MagicMock()
    mock_logits = MagicMock()
    mock_logits.view.return_value.float.return_value.numpy.return_value.tolist.return_value = [0.9, 0.2]
    
    mock_outputs = MagicMock()
    mock_outputs.logits = mock_logits
    mock_model.return_value = mock_outputs
    
    transformers.AutoModelForSequenceClassification.from_pretrained.return_value = mock_model
    
    torch.cuda.is_available.return_value = False
    
    mock_no_grad = MagicMock()
    mock_no_grad.__enter__ = MagicMock()
    mock_no_grad.__exit__ = MagicMock()
    torch.no_grad.return_value = mock_no_grad
    
    reranker = Reranker()
    chunks = [
        RetrievedChunk(chunk_id="c1", doc_id="d1", section_id="s1", text="good", score=0.0, citation_label="c1"),
        RetrievedChunk(chunk_id="c2", doc_id="d2", section_id="s2", text="bad", score=0.0, citation_label="c2")
    ]
    
    results = await reranker.rerank("query", chunks)
    assert len(results) == 2
    assert results[0].score == 0.9


# Contradiction tests
@pytest.mark.asyncio
async def test_contradiction_gating(mock_transformers):
    transformers, _ = mock_transformers
    
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = [{"label": "contradiction", "score": 0.9}]
    transformers.pipeline.return_value = mock_pipeline
    
    gating = ContradictionGating()
    
    chunks = [
        RetrievedChunk(chunk_id="c1", doc_id="d1", section_id="s1", text="Cost is $50", score=0.0, citation_label="c1"),
        RetrievedChunk(chunk_id="c2", doc_id="d2", section_id="s2", text="Cost is $60", score=0.0, citation_label="c2")
    ]
    
    contradictions = await gating.detect_contradictions(chunks, "cost")
    assert len(contradictions) == 1
    assert contradictions[0]["slot"] == "currency"
    assert contradictions[0]["nli_score"] == 0.9

def test_extract_typed_slots():
    text = "The CEO approved the budget of $1,000 for a duration of 5 weeks starting 2023-01-01, representing 50.5%."
    slots = extract_typed_slots(text)
    assert "CEO" in slots.get("approval_role", [])
    assert "$1,000" in slots.get("currency", [])
    assert "5 weeks" in slots.get("duration", [])
    assert "2023-01-01" in slots.get("date", [])
    assert "50.5%" in slots.get("percentage", [])
