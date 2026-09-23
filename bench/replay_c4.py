"""Component 4 golden replay -> run records for ``bench.metrics`` (roadmap 4.11).

Replays every scenario in ``tests/fixtures/golden_scenarios.json`` in harness order
(audit C-3): one ``SessionStore`` session per scenario; ``classify()`` at utterance
end; Components 2-3 fixture evidence only when ``needs_upstream_retrieval``; targeted
delta queries through a fixture retriever. Stands in for ``slrag replay`` until
Matangi's harness lands, and emits the same record shape ``bench.metrics`` scores.

    python -m bench.replay_c4 --out runs/c4_golden.jsonl [--backend cross_encoder]
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from bench import _ROOT  # noqa: F401  (puts src/ on sys.path)
from slrag.core.session import SessionStore
from slrag.synth.config import load_synth_config
from slrag.synth.engine import SynthesisEngine, TurnInput
from tests.helpers import (  # the golden fixtures are the test suite's; reuse their loaders
    FixtureRetriever,
    load_scenarios,
    scenario_turns,
    turn_decisions,
    turn_evidence,
    turn_sub_intents,
)


def record(session_id: str, engine: SynthesisEngine, result: Any, scenario: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "session_id": session_id,
        "turn_id": result.output.turn_id,
        "turn_type": result.turn_type,
        "output": result.to_json(),
        "context_labels": sorted(engine.graph.known_labels()),
        "telemetry": [event.model_dump(mode="json") for event in result.telemetry],
    }


async def replay_scenario(name: str, config: dict[str, Any] | None = None, scorer: Any = None) -> list[dict[str, Any]]:
    turns = scenario_turns(name)
    delta_evidence = {k: v for turn in turns for k, v in turn.get("delta_evidence", {}).items()}
    retriever = FixtureRetriever(delta_evidence)
    store = SessionStore(
        lambda sid: SynthesisEngine(sid, config=config, retrieve_fn=retriever, scorer=scorer), ttl_s=600
    )
    session_id = f"sess_{name}"
    records = []
    for turn in turns:
        async with store.turn(session_id) as engine:
            decisions = turn_decisions(turn)
            classification = engine.classify(turn["utterance"], decisions)
            routed = TurnInput(turn_id=turn["turn_id"], utterance=turn["utterance"], t_s_end=turn["t_s_end"],
                               controller_decisions=decisions, classification=classification)
            if classification.needs_upstream_retrieval:
                routed.sub_intents = turn_sub_intents(turn)
                routed.evidence = turn_evidence(turn)
                routed.retrieval_events = turn["retrieval_events"]
            result = await engine.handle_turn(routed)
            records.append(record(session_id, engine, result, name))
    store.close()
    return records


async def replay_all(names: Sequence[str] | None = None, *, backend: str | None = None) -> list[dict[str, Any]]:
    config = None
    scorer = None
    if backend is not None:
        config = copy.deepcopy(load_synth_config())
        config["verifier"]["entailment_backend"] = backend
        from slrag.synth.verifier import make_scorer

        scorer = make_scorer(config)       # load the model once, share across sessions
    records: list[dict[str, Any]] = []
    for name in names or sorted(load_scenarios()):
        records += await replay_scenario(name, config, scorer)
    return records


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="runs/c4_golden.jsonl")
    parser.add_argument("--scenario", action="append", help="replay only these scenarios (repeatable)")
    parser.add_argument("--backend", choices=("lexical", "cross_encoder"), help="override verifier backend")
    args = parser.parse_args(argv)

    records = asyncio.run(replay_all(args.scenario, backend=args.backend))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    print(f"wrote {len(records)} run records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
