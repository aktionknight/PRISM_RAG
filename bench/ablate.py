"""Run simple replay arms and write comparable telemetry summaries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from metrics import load_events, summarize


ARMS = ("hybrid", "dense_only", "bm25_only")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run retrieval ablation arms")
    parser.add_argument("--stream", default="bench/data/golden_example.jsonl")
    parser.add_argument("--out", default="runs/ablation.json")
    args = parser.parse_args()

    results = {}
    for arm in ARMS:
        run_path = Path(args.out).with_suffix(f".{arm}.jsonl")
        env = os.environ.copy()
        env["SLRAG_ABLATION_ARM"] = arm
        command = [sys.executable, "-m", "slrag.api.cli", "replay", "--stream", args.stream, "--out", str(run_path)]
        completed = subprocess.run(command, env=env, check=False)
        results[arm] = {"returncode": completed.returncode}
        if completed.returncode == 0 and run_path.exists():
            results[arm]["metrics"] = summarize(load_events(run_path))

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
