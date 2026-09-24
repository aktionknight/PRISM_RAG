from slrag.core.schemas import TranscriptChunk, ControllerDecision, Claim

def test_transcript_chunk_schema():
    chunk = TranscriptChunk(t_s=1.0, text="hello", is_final=False)
    assert chunk.text == "hello"

def test_controller_decision_schema():
    decision = ControllerDecision(
        t_s=2.5,
        decision="RETRIEVE",
        reason="test",
        confidence=0.9
    )
    assert decision.decision == "RETRIEVE"
