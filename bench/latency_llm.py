"""Live local-LLM latency for Component 4 (audit I-8, N-2).

Runs the golden NEW_INTENT and refinement turns through ``SynthesisEngine`` with the
``openai_compatible`` generator (config ``generator.openai_compatible``: local Ollama or
vLLM serving Qwen2.5-7B-Instruct, SSE streaming on) and reports, per turn type:

* ``first_draft_ms`` — LLM call start -> first complete claim (from telemetry);
* ``first_provisional_ms`` — turn start -> first PROVISIONAL sentence reaching the UI,
  the Component 4 share of ``time_to_first_token_after_utterance_end``;
* ``generation_ms`` / ``llm_calls`` / token counts, plus committed vs retracted sentences.

Needs the local model running; nothing here runs in CI.

    ollama pull qwen2.5:7b-instruct && ollama serve
    python -m bench.latency_llm --repeat 10 [--base-url http://localhost:11434/v1] [--model qwen2.5:7b-instruct]
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

from bench import _ROOT  # noqa: F401  (puts src/ on sys.path)
from slrag.synth.config import load_synth_config
from slrag.synth.engine import SynthesisEngine, SynthesisResult, TurnInput
from slrag.synth.generator import LLMGenerator, OpenAICompatibleClient
from tests.helpers import FixtureRetriever, scenario_turns, turn_decisions, turn_evidence, turn_sub_intents

SCENARIOS = ("example1_multi_intent", "example2_refinement")


def _input(turn: dict[str, Any]) -> TurnInput:
    return TurnInput(turn_id=turn["turn_id"], utterance=turn["utterance"], t_s_end=turn["t_s_end"],
                     sub_intents=turn_sub_intents(turn), evidence=turn_evidence(turn),
                     retrieval_events=turn["retrieval_events"], controller_decisions=turn_decisions(turn))


def reachable(base_url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError):
        return False


async def _timed_turn(engine: SynthesisEngine, turn: TurnInput) -> dict[str, Any]:
    started = time.perf_counter()
    first_provisional = None
    result: SynthesisResult | None = None
    async for item in engine.stream_turn(turn):
        if isinstance(item, SynthesisResult):
            result = item
        elif item.kind == "provisional" and first_provisional is None:
            first_provisional = (time.perf_counter() - started) * 1000
    assert result is not None
    generation = next((e.payload | {"latency_ms": e.latency_ms} for e in result.telemetry
                       if e.component == "synthesis.generation"), {})
    return {
        "turn_type": result.turn_type,
        "first_provisional_ms": first_provisional,
        "first_draft_ms": generation.get("first_draft_ms"),
        "generation_ms": generation.get("latency_ms"),
        "llm_calls": generation.get("llm_calls"),
        "prompt_tokens": generation.get("prompt_tokens"),
        "completion_tokens": generation.get("completion_tokens"),
        "committed": generation.get("committed"),
        "retracted": generation.get("retracted"),
    }


async def measure(config: dict[str, Any], repeat: int, client_factory: Any = None) -> list[dict[str, Any]]:
    make_client = client_factory or OpenAICompatibleClient
    rows = []
    for _ in range(repeat):
        for name in SCENARIOS:
            turns = scenario_turns(name)
            delta = {k: v for t in turns for k, v in t.get("delta_evidence", {}).items()}
            generator = LLMGenerator(make_client(config), config=config)
            engine = SynthesisEngine(f"lat_{name}", config=config, generator=generator,
                                     retrieve_fn=FixtureRetriever(delta))
            for turn in turns:
                rows.append({"scenario": name, **await _timed_turn(engine, _input(turn))})
    return rows


def summarise(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for turn_type in sorted({r["turn_type"] for r in rows}):
        group = [r for r in rows if r["turn_type"] == turn_type]
        stats = {}
        for key in ("first_provisional_ms", "first_draft_ms", "generation_ms"):
            values = sorted(r[key] for r in group if r[key] is not None)
            if values:
                p95 = values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]
                stats[key] = {"p50": round(statistics.median(values), 1), "p95": round(p95, 1), "n": len(values)}
        stats["llm_calls_max"] = max((r["llm_calls"] or 0) for r in group)
        stats["retracted_total"] = sum((r["retracted"] or 0) for r in group)
        out[turn_type] = stats
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--base-url", help="override generator.openai_compatible.base_url")
    parser.add_argument("--model", help="override generator.openai_compatible.model")
    parser.add_argument("--no-stream", action="store_true", help="blocking request (compare against SSE)")
    args = parser.parse_args(argv)

    config = copy.deepcopy(load_synth_config())
    opts = config["generator"]["openai_compatible"]
    config["generator"]["backend"] = "openai_compatible"
    if args.base_url:
        opts["base_url"] = args.base_url
    if args.model:
        opts["model"] = args.model
    if args.no_stream:
        opts["stream"] = False
    if not reachable(opts["base_url"]):
        print(f"no OpenAI-compatible server at {opts['base_url']} - start the local model first "
              f"(e.g. `ollama pull {opts['model']} && ollama serve`)", file=sys.stderr)
        return 2
    rows = asyncio.run(measure(config, args.repeat))
    print(json.dumps({"model": opts["model"], "stream": opts["stream"], "summary": summarise(rows)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
