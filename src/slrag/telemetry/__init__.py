"""
telemetry — bus, sinks, cost model, coverage checker.

Component 5 — Observability & Telemetry (Matangi).
"""

from slrag.telemetry.bus import TelemetryBus, generate_event_id
from slrag.telemetry.cost import CostTracker
from slrag.telemetry.coverage import TraceCoverageReport, TraceCoverageSuite
from slrag.telemetry.jsonl_sink import JSONLSink
from slrag.telemetry.otel_sink import OpenTelemetrySink

__all__ = [
    "TelemetryBus",
    "generate_event_id",
    "JSONLSink",
    "CostTracker",
    "OpenTelemetrySink",
    "TraceCoverageSuite",
    "TraceCoverageReport",
]
