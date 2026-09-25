"""
bench/coverage.py — Evaluation runner for Gate G6 Trace-Coverage Invariant Suite.

Component 5 — Observability & Telemetry (Matangi).
CLI entry point to verify events.jsonl against the 6 required invariants.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from slrag.telemetry.coverage import TraceCoverageSuite, load_indexed_citation_labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Trace Coverage Invariants (Gate G6)")
    parser.add_argument("--run", default="runs/events.jsonl", help="Path to events.jsonl")
    parser.add_argument("--index", default="./.index", help="Built index directory for citation validation")
    args = parser.parse_args()

    try:
        labels = load_indexed_citation_labels(args.index)
    except FileNotFoundError as exc:
        parser.error(str(exc))
    suite = TraceCoverageSuite(indexed_citation_labels=labels)
    report = suite.evaluate_file(args.run)
    print(report.summary())

    if not report.is_clean:
        sys.exit(1)
    print("\nGate G6 Passed: 100% Trace Coverage Invariant Compliance Verified.")
    sys.exit(0)


if __name__ == "__main__":
    main()
