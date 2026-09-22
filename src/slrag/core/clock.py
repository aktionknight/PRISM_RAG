"""
core/clock.py — Stream clock abstraction.

Provides both real-time and virtual-time (replay) clocks so that
timestamp_s in every event is always stream-time from utterance start,
never wall-clock time.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod


class StreamClock(ABC):
    """Abstract clock that maps wall-time to stream-time."""

    @abstractmethod
    def stream_time(self) -> float:
        """Return current stream time in seconds from utterance start."""
        ...

    @abstractmethod
    async def wait_until(self, t_s: float) -> None:
        """Block until stream time reaches t_s."""
        ...

    @abstractmethod
    def reset(self) -> None:
        """Reset the clock for a new utterance."""
        ...


class RealTimeClock(StreamClock):
    """Clock that tracks real elapsed time from utterance start."""

    def __init__(self) -> None:
        self._start: float = time.monotonic()

    def stream_time(self) -> float:
        return time.monotonic() - self._start

    async def wait_until(self, t_s: float) -> None:
        remaining = t_s - self.stream_time()
        if remaining > 0:
            await asyncio.sleep(remaining)

    def reset(self) -> None:
        self._start = time.monotonic()


class VirtualClock(StreamClock):
    """Clock driven by replay timestamps — no real waiting.

    Used by ReplaySource for deterministic, fast-forward evaluation.
    """

    def __init__(self) -> None:
        self._current_t: float = 0.0

    def stream_time(self) -> float:
        return self._current_t

    def advance_to(self, t_s: float) -> None:
        """Advance virtual clock to the given stream time."""
        self._current_t = max(self._current_t, t_s)

    async def wait_until(self, t_s: float) -> None:
        # In virtual mode, no actual waiting — just advance
        self.advance_to(t_s)

    def reset(self) -> None:
        self._current_t = 0.0
