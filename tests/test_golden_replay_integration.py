"""
tests/test_golden_replay_integration.py — Integration test for replay harness and G6 coverage.

Component 5 & Integration Lead (Matangi).
Verifies that replaying the golden example through the walking skeleton produces
schema-valid events.jsonl that achieves 100% trace coverage on the 6 invariants.
"""

import asyncio
from pathlib import Path
import pytest

from slrag.core.orchestrator import Orchestrator
from slrag.core.schemas import AnswerOutput
from slrag.core.session import SessionState
from slrag.stream.source_replay import ReplaySource
from slrag.telemetry.bus import TelemetryBus
from slrag.telemetry.coverage import TraceCoverageSuite
from slrag.telemetry.jsonl_sink import JSONLSink


def test_golden_replay_end_to_end(tmp_path: Path):
    golden_file = Path("bench/data/golden_example.jsonl")
    assert golden_file.exists()

    events_out = tmp_path / "events.jsonl"

    async def _run():
        bus = TelemetryBus()
        sink = JSONLSink(file_path=events_out)
        bus.subscribe(sink.write)

        session = SessionState(session_id="sess_integration_test")
        orchestrator = Orchestrator(session=session, bus=bus)
        source = ReplaySource(file_path=golden_file, real_time=False)

        last_ts = 0.0
        async for chunk in source.stream():
            last_ts = chunk.t_s
            await orchestrator.process_chunk(chunk)

        output = await orchestrator.finalize_turn(last_ts=last_ts)
        sink.close()
        return output

    output: AnswerOutput = asyncio.run(_run())

    # 1. Verify contractual 5 keys
    assert isinstance(output.retrieval_events, list)
    assert len(output.retrieval_events) > 0
    assert isinstance(output.sub_queries, list)
    assert len(output.sub_queries) > 0
    assert isinstance(output.answer, str)
    assert len(output.answer) > 0
    assert isinstance(output.citations, list)
    assert len(output.citations) > 0
    assert isinstance(output.uncertainty, str)

    # 2. Verify events.jsonl file was generated and populated
    assert events_out.exists()
    lines = events_out.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 8

    # 3. Verify Gate G6: 100% Trace Coverage Invariant Suite
    suite = TraceCoverageSuite(
        indexed_citation_labels={"Doc_12 §2", "Doc_31 §4", "Doc_09 §1"}
    )
    report = suite.evaluate_file(events_out)
    assert report.is_clean is True, f"Failed invariants: {report.details}"
    assert report.coverage_pct == 100.0
    assert report.passed == 6
