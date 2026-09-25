"""Deterministic rule-based retrieval controller for local/offline runs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from slrag.core.schemas import (
    ControllerDecision,
    ControllerDecisionType,
    ControllerReason,
    TranscriptChunk,
)


class RuleController:
    """Cheap controller implementing suppression, content floor, and safety net."""

    def __init__(self, config_path: str | Path = "config/controller.yaml") -> None:
        with Path(config_path).open("r", encoding="utf-8") as f:
            config: dict[str, Any] = yaml.safe_load(f) or {}
        cascade = config.get("cascade", {})
        self.presentation_verbs = set(cascade.get("presentation_verbs", []))
        self.correction_markers = tuple(cascade.get("correction_markers", []))
        self._seen_retrieval = False
        self._prefix = ""

    def decide(self, chunk: TranscriptChunk) -> ControllerDecision:
        self._prefix += chunk.text
        lowered = self._prefix.lower()
        tokens = re.findall(r"[a-z0-9]+", lowered)
        content_tokens = [token for token in tokens if len(token) > 2]

        if any(verb in tokens for verb in self.presentation_verbs) and not chunk.is_final:
            return ControllerDecision(
                t_s=chunk.t_s,
                decision=ControllerDecisionType.NO_RETRIEVAL,
                reason=ControllerReason.presentation_restructure,
                confidence=0.9,
                stage=0,
            )

        if chunk.is_final:
            self._seen_retrieval = True
            return ControllerDecision(
                t_s=chunk.t_s,
                decision=ControllerDecisionType.RETRIEVE,
                reason=ControllerReason.utterance_end_safety,
                confidence=1.0,
                stage=4,
            )

        if len(content_tokens) < 2:
            return ControllerDecision(
                t_s=chunk.t_s,
                decision=ControllerDecisionType.WAIT,
                reason=ControllerReason.intent_unstable,
                confidence=0.35,
                stage=1,
            )

        fresh_anchor = any(marker in lowered for marker in (" and ", " also ", " plus "))
        if not self._seen_retrieval or fresh_anchor:
            self._seen_retrieval = True
            return ControllerDecision(
                t_s=chunk.t_s,
                decision=ControllerDecisionType.RETRIEVE,
                reason=ControllerReason.corpus_discriminative,
                confidence=0.7,
                stage=2,
            )

        return ControllerDecision(
            t_s=chunk.t_s,
            decision=ControllerDecisionType.WAIT,
            reason=ControllerReason.intent_unstable,
            confidence=0.5,
            stage=3,
        )
