import pytest
import asyncio
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

from slrag.core.schemas import IntentStatus, SubIntent
from slrag.decompose.decomposer import Decomposer
from slrag.decompose.facets import FacetTagger
from slrag.decompose.intent_set import IntentSet
from slrag.decompose.overlap import OverlapMerger

@pytest.fixture
def mock_decomposer(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text("engine:\n  max_llm_calls_per_turn: 3")
    (config_dir / "facets.yaml").write_text("facets:\n  general:\n    description: default\n  pricing:\n    description: pricing\n")
    prompts_dir = config_dir / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "decompose.jinja").write_text("mock prompt")

    decomposer = Decomposer(config_dir=config_dir)
    return decomposer

@pytest.mark.asyncio
async def test_decomposer_syntactic_split(mock_decomposer):
    text = "Hello and welcome"
    splits = mock_decomposer._syntactic_split(text)
    assert isinstance(splits, list)
    assert len(splits) > 0

@pytest.mark.asyncio
async def test_decomposer_call_llm(mock_decomposer):
    with patch("slrag.decompose.decomposer.aiohttp.ClientSession") as mock_session:
        mock_session_inst = MagicMock()
        mock_session.return_value = mock_session_inst
        mock_session_inst.__aenter__.return_value = mock_session_inst
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"sub_intents": [{"query_nl": "test", "facet": "general", "novel": true, "search_string": "test"}]}'}}]
        }
        
        mock_post_ctx = MagicMock()
        mock_post_ctx.__aenter__.return_value = mock_response
        
        mock_session_inst.post.return_value = mock_post_ctx
        
        response = await mock_decomposer._call_llm("test prompt")
        assert response == {"sub_intents": [{"query_nl": "test", "facet": "general", "novel": True, "search_string": "test"}]}

@pytest.mark.asyncio
async def test_decomposer_decompose(mock_decomposer):
    with patch.object(mock_decomposer, "_call_llm", new_callable=AsyncMock) as mock_call_llm:
        mock_call_llm.return_value = {
            "sub_intents": [
                {"query_nl": "What is the price?", "facet": "pricing", "novel": True, "search_string": "price"}
            ]
        }
        
        intents = await mock_decomposer.decompose("What is the price?", {}, 1.0)
        assert len(intents) == 1
        assert intents[0].facet == "pricing"
        assert intents[0].query_nl == "What is the price?"

@pytest.fixture
def mock_facet_tagger(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    facets_path = config_dir / "facets.yaml"
    facets_path.write_text("facets:\n  general:\n    description: default\n  pricing:\n    description: pricing\n")
    
    with patch("slrag.decompose.facets.SentenceTransformer") as mock_st:
        mock_instance = MagicMock()
        mock_instance.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]])
        mock_st.return_value = mock_instance
        
        with patch("slrag.decompose.facets.HAS_SENTENCE_TRANSFORMERS", True):
            tagger = FacetTagger(facets_config_path=facets_path)
            tagger.facet_embeddings = np.array([[1.0, 0.0], [0.0, 1.0]])
            return tagger

def test_facet_tagger_tag(mock_facet_tagger):
    with patch("slrag.decompose.facets.cos_sim") as mock_cos_sim:
        mock_cos_sim.return_value = np.array([[0.1, 0.9]])
        mock_facet_tagger.encoder.encode.return_value = np.array([0.0, 1.0])
        facet = mock_facet_tagger.tag("how much does it cost?")
        assert facet == "pricing"

@pytest.fixture
def session_state():
    class MockSessionState:
        def __init__(self):
            self.intent_set = {}
        def get_pending_intents(self):
            return [i for i in self.intent_set.values() if i.status == IntentStatus.pending]
        def get_dispatched_intents(self):
            return [i for i in self.intent_set.values() if i.status == IntentStatus.dispatched]
    return MockSessionState()

@pytest.mark.asyncio
async def test_intent_set_add_intents(session_state):
    with patch("slrag.decompose.intent_set._get_embedding_model") as mock_get_model:
        mock_model = MagicMock()
        def encode_side_effect(text, **kwargs):
            if text == "first": return np.array([1.0, 0.0])
            if text == "second": return np.array([0.0, 1.0])
            if text == "duplicate": return np.array([1.0, 0.0])
            return np.array([0.5, 0.5])
        mock_model.encode.side_effect = encode_side_effect
        mock_get_model.return_value = mock_model
        
        intent_set = IntentSet(session=session_state)
        
        intent1 = SubIntent(intent_id="", facet="general", query_nl="first", search_string="first", novel=True, first_seen_ts=1.0, status=IntentStatus.pending)
        intent2 = SubIntent(intent_id="", facet="general", query_nl="second", search_string="second", novel=True, first_seen_ts=1.0, status=IntentStatus.pending)
        intent3 = SubIntent(intent_id="", facet="general", query_nl="duplicate", search_string="duplicate", novel=True, first_seen_ts=1.0, status=IntentStatus.pending)
        
        novel1 = await intent_set.add_intents([intent1, intent2])
        assert len(novel1) == 2
        
        novel2 = await intent_set.add_intents([intent3])
        assert len(novel2) == 0

def test_overlap_merger(session_state):
    merger = OverlapMerger()
    
    intent_a = SubIntent(intent_id="a", facet="general", query_nl="q", search_string="q", novel=True, first_seen_ts=1.0, status=IntentStatus.dispatched)
    intent_b = SubIntent(intent_id="b", facet="general", query_nl="q2", search_string="q2", novel=True, first_seen_ts=1.0, status=IntentStatus.dispatched)
    
    session_state.intent_set["a"] = intent_a
    session_state.intent_set["b"] = intent_b
    
    chunk1 = MagicMock(chunk_id="c1")
    chunk2 = MagicMock(chunk_id="c2")
    chunk3 = MagicMock(chunk_id="c3")
    
    res = merger.check_and_merge(session_state, "a", "b", [chunk1, chunk2], [chunk1, chunk2])
    assert res is True
    assert intent_b.status == IntentStatus.merged

    intent_c = SubIntent(intent_id="c", facet="general", query_nl="q3", search_string="q3", novel=True, first_seen_ts=1.0, status=IntentStatus.dispatched)
    session_state.intent_set["c"] = intent_c
    res2 = merger.check_and_merge(session_state, "a", "c", [chunk1], [chunk3])
    assert res2 is False
    assert intent_c.status == IntentStatus.dispatched

    intent_d = SubIntent(intent_id="d", facet="other", query_nl="q4", search_string="q4", novel=True, first_seen_ts=1.0, status=IntentStatus.dispatched)
    session_state.intent_set["d"] = intent_d
    res3 = merger.check_and_merge(session_state, "a", "d", [chunk1], [chunk1])
    assert res3 is False
    assert intent_d.status == IntentStatus.dispatched
