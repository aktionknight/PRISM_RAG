from slrag.controller.probe import evaluate_probe

def test_probe_empty():
    decision = evaluate_probe("", 1.0, None)
    assert decision.decision == "WAIT"

def test_probe_discriminative(mock_index_discriminative):
    # 'apple' triggers peaked scores in mock -> RETRIEVE
    decision = evaluate_probe("apple products", 1.0, mock_index_discriminative)
    assert decision is not None
    assert decision.decision == "RETRIEVE"

def test_probe_ambiguous(mock_index_ambiguous):
    # flat scores -> WAIT
    decision = evaluate_probe("stuff", 1.0, mock_index_ambiguous)
    assert decision is not None
    assert decision.decision == "WAIT"

def test_probe_no_index():
    # Pass to Stage 3 if no index
    decision = evaluate_probe("hello", 1.0, None)
    assert decision is None
