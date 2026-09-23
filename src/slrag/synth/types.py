"""Component 4 internal contract.

These types are shared by claims / delta / generator / verifier / uncertainty /
renderer / engine. They are *internal* to Component 4 — the cross-team contract
remains ``slrag.core.schemas`` and is never widened here. Anything the frozen
``Claim`` / ``AnswerOutput`` cannot carry (confidence, superseded_by, lineage,
stream events) lives in these side structures instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Literal, Mapping, Protocol, Sequence, Union

from slrag.core.schemas import RetrievedChunk, SubIntent

TurnType = Literal["NEW_INTENT", "CONSTRAINT_REFINEMENT", "PRESENTATION_ONLY"]
StreamEventKind = Literal["provisional", "committed", "retracted"]
CoverageState = Literal["covered", "partial", "ambiguous", "uncovered"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class SynthError(Exception):
    """Base class for Component 4 invariant violations."""


class CitationNotAllowedError(SynthError):
    """A claim cited a label that was never admitted to the session context (S-6)."""


class PresentationInvariantError(SynthError):
    """A presentation-only turn produced citations outside the prior turn's set."""


class ClaimGraphError(SynthError):
    """Illegal ClaimGraph mutation (unknown claim, double revision, ...)."""


# ---------------------------------------------------------------------------
# Generation + verification (S-5 / S-6)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DraftClaim:
    """One generated sentence before verification. Never enters the graph unverified."""

    seq: int
    facet: str
    text: str
    citations: tuple[str, ...]
    intent_id: str | None = None
    confidence: float = 1.0


@dataclass(frozen=True)
class VerificationResult:
    draft: DraftClaim
    ok: bool
    text: str                                  # final sentence text, citation markers removed
    citations: tuple[str, ...]                 # final citations (allowlisted, maybe re-attributed)
    fabricated: tuple[str, ...] = ()           # labels stripped because they are not in the allowlist
    entailment: float | None = None            # best entailment score over cited chunks
    missing_values: tuple[str, ...] = ()       # numerals/entities absent from every cited chunk
    reattributed: bool = False
    supporting_chunk_ids: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()              # machine-readable failure / repair reasons
    latency_ms: float = 0.0


@dataclass(frozen=True)
class StreamEvent:
    """Two-pass streaming event: PROVISIONAL (dimmed) then COMMITTED (solid) or RETRACTED."""

    kind: StreamEventKind
    seq: int
    text: str
    citations: tuple[str, ...]
    facet: str
    intent_id: str | None = None
    verification: VerificationResult | None = None   # None on provisional events

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "seq": self.seq,
            "text": self.text,
            "citations": list(self.citations),
            "facet": self.facet,
            "intent_id": self.intent_id,
        }
        if self.verification is not None:
            payload["entailment"] = self.verification.entailment
            payload["fabricated"] = list(self.verification.fabricated)
            payload["reasons"] = list(self.verification.reasons)
            payload["verify_latency_ms"] = self.verification.latency_ms
        return payload


@dataclass(frozen=True)
class GenerationUsage:
    """Token accounting for Matangi's cost model (``count(llm_calls) == count(cost_records)``)."""

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    backend: str = "extractive"
    latency_ms: float = 0.0
    first_draft_ms: float | None = None   # LLM call start -> first complete claim (TTFT evidence, audit W-1)


# ---------------------------------------------------------------------------
# Delta engine (S-4)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConstraintDelta:
    slots: Mapping[str, str] = field(default_factory=dict)   # {slot: value}, e.g. {"trip_type": "international"}
    raw_text: str = ""

    def __bool__(self) -> bool:
        return bool(self.slots)


