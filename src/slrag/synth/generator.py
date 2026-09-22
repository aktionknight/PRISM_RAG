"""Claim generator — the single synthesis LLM call per turn (roadmap 4.6, S-6).

The generator emits the answer *as claims*: one self-contained sentence per
claim, tagged with its sub-intent, facet and citation labels. It never verifies
or renders; ``generate`` is an async generator of ``DraftClaim`` so the two-pass
streamer (S-5) can verify sentence N while N+1 is still arriving.

Backends (``config/synth.yaml`` ``generator.backend``):
  * ``extractive`` — deterministic, offline, zero LLM calls (CI / golden replay);
  * ``openai_compatible`` — Qwen2.5-7B-Instruct on local Ollama/vLLM: exactly one
    ``complete`` call per ``generate`` (HC-5), json-schema mode constrains
    citations to the allowlist enum (S-6 layer 2).

S-6 layer 1: ``allowed_ids`` is built from the chunks passed in and nothing
else; the prompts (``config/prompts/*.jinja``, HC-2) forbid any other label and
any parametric knowledge (HC-1). Layer 3, the post-hoc validator, lives in the
verifier — fabricated labels are passed through here untouched.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlparse

import jinja2

from slrag.core.citations import label_for_chunk, labels_for_chunks
from slrag.core.schemas import Claim, RetrievedChunk, SubIntent
from slrag.synth.config import facet_label, load_facets, load_synth_config, resolve_path
from slrag.synth.text import content_tokens, overlap, split_sentences, stopwords_from
from slrag.synth.types import DraftClaim, GenerationUsage

log = logging.getLogger(__name__)

Evidence = Mapping[str, Sequence[RetrievedChunk]]
Transport = Callable[[str, dict, dict, float], dict]   # (url, body, headers, timeout_s) -> parsed JSON

MODES = ("synthesize", "refine")
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal"})
_FENCE_RE = re.compile(r"```(?:json)?[ \t]*\n?(.*?)```", re.DOTALL | re.IGNORECASE)


# ---------------------------------------------------------------------------
# Prompts (HC-2: every word the model sees lives in config/prompts/*.jinja)
# ---------------------------------------------------------------------------
class PromptLibrary:
    def __init__(self, config: dict | None = None) -> None:
        cfg = (config if config is not None else load_synth_config())["generator"]
        self.templates: dict[str, str] = dict(cfg["templates"])
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(resolve_path(cfg["prompts_dir"]))),
            undefined=jinja2.StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, name: str, **ctx: Any) -> str:
        if name not in self.templates:
            raise KeyError(f"unknown prompt template {name!r}; known: {sorted(self.templates)}")
        return self.env.get_template(self.templates[name]).render(**ctx)


def claims_json_schema(allowed_ids: Sequence[str], intent_ids: Sequence[str]) -> dict:
    """JSON schema for ``{"claims": [...]}``; citations are an enum over the allowlist (S-6 layer 2)."""
    intent_id: dict[str, Any] = (
        {"type": "string", "enum": list(intent_ids)} if intent_ids else {"type": ["string", "null"]}
    )
    claim = {
        "type": "object",
        "properties": {
            "intent_id": intent_id,
            "facet": {"type": "string"},
            "text": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {"type": "string", "enum": list(allowed_ids)},
                "minItems": 1,
            },
        },
        "required": ["intent_id", "facet", "text", "citations"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"claims": {"type": "array", "items": claim}},
        "required": ["claims"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# LLM client (local OpenAI-compatible endpoint; HC-1 guarded)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int


class LLMClient(Protocol):
    async def complete(self, prompt: str, *, json_schema: dict | None = None) -> LLMResponse: ...


def is_local_endpoint(base_url: str) -> bool:
    """Loopback, docker host alias, or a dot-less service name (e.g. ``ollama``) — HC-1."""
    host = (urlparse(base_url).hostname or "").lower()
    if not host:
        return False
    if host in _LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return "." not in host


def _urllib_transport(url: str, body: dict, headers: dict, timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (scheme/host vetted)
        return json.loads(response.read().decode("utf-8"))


class OpenAICompatibleClient:
    """``POST {base_url}/chat/completions`` against local Ollama/vLLM; one request per ``complete``."""

    def __init__(self, config: dict | None = None, *, transport: Transport | None = None) -> None:
        opts = (config if config is not None else load_synth_config())["generator"]["openai_compatible"]
        self.base_url = str(opts["base_url"]).rstrip("/")
        self.model = str(opts["model"])
        self.temperature = float(opts["temperature"])
        self.max_tokens = int(opts["max_tokens"])
        self.timeout_s = float(opts["timeout_s"])
        self.json_schema_mode = bool(opts["json_schema_mode"])
        self.api_key_env = opts.get("api_key_env")
        if urlparse(self.base_url).scheme not in ("http", "https"):
            raise ValueError(f"LLM base_url must be http(s): {self.base_url!r}")
        if not opts.get("allow_remote", False) and not is_local_endpoint(self.base_url):
            raise ValueError(f"HC-1: refusing non-local LLM endpoint {self.base_url!r} (set allow_remote)")
        self._transport = transport or _urllib_transport

    def build_request(self, prompt: str, json_schema: dict | None = None) -> tuple[str, dict, dict]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_schema is not None and self.json_schema_mode:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "claims", "schema": json_schema, "strict": True},
            }
        headers = {"Content-Type": "application/json"}
        api_key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return f"{self.base_url}/chat/completions", body, headers

    async def complete(self, prompt: str, *, json_schema: dict | None = None) -> LLMResponse:
        url, body, headers = self.build_request(prompt, json_schema)
        data = await asyncio.to_thread(self._transport, url, body, headers, self.timeout_s)
        return _parse_completion(data, prompt)


def _parse_completion(data: Any, prompt: str) -> LLMResponse:
    data = data if isinstance(data, dict) else {}
    choices = data.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    text = content if isinstance(content, str) else ""
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    return LLMResponse(
        text=text,
        prompt_tokens=prompt_tokens if isinstance(prompt_tokens, int) else len(prompt.split()),
        completion_tokens=completion_tokens if isinstance(completion_tokens, int) else len(text.split()),
    )


# ---------------------------------------------------------------------------
# Model-output parsing (never raises on bad output)
# ---------------------------------------------------------------------------
def parse_claim_objects(text: str) -> tuple[list[Any], int]:
    """Candidate claim items from raw model output, plus the number of broken fragments.

    Accepts ``{"claims": [...]}``, a bare JSON list, a single claim object,
    JSON-lines, ```json fences, surrounding prose, and truncated output: when the
    whole body is not one JSON document, every complete object is salvaged and each
    gap that holds an unparseable object fragment counts as broken.
    """
    body = _strip_fences(text).strip()
    if not body:
        return [], 0
    try:
        return _unwrap(json.loads(body)), 0
    except ValueError:
        pass
    decoder = json.JSONDecoder()
    items: list[Any] = []
    broken = pos = gap_start = 0
    while (start := body.find("{", pos)) != -1:
        try:
            obj, end = decoder.raw_decode(body, start)
        except ValueError:
            pos = start + 1
            continue
        broken += "{" in body[gap_start:start]
        items.extend(_unwrap(obj))
        pos = gap_start = end
    broken += "{" in body[gap_start:]
    return items, broken if items else max(broken, 1)


def _strip_fences(text: str) -> str:
    blocks = _FENCE_RE.findall(text or "")
    return "\n".join(blocks) if blocks else (text or "")


def _unwrap(obj: Any) -> list[Any]:
    if isinstance(obj, dict) and "claims" in obj:
        inner = obj["claims"]
        return list(inner) if isinstance(inner, list) else [inner]
    return list(obj) if isinstance(obj, list) else [obj]


def _item_to_draft(
    item: Any,
    seq: int,
    intents: Mapping[str, SubIntent],
    fallback_facet: str,
    scores: Mapping[str, float],
) -> DraftClaim | None:
    """One parsed item -> DraftClaim; None if malformed. Labels are kept verbatim (verifier strips)."""
    if not isinstance(item, dict):
        return None
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    raw = item.get("citations")
    raw = [raw] if isinstance(raw, str) else raw if isinstance(raw, (list, tuple)) else []
    citations = tuple(label for label in raw if isinstance(label, str))
    intent_id = item.get("intent_id") if isinstance(item.get("intent_id"), str) else None
    intent = intents.get(intent_id or "")
    facet = item.get("facet")
    if not isinstance(facet, str) or not facet.strip():
        facet = intent.facet if intent else fallback_facet
    return DraftClaim(
        seq=seq,
        facet=facet,
        text=text.strip(),
        citations=citations,
        intent_id=intent_id,
        confidence=max((scores[c] for c in citations if c in scores), default=0.0),
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _check_mode(mode: str) -> None:
    if mode not in MODES:
        raise ValueError(f"unknown generation mode {mode!r}; expected one of {MODES}")


def _context_chunks(evidence: Evidence) -> list[RetrievedChunk]:
    """Every chunk passed in, de-duplicated by chunk_id, first-seen order."""
    seen: dict[str, RetrievedChunk] = {}
    for chunks in evidence.values():
        for chunk in chunks:
            seen.setdefault(chunk.chunk_id, chunk)
    return list(seen.values())


def _claim_row(claim: Claim | Mapping[str, Any]) -> dict[str, Any]:
    """A frozen ``Claim`` (or an equivalent mapping) as a template-ready dict."""
    if isinstance(claim, Mapping):
        return {
            "claim_id": str(claim.get("claim_id", "")),
            "facet": str(claim.get("facet", "")),
            "text": str(claim.get("text", "")),
            "citations": list(claim.get("citations", ())),
        }
    return {"claim_id": claim.claim_id, "facet": claim.facet, "text": claim.text, "citations": list(claim.citations)}


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


# ---------------------------------------------------------------------------
# Backend: extractive (deterministic, zero LLM calls)
# ---------------------------------------------------------------------------
class ExtractiveGenerator:
    """Verbatim corpus sentences as claims — the offline backend for CI and golden replay."""

    backend = "extractive"

    def __init__(self, config: dict | None = None, facets: dict | None = None) -> None:
        self.config = config if config is not None else load_synth_config()
        self.facets = facets if facets is not None else load_facets()
        opts = self.config["generator"]["extractive"]
        self.min_chunk_score = float(opts["min_chunk_score"])
        self.max_claims_per_intent = int(opts["max_claims_per_intent"])
        self.min_relevance = float(opts["min_relevance"])
        self._stopwords = stopwords_from(self.config)
        self.usage = GenerationUsage(backend=self.backend)

    async def generate(
        self,
        sub_intents: Sequence[SubIntent],
        evidence: Evidence,
        *,
        constraints: Mapping[str, str] | None = None,
        mode: str = "synthesize",
        retained_claims: Iterable[Claim | Mapping[str, Any]] = (),
    ) -> AsyncIterator[DraftClaim]:
        started = time.perf_counter()
        drafts = self.draft(sub_intents, evidence, mode=mode, retained_claims=retained_claims)
        self.usage = GenerationUsage(llm_calls=0, backend=self.backend, latency_ms=_ms(started))
        for draft in drafts:
            yield draft

    def draft(
        self,
        sub_intents: Sequence[SubIntent],
        evidence: Evidence,
        *,
        mode: str = "synthesize",
        retained_claims: Iterable[Claim | Mapping[str, Any]] = (),
    ) -> list[DraftClaim]:
        """Synchronous core of ``generate`` (constraints are already reflected in the evidence)."""
        _check_mode(mode)
        retained = {_norm(_claim_row(claim)["text"]) for claim in retained_claims}
        drafts: list[DraftClaim] = []
        for intent in sub_intents:
            for chunk, sentence in self._select(intent, evidence.get(intent.intent_id, ()), retained):
                drafts.append(
                    DraftClaim(
                        seq=len(drafts),
                        facet=intent.facet,
                        text=sentence,
                        citations=(label_for_chunk(chunk),),
                        intent_id=intent.intent_id,
                        confidence=chunk.score,
                    )
                )
        return drafts

    def _select(
        self, intent: SubIntent, chunks: Sequence[RetrievedChunk], retained: set[str]
    ) -> list[tuple[RetrievedChunk, str]]:
        keywords = " ".join(map(str, self.facets.get(intent.facet, {}).get("keywords", ()) or ()))
        query = content_tokens(f"{intent.query_nl} {intent.search_string} {keywords}", self._stopwords)
        usable = sorted((c for c in chunks if c.score >= self.min_chunk_score), key=lambda c: -c.score)
        picked: list[tuple[RetrievedChunk, str]] = []
        seen = set(retained)
        for chunk in usable:
            for sentence in split_sentences(chunk.text):
                if len(picked) >= self.max_claims_per_intent:
                    return picked
                key = _norm(sentence)
                if key in seen:
                    continue
                if overlap(content_tokens(sentence, self._stopwords), query) >= self.min_relevance:
                    picked.append((chunk, sentence))
                    seen.add(key)
        return picked


# ---------------------------------------------------------------------------
# Backend: LLM (exactly one call per generate, HC-5)
# ---------------------------------------------------------------------------
class LLMGenerator:
    backend = "openai_compatible"

    def __init__(
        self,
        client: LLMClient,
        *,
        config: dict | None = None,
        facets: dict | None = None,
        prompts: PromptLibrary | None = None,
    ) -> None:
        self.client = client
        self.config = config if config is not None else load_synth_config()
        self.facets = facets if facets is not None else load_facets()
        self.prompts = prompts if prompts is not None else PromptLibrary(self.config)
        self.json_schema_mode = bool(self.config["generator"]["openai_compatible"]["json_schema_mode"])
        self.usage = GenerationUsage(backend=self.backend)
        self.parse_errors = 0
        self.last_error: str | None = None

    def render_prompt(
        self,
        sub_intents: Sequence[SubIntent],
        evidence: Evidence,
        *,
        constraints: Mapping[str, str] | None = None,
        mode: str = "synthesize",
        retained_claims: Iterable[Claim | Mapping[str, Any]] = (),
    ) -> tuple[str, list[str]]:
        """(prompt, allowed_ids); allowed_ids = labels of every chunk passed in (S-6 layer 1)."""
        _check_mode(mode)
        chunks = _context_chunks(evidence)
        allowed = labels_for_chunks(chunks)
        ctx: dict[str, Any] = {
            "sub_intents": [
                {
                    "intent_id": intent.intent_id,
                    "facet": intent.facet,
                    "facet_label": facet_label(self.facets, intent.facet),
                    "query_nl": intent.query_nl,
                }
                for intent in sub_intents
            ],
            "chunks": [{"label": label_for_chunk(chunk), "text": chunk.text} for chunk in chunks],
            "allowed_ids": allowed,
            "constraints": dict(constraints or {}),
        }
        if mode == "refine":
            ctx["retained_claims"] = [
                {"text": row["text"], "citations": row["citations"]} for row in map(_claim_row, retained_claims)
            ]
        return self.prompts.render(mode, **ctx), allowed

    async def generate(
        self,
        sub_intents: Sequence[SubIntent],
        evidence: Evidence,
        *,
        constraints: Mapping[str, str] | None = None,
        mode: str = "synthesize",
        retained_claims: Iterable[Claim | Mapping[str, Any]] = (),
    ) -> AsyncIterator[DraftClaim]:
        self.parse_errors = 0
        self.last_error = None
        intents = list(sub_intents)
        prompt, allowed = self.render_prompt(
            intents, evidence, constraints=constraints, mode=mode, retained_claims=retained_claims
        )
        if not intents or not allowed:        # nothing to ground on: spend no call (coverage reports it)
            self.usage = GenerationUsage(backend=self.backend)
            return
        schema = claims_json_schema(allowed, [i.intent_id for i in intents]) if self.json_schema_mode else None
        response = await self._complete_once(prompt, schema)
        scores = _label_scores(evidence)
        by_id = {intent.intent_id: intent for intent in intents}
        fallback = intents[0].facet if len(intents) == 1 else ""
        for draft in self._drafts(response, by_id, fallback, scores):
            yield draft

    async def restyle(
        self, claims: Sequence[Claim | Mapping[str, Any]], instruction: str
    ) -> AsyncIterator[DraftClaim]:
        """Optional PRESENTATION_ONLY restyle (translation/tone) of existing claims; one call.

        Citations are constrained to the claims' own labels; the caller still asserts
        the presentation invariant (subset of the prior turn's citations).
        """
        self.parse_errors = 0
        self.last_error = None
        rows = [_claim_row(claim) for claim in claims]
        allowed = list(dict.fromkeys(label for row in rows for label in row["citations"]))
        if not rows or not allowed:
            self.usage = GenerationUsage(backend=self.backend)
            return
        prompt = self.prompts.render("present_only", claims=rows, instruction=instruction)
        schema = claims_json_schema(allowed, ()) if self.json_schema_mode else None
        response = await self._complete_once(prompt, schema)
        scores = dict.fromkeys(allowed, 1.0)
        fallback = rows[0]["facet"] if len({row["facet"] for row in rows}) == 1 else ""
        for draft in self._drafts(response, {}, fallback, scores):
            yield draft

    async def _complete_once(self, prompt: str, schema: dict | None) -> LLMResponse | None:
        """The single LLM call (HC-5). Transport failures degrade to zero claims; no retry."""
        started = time.perf_counter()
        try:
            response = await self.client.complete(prompt, json_schema=schema)
        except (OSError, ValueError) as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            log.warning("synthesis LLM call failed: %s", self.last_error)
            self.usage = GenerationUsage(
                llm_calls=1, prompt_tokens=len(prompt.split()), backend=self.backend, latency_ms=_ms(started)
            )
            return None
        self.usage = GenerationUsage(
            llm_calls=1,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            backend=self.backend,
            latency_ms=_ms(started),
        )
        return response

    def _drafts(
        self,
        response: LLMResponse | None,
        intents: Mapping[str, SubIntent],
        fallback_facet: str,
        scores: Mapping[str, float],
    ) -> list[DraftClaim]:
        if response is None:
            return []
        items, broken = parse_claim_objects(response.text)
        drafts: list[DraftClaim] = []
        for item in items:
            draft = _item_to_draft(item, len(drafts), intents, fallback_facet, scores)
            if draft is None:
                broken += 1
            else:
                drafts.append(draft)
        self.parse_errors = broken
        return drafts


def _label_scores(evidence: Evidence) -> dict[str, float]:
    scores: dict[str, float] = {}
    for chunk in _context_chunks(evidence):
        label = label_for_chunk(chunk)
        scores[label] = max(scores.get(label, chunk.score), chunk.score)
    return scores



# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def make_generator(
    config: dict | None = None, facets: dict | None = None, *, client: LLMClient | None = None
) -> ExtractiveGenerator | LLMGenerator:
    cfg = config if config is not None else load_synth_config()
    backend = cfg["generator"]["backend"]
    if backend == "extractive":
        return ExtractiveGenerator(cfg, facets)
    if backend == "openai_compatible":
        return LLMGenerator(client if client is not None else OpenAICompatibleClient(cfg), config=cfg, facets=facets)
    raise ValueError(f"unknown generator backend {backend!r}")
