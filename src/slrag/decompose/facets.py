"""
decompose/facets.py — Facet tagging module for sub-intents.

Assigns the correct facet key to each decomposed sub-intent candidate using
a dual strategy: fast keyword-based scoring with an optional embedding-based
fallback/refinement.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import yaml

try:
    from sentence_transformers import SentenceTransformer
    from sentence_transformers.util import cos_sim

    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False


logger = logging.getLogger(__name__)


# Comprehensive keyword lists derived from facets.yaml taxonomy
FACET_KEYWORDS: dict[str, set[str]] = {
    "venue_capacity": {
        "capacity", "room", "size", "seat", "headcount", "attendees",
        "people", "hall", "space", "accommodate", "fit", "large",
        "small", "max", "maximum", "occupancy", "layout",
    },
    "cancellation_terms": {
        "cancel", "refund", "penalty", "reschedule", "no-show",
        "terms", "policy", "forfeit", "fee", "late", "change", "rebook",
    },
    "pricing": {
        "price", "cost", "rate", "fee", "charge", "package", "deposit",
        "payment", "per-head", "budget", "expensive", "cheap", "afford",
        "currency", "discount", "total", "pay",
    },
    "catering_options": {
        "food", "catering", "menu", "dietary", "vegetarian", "cuisine",
        "meal", "snack", "beverage", "caterer", "kitchen", "drinks",
        "vegan", "allergy", "lunch", "dinner", "breakfast", "beverages",
    },
    "logistics": {
        "equipment", "av", "projector", "parking", "wifi", "accessibility",
        "check-in", "check-out", "location", "address", "transport",
        "audio", "visual", "internet", "directions", "facilities", "screen",
    },
    "eligibility": {
        "eligible", "approval", "authorize", "permission", "role", "manager",
        "department", "who can", "requirement", "qualify", "allowed",
        "staff", "employee", "require",
    },
    "procedure": {
        "book", "reserve", "form", "step", "process", "submit", "confirm",
        "schedule", "arrange", "how to", "instruction", "guide", "portal",
        "bookable",
    },
    "comparison": {
        "compare", "versus", "vs", "better", "difference", "alternative",
        "which one", "pros", "cons", "instead", "options", "differences",
        "prefer",
    },
}


class FacetTagger:
    """Tags decomposed sub-intents with the most relevant facet key."""

    def __init__(
        self,
        facets_config_path: str | Path,
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",
        keyword_threshold: int = 1,
    ) -> None:
        """Initialize the FacetTagger.

        Args:
            facets_config_path: Path to the facets.yaml configuration.
            embedding_model_name: HuggingFace model name for sentence embeddings.
            keyword_threshold: Minimum keyword matches required to assign a facet.
        """
        self.facets_config_path = Path(facets_config_path)
        self.keyword_threshold = keyword_threshold

        self.facets: dict[str, dict[str, Any]] = {}
        self.default_facet: str = "general"
        self._load_config()

        # Build embedding resources if available
        self.encoder: Optional[SentenceTransformer] = None
        self.facet_embeddings: Optional[Any] = None
        self.facet_keys_ordered: list[str] = list(self.facets.keys())

        if HAS_SENTENCE_TRANSFORMERS:
            try:
                logger.info(
                    f"Loading embedding model {embedding_model_name} for facet tagging."
                )
                self.encoder = SentenceTransformer(embedding_model_name)
                # Pre-compute embeddings for facet descriptions
                descriptions = [
                    f"{v.get('display', k)}: {v.get('description', '')}"
                    for k, v in self.facets.items()
                ]
                self.facet_embeddings = self.encoder.encode(
                    descriptions, convert_to_tensor=True
                )
                logger.info(
                    "Successfully loaded embedding model and pre-computed facet embeddings."
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load sentence-transformers model: {e}. "
                    "Falling back to keywords only."
                )
                self.encoder = None

    def _load_config(self) -> None:
        """Load facet definitions from the YAML config."""
        if not self.facets_config_path.exists():
            logger.error(f"Facets config not found at {self.facets_config_path}")
            raise FileNotFoundError(
                f"Config file not found: {self.facets_config_path}"
            )

        try:
            with open(self.facets_config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self.facets = config.get("facets", {})
            self.default_facet = config.get("default_facet", "general")

            if not self.facets:
                logger.warning("No facets defined in config.")

            logger.debug(f"Loaded {len(self.facets)} facets from config.")
        except Exception as e:
            logger.error(f"Failed to parse facets config: {e}")
            raise

    def tag(self, query_nl: str) -> str:
        """Assign the best matching facet key to a natural language query.

        Args:
            query_nl: The natural language sub-intent query.

        Returns:
            The best matching facet key, or the default facet if none match.
        """
        if not query_nl or not query_nl.strip():
            return self.default_facet

        # Normalize query: lowercase and tokenise for keyword matching
        normalized_query = query_nl.lower()
        tokens = set(re.findall(r"\b\w+(?:-\w+)*\b", normalized_query))

        # 1. Keyword-based scoring (fast path)
        scores: dict[str, int] = {}
        for facet_key, keywords in FACET_KEYWORDS.items():
            if facet_key not in self.facets:
                continue

            score = 0
            for kw in keywords:
                if " " in kw:
                    if kw in normalized_query:
                        score += 2  # Higher weight for multi-word phrases
                else:
                    if kw in tokens:
                        score += 1
            if score > 0:
                scores[facet_key] = score

        best_keyword_facet = None
        best_keyword_score = 0
        if scores:
            best_keyword_facet = max(scores, key=lambda k: scores[k])
            best_keyword_score = scores[best_keyword_facet]

        if best_keyword_score >= self.keyword_threshold:
            logger.debug(
                f"Tagged '{query_nl}' as '{best_keyword_facet}' "
                f"(keyword score: {best_keyword_score})"
            )
            return best_keyword_facet

        # 2. Embedding similarity (fallback/refinement)
        if (
            self.encoder is not None
            and self.facet_embeddings is not None
            and len(self.facet_keys_ordered) > 0
        ):
            try:
                query_emb = self.encoder.encode(query_nl, convert_to_tensor=True)
                similarities = cos_sim(query_emb, self.facet_embeddings)[0]

                # Find the best match
                best_idx = similarities.argmax().item()
                best_score = similarities[best_idx].item()

                # Threshold for semantic match
                if best_score >= 0.5:
                    best_facet = self.facet_keys_ordered[best_idx]
                    logger.debug(
                        f"Tagged '{query_nl}' as '{best_facet}' "
                        f"(embedding score: {best_score:.3f})"
                    )
                    return best_facet
            except Exception as e:
                logger.warning(
                    f"Embedding fallback failed for query '{query_nl}': {e}"
                )

        # 3. Default
        logger.debug(f"Tagged '{query_nl}' as default facet '{self.default_facet}'")
        return self.default_facet

    def tag_batch(self, queries: list[str]) -> list[str]:
        """Tag a batch of sub-intents.

        Args:
            queries: A list of natural language queries.

        Returns:
            A list of facet keys corresponding to the queries.
        """
        if not queries:
            return []

        return [self.tag(q) for q in queries]
