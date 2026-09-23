"""Gate scorers (roadmap 2.10 / 3.13 / 4.11). This file holds G4 and G5 (Component 4).

G2 (Diya) and G3 (Aakrit) scorers belong in this module too; each section only
reads run records, never engine internals.

Run record: one JSON object per answered turn (``bench/replay_c4.py`` writes them;
Matangi's ``events.jsonl`` maps onto the same keys)::

    {"session_id": str, "turn_id": int, "turn_type": str,
     "output": {...},                 # SynthesisResult.to_json(): the 5 keys + extensions
     "context_labels": [str, ...],    # the closed citation allowlist when the turn ran
     "telemetry": [TelemetryEvent, ...]}

G4 (grounding): ``citation_support_rate`` >= 0.85 and ``fabricated_id_count`` == 0.
Each claim is judged once per session (a retained claim is not re-counted on later
versions): it is supported when some chunk of a label it cites entails it at
``threshold`` under the judge. The lexical judge matches the CI verifier, so it only
catches drift; the independent measurement is ``--judge cross_encoder``.

G5 (state continuity): on refinement ``full_corpus_searches`` == 0 and
``session_cleared`` is false; presentation-only turns issue no retrieval, keep the
answer version, and cite a subset of the prior answer. ``claims_retained_pct`` and
``delta_queries_per_refinement`` are reported (A_FINAL_ARCHITECTURE §4.4 metrics).

    python -m bench.metrics --run runs/c4_golden.jsonl --corpus tests/fixtures/fixture_chunks.jsonl \\
        [--gold bench/data/c4_gold.jsonl] [--judge lexical|cross_encoder] [--gate]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from bench import _ROOT  # noqa: F401  (puts src/ on sys.path)
from slrag.core.citations import find_markers, label_for_chunk, normalize_label
from slrag.core.schemas import RetrievedChunk
from slrag.synth.config import load_synth_config
from slrag.synth.verifier import make_scorer, threshold_for

G4_MIN_CITATION_SUPPORT = 0.85


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def corpus_by_label(rows: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Citation label -> chunk texts, from RetrievedChunk-shaped rows."""
    out: dict[str, list[str]] = {}
    for row in rows:
        chunk = RetrievedChunk(**{"score": 0.0, **row})
        out.setdefault(label_for_chunk(chunk), []).append(chunk.text)
    return out


def _events(record: Mapping[str, Any], component: str) -> list[Mapping[str, Any]]:
    return [e for e in record.get("telemetry", ()) if e.get("component") == component]


def _payload(record: Mapping[str, Any], component: str) -> Mapping[str, Any] | None:
    events = _events(record, component)
    return events[-1].get("payload", {}) if events else None


# ---------------------------------------------------------------------------
# G4 — citation support + fabricated IDs
# ---------------------------------------------------------------------------
def output_labels(output: Mapping[str, Any]) -> list[str]:
    """Every label the turn emitted: ``citations``, answer markers, and claim citations."""
    labels = list(output.get("citations", ()))
    labels += [label for _, found in find_markers(str(output.get("answer", ""))) for label in found]
    labels += [label for claim in output.get("claims", ()) or () for label in claim.get("citations", ())]
    return labels


def fabricated_ids(record: Mapping[str, Any], corpus_labels: Iterable[str]) -> list[str]:
    """Emitted labels outside the turn's allowlist (or, without one, outside the corpus)."""
    allowed = set(record.get("context_labels") or corpus_labels)
    return sorted({label for label in output_labels(record["output"]) if normalize_label(label) not in allowed})


