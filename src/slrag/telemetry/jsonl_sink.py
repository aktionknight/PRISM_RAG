"""
telemetry/jsonl_sink.py — Always-on, append-only JSONL sink for events.jsonl.

Component 5 — Observability & Telemetry (Matangi).
Writes schema-compliant TelemetryEvent lines directly to disk. This is the
exact artifact evaluated by the replay and scoring harnesses (Gate G6, HC-5).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Union

from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)


class JSONLSink:
    """Appends TelemetryEvent records to a JSONL file immediately.
    
    Zero third-party service dependencies. Flushes every event to disk so that
    streaming runs are crash-resilient and auditable in real-time.
    """

    def __init__(self, file_path: Union[str, Path] = "runs/events.jsonl") -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.file_path, "a", encoding="utf-8")
        self._closed = False

    def write(self, event: TelemetryEvent) -> None:
        """Write a single TelemetryEvent to the JSONL log."""
        if self._closed:
            raise RuntimeError("Cannot write to a closed JSONLSink.")
        try:
            line = event.model_dump_json()
            self._file.write(line + "\n")
            self._file.flush()
        except Exception as e:
            logger.error(f"Failed to write event {event.event_id} to {self.file_path}: {e}")

    def close(self) -> None:
        """Flush and close the underlying file."""
        if not self._closed:
            self._file.flush()
            self._file.close()
            self._closed = True

    def __enter__(self) -> JSONLSink:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
