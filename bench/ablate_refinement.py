"""Ablation A3 — delta refinement vs full restart (roadmap 5.5; the G5 headline).

For every golden scenario with a CONSTRAINT_REFINEMENT turn, the refinement is run
two ways against the same fixture evidence:

* **delta** — the shipped path: V1 in the session, then the refinement turn through
  ``SynthesisEngine`` (impact analysis, targeted queries only, one revision);
* **restart** — the naive baseline: a fresh session that re-decomposes the whole
  conversation, re-retrieves every V1 sub-intent plus the delta targets, and
  synthesises from scratch.

Reported per path: retrieval calls, synthesis prompt size (the real ``refine`` /
``synthesize`` templates rendered by ``LLMGenerator.render_prompt``; tokens estimated
at 4 characters each) and evidence chunks sent to the model, Component 4 latency
(median of ``--repeat`` runs, deterministic backend), V1 claims kept verbatim,
citation continuity (share of V1 labels still cited), **stale claims** (final claims
whose own text scopes them to a constraint value that no longer holds, e.g. the
domestic-trip rule after "the trip was international") and answer lineage. Continuity alone rewards a restart for keeping a stale claim, so read
it together with ``stale_claims``.

    python -m bench.ablate_refinement [--repeat 20] [--out runs/ablation_a3.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from bench import _ROOT  # noqa: F401  (puts src/ on sys.path)
from slrag.synth.config import load_facets, load_synth_config
from slrag.synth.delta import ConstraintExtractor, merge_constraints
from slrag.synth.engine import SynthesisEngine, TurnInput
from slrag.synth.generator import LLMGenerator, make_generator
from tests.helpers import (  # the golden fixtures are the test suite's; reuse their loaders
    FixtureRetriever,
    load_scenarios,
    scenario_turns,
    turn_decisions,
    turn_evidence,
    turn_sub_intents,
)

CHARS_PER_TOKEN = 4


class PromptMeter:
    """Deterministic generator that also records the size of the prompt an LLM backend would get."""

    def __init__(self, config: dict[str, Any], facets: dict[str, Any]) -> None:
        self.inner = make_generator(config, facets)
        self.renderer = LLMGenerator(client=None, config=config, facets=facets)
        self.prompt_chars: list[int] = []
        self.evidence_chunks: list[int] = []

    @property
    def usage(self):
        return self.inner.usage

    def generate(self, sub_intents, evidence, **kwargs):
        prompt, _ = self.renderer.render_prompt(sub_intents, evidence, **kwargs)
        self.prompt_chars.append(len(prompt))
        self.evidence_chunks.append(len({c.chunk_id for rows in evidence.values() for c in rows}))
        return self.inner.generate(sub_intents, evidence, **kwargs)


def _input(turn: dict[str, Any], **overrides: Any) -> TurnInput:
    fields = dict(turn_id=turn["turn_id"], utterance=turn["utterance"], t_s_end=turn["t_s_end"],
                  sub_intents=turn_sub_intents(turn), evidence=turn_evidence(turn),
                  retrieval_events=turn["retrieval_events"], controller_decisions=turn_decisions(turn))
    fields.update(overrides)
    return TurnInput(**fields)


def _v1_stats(v1_claims: list[dict], final_claims: list[dict]) -> dict[str, Any]:
    final = {(c["text"], tuple(c["citations"])) for c in final_claims}
    v1_labels = {label for c in v1_claims for label in c["citations"]}
    final_labels = {label for c in final_claims for label in c["citations"]}
    return {
        "v1_claims_kept_verbatim": sum((c["text"], tuple(c["citations"])) in final for c in v1_claims),
        "v1_claims": len(v1_claims),
        "citation_continuity": round(len(v1_labels & final_labels) / len(v1_labels), 3) if v1_labels else None,
    }


async def _delta(name: str, config, facets) -> dict[str, Any]:
    turns = scenario_turns(name)
    delta_evidence = {k: v for t in turns for k, v in t.get("delta_evidence", {}).items()}
    retriever = FixtureRetriever(delta_evidence)
    meter = PromptMeter(config, facets)
    engine = SynthesisEngine(f"a3_delta_{name}", config=config, facets=facets, generator=meter, retrieve_fn=retriever)
    results = [await engine.handle_turn(_input(t)) for t in turns]
    index = next(i for i, r in enumerate(results) if r.turn_type == "CONSTRAINT_REFINEMENT")
    before, after = results[index - 1], results[index]
    upstream = len(turns[index]["retrieval_events"]) if after.classification.mixed else 0
    return {
        "retrieval_calls": len(retriever.calls) + upstream,
        "prompt_tokens_est": meter.prompt_chars[-1] // CHARS_PER_TOKEN,
        "evidence_chunks": meter.evidence_chunks[-1],
        "answer_version": after.output.answer_version,
        "lineage": after.extensions["version_lineage"],
        **_v1_stats(before.extensions["claims"], after.extensions["claims"]),
        "_final": after.extensions["claims"],
    }


async def _restart(name: str, config, facets) -> dict[str, Any]:
    """Fresh session: the whole conversation re-decomposed and every sub-intent re-retrieved."""
    turns = scenario_turns(name)
    index = next(i for i, t in enumerate(turns) if t.get("expected", {}).get("turn_type") == "CONSTRAINT_REFINEMENT")
    probe = SynthesisEngine(f"a3_probe_{name}", config=config, facets=facets,
                            retrieve_fn=FixtureRetriever({k: v for t in turns for k, v in t.get("delta_evidence", {}).items()}))
    v1 = None
    for turn in turns[:index]:
        v1 = await probe.handle_turn(_input(turn))
    delta = probe.classify(turns[index]["utterance"]).delta
    plan = probe.delta.plan(probe.graph, delta, turn_id=turns[index]["turn_id"])
    current = merge_constraints(probe.session_constraints, delta)
    delta_rows = {k: v for t in turns for k, v in t.get("delta_evidence", {}).items()}
    delta_intents = [t.sub_intent for t in plan.targets]
    intents = [i for t in turns[:index + 1] for i in turn_sub_intents(t)] + delta_intents
    evidence: dict[str, list] = {}
    for turn in turns[:index + 1]:
        evidence.update(turn_evidence(turn))
    retriever = FixtureRetriever(delta_rows)
    for intent in delta_intents:
        evidence[intent.intent_id] = retriever(intent)
    meter = PromptMeter(config, facets)
    engine = SynthesisEngine(f"a3_restart_{name}", config=config, facets=facets, generator=meter)
    utterance = " ".join(t["utterance"] for t in turns[:index + 1])
    result = await engine.handle_turn(TurnInput(turn_id=1, utterance=utterance, t_s_end=turns[index]["t_s_end"],
                                                sub_intents=intents, evidence=evidence))
    return {
        "retrieval_calls": len(intents),
        "prompt_tokens_est": meter.prompt_chars[-1] // CHARS_PER_TOKEN,
        "evidence_chunks": meter.evidence_chunks[-1],
        "answer_version": result.output.answer_version,
        "lineage": result.extensions["version_lineage"],
        **_v1_stats(v1.extensions["claims"], result.extensions["claims"]),
        "_final": result.extensions["claims"],
        "_current": current,
    }


def stale_claims(claims: list[dict], current: dict[str, str], extractor: ConstraintExtractor) -> list[str]:
    """Claims whose own text scopes them to a constraint value other than the current one."""
    stale = []
    for claim in claims:
        scoped = extractor.derive_preconditions(claim["text"], claim["facet"], {})
        if any(slot in current and value != current[slot] for slot, value in scoped.items()):
            stale.append(claim["text"])
    return stale


async def _latency(run, name: str, config, facets, repeat: int) -> float:
    samples = []
    for _ in range(repeat):
        started = time.perf_counter()
        await run(name, config, facets)
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 3)


async def ablate(repeat: int = 20) -> dict[str, Any]:
    config, facets = load_synth_config(), load_facets()
    report: dict[str, Any] = {}
    for name in sorted(load_scenarios()):
        if not any(t.get("expected", {}).get("turn_type") == "CONSTRAINT_REFINEMENT" for t in scenario_turns(name)):
            continue
        delta = await _delta(name, config, facets)
        restart = await _restart(name, config, facets)
        current = restart.pop("_current")
        for path in (delta, restart):
            path["stale_claims"] = stale_claims(path.pop("_final"), current, ConstraintExtractor(config, facets))
        delta["session_latency_ms_p50"] = await _latency(_delta, name, config, facets, repeat)
        restart["session_latency_ms_p50"] = await _latency(_restart, name, config, facets, repeat)
        report[name] = {
            "delta": delta,
            "restart": restart,
            "retrieval_calls_saved": restart["retrieval_calls"] - delta["retrieval_calls"],
            "prompt_tokens_ratio": round(restart["prompt_tokens_est"] / max(1, delta["prompt_tokens_est"]), 2),
            "evidence_chunks_ratio": round(restart["evidence_chunks"] / max(1, delta["evidence_chunks"]), 2),
        }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeat", type=int, default=20)
    parser.add_argument("--out", help="also write the report JSON here")
    args = parser.parse_args(argv)
    report = asyncio.run(ablate(args.repeat))
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
