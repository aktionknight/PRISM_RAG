"""Held-out generalisation suite: a library / IT-services corpus unrelated to the brief's examples.

Nothing in config/ names this domain (its facets are not in facets.yaml, no slot or keyword
mentions books, laptops or staff), so passing here is evidence the pipeline is not fitted to
the three golden examples. Targeted delta queries are answered by a retriever that matches on
the constraint *value* inside whatever query string the engine generates, so the tests do not
pin the query template either.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slrag.core.citations import find_markers
from slrag.core.schemas import ControllerDecision, RetrievedChunk, SubIntent
from slrag.synth.engine import SynthesisEngine, TurnInput

HELDOUT = Path(__file__).resolve().parents[1] / "fixtures" / "heldout"


def _corpus() -> dict[str, RetrievedChunk]:
    rows = [json.loads(line) for line in (HELDOUT / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    return {row["chunk_id"]: RetrievedChunk(**row) for row in rows}


CORPUS = _corpus()
SCENARIOS = {k: v for k, v in json.loads((HELDOUT / "scenarios.json").read_text(encoding="utf-8")).items()
             if not k.startswith("_")}


def _scored(chunk_id: str, score: float) -> RetrievedChunk:
    return CORPUS[chunk_id].model_copy(update={"score": score})


def _turns(name: str) -> list[dict]:
    scenario = SCENARIOS[name]
    prefix = scenario.get("session_prefix")
    return (_turns(prefix) if prefix else []) + list(scenario["turns"])


class ValueRetriever:
    """Returns a turn's delta evidence when the generated query mentions the constraint value."""

    def __init__(self) -> None:
        self.rows: dict[str, list] = {}
        self.calls: list[SubIntent] = []

    def __call__(self, sub_intent: SubIntent) -> list[RetrievedChunk]:
        self.calls.append(sub_intent)
        text = f"{sub_intent.query_nl} {sub_intent.search_string}".lower()
        return [_scored(cid, s) for value, rows in self.rows.items() if value.lower() in text for cid, s in rows]


def _input(turn: dict) -> TurnInput:
    return TurnInput(
        turn_id=turn["turn_id"], utterance=turn["utterance"], t_s_end=turn["t_s_end"],
        sub_intents=[SubIntent(**row) for row in turn.get("sub_intents", [])],
        evidence={iid: [_scored(cid, s) for cid, s in rows] for iid, rows in turn.get("evidence", {}).items()},
        retrieval_events=turn.get("retrieval_events", []),
        controller_decisions=[ControllerDecision(**row) for row in turn.get("controller_decisions", [])],
    )


async def _run(name: str):
    retriever = ValueRetriever()
    engine = SynthesisEngine(f"heldout_{name}", retrieve_fn=retriever)
    results = []
    for turn in _turns(name):
        retriever.rows = turn.get("delta_evidence_by_value", {})
        before = len(retriever.calls)
        result = await engine.handle_turn(_input(turn))
        results.append((turn, result, len(retriever.calls) - before))
    return engine, results


@pytest.mark.parametrize("name", sorted(SCENARIOS))
async def test_heldout_scenario(name):
    _, results = await _run(name)
    prior_citations: list[str] = []
    prior_claims: list[dict] = []
    for turn, result, queries in results:
        expected = turn["expected"]
        out = result.output
        assert result.turn_type == expected["turn_type"], (turn["utterance"], result.classification)
        assert result.fabricated_id_count == 0
        marked = {label for _, labels in find_markers(out.answer) for label in labels}
        assert marked <= set(out.citations)
        for label in expected.get("citations_include", ()):
            assert label in out.citations, (turn["utterance"], out.citations)
        for label in expected.get("citations_exclude", ()):
            assert label not in out.citations, (turn["utterance"], out.citations)
        if "uncertainty" in expected:
            assert out.uncertainty == expected["uncertainty"]
        for fragment in expected.get("uncertainty_contains", ()):
            assert fragment in out.uncertainty, out.uncertainty
        if "delta_keys" in expected:
            assert sorted(result.classification.delta.slots) == sorted(expected["delta_keys"]), result.classification
        if "delta_queries" in expected:
            assert queries == expected["delta_queries"] == result.refinement.delta_queries_issued
        if "full_corpus_searches" in expected:
            assert result.refinement.full_corpus_searches == expected["full_corpus_searches"]
        if "answer_version" in expected:
            assert out.answer_version == expected["answer_version"]
        if expected.get("claims_kept_verbatim_from_v1"):
            assert all(claim in result.extensions["claims"] for claim in prior_claims)
        if expected["turn_type"] == "PRESENTATION_ONLY":
            assert out.retrieval_events == [] and set(out.citations) <= set(prior_citations)
            bullets = [line for line in out.answer.splitlines() if line.strip()]
            assert len(bullets) == expected["bullet_count"]
        prior_citations, prior_claims = list(out.citations), list(result.extensions["claims"])


def test_config_names_nothing_from_the_heldout_domain():
    """Guard: generalisation must not come from adding this suite's words to config."""
    import re

    config_text = " ".join(p.read_text(encoding="utf-8").lower() for p in Path("config").rglob("*.yaml"))
    for word in ("book", "borrow", "laptop", "warranty", "refurbished", "undergraduate", "staff", "study room",
                 "fine", "loan"):
        assert not re.search(rf"\b{word}", config_text), word


def test_component4_config_names_nothing_from_the_brief_examples():
    """Guard: Component 4's rules must not be fitted to the three golden examples either.
    (config/facets.yaml is the team's facet taxonomy, owned jointly, and is only read for labels.)"""
    import re

    paths = [Path("config/synth.yaml"), *Path("config/prompts").glob("*.jinja")]
    text = " ".join(p.read_text(encoding="utf-8").lower() for p in paths)
    for word in ("venue", "pune", "mumbai", "reimburs", "catering", "trip", "hotel", "workshop", "airfare",
                 "cancellation", "refund", "headcount", "domestic", "international"):
        assert not re.search(rf"\b{word}", text), word
