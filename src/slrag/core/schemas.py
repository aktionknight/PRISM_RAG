"""
core/schemas.py — FROZEN AFTER DAY-1 CONTRACT SESSION.
═══════════════════════════════════════════════════════
Changes require a ping to ALL 4 team members (Diya, Aakrit, Sivansh, Matangi).

These Pydantic models are the inter-component contracts for the entire
Streaming Live RAG pipeline.  Every module reads from, and writes to,
exactly these types.  No field additions/removals without coordination.

Validated against:
  - A_FINAL_ARCHITECTURE.md §6 (Output Schema — Contractual)
  - C_TEAM_COORDINATION.md §2 (Contract Freeze)
  - 02_SOLUTION_DESIGN.md (all module interfaces)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════
# Enums — shared vocabularies
# ═══════════════════════════════════════════════════════════════════

class ControllerDecisionType(str, Enum):
    """Ternary decision emitted by the Retrieval Controller."""
    WAIT = "WAIT"
    RETRIEVE = "RETRIEVE"
    NO_RETRIEVAL = "NO_RETRIEVAL"


class ControllerReason(str, Enum):
    """Machine-readable reason for a controller decision."""
    intent_unstable = "intent_unstable"
    corpus_ambiguous = "corpus_ambiguous"
    corpus_discriminative = "corpus_discriminative"
    intent_stabilised = "intent_stabilised"
    presentation_restructure = "presentation_restructure"
    new_conjunction_anchor = "new_conjunction_anchor"
    utterance_end_safety = "utterance_end_safety"
    refractory_suppressed = "refractory_suppressed"
    llm_tiebreak = "llm_tiebreak"
    stub = "stub"


class RetrievalTrigger(str, Enum):
    """How/why a retrieval event was initiated."""
    provisional = "provisional"
    multi_intent = "multi_intent"
    late_constraint = "late_constraint"
    clarification_followup = "clarification_followup"
    final_confirm = "final_confirm"


class ClaimStatus(str, Enum):
    """Lifecycle state of a Claim in the ClaimGraph."""
    active = "active"
    superseded = "superseded"
    retracted = "retracted"


class TurnType(str, Enum):
    """Classification of an incoming turn for the delta engine."""
    NEW_INTENT = "NEW_INTENT"
    CONSTRAINT_REFINEMENT = "CONSTRAINT_REFINEMENT"
    PRESENTATION_ONLY = "PRESENTATION_ONLY"


class IntentStatus(str, Enum):
    """Lifecycle state of a sub-intent in the IntentSet."""
    pending = "pending"
    dispatched = "dispatched"
    merged = "merged"
    refined = "refined"


# ═══════════════════════════════════════════════════════════════════
# Input — Stream Layer
# ═══════════════════════════════════════════════════════════════════

class TranscriptChunk(BaseModel):
    """A single chunk emitted by the stream source (replay, WS, or mic)."""
    t_s: float = Field(..., description="Stream time in seconds from utterance start")
    text: str = Field(..., description="Chunk text content")
    is_final: bool = Field(False, description="True when this is the utterance-end marker")


# ═══════════════════════════════════════════════════════════════════
# Component 1 — Retrieval Controller (Diya)
# ═══════════════════════════════════════════════════════════════════

class ControllerDecision(BaseModel):
    """Per-chunk ternary decision emitted by the Retrieval Controller."""
    t_s: float = Field(..., description="Stream time of the chunk this decision covers")
    decision: ControllerDecisionType
    reason: ControllerReason
    confidence: float = Field(..., ge=0.0, le=1.0)
    stage: Optional[int] = Field(
        None, description="Which cascade stage produced this decision (0-4)"
    )


# ═══════════════════════════════════════════════════════════════════
# Component 2 — Multi-Intent Decomposition (Aakrit)
# ═══════════════════════════════════════════════════════════════════

class SubIntent(BaseModel):
    """A single decomposed sub-intent from a compound utterance."""
    intent_id: str = Field(..., description="Unique identifier, e.g. 'i1', 'i2'")
    facet: str = Field(..., description="Facet key from config/facets.yaml")
    query_nl: str = Field(..., description="Natural language query, self-contained")
    search_string: str = Field(..., description="Optimised search string for retrieval")
    novel: bool = Field(True, description="True if newly identified in this decomposition pass")
    first_seen_ts: Optional[float] = Field(
        None, description="Stream time when this intent was first identified"
    )
    dispatched: bool = Field(False, description="Whether retrieval has been dispatched")
    retrieval_event_ids: list[str] = Field(
        default_factory=list, description="IDs of retrieval events for this intent"
    )
    status: IntentStatus = Field(IntentStatus.pending)


# ═══════════════════════════════════════════════════════════════════
# Component 3 — Corpus Retrieval & Fusion (Aakrit)
# ═══════════════════════════════════════════════════════════════════

class RetrievalEvent(BaseModel):
    """A record of a single retrieval dispatch."""
    event_id: str = Field(..., description="Unique event identifier")
    timestamp_s: float = Field(..., description="Stream time when retrieval was initiated")
    query: str = Field(..., description="The search string used")
    trigger: RetrievalTrigger
    sub_intent_id: str = Field(..., description="Which sub-intent triggered this retrieval")


class RetrievedChunk(BaseModel):
    """A single chunk returned from the hybrid retrieval pipeline."""
    chunk_id: str = Field(
        ..., description="Internal ID: doc_id#section_id#ordinal"
    )
    doc_id: str
    section_id: str
    text: str
    score: float = Field(..., description="Final fused/reranked score")
    citation_label: str = Field(
        ..., description="Display-ready citation, e.g. 'Doc_12 §2'"
    )


class EvidencePoolEntry(BaseModel):
    """An entry in the session-scoped EvidencePool.

    Stores every chunk ever retrieved (confirmed, speculative, or cancelled)
    so refinement turns can re-rank without new corpus queries.
    """
    chunk_id: str
    doc_id: str
    section_id: str
    citation_label: str
    text: str
    embedding: Optional[list[float]] = Field(
        None, description="Dense embedding vector (stored for cosine dedup)"
    )
    scores_by_subquery: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of intent_id → retrieval/rerank score",
    )
    first_retrieved_ts: float = Field(
        ..., description="Stream time of first retrieval"
    )
    used_in_versions: list[int] = Field(
        default_factory=list, description="Answer versions this chunk contributed to"
    )
    speculative: bool = Field(False, description="True if from a speculative branch")


class FusedContext(BaseModel):
    """The assembled evidence bundle ready for synthesis, after quota + dedup."""
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    total_tokens: int = Field(0, description="Token count of all chunks combined")
    facet_coverage: dict[str, int] = Field(
        default_factory=dict, description="Facet → number of chunks allocated"
    )
    contradictions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detected contradictions: [{facet, chunk_a, chunk_b, slot, values}]",
    )


# ═══════════════════════════════════════════════════════════════════
# Component 4 — Session Refinement & Grounding (Sivansh)
# ═══════════════════════════════════════════════════════════════════

class Claim(BaseModel):
    """A single grounded claim in the ClaimGraph — the atomic unit of the answer."""
    claim_id: str
    facet: str
    text: str = Field(..., description="Human-readable claim sentence")
    citations: list[str] = Field(
        ..., description="Citation labels, e.g. ['Doc_12 §2', 'Doc_31 §4']"
    )
    preconditions: dict[str, str] = Field(
        default_factory=dict,
        description="Constraint context, e.g. {'trip_type': 'domestic'}",
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    introduced_in_version: int = Field(1)
    status: ClaimStatus = Field(ClaimStatus.active)
    superseded_by: Optional[str] = Field(
        None, description="claim_id of the claim that superseded this one"
    )


class VersionLineage(BaseModel):
    """Tracks how the answer evolved between versions (G5 evidence)."""
    from_version: int
    to_version: int
    retained: list[str] = Field(default_factory=list, description="Retained claim_ids")
    superseded: list[str] = Field(default_factory=list, description="Superseded claim_ids")
    added: list[str] = Field(default_factory=list, description="Newly added claim_ids")


class TelemetrySummary(BaseModel):
    """Per-turn telemetry summary embedded in AnswerOutput."""
    latency_ms: dict[str, float] = Field(
        default_factory=dict,
        description="Named latencies: first_retrieval, first_token_after_end, total",
    )
    tokens: dict[str, int] = Field(
        default_factory=dict, description="Token counts: prompt, completion"
    )
    cost_usd: float = Field(0.0, description="Estimated cost for this turn")


# ═══════════════════════════════════════════════════════════════════
# Final Output — The 5 Required Keys + Extensions
# ═══════════════════════════════════════════════════════════════════

class AnswerOutput(BaseModel):
    """Top-level output schema matching the brief's five required keys,
    plus the additive fields from the committed architecture (A §6).

    The five REQUIRED keys:
      retrieval_events, sub_queries, answer, citations, uncertainty

    Extensions (additive, never conflict with required schema):
      session_id, turn_id, answer_version, retrieval_required,
      suppression_reason, controller_decisions, claims,
      version_lineage, telemetry
    """
    # ── Required keys (exact names and types from the brief) ──
    retrieval_events: list[RetrievalEvent] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list)
    answer: str = Field("", description="The unified narrative answer")
    citations: list[str] = Field(
        default_factory=list,
        description="Flat list of citation labels used in the answer",
    )
    uncertainty: str = Field(
        "", description="Explicit uncertainty / uncovered sub-intents"
    )

    # ── Extensions ──
    session_id: str = Field("")
    turn_id: int = Field(1)
    answer_version: int = Field(1)
    retrieval_required: bool = Field(True)
    suppression_reason: Optional[str] = Field(None)
    controller_decisions: list[ControllerDecision] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    version_lineage: Optional[VersionLineage] = Field(None)
    telemetry: Optional[TelemetrySummary] = Field(None)


# ═══════════════════════════════════════════════════════════════════
# Component 5 — Telemetry (Matangi)
# ═══════════════════════════════════════════════════════════════════

class TelemetryEvent(BaseModel):
    """A single event written to events.jsonl by the TelemetryBus."""
    schema_version: str = Field("1.0", description="Telemetry event schema version")
    event_id: str
    session_id: str
    turn_id: int
    ts_stream_s: float = Field(..., description="Stream time (seconds from utterance start)")
    ts_wall: Optional[str] = Field(None, description="ISO-8601 wall-clock timestamp")
    component: str = Field(
        ..., description="Emitting component: controller|decomposer|retriever|synthesizer|verifier"
    )
    event_type: str = Field(
        ..., description="Event name, e.g. controller_decision, retrieval_started, answer_version"
    )
    latency_ms: float = Field(0.0)
    payload: dict[str, Any] = Field(default_factory=dict)
