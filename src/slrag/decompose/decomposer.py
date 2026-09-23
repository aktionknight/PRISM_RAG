"""
decompose/decomposer.py — Multi-intent decomposition engine (Phase 3, Tasks 3.1 & 3.2).

Responsible for:
  Task 3.1: Syntactic candidate splitting at conjunction boundaries using spaCy
  Task 3.2: LLM canonicalisation under JSON grammar — ellipsis/anaphora resolution,
            self-containment validation with one re-prompt allowed.

The syntactic splitter runs FIRST to produce candidates, then LLM canonicalises
them into self-contained, facet-tagged SubIntents. Falls back to syntactic-only
decomposition with heuristic facet assignment if LLM is unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import spacy

    HAS_SPACY = True
except ImportError:
    HAS_SPACY = False

try:
    import ulid as _ulid_mod

    def _make_ulid() -> str:
        if hasattr(_ulid_mod, "new"):
            return str(_ulid_mod.new())
        return str(_ulid_mod.ULID())

except ImportError:
    import uuid

    def _make_ulid() -> str:
        return f"i_{uuid.uuid4().hex[:12]}"


from jinja2 import Environment, FileSystemLoader

from slrag.core.schemas import IntentStatus, SubIntent

logger = logging.getLogger(__name__)


# Pronoun/ellipsis detection for self-containment check
_PRONOUNS_RE = re.compile(
    r"\b(it|its|they|their|them|he|his|him|she|hers|her|this|that|these|those)\b",
    re.IGNORECASE,
)


class Decomposer:
    """Component 2: Multi-Intent Decomposition (Tasks 3.1 & 3.2).

    Syntactically splits compound utterances, then canonicalises each
    candidate into a self-contained SubIntent via a local LLM.
    """

    def __init__(self, config_dir: str | Path = "config") -> None:
        self.config_dir = Path(config_dir)
        self.app_config = self._load_yaml(self.config_dir / "app.yaml")
        
        # Prefer generated facets over manual config
        index_facets_path = self.config_dir.parent / ".index" / "facets.yaml"
        if index_facets_path.exists():
            self.facets_config = self._load_yaml(index_facets_path)
            logger.info("Decomposer: loaded generated facets from .index/facets.yaml")
        else:
            self.facets_config = self._load_yaml(self.config_dir / "facets.yaml")
            logger.info("Decomposer: loaded fallback facets from config/facets.yaml")

        self.max_llm_calls: int = self.app_config.get("engine", {}).get(
            "max_llm_calls_per_turn", 3
        )
        self.facets: list[str] = list(
            self.facets_config.get("facets", {}).keys()
        )
        self.default_facet: str = self.facets_config.get("default_facet", "general")

        # Jinja setup for prompt templates (all prompts in config/prompts/)
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.config_dir / "prompts"))
        )
        self.prompt_template = self.jinja_env.get_template("decompose.jinja")

        # spaCy for syntactic splitting
        self.nlp = None
        if HAS_SPACY:
            try:
                self.nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.warning(
                    "en_core_web_sm not found. Attempting download..."
                )
                try:
                    import spacy.cli

                    spacy.cli.download("en_core_web_sm")
                    self.nlp = spacy.load("en_core_web_sm")
                except Exception as e:
                    logger.error(f"Failed to load/download spaCy model: {e}")

        # LLM endpoint (OpenAI-compatible — Ollama/vLLM)
        self.llm_url = "http://localhost:11434/v1/chat/completions"

    # ── Config helpers ──────────────────────────────────────────────

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        """Load a YAML config file, returning empty dict on failure."""
        try:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config {path}: {e}")
            return {}

    # ── Task 3.1: Syntactic Candidate Splitter ──────────────────────

    def _syntactic_split(self, text: str) -> list[str]:
        """Split compound utterances at conjunction boundaries.

        Uses spaCy dependency parsing to identify coordinating conjunctions
        (and, also, plus, as well as) and split the utterance into candidates.
        Falls back to returning the full text if spaCy is unavailable.
        """
        if not self.nlp:
            return [text]

        doc = self.nlp(text)
        candidates: list[str] = []
        current_chunk: list = []

        split_lemmas = {"and", "also", "plus"}

        i = 0
        while i < len(doc):
            token = doc[i]

            # Handle multi-token "as well as"
            if token.text.lower() == "as" and i + 2 < len(doc):
                if (
                    doc[i + 1].text.lower() == "well"
                    and doc[i + 2].text.lower() == "as"
                ):
                    if current_chunk:
                        candidates.append(
                            " ".join(t.text for t in current_chunk)
                        )
                        current_chunk = []
                    i += 3
                    continue

            # Split on coordinating conjunctions
            if token.lemma_.lower() in split_lemmas and token.dep_ == "cc":
                if current_chunk:
                    candidates.append(
                        " ".join(t.text for t in current_chunk)
                    )
                    current_chunk = []
            else:
                current_chunk.append(token)

            i += 1

        if current_chunk:
            candidates.append(" ".join(t.text for t in current_chunk))

        cleaned = [c.strip() for c in candidates if c.strip()]
        return cleaned if cleaned else [text]

    # ── Self-containment validation ─────────────────────────────────

    @staticmethod
    def _is_self_contained(text: str) -> bool:
        """Check that a sub-query has no unresolved pronouns or ellipsis."""
        return not bool(_PRONOUNS_RE.search(text))

    # ── Task 3.2: LLM Canonicalisation ──────────────────────────────

    async def _call_llm(self, prompt: str) -> dict[str, Any] | None:
        """Call local LLM via OpenAI-compatible API.

        Returns parsed JSON response or None on failure.
        """
        if not HAS_AIOHTTP:
            logger.warning("aiohttp not available — LLM calls disabled")
            return None

        payload = {
            "model": "qwen2.5:7b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a json-only decomposition engine.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.llm_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=8.0),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        content = data["choices"][0]["message"]["content"]

                        # Strip markdown fences if present
                        if "```json" in content:
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif "```" in content:
                            content = content.split("```")[1].split("```")[0].strip()

                        return json.loads(content)
                    else:
                        logger.warning(
                            f"LLM returned status {response.status}"
                        )
        except asyncio.TimeoutError:
            logger.warning("LLM call timed out")
        except Exception as e:
            logger.error(f"LLM call failed: {e}")

        return None

    # ── Heuristic facet assignment (fallback) ───────────────────────

    def _heuristic_facet(self, text: str) -> str:
        """Assign a facet by simple keyword overlap — used when LLM is unavailable."""
        text_lower = text.lower()
        for facet in self.facets:
            # e.g. "cancellation_terms" → "cancellation terms"
            if facet.replace("_", " ") in text_lower:
                return facet
        return self.default_facet

    # ── Main entry point ────────────────────────────────────────────

    async def decompose(
        self,
        prefix: str,
        existing_intents: dict[str, SubIntent],
        ts: float,
    ) -> list[SubIntent]:
        """Decompose a transcript prefix into self-contained sub-intents.

        Pipeline:
          1. Syntactic split (spaCy) → candidate fragments
          2. LLM canonicalisation (Jinja prompt → local LLM → JSON parse)
          3. Self-containment validation (pronoun check, 1 re-prompt allowed)
          4. Fallback: syntactic-only with heuristic facet assignment

        Args:
            prefix: Current accumulated transcript prefix.
            existing_intents: Already-identified intents (to avoid duplication).
            ts: Stream time when decomposition was triggered.

        Returns:
            List of new SubIntent candidates (not yet deduplicated by IntentSet).
        """
        # Task 3.1: syntactic split for candidate context
        candidates = self._syntactic_split(prefix)
        logger.debug(f"Syntactic candidates ({len(candidates)}): {candidates}")

        # Render prompt for LLM canonicalisation
        prompt = self.prompt_template.render(
            prefix=prefix,
            existing_intents=list(existing_intents.values()),
            facets=self.facets,
        )

        # Task 3.2: LLM canonicalisation with 1 re-prompt allowed
        llm_response = None
        attempts = 0
        max_attempts = min(2, self.max_llm_calls)

        while attempts < max_attempts:
            attempts += 1
            llm_response = await self._call_llm(prompt)

            if llm_response and "sub_intents" in llm_response:
                # Validate self-containment of every sub-query
                all_valid = all(
                    self._is_self_contained(si.get("query_nl", ""))
                    for si in llm_response["sub_intents"]
                )
                if all_valid:
                    break
                else:
                    # One re-prompt allowed
                    prompt += (
                        "\n\nError: A sub-query contained unresolved pronouns. "
                        "Rewrite every sub-query to be fully self-contained."
                    )
                    logger.debug("Re-prompting LLM for self-containment fix")
            else:
                prompt += (
                    "\n\nError: Output must match the requested JSON format "
                    "containing 'sub_intents'."
                )

        # Build SubIntent objects
        new_intents: list[SubIntent] = []

        if llm_response and "sub_intents" in llm_response:
            for si_data in llm_response["sub_intents"]:
                facet = si_data.get("facet", self.default_facet)
                if facet not in self.facets:
                    facet = self.default_facet

                intent = SubIntent(
                    intent_id=f"i_{_make_ulid()}",
                    facet=facet,
                    query_nl=si_data.get("query_nl", ""),
                    search_string=si_data.get("search_string", ""),
                    novel=si_data.get("novel", True),
                    first_seen_ts=ts,
                    status=IntentStatus.pending,
                )
                new_intents.append(intent)
            logger.info(
                f"LLM decomposition produced {len(new_intents)} intent(s)"
            )
        else:
            # Fallback: syntactic-only with heuristic facet assignment
            logger.warning(
                "LLM canonicalisation failed — falling back to syntactic splits"
            )
            for cand in candidates:
                intent = SubIntent(
                    intent_id=f"i_{_make_ulid()}",
                    facet=self._heuristic_facet(cand),
                    query_nl=cand,
                    search_string=cand,
                    novel=True,
                    first_seen_ts=ts,
                    status=IntentStatus.pending,
                )
                new_intents.append(intent)

        return new_intents
