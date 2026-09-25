"""Async hybrid retrieval adapter for the orchestrator."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import yaml

from slrag.core.schemas import RetrievedChunk, SubIntent
from slrag.retrieve.dense import DenseRetriever
from slrag.retrieve.rerank import Reranker
from slrag.retrieve.rrf import apply_rrf
from slrag.retrieve.sparse import SparseRetriever


class HybridRetriever:
    """Run sparse+dense retrieval, weighted RRF, and optional reranking."""

    def __init__(self, config_path: str | Path = "config/retrieval.yaml") -> None:
        with Path(config_path).open("r", encoding="utf-8") as f:
            self.config: dict[str, Any] = yaml.safe_load(f) or {}
        index = self.config.get("index", {})
        self.sparse = SparseRetriever(index.get("sparse_path", ".index/bm25"), index.get("chunks_path", ".index/chunks.jsonl"))
        embedding = self.config.get("embedding", {})
        self.dense = DenseRetriever(
            index.get("dense_path", ".index/faiss"),
            index.get("chunks_path", ".index/chunks.jsonl"),
            embedding.get("model_name", "BAAI/bge-small-en-v1.5"),
        )
        reranker = self.config.get("reranker", {})
        self.reranker = Reranker(reranker.get("model_name", "BAAI/bge-reranker-base"))
        top_k = self.config.get("top_k", {})
        self.sparse_k = top_k.get("sparse", 50)
        self.dense_k = top_k.get("dense", 50)
        self.fused_k = top_k.get("fused", 30)
        self.final_k = top_k.get("final", 8)

    async def retrieve(self, intent: SubIntent) -> list[RetrievedChunk]:
        arm = os.environ.get("SLRAG_ABLATION_ARM", "hybrid")
        if arm == "dense_only":
            sparse_results = []
            dense_results = await self.dense.search(intent.search_string, self.dense_k)
        elif arm == "bm25_only":
            sparse_results = await self.sparse.search(intent.search_string, self.sparse_k)
            dense_results = []
        else:
            sparse_results, dense_results = await asyncio.gather(
                self.sparse.search(intent.search_string, self.sparse_k),
                self.dense.search(intent.search_string, self.dense_k),
            )
        fused = apply_rrf(sparse_results, dense_results, intent.facet, self.config)
        return await self.reranker.rerank(intent.search_string, fused[: self.fused_k], self.final_k)
