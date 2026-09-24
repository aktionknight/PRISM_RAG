"""
core/events.py — Typed event constants and helpers for the TelemetryBus.

Every stage in the pipeline emits events through the TelemetryBus using
these event-type constants.  The bus writes them as TelemetryEvent records
to events.jsonl (always-on) and optionally to OTel spans.
"""

from __future__ import annotations


# ── Controller events ──
EVT_CHUNK_RECEIVED = "chunk_received"
EVT_CONTROLLER_DECISION = "controller_decision"
EVT_SPECULATION_STARTED = "speculation_started"
EVT_SPECULATION_CONFIRMED = "speculation_confirmed"
EVT_SPECULATION_CANCELLED = "speculation_cancelled"

# ── Decomposition events ──
EVT_DECOMPOSITION_STARTED = "decomposition_started"
EVT_DECOMPOSITION_COMPLETED = "decomposition_completed"
EVT_INTENT_ADDED = "intent_added"
EVT_INTENT_MERGED = "intent_merged"
EVT_INTENT_REFINED = "intent_refined"

# ── Retrieval events ──
EVT_RETRIEVAL_STARTED = "retrieval_started"
EVT_RETRIEVAL_COMPLETED = "retrieval_completed"
EVT_RERANK_COMPLETED = "rerank_completed"
EVT_CONTEXT_ASSEMBLED = "context_assembled"
EVT_CONTRADICTION_DETECTED = "contradiction_detected"

# ── Synthesis events ──
EVT_SYNTHESIS_STARTED = "synthesis_started"
EVT_SENTENCE_PROVISIONAL = "sentence_provisional"
EVT_SENTENCE_COMMITTED = "sentence_committed"
EVT_SENTENCE_RETRACTED = "sentence_retracted"
EVT_ANSWER_VERSION = "answer_version"
EVT_ANSWER_REFINED = "answer_refined"

# ── Verification events ──
EVT_CITATION_VERIFIED = "citation_verified"
EVT_CITATION_FABRICATED = "citation_fabricated"
EVT_ENTAILMENT_CHECKED = "entailment_checked"

# ── Session events ──
EVT_SESSION_STARTED = "session_started"
EVT_SESSION_ENDED = "session_ended"
EVT_TURN_STARTED = "turn_started"
EVT_TURN_COMPLETED = "turn_completed"

# ── Cost tracking ──
EVT_LLM_CALL = "llm_call"
EVT_COST_RECORD = "cost_record"
