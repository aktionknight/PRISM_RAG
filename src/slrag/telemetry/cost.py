"""
telemetry/cost.py — Token, compute, and dollar cost accounting.

Component 5 — Observability & Telemetry (Matangi).
Tracks token counts per LLM call and compute proxy items (embeddings, rerankers)
against config/pricing.yaml to compute cost_usd per turn, component, and session.
Enforces HC-5 parsimony tracking.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional, Union
import yaml

from slrag.core.events import EVT_COST_RECORD, EVT_LLM_CALL
from slrag.core.schemas import TelemetrySummary
from slrag.telemetry.bus import generate_event_id

logger = logging.getLogger(__name__)

DEFAULT_PRICING_PATH = Path("config/pricing.yaml")


class CostTracker:
    """Computes and tracks LLM and retrieval costs according to pricing.yaml."""

    def __init__(
        self,
        pricing_path: Union[str, Path] = DEFAULT_PRICING_PATH,
        bus: Optional[Any] = None,
    ) -> None:
        self.pricing_path = Path(pricing_path)
        self.bus = bus
        self.pricing = self._load_pricing()
        self.records: list[dict[str, Any]] = []

    def _load_pricing(self) -> dict[str, Any]:
        """Load pricing tables from YAML."""
        if not self.pricing_path.exists():
            logger.warning(f"Pricing config not found at {self.pricing_path}, using default fallbacks.")
            return {
                "models": {
                    "qwen2.5-7b-instruct": {
                        "prompt_per_1k_tokens": 0.0005,
                        "completion_per_1k_tokens": 0.0015,
                    },
                    "qwen2.5-0.5b": {
                        "prompt_per_1k_tokens": 0.0001,
                        "completion_per_1k_tokens": 0.0003,
                    },
                },
                "embedding": {"cost_per_1k_items": 0.0001},
                "reranker": {"cost_per_1k_items": 0.0005},
            }
        try:
            with open(self.pricing_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to read pricing yaml: {e}")
            return {}

    def record_llm_call(
        self,
        component: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        session_id: str = "",
        turn_id: int = 1,
        ts_stream_s: float = 0.0,
        latency_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Record an LLM call, calculate cost, and emit telemetry."""
        model_rates = self.pricing.get("models", {}).get(model_name, {})
        p_rate = model_rates.get("prompt_per_1k_tokens", 0.0005)
        c_rate = model_rates.get("completion_per_1k_tokens", 0.0015)

        cost_prompt = (prompt_tokens / 1000.0) * p_rate
        cost_completion = (completion_tokens / 1000.0) * c_rate
        total_cost = cost_prompt + cost_completion
        call_id = generate_event_id()

        record = {
            "call_id": call_id,
            "type": "llm",
            "component": component,
            "model": model_name,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "cost_usd": round(total_cost, 6),
            "session_id": session_id,
            "turn_id": turn_id,
            "ts_stream_s": ts_stream_s,
            "latency_ms": latency_ms,
        }
        self.records.append(record)

        if self.bus:
            self.bus.emit(
                event_type=EVT_LLM_CALL,
                component=component,
                session_id=session_id,
                turn_id=turn_id,
                ts_stream_s=ts_stream_s,
                latency_ms=latency_ms,
                payload={
                    "call_id": call_id,
                    "model": model_name,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                },
            )
            self.bus.emit(
                event_type=EVT_COST_RECORD,
                component=component,
                session_id=session_id,
                turn_id=turn_id,
                ts_stream_s=ts_stream_s,
                latency_ms=0.0,
                payload={
                    "call_id": call_id,
                    "cost_usd": record["cost_usd"],
                    "item_type": "llm",
                    "model": model_name,
                },
            )

        return record

    def record_compute_proxy(
        self,
        component: str,
        category: str,  # 'embedding' or 'reranker'
        items_count: int,
        session_id: str = "",
        turn_id: int = 1,
        ts_stream_s: float = 0.0,
        latency_ms: float = 0.0,
    ) -> dict[str, Any]:
        """Record embedding or rerank item processing as a compute-proxy cost."""
        cat_info = self.pricing.get(category, {})
        rate = cat_info.get("cost_per_1k_items", 0.0001)
        cost = (items_count / 1000.0) * rate

        record = {
            "type": category,
            "component": component,
            "items_count": items_count,
            "cost_usd": round(cost, 6),
            "session_id": session_id,
            "turn_id": turn_id,
            "ts_stream_s": ts_stream_s,
            "latency_ms": latency_ms,
        }
        self.records.append(record)

        if self.bus:
            self.bus.emit(
                event_type=EVT_COST_RECORD,
                component=component,
                session_id=session_id,
                turn_id=turn_id,
                ts_stream_s=ts_stream_s,
                latency_ms=0.0,
                payload={
                    "cost_usd": record["cost_usd"],
                    "item_type": category,
                    "items_count": items_count,
                },
            )

        return record

    def get_turn_summary(
        self,
        turn_id: int,
        latency_metrics: Optional[dict[str, float]] = None,
    ) -> TelemetrySummary:
        """Assemble a TelemetrySummary model for embedding into AnswerOutput."""
        turn_records = [r for r in self.records if r.get("turn_id") == turn_id]
        prompt_toks = sum(r.get("prompt_tokens", 0) for r in turn_records if r.get("type") == "llm")
        comp_toks = sum(r.get("completion_tokens", 0) for r in turn_records if r.get("type") == "llm")
        total_cost = sum(r.get("cost_usd", 0.0) for r in turn_records)

        return TelemetrySummary(
            latency_ms=latency_metrics or {},
            tokens={"prompt": prompt_toks, "completion": comp_toks},
            cost_usd=round(total_cost, 6),
        )

    def get_total_cost(self, session_id: Optional[str] = None) -> float:
        """Get aggregate cost in USD."""
        recs = self.records
        if session_id:
            recs = [r for r in recs if r.get("session_id") == session_id]
        return round(sum(r.get("cost_usd", 0.0) for r in recs), 6)
