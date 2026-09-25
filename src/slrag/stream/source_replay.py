"""
stream/source_replay.py — JSONL streaming transcript replay source.

Component 5 & Stream Layer (Matangi).
Replays timestamped transcript chunks from JSONL benchmark fixtures against
either a virtual clock (instantaneous for CI/evaluation) or a real-time clock
(for live paced demos).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator, Optional, Union

from slrag.core.clock import RealTimeClock, StreamClock, VirtualClock
from slrag.core.schemas import TranscriptChunk

logger = logging.getLogger(__name__)


class ReplaySource:
    """Async generator yielding TranscriptChunks from a recorded JSONL stream."""

    def __init__(
        self,
        file_path: Union[str, Path],
        clock: Optional[StreamClock] = None,
        real_time: bool = False,
        speed_factor: float = 1.0,
    ) -> None:
        self.file_path = Path(file_path)
        if not self.file_path.exists():
            raise FileNotFoundError(f"Stream file not found: {self.file_path}")

        if clock is not None:
            self.clock = clock
        else:
            self.clock = RealTimeClock() if real_time else VirtualClock()

        self.speed_factor = max(0.1, float(speed_factor))
        self.real_time = real_time

    async def stream(self) -> AsyncGenerator[TranscriptChunk, None]:
        """Stream chunks asynchronously with timing governed by the clock."""
        self.clock.reset()

        with open(self.file_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    chunk = TranscriptChunk(**data)
                except Exception as e:
                    logger.warning(f"Skipping malformed chunk at line {line_no} in {self.file_path}: {e}")
                    continue

                target_t = chunk.t_s / self.speed_factor
                await self.clock.wait_until(target_t)
                yield chunk
