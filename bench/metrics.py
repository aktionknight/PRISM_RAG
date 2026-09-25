"""Metrics for replay traces used by local development and ablations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_events(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    chunks = [e for e in events if e.get("event_type") == "chunk_received"]
    decisions = [e for e in events if e.get("event_type") == "controller_decision"]
    retrievals = [e for e in events if e.get("event_type") == "retrieval_started"]
    costs = [e for e in events if e.get("event_type") == "cost_record"]
    retrieve_decisions = [
        e for e in decisions if e.get("payload", {}).get("decision") == "RETRIEVE"
    ]
    return {
        "events": len(events),
        "chunks": len(chunks),
        "controller_decisions": len(decisions),
        "retrievals": len(retrievals),
        "early_retrieval_rate": float(bool(retrieve_decisions)),
        "first_retrieval_ts": (
            retrieve_decisions[0].get("ts_stream_s") if retrieve_decisions else None
        ),
        "cost_usd": round(
            sum(e.get("payload", {}).get("cost_usd", 0.0) for e in costs), 6
        ),
        "chunk_decision_coverage": len(decisions) / len(chunks) if chunks else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a replay telemetry trace")
    parser.add_argument("--run", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    result = summarize(load_events(args.run))
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
