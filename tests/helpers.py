"""Shared fixture loaders for the mini test corpus and golden Examples 1-3."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from slrag.core.schemas import ControllerDecision, RetrievedChunk, SubIntent, TranscriptChunk

FIXTURES = Path(__file__).parent / "fixtures"


@lru_cache(maxsize=1)
def _corpus_raw() -> tuple[dict[str, Any], ...]:
    lines = (FIXTURES / "fixture_chunks.jsonl").read_text(encoding="utf-8").splitlines()
    return tuple(json.loads(line) for line in lines if line.strip())


def load_corpus() -> dict[str, RetrievedChunk]:
    """chunk_id -> RetrievedChunk (score 0.0; use ``scored`` for per-query scores)."""
    return {row["chunk_id"]: RetrievedChunk(**row) for row in _corpus_raw()}


def scored(chunk_id: str, score: float) -> RetrievedChunk:
    return load_corpus()[chunk_id].model_copy(update={"score": score})


def load_stream(name: str) -> list[TranscriptChunk]:
    lines = (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return [TranscriptChunk(**json.loads(line)) for line in lines if line.strip()]


def split_turns(chunks: list[TranscriptChunk]) -> list[list[TranscriptChunk]]:
    """A session stream is a sequence of utterances, each closed by ``is_final=true``."""
    turns, current = [], []
    for chunk in chunks:
        current.append(chunk)
        if chunk.is_final:
            turns.append(current)
            current = []
    if current:
        turns.append(current)
    return turns


def load_scenarios() -> dict[str, Any]:
    data = json.loads((FIXTURES / "golden_scenarios.json").read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("_")}


def scenario_turns(name: str) -> list[dict[str, Any]]:
    """Turns of a scenario, with any ``session_prefix`` scenario's turns prepended."""
    scenarios = load_scenarios()
    scenario = scenarios[name]
    prefix = scenario.get("session_prefix")
    return (scenario_turns(prefix) if prefix else []) + list(scenario["turns"])


def turn_sub_intents(turn: dict[str, Any]) -> list[SubIntent]:
    return [SubIntent(**row) for row in turn.get("sub_intents", [])]


def turn_evidence(turn: dict[str, Any]) -> dict[str, list[RetrievedChunk]]:
    return {
        intent_id: [scored(chunk_id, score) for chunk_id, score in rows]
        for intent_id, rows in turn.get("evidence", {}).items()
    }


def turn_decisions(turn: dict[str, Any]) -> list[ControllerDecision]:
    return [ControllerDecision(**row) for row in turn.get("controller_decisions", [])]


class FixtureRetriever:
    """Stands in for Aakrit's retriever on targeted delta queries; records every call."""

    def __init__(self, delta_evidence: dict[str, list[list[Any]]] | None = None) -> None:
        self.delta_evidence = delta_evidence or {}
        self.calls: list[SubIntent] = []

    def __call__(self, sub_intent: SubIntent) -> list[RetrievedChunk]:
        self.calls.append(sub_intent)
        rows = self.delta_evidence.get(sub_intent.search_string, [])
        return [scored(chunk_id, score) for chunk_id, score in rows]
