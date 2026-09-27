"""
core/orchestrator.py — Main pipeline orchestrator for Streaming Live RAG.

Wires together the controller, decomposer, retriever, and state management.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from slrag.core.schemas import (
    ControllerDecision,
    ControllerDecisionType,
    TranscriptChunk,
    RetrievalEvent,
    RetrievalTrigger,
)
from slrag.core.session import SessionState
from slrag.decompose.decomposer import Decomposer
from slrag.decompose.intent_set import IntentSet
from slrag.retrieve.pool import add_to_pool
from slrag.controller.cascade import RetrievalController

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, session: SessionState):
        self.session = session
        self.decomposer = Decomposer()
        self.intent_set = IntentSet(session=session)
        self.prefix = ""

    async def process_chunk(self, chunk: TranscriptChunk) -> ControllerDecision:
        """Process a single transcript chunk through the pipeline."""
        self.prefix += chunk.text

        # 1. Controller Decision
        controller = RetrievalController(session=self.session.controller)
        decision_result = controller.process_chunk(chunk)
        decision = decision_result.decision
        # v1.1 contract: decision/reason are plain strings (str-enum values are accepted and stored as str)
        logger.info(f"Chunk at {chunk.t_s}s -> Controller: {decision} ({decision_result.reason})")

        # 2. Decompose and Retrieve if needed
        if decision.decision == ControllerDecisionType.RETRIEVE:
            # 2a. Decompose
            logger.info("Decomposing intent...")
            new_candidates = await self.decomposer.decompose(
                prefix=self.prefix,
                existing_intents=self.session.intent_set,
                ts=chunk.t_s
            )

            # 2b. Add to IntentSet (handles deduplication)
            novel_intents = await self.intent_set.add_intents(new_candidates)

            # 2c. Parallel Retrieval for novel intents
            retrieval_tasks = []
            for intent in novel_intents:
                # Trigger retrieval
                # (Assuming a real retriever would be used here, but for now we'll just log since this is not the main API path)
                logger.info(f"Dispatching retrieval for intent: {intent.intent_id} ({intent.facet})")
                
                async def do_retrieve(sub_intent):
                    return sub_intent, []

                retrieval_tasks.append(
                    do_retrieve(intent)
                )

            if retrieval_tasks:
                results = await asyncio.gather(*retrieval_tasks)
                
                # 2d. Apply RRF / Add to Pool
                for intent, chunks in results:
                    # Log retrieval event
                    # For simplicity, trigger is provisional or multi_intent based on chunks/time
                    for c in chunks:
                        add_to_pool(
                            session=self.session,
                            chunk=c,
                            intent_id=intent.intent_id,
                            ts_stream_s=chunk.t_s,
                            speculative=False
                        )
                    self.intent_set.mark_dispatched(intent.intent_id)

        return decision

    async def process_stream(self, stream: AsyncGenerator[TranscriptChunk, None]):
        """Process an entire stream of chunks."""
        async for chunk in stream:
            await self.process_chunk(chunk)
