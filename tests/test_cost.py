"""
tests/test_cost.py — Unit tests for CostTracker and pricing accounting.

Component 5 — Observability & Telemetry (Matangi).
"""

from pathlib import Path
import pytest

from slrag.core.schemas import TelemetrySummary
from slrag.telemetry.bus import TelemetryBus
from slrag.telemetry.cost import CostTracker


class TestCostTracker:
    def test_cost_calculation_llm(self):
        bus = TelemetryBus()
        tracker = CostTracker(bus=bus)

        # qwen2.5-7b-instruct: prompt $0.0005/1k, completion $0.0015/1k
        # 1000 prompt tok = $0.0005, 1000 comp tok = $0.0015 -> total = $0.0020
        rec = tracker.record_llm_call(
            component="synthesizer",
            model_name="qwen2.5-7b-instruct",
            prompt_tokens=1000,
            completion_tokens=1000,
            session_id="s1",
            turn_id=1,
            ts_stream_s=1.5,
        )

        assert rec["cost_usd"] == 0.002
        assert rec["total_tokens"] == 2000
        assert tracker.get_total_cost() == 0.002

        # Check bus emitted events
        events = bus.get_events()
        assert len(events) == 2
        assert events[0].event_type == "llm_call"
        assert events[1].event_type == "cost_record"

    def test_compute_proxy_cost(self):
        tracker = CostTracker()
        rec_emb = tracker.record_compute_proxy("embedder", "embedding", 500)
        # embedding: $0.0001/1k -> 500 items = $0.00005
        assert rec_emb["cost_usd"] == 0.00005

        rec_rrk = tracker.record_compute_proxy("reranker", "reranker", 100)
        # reranker: $0.0005/1k -> 100 items = $0.00005
        assert rec_rrk["cost_usd"] == 0.00005

    def test_turn_summary(self):
        tracker = CostTracker()
        tracker.record_llm_call("decomposer", "qwen2.5-0.5b", 200, 50, turn_id=1)
        tracker.record_llm_call("synthesizer", "qwen2.5-7b-instruct", 500, 150, turn_id=1)

        summary = tracker.get_turn_summary(
            turn_id=1,
            latency_metrics={"first_retrieval": 800.0, "first_token_after_end": 280.0},
        )
        assert isinstance(summary, TelemetrySummary)
        assert summary.tokens["prompt"] == 700
        assert summary.tokens["completion"] == 200
        assert summary.cost_usd > 0.0
        assert summary.latency_ms["first_retrieval"] == 800.0
