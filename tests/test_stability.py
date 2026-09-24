from slrag.controller.stability import evaluate_stability

def test_stability_first_turn(session, mock_encoder):
    # First turn sets embedding but shouldn't trigger
    decision = evaluate_stability("Apple revenue", 1.0, session, mock_encoder)
    assert decision is None
    assert session.last_embedding is not None

def test_stability_stabilised(session, mock_encoder_static):
    # Static encoder means zero drift. 
    # Need 2 content anchors (e.g. 'Apple', 'revenue') to trigger
    evaluate_stability("Apple revenue", 1.0, session, mock_encoder_static) # Sets baseline
    
    # Next identical embedding should trigger RETRIEVE because drift is 0
    decision = evaluate_stability("Apple revenue in 2023", 2.0, session, mock_encoder_static)
    assert decision is not None
    assert decision.decision == "RETRIEVE"
