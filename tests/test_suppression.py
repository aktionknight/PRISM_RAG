from slrag.controller.suppression import evaluate_suppression

def test_suppression_presentation_verb():
    # Should suppress (NO_RETRIEVAL)
    decision = evaluate_suppression("Can you summarize that?", 1.0)
    assert decision is not None
    assert decision.decision == "NO_RETRIEVAL"
    
def test_suppression_anaphora():
    # Should suppress
    decision = evaluate_suppression("What about this?", 1.0)
    assert decision is not None
    assert decision.decision == "NO_RETRIEVAL"
    
def test_suppression_pass():
    # Should pass (None)
    decision = evaluate_suppression("What is the capital of France?", 1.0)
    assert decision is None
