import pytest
from slrag.controller.suppression import evaluate_suppression
from slrag.controller.cascade import RetrievalController
from slrag.core.session import ControllerState
from slrag.core.schemas import TranscriptChunk

def test_suppression_presentation_restructure_cases():
    """True presentation-only turns must trigger NO_RETRIEVAL with reason presentation_restructure."""
    turns = [
        "repeat that in two bullets",
        "summarize your last answer",
        "can you make it shorter",
        "rephrase that in simpler terms",
    ]
    for turn in turns:
        decision = evaluate_suppression(turn, 0.5)
        assert decision is not None, f"Expected suppression for '{turn}'"
        assert decision.decision == "NO_RETRIEVAL"
        assert decision.reason == "presentation_restructure"

def test_suppression_information_queries_not_suppressed():
    """Information queries and comparative clauses must NOT be suppressed at Stage 0."""
    queries = [
        "tell me why I should choose it over anything else on",
        "list out the features of the content studio project",
        "what is the cancellation policy?",
        "why should I choose it?",
        "how does this work?",
    ]
    for q in queries:
        decision = evaluate_suppression(q, 0.5)
        assert decision is None, f"Query '{q}' should NOT be suppressed at Stage 0"

def test_suppression_indexed_document_terms_not_suppressed():
    """Queries referencing indexed document terms must NOT be suppressed."""
    # Even if phrased with pronouns or formatting requests
    queries = [
        "features of the content studio project in bullets",
        "tell me about campaign launchpad",
    ]
    for q in queries:
        decision = evaluate_suppression(q, 0.5)
        assert decision is None, f"Document-referencing query '{q}' should NOT be suppressed"
