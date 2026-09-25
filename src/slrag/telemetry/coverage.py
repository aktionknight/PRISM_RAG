"""
telemetry/coverage.py — Trace-Coverage Invariant Suite.

Component 5 — Observability & Telemetry (Matangi).
Proves Gate G6 and deliverable D5 through 6 assertable invariants over events.jsonl:
  1. Every chunk has a decision: count(chunks) == count(controller_decisions)
  2. Every retrieval has a parent: every retrieval follows a RETRIEVE decision
  3. Every citation resolves: citations in indexed chunk IDs / valid format
  4. Every answer has lineage: version > 1 has a version_lineage record
  5. Every LLM call is costed: count(llm_calls) == count(cost_records)
  6. Every turn is timed: ts_stream_s is present and monotonic
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from slrag.core.events import (
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_COST_RECORD,
    EVT_LLM_CALL,
    EVT_RETRIEVAL_STARTED,
)
from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)

class TraceCoverageReport:
    """Encapsulates results of trace-coverage invariant validation."""

    def __init__(self, passed: int, total: int, details: Dict[str, Dict[str, Any]]) -> None:
        self.passed = passed
        self.total = total
        self.details = details
        self.coverage_pct = round((passed / total * 100.0) if total > 0 else 0.0, 2)
        self.is_clean = (passed == total)

    def summary(self) -> str:
        lines = [
            f"=== Trace-Coverage Invariant Report ===",
            f"Result: {self.passed}/{self.total} Invariants Passed ({self.coverage_pct}%)",
        ]
        for name, d in self.details.items():
            status = "PASS" if d["passed"] else "FAIL"
            lines.append(f"  [{status}] {name}: {d['message']}")
        return "\n".join(lines)


class TraceCoverageSuite:
    """Evaluates an events stream (in-memory or events.jsonl) against the 6 invariants."""

    def __init__(self, indexed_citation_labels: Optional[set[str]] = None) -> None:
        self.indexed_citation_labels = indexed_citation_labels

    def evaluate_events(self, events: List[Union[TelemetryEvent, dict]]) -> TraceCoverageReport:
        """Run all 6 invariants across a list of TelemetryEvent records."""
        parsed_events: List[dict] = []
        for e in events:
            if isinstance(e, TelemetryEvent):
                parsed_events.append(e.model_dump())
            elif isinstance(e, dict):
                parsed_events.append(e)

        details: Dict[str, Dict[str, Any]] = {}

        # Invariant 1: Every chunk has a decision
        # count(chunks) == count(controller_decisions)
        chunk_count = sum(1 for e in parsed_events if e.get("event_type") == EVT_CHUNK_RECEIVED)
        decision_count = sum(1 for e in parsed_events if e.get("event_type") == EVT_CONTROLLER_DECISION)
        inv1_pass = (chunk_count == decision_count) and (chunk_count > 0)
        details["chunk_decision_parity"] = {
            "passed": inv1_pass,
            "message": f"{decision_count} decisions for {chunk_count} chunks",
            "stats": {"chunks": chunk_count, "decisions": decision_count},
        }

        # Invariant 2: Every retrieval has a parent
        # every retrieval_event follows a RETRIEVE controller decision
        inv2_pass = True
        inv2_msg = "All retrieval events have preceding RETRIEVE decisions"
        has_retrieve_decision = False
        retrieval_count = 0
        for e in parsed_events:
            ev_type = e.get("event_type")
            if ev_type == EVT_CONTROLLER_DECISION:
                payload = e.get("payload", {})
                if payload.get("decision") == "RETRIEVE":
                    has_retrieve_decision = True
            elif ev_type == EVT_RETRIEVAL_STARTED:
                retrieval_count += 1
                if not has_retrieve_decision:
                    inv2_pass = False
                    inv2_msg = f"Retrieval event at {e.get('ts_stream_s')}s occurred without preceding RETRIEVE"
                    break
        details["retrieval_parentage"] = {
            "passed": inv2_pass,
            "message": inv2_msg,
            "stats": {"retrievals": retrieval_count},
        }

        # Invariant 3: Every citation resolves
        # Every citation must resolve to a label from the built index.
        inv3_pass = True
        inv3_msg = "All emitted citations resolve"
        total_citations = 0
        for e in parsed_events:
            payload = e.get("payload", {})
            citations = payload.get("citations", [])
            for cit in citations:
                total_citations += 1
                if self.indexed_citation_labels is None:
                    inv3_pass = False
                    inv3_msg = "Citation allowlist was not supplied"
                    break
                if cit not in self.indexed_citation_labels:
                    inv3_pass = False
                    inv3_msg = f"Citation '{cit}' not found in index"
                    break
            if not inv3_pass:
                break
        details["citation_resolution"] = {
            "passed": inv3_pass,
            "message": inv3_msg,
            "stats": {"citations_checked": total_citations},
        }

        # Invariant 4: Every answer version > 1 has a version_lineage record
        inv4_pass = True
        inv4_msg = "All multi-version answers have version_lineage records"
        versions_seen = set()
        lineages_seen = set()
        for e in parsed_events:
            payload = e.get("payload", {})
            v = payload.get("version") or payload.get("answer_version")
            if v and v > 1:
                versions_seen.add(v)
            if "version_lineage" in payload and payload["version_lineage"]:
                lineage = payload["version_lineage"]
                to_ver = lineage.get("to_version") or lineage.get("to")
                if to_ver:
                    lineages_seen.add(to_ver)
        for v in versions_seen:
            if v not in lineages_seen:
                inv4_pass = False
                inv4_msg = f"Answer version {v} lacks version_lineage record"
                break
        details["version_lineage"] = {
            "passed": inv4_pass,
            "message": inv4_msg,
            "stats": {"versions_gt_1": list(versions_seen)},
        }

        # Invariant 5: Every LLM call is costed
        # Every LLM call must have exactly one matching cost record.
        llm_ids = [
            e.get("payload", {}).get("call_id")
            for e in parsed_events
            if e.get("event_type") == EVT_LLM_CALL
        ]
        cost_ids = [
            e.get("payload", {}).get("call_id")
            for e in parsed_events
            if e.get("event_type") == EVT_COST_RECORD
            and e.get("payload", {}).get("item_type") == "llm"
        ]
        inv5_pass = (
            all(call_id for call_id in llm_ids)
            and len(llm_ids) == len(cost_ids)
            and len(set(llm_ids)) == len(llm_ids)
            and set(llm_ids) == set(cost_ids)
        )
        details["cost_accounting"] = {
            "passed": inv5_pass,
            "message": f"{len(cost_ids)} matched LLM cost records for {len(llm_ids)} calls",
            "stats": {"llm_calls": len(llm_ids), "llm_cost_records": len(cost_ids)},
        }

        # Invariant 6: Every turn is timed and monotonic
        # ts_stream_s present and monotonic across events
        inv6_pass = True
        inv6_msg = "All stream timestamps are present and monotonic"
        prev_ts = -1.0
        for e in parsed_events:
            ts = e.get("ts_stream_s")
            if ts is None:
                inv6_pass = False
                inv6_msg = f"Event {e.get('event_id')} missing ts_stream_s"
                break
            if ts < prev_ts:
                inv6_pass = False
                inv6_msg = f"Timestamp regress from {prev_ts}s to {ts}s at event {e.get('event_id')}"
                break
            prev_ts = ts
        details["monotonic_timestamps"] = {
            "passed": inv6_pass,
            "message": inv6_msg,
            "stats": {"final_ts": prev_ts},
        }

        passed_count = sum(1 for d in details.values() if d["passed"])
        total_count = len(details)
        return TraceCoverageReport(passed=passed_count, total=total_count, details=details)

    def evaluate_file(
        self,
        file_path: Union[str, Path],
        indexed_citation_labels: Optional[set[str]] = None,
    ) -> TraceCoverageReport:
        """Read and evaluate an events.jsonl file."""
        path = Path(file_path)
        if not path.exists():
            return TraceCoverageReport(
                passed=0,
                total=6,
                details={"file": {"passed": False, "message": f"File not found: {path}"}},
            )
        events = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        if indexed_citation_labels is not None:
            self.indexed_citation_labels = indexed_citation_labels
        return self.evaluate_events(events)


def load_indexed_citation_labels(index_dir: Union[str, Path] = ".index") -> set[str]:
    """Load citation labels emitted by the built corpus index."""
    index_path = Path(index_dir)
    chunks_path = index_path / "chunks.jsonl"
    if not chunks_path.exists():
        raise FileNotFoundError(
            f"Indexed chunks not found at {chunks_path}; build the index before coverage checks"
        )

    labels: set[str] = set()
    with chunks_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                label = record.get("citation_label")
                if label:
                    labels.add(label)
    return labels