@dataclass(frozen=True)
class TurnClassification:
    turn_type: TurnType
    reason: str
    delta: ConstraintDelta = field(default_factory=ConstraintDelta)
    # SynthesisEngine turn counter when classify() ran; handle_turn() re-classifies if
    # another turn ran on the session in between (audit N-3). None = not stamped.
    session_epoch: int | None = None

    @property
    def needs_upstream_retrieval(self) -> bool:
        """Whether Components 2-3 should decompose and retrieve for this turn (audit C-3).

        Refinement turns issue only Component 4's targeted delta queries, and
        presentation turns retrieve nothing, so both skip the full upstream pass.
        """
        return self.turn_type == "NEW_INTENT"


@dataclass(frozen=True)
class DeltaTarget:
    """One (affected facet x new constraint) pair — the unit of targeted re-retrieval."""

    facet: str
    slot: str
    value: str
    affected_claim_ids: tuple[str, ...]
    sub_intent: SubIntent                              # the targeted delta query
    pool_chunks: tuple[RetrievedChunk, ...] = ()       # non-empty => resolved from EvidencePool

    @property
    def resolved_from_pool(self) -> bool:
        return bool(self.pool_chunks)


@dataclass
class DeltaPlan:
    delta: ConstraintDelta
    retained: list[str]                  # active claim ids kept verbatim
    affected: list[str]                  # active claim ids whose preconditions conflict
    targets: list[DeltaTarget]

    @property
    def queries(self) -> list[SubIntent]:
        """Targeted delta queries that still need dispatch (not resolvable from the pool)."""
        return [t.sub_intent for t in self.targets if not t.resolved_from_pool]


@dataclass(frozen=True)
class VersionLineage:
    from_version: int
    to_version: int
    retained: tuple[str, ...]
    superseded: tuple[str, ...]
    added: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """The additive ``version_lineage`` output field (A_FINAL_ARCHITECTURE §6)."""
        return {
            "from": self.from_version,
            "to": self.to_version,
            "retained": list(self.retained),
            "superseded": list(self.superseded),
            "added": list(self.added),
        }


@dataclass
class RefinementReport:
    """G5 evidence, emitted on every refinement (A_FINAL_ARCHITECTURE §4.2)."""

    from_version: int
    to_version: int
    claims_retained: int
    claims_superseded: int
    claims_added: int
    delta_queries_issued: int
    citations_preserved: list[str] = field(default_factory=list)
    citations_added: list[str] = field(default_factory=list)
    pool_resolved_targets: int = 0
    latency_ms: float = 0.0
    full_corpus_searches: int = 0        # structurally 0: the delta path only issues targeted queries
    session_cleared: bool = False

    def to_event(self) -> dict[str, Any]:
        return {
            "event": "answer_refined",
            "from_version": self.from_version,
            "to_version": self.to_version,
            "claims_retained": self.claims_retained,
            "claims_superseded": self.claims_superseded,
            "claims_added": self.claims_added,
            "delta_queries_issued": self.delta_queries_issued,
            "full_corpus_searches": self.full_corpus_searches,
            "citations_preserved": list(self.citations_preserved),
            "citations_added": list(self.citations_added),
            "pool_resolved_targets": self.pool_resolved_targets,
            "session_cleared": self.session_cleared,
            "latency_ms": self.latency_ms,
        }


# ---------------------------------------------------------------------------
# Coverage matrix (S-10)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CoverageRow:
    intent_id: str
    facet: str
    query: str
    best_score: float | None
    claim_ids: tuple[str, ...]
    state: CoverageState
    message: str | None = None           # uncertainty sentence or clarification question
    is_clarification: bool = False
    missing_entities: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Ports to other components (never import their internals)
# ---------------------------------------------------------------------------
# Aakrit's retriever, same signature as stubs.fake_retriever.fake_retrieve (sync or async).
RetrieveFn = Callable[[SubIntent], Union[Sequence[RetrievedChunk], Awaitable[Sequence[RetrievedChunk]]]]


class EvidencePoolView(Protocol):
    """Read-only view of Aakrit's session EvidencePool (retrieve/pool.py)."""

    def chunks(self) -> Iterable[RetrievedChunk]: ...
