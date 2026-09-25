"""Generate a deterministic local streaming development suite.

The generated data is synthetic development data derived from the sample corpus;
it is never imported by production code or used as the held-out evaluation set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCENARIOS = [
    ("multi_intent", [
        ("I need a venue in Pune that can hold", False),
        (" 30 people for a workshop", False),
        (" and I also need cancellation and catering details", False),
        ("", True),
    ]),
    ("refinement", [
        ("I need a workshop venue in Pune", False),
        (" for 30 people", False),
        (" actually make that 20 people", False),
        ("", True),
    ]),
    ("presentation_only", [
        ("Repeat the answer", False),
        (" in two bullets", False),
        ("", True),
    ]),
    ("adversarial", [
        ("I need cancellation and refund terms", False),
        (" no wait, I mean catering options", False),
        ("", True),
    ]),
]


def write_suite(output_dir: Path, count: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    t_step = 0.8
    proportions = (40, 25, 20, 15)
    allocations = [count * proportion // 100 for proportion in proportions]
    for index in range(count - sum(allocations)):
        allocations[index % len(allocations)] += 1

    for (scenario, chunks), allocation in zip(SCENARIOS, allocations):
        for repeat in range(allocation):
            stream_name = f"{scenario}_{repeat:03d}.jsonl"
            stream_path = output_dir / stream_name
            records = [
                {"t_s": round(index * t_step, 1), "text": text, "is_final": is_final}
                for index, (text, is_final) in enumerate(chunks)
            ]
            with stream_path.open("w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")
            manifest.append({"stream": stream_name, "stratum": scenario})
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate local streaming development fixtures")
    parser.add_argument("--out", default="bench/data/generated")
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    write_suite(Path(args.out), max(4, args.count))


if __name__ == "__main__":
    main()
