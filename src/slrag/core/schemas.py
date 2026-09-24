"""Inter-component contract, v1.1 (additive merge of the Day-1 freeze and Component 2/3 models).

v1.0 is transcribed from ``markdowns/globals/C_TEAM_COORDINATION.md`` §2. v1.1 merges the
models Aakrit's decomposition/retrieval branch needs, *additively*:

* every v1.0 field keeps its name, position (first) and type — ``Literal`` value sets may
  only grow (``Claim.status`` gains ``"retracted"``) and ``AnswerOutput.retrieval_events``
  also accepts typed ``RetrievalEvent`` items next to the brief's plain dicts;
* every added field has a default, so producers written against v1.0 still validate;
* enums are ``str`` enums whose values are exactly the strings v1.0 already used, so
  ``ControllerDecisionType.WAIT`` and ``"WAIT"`` are interchangeable in every field.

``tests/core/test_schemas_contract.py`` pins all of this. Do NOT edit without pinging all
four module owners (Diya, Aakrit, Sivansh, Matangi).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

SECTION_SIGN = "§"


# ═══════════════════════════════════════════════════════════════════
# Shared vocabularies (str enums; values equal the v1.0 strings)
# ═══════════════════════════════════════════════════════════════════
class ControllerDecisionType(str, Enum):
    WAIT = "WAIT"
    RETRIEVE = "RETRIEVE"
    NO_RETRIEVAL = "NO_RETRIEVAL"


class ControllerReason(str, Enum):
    """Common controller reasons. ``ControllerDecision.reason`` stays an open ``str``."""
    intent_unstable = "intent_unstable"
    corpus_ambiguous = "corpus_ambiguous"
    corpus_discriminative = "corpus_discriminative"
    intent_stabilised = "intent_stabilised"
    presentation_restructure = "presentation_restructure"
    new_conjunction_anchor = "new_conjunction_anchor"
    utterance_end_safety = "utterance_end_safety"
    refractory_suppressed = "refractory_suppressed"
    llm_tiebreak = "llm_tiebreak"
    new_intent = "new_intent"
    stub = "stub"


class RetrievalTrigger(str, Enum):
    provisional = "provisional"
    multi_intent = "multi_intent"
    late_constraint = "late_constraint"
    clarification_followup = "clarification_followup"
    final_confirm = "final_confirm"


class ClaimStatus(str, Enum):
    active = "active"
    superseded = "superseded"
    retracted = "retracted"


class TurnType(str, Enum):
    NEW_INTENT = "NEW_INTENT"
    CONSTRAINT_REFINEMENT = "CONSTRAINT_REFINEMENT"
    PRESENTATION_ONLY = "PRESENTATION_ONLY"


class IntentStatus(str, Enum):
    pending = "pending"
    dispatched = "dispatched"
    merged = "merged"
    refined = "refined"


# ═══════════════════════════════════════════════════════════════════
# v1.0 models (frozen fields first) + v1.1 additive fields
# ═══════════════════════════════════════════════════════════════════
class TranscriptChunk(BaseModel):
    t_s: float; text: str; is_final: bool = False


class ControllerDecision(BaseModel):        # Diya emits this
    t_s: float; decision: Literal["WAIT", "RETRIEVE", "NO_RETRIEVAL"]
    reason: str; confidence: float
    # v1.1
    stage: Optional[int] = Field(None, description="Cascade stage that produced the decision (0-4)")


class SubIntent(BaseModel):                 # Aakrit emits this
    intent_id: str; facet: str; query_nl: str; search_string: str; novel: bool = True
    # v1.1
    first_seen_ts: Optional[float] = None
    dispatched: bool = False
    retrieval_event_ids: list[str] = Field(default_factory=list)
    status: IntentStatus = IntentStatus.pending


class RetrievedChunk(BaseModel):            # Aakrit emits this
    chunk_id: str; doc_id: str; section_id: str; text: str; score: float
    # v1.1 — display label; derived from doc_id/section_id when not given ("Doc_12 §2")
    citation_label: str = ""

    @model_validator(mode="after")
    def _default_label(self) -> "RetrievedChunk":
        if not self.citation_label:
            self.citation_label = f"{self.doc_id} {SECTION_SIGN}{self.section_id}"
        return self


class Claim(BaseModel):                     # Sivansh owns this
    claim_id: str; facet: str; text: str; citations: list[str]
    preconditions: dict = Field(default_factory=dict)
    status: Literal["active", "superseded", "retracted"] = "active"
    introduced_in_version: int = 1
    # v1.1
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    superseded_by: Optional[str] = None


class RetrievalEvent(BaseModel):
    """A typed retrieval dispatch record (Component 3); serialises to the brief's keys plus ids."""
    event_id: str
    timestamp_s: float
    query: str
    trigger: RetrievalTrigger
    sub_intent_id: str


class EvidencePoolEntry(BaseModel):
    """Every chunk ever retrieved in a session (confirmed, speculative or cancelled)."""
    chunk_id: str
    doc_id: str
    section_id: str
    citation_label: str
    text: str
    embedding: Optional[list[float]] = None
    scores_by_subquery: dict[str, float] = Field(default_factory=dict)
    first_retrieved_ts: float
    used_in_versions: list[int] = Field(default_factory=list)
    speculative: bool = False


class FusedContext(BaseModel):
    """Evidence bundle after facet quota + dedup, ready for synthesis."""
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    total_tokens: int = 0
    facet_coverage: dict[str, int] = Field(default_factory=dict)
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


class VersionLineage(BaseModel):
    from_version: int
    to_version: int
    retained: list[str] = Field(default_factory=list)
    superseded: list[str] = Field(default_factory=list)
    added: list[str] = Field(default_factory=list)


class TelemetrySummary(BaseModel):
    latency_ms: dict[str, float] = Field(default_factory=dict)
    tokens: dict[str, int] = Field(default_factory=dict)
    cost_usd: float = 0.0


class AnswerOutput(BaseModel):              # the 5 required keys + extensions — Sivansh renders this
    retrieval_events: list[Union[RetrievalEvent, dict]] = Field(default_factory=list)
    sub_queries: list[str] = Field(default_factory=list)
    answer: str = ""
    citations: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    session_id: str = ""
    turn_id: int = 1
    answer_version: int = 1
    # v1.1 — the additive A_FINAL_ARCHITECTURE §6 fields (schema proposal, option A)
    retrieval_required: bool = True
    suppression_reason: Optional[str] = None
    controller_decisions: list[ControllerDecision] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    version_lineage: Optional[VersionLineage] = None
    telemetry: Optional[TelemetrySummary] = None


class TelemetryEvent(BaseModel):            # Matangi consumes ALL of the above to log them
    event_id: str; session_id: str; turn_id: int; ts_stream_s: float
    component: str; latency_ms: float = 0.0; payload: dict = Field(default_factory=dict)
    # v1.1
    event_type: str = ""
    ts_wall: Optional[str] = None
