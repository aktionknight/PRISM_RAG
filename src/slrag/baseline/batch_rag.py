"""
baseline/batch_rag.py — Baseline non-streaming Batch RAG (Phase 1, Task 1.8).

The Day-3 comparison denominator. A simple, non-streaming RAG that:
  1. Waits for the FULL utterance (is_final=True)
  2. Takes the ENTIRE utterance as a single query (no decomposition)
  3. Runs dense-only top-k retrieval (no hybrid, no RRF)
  4. Single-shot LLM generation (no refinement, no claim graph)
  5. Returns a schema-valid AnswerOutput

This is intentionally simple — it's the baseline the streaming system must beat.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from typing import Any

from slrag.core.schemas import AnswerOutput, RetrievalEvent, RetrievalTrigger
from slrag.retrieve.dense import DenseRetriever

logger = logging.getLogger(__name__)


class BatchRAG:
    """Baseline non-streaming Batch RAG pipeline.

    Waits for the full utterance, performs dense retrieval, and generates
    a single-shot answer. No decomposition, no RRF, no refinement.
    """

    def __init__(
        self,
        index_path: str,
        chunks_path: str,
        model_name: str = "BAAI/bge-small-en-v1.5",
    ) -> None:
        self.retriever = DenseRetriever(
            index_path=index_path,
            chunks_path=chunks_path,
            model_name=model_name,
        )

    async def answer(
        self, query: str, session_id: str = "", turn_id: int = 1
    ) -> AnswerOutput:
        """Run the full baseline RAG pipeline for a single query.

        Args:
            query: The complete user utterance.
            session_id: Session identifier for output.
            turn_id: Turn number within the session.

        Returns:
            Schema-valid AnswerOutput with all required fields.
        """
        start_time = time.time()

        # 1. Dense retrieval top-10
        retrieved_chunks = await self.retriever.search(query, top_k=10)

        retrieval_event = RetrievalEvent(
            event_id=f"evt_batch_{int(time.time() * 1000)}",
            timestamp_s=time.time() - start_time,
            query=query,
            trigger=RetrievalTrigger.final_confirm,
            sub_intent_id="baseline_intent",
        )

        # 2. Build context string
        context_parts: list[str] = []
        citations: list[str] = []
        for chunk in retrieved_chunks:
            context_parts.append(f"[{chunk.citation_label}] {chunk.text}")
            if chunk.citation_label not in citations:
                citations.append(chunk.citation_label)

        context_str = "\n\n".join(context_parts)

        # 3. Call LLM (OpenAI-compatible at localhost:11434/v1)
        system_prompt = (
            "You are a helpful assistant. Answer the user's query based ONLY on "
            "the provided context.\n"
            "Cite your sources using the labels provided in brackets, "
            "e.g., [Doc_1 §2].\n"
            "If the context does not contain the answer, say you don't know."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_str}\n\nQuery: {query}"},
        ]

        payload = {
            "model": "qwen2.5",
            "messages": messages,
            "temperature": 0.1,
            "stream": False,
        }

        answer_text = ""
        try:
            req = urllib.request.Request(
                "http://localhost:11434/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            def _call_llm() -> dict[str, Any]:
                with urllib.request.urlopen(req, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8"))

            result = await asyncio.to_thread(_call_llm)
            answer_text = result["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error(f"LLM call failed: {e}. Falling back to extraction.")
            # 4. Fallback if LLM unavailable
            if retrieved_chunks:
                answer_text = (
                    "Based on the documents, here is the most relevant "
                    f"information:\n{context_parts[0]}"
                )
            else:
                answer_text = (
                    "I'm sorry, I couldn't find any relevant information "
                    "to answer your query."
                )

        return AnswerOutput(
            retrieval_events=[retrieval_event] if retrieved_chunks else [],
            sub_queries=[query],
            answer=answer_text,
            citations=citations,
            uncertainty="",
            session_id=session_id,
            turn_id=turn_id,
            answer_version=1,
            retrieval_required=True,
            suppression_reason=None,
        )
