from typing import Literal, Optional
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Component 1: Retrieval Controller (Diya)
# -----------------------------------------------------------------------------

class TranscriptChunk(BaseModel):
    """Input chunk from the ASR/VAD stream."""
    t_s: float
    text: str
    is_final: bool

class ControllerDecision(BaseModel):
    """Output from the Retrieval Controller."""
    t_s: float
    decision: Literal["WAIT", "RETRIEVE", "NO_RETRIEVAL"]
    reason: str
    confidence: float


# -----------------------------------------------------------------------------
# Component 2 & 3: Decomposition & Retrieval (Aakrit)
# -----------------------------------------------------------------------------

class SubIntent(BaseModel):
    intent_id: str
    facet: str
    query_nl: str
    search_string: str
    novel: bool

class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    section_id: str
    text: str
    score: float


# -----------------------------------------------------------------------------
# Component 4: Synthesis & Refinement (Sivansh)
# -----------------------------------------------------------------------------

class Claim(BaseModel):
    claim_id: str
    facet: str
    text: str
    citations: list[str]
    preconditions: dict
    status: Literal["active", "superseded", "retracted"]
    introduced_in_version: int
    superseded_by: Optional[str] = None
    confidence: Optional[float] = None

class AnswerOutput(BaseModel):
    retrieval_events: list[dict]
    sub_queries: list[str]
    answer: str
    citations: list[str]
    uncertainty: str
    session_id: str
    turn_id: int
    answer_version: int


# -----------------------------------------------------------------------------
# Component 5: Telemetry (Matangi)
# -----------------------------------------------------------------------------

class TelemetryEvent(BaseModel):
    event_id: str
    session_id: str
    turn_id: int
    ts_stream_s: float
    component: str
    latency_ms: float
    payload: dict
