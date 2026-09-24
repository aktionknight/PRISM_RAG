"""Cost model — token accounting × pricing.yaml (Component 5, §5.3).

Tracks prompt/completion tokens per call, multiplied by configurable
per-token rates.  Also tracks embedding and rerank item counts as a
compute proxy for the parsimony argument (HC-5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_PRICING_PATH = Path("config/pricing.yaml")


@dataclass
class CostAccumulator:
    """Per-session cost tracker."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    embedding_items: int = 0
    rerank_items: int = 0
    llm_calls: int = 0
    _rates: dict = field(default_factory=dict)

    def add_llm_call(self, prompt_tokens: int, completion_tokens: int) -> float:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.llm_calls += 1
        return self._compute_cost(prompt_tokens, completion_tokens)

    def add_embedding(self, items: int) -> None:
        self.embedding_items += items

    def add_rerank(self, items: int) -> None:
        self.rerank_items += items

    @property
    def total_cost_usd(self) -> float:
        return self._compute_cost(self.prompt_tokens, self.completion_tokens)

    def _compute_cost(self, prompt: int, completion: int) -> float:
        prompt_rate = self._rates.get("prompt_per_1k", 0.0) / 1000.0
        completion_rate = self._rates.get("completion_per_1k", 0.0) / 1000.0
        return prompt * prompt_rate + completion * completion_rate

    def summary(self) -> dict[str, Any]:
        return {
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
            },
            "cost_usd": round(self.total_cost_usd, 6),
            "llm_calls": self.llm_calls,
            "embedding_items": self.embedding_items,
            "rerank_items": self.rerank_items,
        }


def load_pricing(path: Path | None = None) -> dict:
    """Load pricing rates from config/pricing.yaml."""
    p = path or _PRICING_PATH
    if not p.exists():
        logger.warning(f"Pricing config not found at {p}, using zero rates")
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def make_cost_accumulator(config: dict | None = None) -> CostAccumulator:
    """Create a cost accumulator with rates from config."""
    pricing = config or load_pricing()
    rates = pricing.get("llm", {})
    acc = CostAccumulator()
    acc._rates = rates
    return acc
