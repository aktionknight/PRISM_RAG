"""
core/orchestrator.py — Main pipeline orchestrator for Streaming Live RAG.

Component 5 & Integration Lead (Matangi).
Wires together the controller, decomposer, retriever, state management,
telemetry bus, and cost tracking.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncGenerator, Optional

from slrag.core.events import (
    EVT_ANSWER_VERSION,
    EVT_CHUNK_RECEIVED,
    EVT_CONTROLLER_DECISION,
    EVT_DECOMPOSITION_COMPLETED,
    EVT_DECOMPOSITION_STARTED,
    EVT_INTENT_ADDED,
    EVT_RETRIEVAL_COMPLETED,
    EVT_RETRIEVAL_STARTED,
    EVT_SESSION_STARTED,
    EVT_SYNTHESIS_STARTED,
    EVT_TURN_COMPLETED,
    EVT_TURN_STARTED,
)
from slrag.core.schemas import (
    AnswerOutput,
    ControllerDecision,
    ControllerDecisionType,
    RetrievalEvent,
    RetrievalTrigger,
    TranscriptChunk,
)
from slrag.core.session import SessionState
from slrag.decompose.decomposer import Decomposer
from slrag.decompose.intent_set import IntentSet
from slrag.controller.rule_controller import RuleController
from slrag.retrieve.hybrid import HybridRetriever
from slrag.retrieve.pool import add_to_pool
from slrag.stubs.fake_controller import fake_controller
from slrag.stubs.fake_decomposer import fake_decompose
from slrag.stubs.fake_retriever import fake_retrieve
from slrag.stubs.fake_synthesis import fake_synthesize
from slrag.telemetry.bus import TelemetryBus
from slrag.telemetry.cost import CostTracker
import yaml

logger = logging.getLogger(__name__)


class Orchestrator:
    """End-to-end streaming live RAG pipeline orchestrator with full telemetry instrumentation."""

    def __init__(
        self,
        session: SessionState,
        bus: Optional[TelemetryBus] = None,
        cost_tracker: Optional[CostTracker] = None,
    ) -> None:
        self.session = session
        self.bus = bus or TelemetryBus()
        self.cost_tracker = cost_tracker or CostTracker(bus=self.bus)

        # Feature flags from config/app.yaml (C_TEAM_COORDINATION §5)
        self.use_stub_controller = True
        self.use_stub_decomposer = True
        self.use_stub_retriever = True
        self.use_stub_synthesizer = True
        try:
            with open("config/app.yaml", "r", encoding="utf-8") as f:
                app_cfg = yaml.safe_load(f) or {}
            mods = app_cfg.get("modules", {})
            self.use_stub_controller = mods.get("use_stub_controller", True)
            self.use_stub_decomposer = mods.get("use_stub_decomposer", True)
            self.use_stub_retriever = mods.get("use_stub_retriever", True)
            self.use_stub_synthesizer = mods.get("use_stub_synthesizer", True)
        except Exception:
            pass

        if os.environ.get("SLRAG_ABLATION_ARM") in {"hybrid", "dense_only", "bm25_only"}:
            self.use_stub_retriever = False

        self.controller = None if self.use_stub_controller else RuleController()
        self.decomposer = Decomposer() if not self.use_stub_decomposer else None
        self.retriever = None if self.use_stub_retriever else HybridRetriever()
        self.intent_set = IntentSet(session=session)
        self.prefix = ""
        self.decisions: list[ControllerDecision] = []
        self.retrieval_events: list[RetrievalEvent] = []

        # Emit session and turn start
        if self.session.turn_id == 0:
            self.session.new_turn()
            self.bus.emit(
                event_type=EVT_SESSION_STARTED,
                component="orchestrator",
                session_id=self.session.session_id,
                turn_id=self.session.turn_id,
                ts_stream_s=0.0,
            )
            self.bus.emit(
                event_type=EVT_TURN_STARTED,
                component="orchestrator",
                session_id=self.session.session_id,
                turn_id=self.session.turn_id,
                ts_stream_s=0.0,
            )

    async def process_chunk(self, chunk: TranscriptChunk) -> ControllerDecision:
        """Process a single transcript chunk through the pipeline."""
        self.prefix += chunk.text

        # Log chunk receipt
        self.bus.emit(
            event_type=EVT_CHUNK_RECEIVED,
            component="stream",
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=chunk.t_s,
            payload={"text": chunk.text, "is_final": chunk.is_final},
        )

        # 1. Controller Decision
        decision_started = time.perf_counter()
        decision = (
            fake_controller(chunk)
            if self.use_stub_controller
            else self.controller.decide(chunk)
        )
        decision_latency_ms = (time.perf_counter() - decision_started) * 1000
        self.decisions.append(decision)
        logger.info(
            f"Chunk at {chunk.t_s}s -> Controller: {decision.decision.value} ({decision.reason.value})"
        )

        self.bus.emit(
            event_type=EVT_CONTROLLER_DECISION,
            component="controller",
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=chunk.t_s,
            payload={
                "decision": decision.decision.value,
                "reason": decision.reason.value,
                "confidence": decision.confidence,
                "stage": decision.stage,
            },
            latency_ms=decision_latency_ms,
        )

        # 2. Decompose and Retrieve if needed
        if decision.decision == ControllerDecisionType.RETRIEVE:
            self.bus.emit(
                event_type=EVT_DECOMPOSITION_STARTED,
                component="decomposer",
                session_id=self.session.session_id,
                turn_id=self.session.turn_id,
                ts_stream_s=chunk.t_s,
                payload={"prefix": self.prefix},
            )

            decomposition_started = time.perf_counter()
            if self.use_stub_decomposer:
                new_candidates = fake_decompose(
                    self.prefix, existing_intents=self.session.intent_set
                )
            else:
                new_candidates = await self.decomposer.decompose(
                    prefix=self.prefix,
                    existing_intents=self.session.intent_set,
                    ts=chunk.t_s,
                )
            decomposition_latency_ms = (time.perf_counter() - decomposition_started) * 1000

            novel_intents = await self.intent_set.add_intents(new_candidates)

            self.bus.emit(
                event_type=EVT_DECOMPOSITION_COMPLETED,
                component="decomposer",
                session_id=self.session.session_id,
                turn_id=self.session.turn_id,
                ts_stream_s=chunk.t_s,
                payload={
                    "total_candidates": len(new_candidates),
                    "novel_intents": [i.intent_id for i in novel_intents],
                },
                latency_ms=decomposition_latency_ms,
            )

            # Parallel Retrieval for novel intents
            retrieval_tasks = []
            for intent in novel_intents:
                self.bus.emit(
                    event_type=EVT_INTENT_ADDED,
                    component="decomposer",
                    session_id=self.session.session_id,
                    turn_id=self.session.turn_id,
                    ts_stream_s=chunk.t_s,
                    payload={"intent_id": intent.intent_id, "facet": intent.facet},
                )

                # Determine trigger category
                trigger = (
                    RetrievalTrigger.provisional
                    if len(self.retrieval_events) == 0
                    else RetrievalTrigger.multi_intent
                )
                ret_evt_id = f"ret_{chunk.t_s:.1f}_{intent.intent_id}"
                ret_record = RetrievalEvent(
                    event_id=ret_evt_id,
                    timestamp_s=chunk.t_s,
                    query=intent.search_string,
                    trigger=trigger,
                    sub_intent_id=intent.intent_id,
                )
                self.retrieval_events.append(ret_record)

                self.bus.emit(
                    event_type=EVT_RETRIEVAL_STARTED,
                    component="retriever",
                    session_id=self.session.session_id,
                    turn_id=self.session.turn_id,
                    ts_stream_s=chunk.t_s,
                    payload={
                        "event_id": ret_evt_id,
                        "query": intent.search_string,
                        "sub_intent_id": intent.intent_id,
                        "trigger": trigger.value,
                    },
                )

                def do_retrieve(sub_intent):
                    chunks = fake_retrieve(sub_intent)
                    return sub_intent, chunks

                if self.use_stub_retriever:
                    retrieval_tasks.append(asyncio.to_thread(do_retrieve, intent))
                else:
                    retrieval_tasks.append(self._retrieve_real(intent))

            if retrieval_tasks:
                results = await asyncio.gather(*retrieval_tasks)

                for intent, chunks in results:
                    for c in chunks:
                        add_to_pool(
                            session=self.session,
                            chunk=c,
                            intent_id=intent.intent_id,
                            ts_stream_s=chunk.t_s,
                            speculative=False,
                        )
                    self.intent_set.mark_dispatched(intent.intent_id)

                    self.bus.emit(
                        event_type=EVT_RETRIEVAL_COMPLETED,
                        component="retriever",
                        session_id=self.session.session_id,
                        turn_id=self.session.turn_id,
                        ts_stream_s=chunk.t_s,
                        payload={
                            "sub_intent_id": intent.intent_id,
                            "num_chunks": len(chunks),
                        },
                    )

        return decision

    async def _retrieve_real(self, intent):
        """Normalize the real retriever result to the stub result shape."""
        return intent, await self.retriever.retrieve(intent)

    async def process_stream(self, stream: AsyncGenerator[TranscriptChunk, None]):
        """Process an entire stream of chunks."""
        async for chunk in stream:
            await self.process_chunk(chunk)

    async def finalize_turn(self, last_ts: float = 2.1) -> AnswerOutput:
        """Complete the turn, synthesize the answer, emit telemetry and cost accounting."""
        self.bus.emit(
            event_type=EVT_SYNTHESIS_STARTED,
            component="synthesizer",
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=last_ts,
        )

        # Call synthesizer (stub for now, replaced by Sivansh's real synth later)
        output = fake_synthesize(
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
        )

        # Sync retrieval events and controller decisions into output
        if self.retrieval_events:
            output.retrieval_events = list(self.retrieval_events)
        output.controller_decisions = list(self.decisions)

        # Account for synthesis LLM call
        self.cost_tracker.record_llm_call(
            component="synthesizer",
            model_name="qwen2.5-7b-instruct",
            prompt_tokens=1250,
            completion_tokens=220,
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=last_ts,
            latency_ms=180.0,
        )

        # Attach telemetry summary
        output.telemetry = self.cost_tracker.get_turn_summary(
            turn_id=self.session.turn_id,
            latency_metrics={
                "first_retrieval": 800.0,
                "first_token_after_end": 280.0,
                "total": 1200.0,
            },
        )

        self.bus.emit(
            event_type=EVT_ANSWER_VERSION,
            component="synthesizer",
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=last_ts,
            payload={
                "version": output.answer_version,
                "answer": output.answer,
                "citations": output.citations,
                "uncertainty": output.uncertainty,
                "claims_count": len(output.claims),
            },
        )

        self.bus.emit(
            event_type=EVT_TURN_COMPLETED,
            component="orchestrator",
            session_id=self.session.session_id,
            turn_id=self.session.turn_id,
            ts_stream_s=last_ts,
            payload={
                "answer_version": output.answer_version,
                "num_citations": len(output.citations),
            },
        )

        return output
