"""
core/session.py — Ephemeral, in-process session state (HC-4).

Holds the IntentSet, EvidencePool, and ClaimGraph for a single session.
No disk persistence.  Destroyed on session end or TTL expiry.
Cross-session isolation: each session gets its own SessionState instance.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from slrag.core.schemas import (
    Claim,
    ClaimStatus,
    EvidencePoolEntry,
    SubIntent,
    VersionLineage,
)


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
