import pytest
from slrag.controller.suppression import evaluate_suppression
from slrag.controller.cascade import RetrievalController
from slrag.core.session import ControllerState
from slrag.core.schemas import TranscriptChunk

def test_one_line_summary_stays_suppressed_across_chunks(monkeypatch):
    import slrag.controller.cascade as cascade
    monkeypatch.setattr(cascade, "_get_encoder", lambda *args: (_ for _ in ()).throw(
        AssertionError("presentation request must not initialize encoder")))
    controller = RetrievalController(ControllerState())
    for n, text in enumerate(["summarize the previous answer", " in one", " line"]):
        decision = controller.process_chunk(TranscriptChunk(t_s=n*.8, text=text, is_final=n==2))
        assert decision.decision == "NO_RETRIEVAL"

@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [False, True])
async def test_tiebreak_config_lookup_and_budget_skip(monkeypatch, enabled):
    from types import SimpleNamespace
    import slrag.controller.cascade as cascade
    monkeypatch.setattr(cascade, "get_controller_config", lambda: {"llm_tiebreak_enabled": enabled})
    state = SimpleNamespace(session=SimpleNamespace(turn_llm_calls=1))
    await cascade._do_tiebreak("sensor calibration", state)
    assert state.session.turn_llm_calls == 1

def test_previous_answer_summary_does_not_load_encoder(monkeypatch):
    import slrag.controller.cascade as cascade
    def unavailable(*args):
        raise RuntimeError("encoder must not run before suppression")
    monkeypatch.setattr(cascade, "_get_encoder", unavailable)
    decision = RetrievalController(ControllerState()).process_chunk(TranscriptChunk(
        t_s=1.6, text="describe the previous answer in short (summarize it)", is_final=True))
    assert decision.decision == "NO_RETRIEVAL"

def test_suppression_presentation_restructure_cases():
    """True presentation-only turns must trigger NO_RETRIEVAL with reason presentation_restructure."""
    turns = [
        "repeat that in two bullets",
        "summarize your last answer",
        "can you make it shorter",
        "rephrase that in simpler terms",
        "describe the previous answer in short (summarize it)",
        "describe the previous answer in short",
        "Could you summarize the previous answer?",
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
        "summarize the previous answer and give the sensor voltage limit",
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
