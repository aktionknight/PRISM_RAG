"""
stubs/fake_controller.py — Deterministic controller stub for Day 1 integration.

Fires RETRIEVE on the 2nd and 3rd chunks of the golden example.
Swapped out when Diya's real controller is ready (config/app.yaml: use_stub_controller).
"""

from __future__ import annotations

from slrag.core.schemas import (
    ControllerDecision,
    ControllerDecisionType,
    ControllerReason,
    TranscriptChunk,
)


_CALL_COUNT = 0


def fake_controller(chunk: TranscriptChunk) -> ControllerDecision:
    """Deterministic stub: WAIT on first chunk, RETRIEVE on subsequent ones.

    For the golden example:
      chunk 0 (0.0s, "I need a venue...") → WAIT (intent_unstable)
      chunk 1 (0.8s, " 30 people...") → RETRIEVE (corpus_discriminative)
      chunk 2 (1.6s, " and I also...") → RETRIEVE (corpus_discriminative)
      chunk 3 (2.1s, is_final) → RETRIEVE (utterance_end_safety)
    """
    global _CALL_COUNT
    _CALL_COUNT += 1

    if chunk.is_final:
        return ControllerDecision(
            t_s=chunk.t_s,
            decision=ControllerDecisionType.RETRIEVE,
            reason=ControllerReason.utterance_end_safety,
            confidence=1.0,
            stage=None,
        )

    if _CALL_COUNT <= 1:
        return ControllerDecision(
            t_s=chunk.t_s,
            decision=ControllerDecisionType.WAIT,
            reason=ControllerReason.intent_unstable,
            confidence=0.31,
            stage=1,
        )

    return ControllerDecision(
        t_s=chunk.t_s,
        decision=ControllerDecisionType.RETRIEVE,
        reason=ControllerReason.corpus_discriminative,
        confidence=0.78,
        stage=2,
    )


def reset_stub() -> None:
    """Reset stub state between sessions."""
    global _CALL_COUNT
    _CALL_COUNT = 0
