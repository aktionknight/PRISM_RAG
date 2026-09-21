from slrag.controller.cascade import RetrievalController
from slrag.core.schemas import TranscriptChunk

def test_cascade_suppression(session, mock_index_discriminative, mock_encoder_static):
    controller = RetrievalController(session, mock_index_discriminative, mock_encoder_static)
    
    chunk = TranscriptChunk(t_s=1.0, text="Can you summarize that", is_final=False)
    decision = controller.process_chunk(chunk)
    
    assert decision.decision == "NO_RETRIEVAL"

def test_cascade_refractory(session, mock_index_discriminative, mock_encoder_static):
    controller = RetrievalController(session, mock_index_discriminative, mock_encoder_static)
    
    # First retrieve
    chunk1 = TranscriptChunk(t_s=1.0, text="apple products", is_final=False)
    dec1 = controller.process_chunk(chunk1)
    assert dec1.decision == "RETRIEVE"
    
    # Immediate second call should hit refractory period (WAIT)
    chunk2 = TranscriptChunk(t_s=1.1, text="and", is_final=False)
    dec2 = controller.process_chunk(chunk2)
    assert dec2.decision == "WAIT"
    assert dec2.reason == "refractory_period"

def test_cascade_probe_retrieve(session, mock_index_discriminative, mock_encoder):
    controller = RetrievalController(session, mock_index_discriminative, mock_encoder)
    
    chunk = TranscriptChunk(t_s=1.0, text="apple products", is_final=False)
    decision = controller.process_chunk(chunk)
    
    assert decision.decision == "RETRIEVE"
    assert session.current_prefix == "" # Cleared after retrieval

def test_cascade_fallthrough(session, mock_index_ambiguous, mock_encoder):
    controller = RetrievalController(session, mock_index_ambiguous, mock_encoder)
    
    chunk = TranscriptChunk(t_s=1.0, text="I want to know about", is_final=False)
    decision = controller.process_chunk(chunk)
    
    # Ambiguous index -> wait from probe
    assert decision.decision == "WAIT"
