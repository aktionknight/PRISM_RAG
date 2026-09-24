"""JSONL telemetry sink — append-only, schema-versioned (Component 5, §5.1a).

The ``events.jsonl`` file is the scoring artifact the replay harness uses.
It must never depend on external services (HC-5, G1 resilience).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from slrag.core.schemas import TelemetryEvent

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path("runs/events.jsonl")


class JSONLSink:
    """Append-only JSONL writer for telemetry events."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else _DEFAULT_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a", encoding="utf-8")
        self._count = 0

    async def __call__(self, event: TelemetryEvent) -> None:
        """Write one event as a JSON line."""
        try:
            line = event.model_dump_json()
            self._handle.write(line + "\n")
            self._handle.flush()
            self._count += 1
        except Exception:
            logger.exception("JSONL sink write error")

    def close(self) -> None:
        self._handle.close()

    @property
    def count(self) -> int:
        return self._count
