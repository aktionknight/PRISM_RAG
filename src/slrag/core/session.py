"""Ephemeral in-process session store (HC-4, roadmap 4.1).

Session state lives only in this process's memory and is never written to
disk. A session is destroyed (its ``destroy()`` called, then dropped) when it
is ended explicitly, when it has been idle longer than ``ttl_s``, or when the
store closes. Expiry is swept lazily on every access, so no background task is
required; run ``sweep_forever()`` as a task if idle sessions must be reclaimed
even while no traffic arrives.

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
from typing import Any, Dict, Generic, Optional, Protocol, TypeVar

from slrag.core.schemas import Claim, ClaimStatus, EvidencePoolEntry, SubIntent, VersionLineage


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
        """Exclusive access to one session for the duration of a turn.

        A turn that was waiting on the lock when its session was ended runs on a
        fresh session, never on the retired one (audit N-5).
        """
        while True:
            entry = self._entry(session_id)
            entry.busy += 1
            try:
                async with entry.lock:
                    if entry.ended:
                        continue
                    yield entry.value
                    return
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

    async def sweep_forever(self, interval_s: float | None = None) -> None:
        """Sweep on a timer (default every ``ttl_s / 4``) until cancelled, so idle sessions
        are reclaimed even while no traffic arrives (audit I-10)::

            sweeper = asyncio.create_task(store.sweep_forever())
            ...
            sweeper.cancel(); store.close()
        """
        interval = self._ttl_s / 4 if interval_s is None else float(interval_s)
        if interval <= 0:
            raise ValueError(f"interval_s must be positive, got {interval}")
        while True:
            await asyncio.sleep(interval)
            self.sweep()

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


# ---------------------------------------------------------------------------
# Component 1 (Diya): controller-side state — speculation branches, running prefix,
# refractory timer. Lives on ``SessionState.controller``; destroyed with the session (HC-4).
# ---------------------------------------------------------------------------
class EvidencePool:
    """Session-scoped, chunk-ID-keyed store for retrieved evidence."""
    
    def __init__(self):
        # chunk_id -> dict of chunk data
        self._chunks: Dict[str, Dict[str, Any]] = {}
        
    def add_chunk(self, chunk_id: str, data: Dict[str, Any]) -> None:
        if chunk_id not in self._chunks:
            self._chunks[chunk_id] = data
            
    def get_chunk(self, chunk_id: str) -> Dict[str, Any]:
        return self._chunks.get(chunk_id)
        
    def demote_to_pool(self, chunk_id: str, data: Dict[str, Any]) -> None:
        """Add a chunk from a cancelled speculative branch."""
        data['speculative'] = True
        self.add_chunk(chunk_id, data)


class ControllerState:
    """Controller-side, ephemeral per-session state (was ``SessionState`` on the diya branch)."""
    
    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self.evidence_pool = EvidencePool()
        
        # Speculative branches: dict of branch_id -> branch_data
        self.active_speculations: Dict[str, Dict[str, Any]] = {}
        
        # Prefix tracking for the controller
        self.current_prefix: str = ""
        self.last_embedding = None
        self.last_retrieve_time: float = -1000.0  # Allow immediate first retrieval
        
    def clear(self):
        """Destroy session state (HC-4)."""
        self.evidence_pool = EvidencePool()
        self.active_speculations = {}
        self.current_prefix = ""
        self.last_embedding = None
        self.last_retrieve_time = -1000.0


# ---------------------------------------------------------------------------
# Session owner (Aakrit): IntentSet, EvidencePool, ClaimGraph snapshot and the
# controller state for one session. In-process only (HC-4).
# ---------------------------------------------------------------------------
@dataclass
class SessionState:
    """Ephemeral state for a single user session.

    This is the single in-process store satisfying HC-4.
    Contains the IntentSet, EvidencePool, and ClaimGraph.
    """

    session_id: str = ""
    turn_id: int = 0
    answer_version: int = 0
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 3600.0  # 1 hour default

    # ── IntentSet (Component 2 — Aakrit) ──
    # Monotonic: only ever grows.  Keyed by intent_id.
    intent_set: dict[str, SubIntent] = field(default_factory=dict)

    # ── EvidencePool (Component 3 — Aakrit) ──
    # Every chunk ever retrieved, keyed by chunk_id.
    evidence_pool: dict[str, EvidencePoolEntry] = field(default_factory=dict)

    # ── ClaimGraph (Component 4 — Sivansh) ──
    claims: list[Claim] = field(default_factory=list)
    version_lineage: list[VersionLineage] = field(default_factory=list)

    # ── Previous prefix embedding for drift detection ──
    prev_prefix_embedding: Optional[list[float]] = None

    # ── Controller state (Component 1 — Diya) ──
    controller: ControllerState = field(default_factory=ControllerState)

    def __post_init__(self) -> None:
        self.controller.session_id = self.session_id
        self.controller.session = self

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl_seconds

    @property
    def active_claims(self) -> list[Claim]:
        return [c for c in self.claims if c.status == ClaimStatus.active]

    @property
    def all_citation_labels(self) -> set[str]:
        """The closed citation allowlist — union of all evidence pool labels."""
        return {entry.citation_label for entry in self.evidence_pool.values()}

    def new_turn(self) -> int:
        """Advance the turn counter and return the new turn_id."""
        self.turn_id += 1
        return self.turn_id

    def new_version(self) -> int:
        """Advance the answer version counter and return the new version."""
        self.answer_version += 1
        return self.answer_version

    def add_evidence(self, entry: EvidencePoolEntry) -> None:
        """Add or update an evidence pool entry (idempotent by chunk_id)."""
        existing = self.evidence_pool.get(entry.chunk_id)
        if existing:
            # Merge scores and version usage; keep earliest retrieval time
            existing.scores_by_subquery.update(entry.scores_by_subquery)
            existing.used_in_versions = list(
                set(existing.used_in_versions) | set(entry.used_in_versions)
            )
            existing.first_retrieved_ts = min(
                existing.first_retrieved_ts, entry.first_retrieved_ts
            )
            # If it was speculative and is now confirmed, mark confirmed
            if not entry.speculative:
                existing.speculative = False
        else:
            self.evidence_pool[entry.chunk_id] = entry

    def get_dispatched_intents(self) -> list[SubIntent]:
        """Return all intents that have already been dispatched for retrieval."""
        return [i for i in self.intent_set.values() if i.dispatched]

    def get_pending_intents(self) -> list[SubIntent]:
        """Return all intents pending dispatch."""
        return [
            i for i in self.intent_set.values()
            if not i.dispatched and i.status.value == "pending"
        ]

    def destroy(self) -> None:
        """Explicitly clear all session state — called on session end."""
        self.intent_set.clear()
        self.evidence_pool.clear()
        self.claims.clear()
        self.version_lineage.clear()
        self.prev_prefix_embedding = None
        self.controller.clear()
