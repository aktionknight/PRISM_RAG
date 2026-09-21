from slrag.controller.content_floor import evaluate_content_floor

def test_content_floor_dangling_preposition():
    # Dangling preposition -> WAIT
    decision = evaluate_content_floor("Who was he looking at", 1.0)
    assert decision is not None
    assert decision.decision == "WAIT"

def test_content_floor_no_anchors():
    # No nouns/entities -> WAIT
    decision = evaluate_content_floor("I want to", 1.0)
    assert decision is not None
    assert decision.decision == "WAIT"
    
def test_content_floor_pass():
    # Entity "Apple" -> passes floor
    decision = evaluate_content_floor("What does Apple do", 1.0)
    assert decision is None
