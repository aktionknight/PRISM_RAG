"""Prometheus metrics for the SLRAG pipeline (Component 5, obs profile).

Exposes standard metrics that Grafana dashboards query:
- Controller decisions (counter by type)
- Retrieval latency (histogram)
- LLM call count and tokens (counter)
- Active sessions (gauge)
- Citation support rate (gauge)
- Answer versions (counter)
"""

from __future__ import annotations

import logging
from typing import Any

try:
    from prometheus_client import (
        Counter,
        Gauge,
        Histogram,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False

logger = logging.getLogger(__name__)


if HAS_PROMETHEUS:
    # Controller
    CONTROLLER_DECISIONS = Counter(
        "slrag_controller_decisions_total",
        "Controller decisions by type and reason",
        ["decision", "reason"],
    )
    CONTROLLER_LATENCY = Histogram(
        "slrag_controller_latency_seconds",
        "Controller decision latency",
        buckets=[0.001, 0.003, 0.005, 0.010, 0.015, 0.030, 0.060],
    )

    # Retrieval
    RETRIEVAL_LATENCY = Histogram(
        "slrag_retrieval_latency_seconds",
        "Per-subquery retrieval latency",
        buckets=[0.01, 0.03, 0.06, 0.12, 0.25, 0.5, 1.0],
    )
    RETRIEVALS_TOTAL = Counter(
        "slrag_retrievals_total",
        "Total retrieval events",
        ["trigger"],
    )

    # Synthesis
    LLM_CALLS = Counter(
        "slrag_llm_calls_total",
        "LLM calls by component",
        ["component"],
    )
    LLM_TOKENS = Counter(
        "slrag_llm_tokens_total",
        "LLM tokens by type",
        ["type"],
    )
    ANSWER_VERSIONS = Counter(
        "slrag_answer_versions_total",
        "Answer version increments",
    )
    CLAIMS_TOTAL = Counter(
        "slrag_claims_total",
        "Claims by status",
        ["status"],
    )

    # Session
    ACTIVE_SESSIONS = Gauge(
        "slrag_active_sessions",
        "Currently active sessions",
    )

    # Quality gates
    CITATION_SUPPORT_RATE = Gauge(
        "slrag_citation_support_rate",
        "Fraction of claims with citation entailment",
    )
    FABRICATED_IDS = Counter(
        "slrag_fabricated_ids_total",
        "Fabricated citation IDs detected and stripped",
    )


def record_controller_decision(decision: str, reason: str, latency_s: float) -> None:
    if not HAS_PROMETHEUS:
        return
    CONTROLLER_DECISIONS.labels(decision=decision, reason=reason).inc()
    CONTROLLER_LATENCY.observe(latency_s)


def record_retrieval(trigger: str, latency_s: float) -> None:
    if not HAS_PROMETHEUS:
        return
    RETRIEVALS_TOTAL.labels(trigger=trigger).inc()
    RETRIEVAL_LATENCY.observe(latency_s)


def record_llm_call(component: str, prompt_tokens: int, completion_tokens: int) -> None:
    if not HAS_PROMETHEUS:
        return
    LLM_CALLS.labels(component=component).inc()
    LLM_TOKENS.labels(type="prompt").inc(prompt_tokens)
    LLM_TOKENS.labels(type="completion").inc(completion_tokens)


def record_answer_version(claims_retained: int, claims_superseded: int, claims_added: int) -> None:
    if not HAS_PROMETHEUS:
        return
    ANSWER_VERSIONS.inc()
    CLAIMS_TOTAL.labels(status="retained").inc(claims_retained)
    CLAIMS_TOTAL.labels(status="superseded").inc(claims_superseded)
    CLAIMS_TOTAL.labels(status="added").inc(claims_added)


def set_active_sessions(count: int) -> None:
    if not HAS_PROMETHEUS:
        return
    ACTIVE_SESSIONS.set(count)


def set_citation_support_rate(rate: float) -> None:
    if not HAS_PROMETHEUS:
        return
    CITATION_SUPPORT_RATE.set(rate)


def metrics_response() -> tuple[bytes, str]:
    """Return Prometheus exposition format for the /metrics endpoint."""
    if not HAS_PROMETHEUS:
        return b"# prometheus_client not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST
