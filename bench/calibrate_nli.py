"""Calibrate the Component 4 entailment threshold (audit I-4, N-1, W-2).

For each backend (``lexical``, and ``cross_encoder`` when the model is baked):

1. **Raw scorer sweep** — accept a pair when ``score(premise, hypothesis) >= t`` for
   t in 0.05..0.95; reports precision / recall / balanced accuracy per threshold and the
   threshold with the best balanced accuracy (ties go to the higher, stricter value).
2. **Shipped verifier** — the full ``ClaimVerifier`` decision at the configured threshold
   (entailment + polarity check + numeral/entity copy check), broken down by pair kind
   (verbatim, paraphrase, negation, antonym, value, swap, unrelated, unsupported_extra).
3. **Lock cost (W-2)** — ``CrossEncoderNLIScorer`` serialises ``predict`` behind a lock;
   compares N sentences verified concurrently (the two-pass streamer's pattern) with the
   same N scored as one batch, and reports per-pair latency.

    python -m bench.calibrate_nli --pairs bench/data/nli_calibration.jsonl [--backend cross_encoder]
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import statistics
import sys
import time
from collections import defaultdict
from typing import Any, Sequence

from bench import _ROOT  # noqa: F401  (puts src/ on sys.path)
from bench.metrics import load_jsonl
from slrag.core.schemas import RetrievedChunk
from slrag.synth.config import load_synth_config, resolve_path
from slrag.synth.types import DraftClaim
from slrag.synth.verifier import CitationAllowlist, ClaimVerifier, make_scorer, threshold_for

THRESHOLDS = [round(0.05 * i, 2) for i in range(1, 20)]


def _config(backend: str) -> dict[str, Any]:
    config = copy.deepcopy(load_synth_config())
    config["verifier"]["entailment_backend"] = backend
    return config


def _rates(decisions: Sequence[tuple[bool, bool]]) -> dict[str, float]:
    """decisions: (accepted, supported)."""
    tp = sum(a and s for a, s in decisions)
    fp = sum(a and not s for a, s in decisions)
    fn = sum(not a and s for a, s in decisions)
    tn = sum(not a and not s for a, s in decisions)
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    return {
        "precision": round(tp / (tp + fp), 3) if tp + fp else 1.0,
        "recall": round(recall, 3),
        "specificity": round(specificity, 3),
        "balanced_accuracy": round((recall + specificity) / 2, 3),
        "false_accepts": fp,
        "false_rejects": fn,
    }


def sweep(scores: Sequence[float], pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    table = {t: _rates([(s >= t, p["supported"]) for s, p in zip(scores, pairs)]) for t in THRESHOLDS}
    best = max(THRESHOLDS, key=lambda t: (table[t]["balanced_accuracy"], t))
    return {"best_threshold": best, "best": table[best], "table": {str(t): r for t, r in table.items()}}


def verifier_decisions(config: dict[str, Any], scorer: Any, pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    decisions, by_kind, rows = [], defaultdict(list), []
    for n, pair in enumerate(pairs):
        chunk = RetrievedChunk(chunk_id=f"Cal_{n}#1#0", doc_id=f"Cal_{n}", section_id="1", text=pair["premise"], score=1.0)
        verifier = ClaimVerifier(CitationAllowlist.from_chunks([chunk]), config=config, scorer=scorer)
        result = verifier.verify(DraftClaim(seq=n, facet="calibration", text=pair["hypothesis"], citations=(f"Cal_{n} §1",)))
        decisions.append((result.ok, pair["supported"]))
        by_kind[pair["kind"]].append((result.ok, pair["supported"]))
        if result.ok != pair["supported"]:
            rows.append({"kind": pair["kind"], "hypothesis": pair["hypothesis"], "accepted": result.ok,
                         "entailment": None if result.entailment is None else round(result.entailment, 3),
                         "reasons": list(result.reasons)})
    return {
        "threshold": threshold_for(config),
        "overall": _rates(decisions),
        "by_kind": {kind: f"{sum(a == s for a, s in d)}/{len(d)} correct" for kind, d in sorted(by_kind.items())},
        "errors": rows,
    }


async def lock_cost(scorer: Any, pairs: Sequence[dict[str, Any]], n: int = 8) -> dict[str, Any]:
    sample = [(p["premise"], p["hypothesis"]) for p in pairs[:n]]
    started = time.perf_counter()
    await asyncio.gather(*(asyncio.to_thread(scorer.score, premise, hypothesis) for premise, hypothesis in sample))
    concurrent_ms = (time.perf_counter() - started) * 1000
    batch = getattr(scorer, "score_batch", None)
    started = time.perf_counter()
    batch(sample) if callable(batch) else [scorer.score(*pair) for pair in sample]
    batch_ms = (time.perf_counter() - started) * 1000
    singles = []
    for premise, hypothesis in sample:
        started = time.perf_counter()
        scorer.score(premise, hypothesis)
        singles.append((time.perf_counter() - started) * 1000)
    singles.sort()
    return {
        "sentences": len(sample),
        "concurrent_threads_ms": round(concurrent_ms, 1),
        "one_batch_ms": round(batch_ms, 1),
        "per_pair_ms_p50": round(statistics.median(singles), 1),
        "per_pair_ms_max": round(singles[-1], 1),
    }


def calibrate(backend: str, pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    config = _config(backend)
    scorer = make_scorer(config)
    scorer.score(pairs[0]["premise"], pairs[0]["hypothesis"])        # warm-up (model load, first-call JIT)
    batch = getattr(scorer, "score_batch", None)
    started = time.perf_counter()
    scores = batch([(p["premise"], p["hypothesis"]) for p in pairs]) if callable(batch) else [
        scorer.score(p["premise"], p["hypothesis"]) for p in pairs
    ]
    scoring_ms = (time.perf_counter() - started) * 1000
    report = {
        "backend": backend,
        "pairs": len(pairs),
        "raw_scorer": sweep(scores, pairs),
        "shipped_verifier": verifier_decisions(config, scorer, pairs),
        "scoring_ms_total": round(scoring_ms, 1),
    }
    if backend == "cross_encoder":
        report["lock_cost"] = asyncio.run(lock_cost(scorer, pairs))
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pairs", default="bench/data/nli_calibration.jsonl")
    parser.add_argument("--backend", action="append", choices=("lexical", "cross_encoder"))
    parser.add_argument("--full-table", action="store_true", help="print the whole threshold sweep")
    args = parser.parse_args(argv)

    pairs = load_jsonl(args.pairs)
    backends = args.backend
    if not backends:
        model = load_synth_config()["verifier"].get("cross_encoder", {}).get("model_path", "")
        backends = ["lexical"] + (["cross_encoder"] if model and resolve_path(model).exists() else [])
    reports = [calibrate(backend, pairs) for backend in backends]
    if not args.full_table:
        for report in reports:
            report["raw_scorer"].pop("table")
    print(json.dumps(reports, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