def score_citation_support(
    records: Sequence[Mapping[str, Any]],
    corpus: Mapping[str, Sequence[str]],
    judge: Any,
    threshold: float,
) -> dict[str, Any]:
    seen: set[tuple[str, str]] = set()
    judged: list[dict[str, Any]] = []
    for record in records:
        for claim in record["output"].get("claims", ()) or ():
            key = (str(record["session_id"]), str(claim["claim_id"]))
            if key in seen:
                continue
            seen.add(key)
            premises = [text for label in claim.get("citations", ()) for text in corpus.get(normalize_label(label) or label, ())]
            best = max((float(judge.score(premise, claim["text"])) for premise in premises), default=0.0)
            judged.append({"session_id": key[0], "claim_id": key[1], "text": claim["text"],
                           "citations": list(claim.get("citations", ())), "entailment": round(best, 4),
                           "supported": bool(premises) and best >= threshold})
    supported = sum(row["supported"] for row in judged)
    rate = supported / len(judged) if judged else None
    return {
        "claims_judged": len(judged),
        "claims_supported": supported,
        "citation_support_rate": rate,
        "unsupported_claim_rate": None if rate is None else 1.0 - rate,
        "unsupported": [row for row in judged if not row["supported"]],
    }


def score_g4(
    records: Sequence[Mapping[str, Any]],
    corpus: Mapping[str, Sequence[str]],
    *,
    judge: Any,
    threshold: float,
) -> dict[str, Any]:
    fabricated = {f"{r['session_id']}:{r['turn_id']}": ids for r in records if (ids := fabricated_ids(r, corpus))}
    support = score_citation_support(records, corpus, judge, threshold)
    return {"fabricated_id_count": sum(map(len, fabricated.values())), "fabricated": fabricated, **support}


