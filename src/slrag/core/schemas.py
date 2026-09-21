"""Frozen inter-component contract.

Transcribed verbatim from ``markdowns/globals/C_TEAM_COORDINATION.md`` §2.
Field names, types and order are pinned by ``tests/core/test_schemas_contract.py``.
Do NOT edit without pinging all four module owners (Diya, Aakrit, Sivansh, Matangi).
"""

from typing import Literal

from pydantic import BaseModel

# core/schemas.py — FROZEN after the Day 0 session. Changes require a ping to all 4.

class TranscriptChunk(BaseModel):
    t_s: float; text: str; is_final: bool

class ControllerDecision(BaseModel):        # Diya emits this
    t_s: float; decision: Literal["WAIT", "RETRIEVE", "NO_RETRIEVAL"]
    reason: str; confidence: float

class SubIntent(BaseModel):                 # Aakrit emits this
    intent_id: str; facet: str; query_nl: str; search_string: str; novel: bool

class RetrievedChunk(BaseModel):            # Aakrit emits this
    chunk_id: str; doc_id: str; section_id: str; text: str; score: float

class Claim(BaseModel):                     # Sivansh owns this
    claim_id: str; facet: str; text: str; citations: list[str]
    preconditions: dict; status: Literal["active", "superseded"]; introduced_in_version: int

class AnswerOutput(BaseModel):              # the 5 required keys + extensions — Sivansh renders this
    retrieval_events: list[dict]; sub_queries: list[str]
    answer: str; citations: list[str]; uncertainty: str
    session_id: str; turn_id: int; answer_version: int

class TelemetryEvent(BaseModel):            # Matangi consumes ALL of the above to log them
    event_id: str; session_id: str; turn_id: int; ts_stream_s: float
    component: str; latency_ms: float; payload: dict
