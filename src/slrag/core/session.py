"""Ephemeral in-process session store (HC-4, roadmap 4.1).

Session state lives only in this process's memory and is never written to
disk. A session is destroyed (its ``destroy()`` called, then dropped) when it
is ended explicitly, when it has been idle longer than ``ttl_s``, or when the
store closes. Expiry is swept lazily on every access, so no background task is
required; call ``sweep()`` from a timer if idle sessions must be reclaimed even
while no traffic arrives.

Turns within one session are serialised (``ClaimGraph`` allows a single open
revision); different sessions run concurrently. A session with a turn running
or waiting is never expired or evicted.

    store = SessionStore(lambda sid: SynthesisEngine(sid, retrieve_fn=retrieve), ttl_s=1800)
    async with store.turn(session_id) as engine:
        classification = engine.classify(utterance, controller_decisions)
        ...
        result = await engine.handle_turn(turn)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Generic, Protocol, TypeVar


class Destroyable(Protocol):
    def destroy(self) -> None: ...


T = TypeVar("T", bound=Destroyable)


class SessionCapacityError(RuntimeError):
    """Every session slot is busy with a running turn; nothing idle to evict."""


@dataclass
class _Entry(Generic[T]):
    value: T
    last_used: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    busy: int = 0              # turns running or waiting on the lock
    ended: bool = False        # destroy once the last turn leaves


class SessionStore(Generic[T]):
    def __init__(
        self,
        factory: Callable[[str], T],
        *,
        ttl_s: float,
        max_sessions: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_s <= 0:
            raise ValueError(f"ttl_s must be positive, got {ttl_s}")
        if max_sessions is not None and max_sessions < 1:
            raise ValueError(f"max_sessions must be >= 1, got {max_sessions}")
        self._factory = factory
        self._ttl_s = float(ttl_s)
        self._max_sessions = max_sessions
        self._clock = clock
        self._entries: dict[str, _Entry[T]] = {}

    @classmethod
    def from_config(cls, factory: Callable[[str], T], config: Mapping[str, Any], **kwargs: Any) -> SessionStore[T]:
        """Build from ``config/app.yaml``'s ``session:`` block (``ttl_s``, optional ``max_sessions``)."""
        session = config.get("session") or {}
        max_sessions = session.get("max_sessions")
        return cls(
            factory,
            ttl_s=float(session["ttl_s"]),
            max_sessions=int(max_sessions) if max_sessions is not None else None,
            **kwargs,
        )

    def __contains__(self, session_id: object) -> bool:
        return session_id in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, session_id: str) -> T:
        """The live session, created on first use. Outside ``turn()`` there is no serialisation."""
        return self._entry(session_id).value

    @asynccontextmanager
    async def turn(self, session_id: str) -> AsyncIterator[T]:
        """Exclusive access to one session for the duration of a turn."""
        entry = self._entry(session_id)
        entry.busy += 1
        try:
            async with entry.lock:
                yield entry.value
        finally:
            entry.busy -= 1
            entry.last_used = self._clock()
            if entry.ended and entry.busy == 0:
                entry.value.destroy()

    def end(self, session_id: str) -> bool:
        """Session end. A running turn finishes first; the next access starts a fresh session."""
        entry = self._entries.pop(session_id, None)
        if entry is None:
            return False
        self._retire(entry)
        return True

    def sweep(self) -> list[str]:
        """Destroy every idle session past its TTL; returns their ids."""
        now = self._clock()
        expired = [
            sid for sid, entry in self._entries.items()
            if entry.busy == 0 and now - entry.last_used > self._ttl_s
        ]
        for sid in expired:
            self._retire(self._entries.pop(sid))
        return expired

    def close(self) -> None:
        """Process shutdown: end every session."""
        for sid in list(self._entries):
            self.end(sid)

    def _entry(self, session_id: str) -> _Entry[T]:
        self.sweep()
        entry = self._entries.get(session_id)
        if entry is None:
            self._make_room()
            entry = _Entry(self._factory(session_id), last_used=self._clock())
            self._entries[session_id] = entry
        else:
            entry.last_used = self._clock()
        return entry

    def _make_room(self) -> None:
        if self._max_sessions is None or len(self._entries) < self._max_sessions:
            return
        idle = [(entry.last_used, sid) for sid, entry in self._entries.items() if entry.busy == 0]
        if not idle:
            raise SessionCapacityError(f"all {self._max_sessions} sessions are mid-turn")
        self.end(min(idle)[1])

    @staticmethod
    def _retire(entry: _Entry[T]) -> None:
        entry.ended = True
        if entry.busy == 0:
            entry.value.destroy()