def score_uncertainty(records: Sequence[Mapping[str, Any]], gold: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``uncertainty_precision``: flagged (non-covered) facets that gold says truly lack support."""
    truth = {(str(g["session_id"]), int(g["turn_id"])): set(g.get("uncovered_facets", ())) for g in gold}
    flagged = correct = missed = 0
    for record in records:
        key = (str(record["session_id"]), int(record["turn_id"]))
        coverage = _payload(record, "synthesis.coverage")
        if key not in truth or coverage is None:
            continue
        marked = {row["facet"] for row in coverage.get("rows", ()) if row.get("state") != "covered"}
        flagged += len(marked)
        correct += len(marked & truth[key])
        missed += len(truth[key] - marked)
    return {
        "uncertainty_flagged": flagged,
        "uncertainty_precision": correct / flagged if flagged else None,
        "uncertainty_recall": correct / (correct + missed) if correct + missed else None,
    }


# ---------------------------------------------------------------------------
# G5 — refinement continuity + presentation-only invariants
# ---------------------------------------------------------------------------
def score_g5(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    refinements: list[Mapping[str, Any]] = []
    presentation = {"turns": 0, "retrieval_events": 0, "citation_subset_violations": [], "version_changes": []}
    prior: dict[str, Mapping[str, Any]] = {}
    for record in records:
        session, output = str(record["session_id"]), record["output"]
        before = prior.get(session)
        report = _payload(record, "synthesis.refinement")
        if report is not None:
            refinements.append(report)
        if record.get("turn_type") == "PRESENTATION_ONLY":
            key = f"{session}:{record['turn_id']}"
            presentation["turns"] += 1
            presentation["retrieval_events"] += len(output.get("retrieval_events", ()))
            prior_citations = set(before["citations"]) if before else set()
            if not set(output.get("citations", ())) <= prior_citations:
                presentation["citation_subset_violations"].append(key)
            if before is not None and output.get("answer_version") != before.get("answer_version"):
                presentation["version_changes"].append(key)
        prior[session] = output

    retained = sum(r.get("claims_retained", 0) for r in refinements)
    superseded = sum(r.get("claims_superseded", 0) for r in refinements)
    return {
        "refinements": len(refinements),
        "full_corpus_searches_on_refinement": sum(r.get("full_corpus_searches", 0) for r in refinements),
        "sessions_cleared_on_refinement": sum(bool(r.get("session_cleared")) for r in refinements),
        "claims_retained_pct": retained / (retained + superseded) if retained + superseded else None,
        "delta_queries_per_refinement": (
            statistics.mean(r.get("delta_queries_issued", 0) for r in refinements) if refinements else None
        ),
        "pool_resolved_targets": sum(r.get("pool_resolved_targets", 0) for r in refinements),
        "presentation": presentation,
    }


def score_latency(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """LLM start -> first complete claim (``first_draft_ms``); None on the extractive backend."""
    values = sorted(
        float(p["first_draft_ms"])
        for r in records
        if (p := _payload(r, "synthesis.generation")) and p.get("first_draft_ms") is not None
    )
    if not values:
        return {"first_draft_ms": None}
    p95 = values[min(len(values) - 1, int(round(0.95 * (len(values) - 1))))]
    return {"first_draft_ms": {"n": len(values), "p50": statistics.median(values), "p95": p95}}


# ---------------------------------------------------------------------------
# Gates + CLI
# ---------------------------------------------------------------------------
def gate_failures(summary: Mapping[str, Any], *, min_support: float = G4_MIN_CITATION_SUPPORT) -> list[str]:
    g4, g5 = summary["g4"], summary["g5"]
    failures = []
    if g4["fabricated_id_count"]:
        failures.append(f"G4 fabricated_id_count={g4['fabricated_id_count']} (must be 0): {g4['fabricated']}")
    rate = g4["citation_support_rate"]
    if rate is not None and rate < min_support:
        failures.append(f"G4 citation_support_rate={rate:.3f} < {min_support}")
    if g5["full_corpus_searches_on_refinement"]:
        failures.append(f"G5 full_corpus_searches_on_refinement={g5['full_corpus_searches_on_refinement']} (must be 0)")
    if g5["sessions_cleared_on_refinement"]:
        failures.append("G5 a refinement cleared the session")
    pres = g5["presentation"]
    if pres["retrieval_events"]:
        failures.append(f"G5 presentation-only turns issued {pres['retrieval_events']} retrieval events")
    if pres["citation_subset_violations"]:
        failures.append(f"G5 presentation citations not a subset of prior: {pres['citation_subset_violations']}")
    if pres["version_changes"]:
        failures.append(f"G5 presentation-only turns changed answer_version: {pres['version_changes']}")
    return failures


def make_judge(kind: str, config: dict[str, Any] | None = None) -> tuple[Any, float]:
    """(scorer, threshold) for ``lexical`` or ``cross_encoder``, from ``config/synth.yaml``."""
    config = json.loads(json.dumps(config if config is not None else load_synth_config()))
    config.setdefault("verifier", {})["entailment_backend"] = kind
    return make_scorer(config), threshold_for(config)


def summarise(
    records: Sequence[Mapping[str, Any]],
    corpus: Mapping[str, Sequence[str]],
    *,
    judge: Any,
    threshold: float,
    gold: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    g4 = score_g4(records, corpus, judge=judge, threshold=threshold)
    if gold:
        g4.update(score_uncertainty(records, gold))
    return {"turns": len(records), "g4": g4, "g5": score_g5(records), "latency": score_latency(records)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="G4/G5 scorers over Component 4 run records")
    parser.add_argument("--run", required=True, help="run records (JSONL)")
    parser.add_argument("--corpus", required=True, help="corpus chunks (JSONL, RetrievedChunk rows)")
    parser.add_argument("--gold", help="optional gold JSONL: {session_id, turn_id, uncovered_facets}")
    parser.add_argument("--judge", choices=("lexical", "cross_encoder"), default="lexical")
    parser.add_argument("--threshold", type=float, help="override verifier.entailment_threshold")
    parser.add_argument("--gate", action="store_true", help="exit 1 if any G4/G5 gate fails")
    parser.add_argument("--out", help="also write the summary JSON here")
    args = parser.parse_args(argv)

    judge, threshold = make_judge(args.judge)
    summary = summarise(
        load_jsonl(args.run),
        corpus_by_label(load_jsonl(args.corpus)),
        judge=judge,
        threshold=args.threshold if args.threshold is not None else threshold,
        gold=load_jsonl(args.gold) if args.gold else (),
    )
    summary["judge"] = {"kind": args.judge, "threshold": args.threshold if args.threshold is not None else threshold}
    summary["gate_failures"] = gate_failures(summary)
    text = json.dumps(summary, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 1 if args.gate and summary["gate_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
