"""Final projection of the ClaimGraph + presentation-only path (Rule 3, roadmap 4.5).

The answer string is never stored anywhere: it is rendered last, from claims only
(A_FINAL_ARCHITECTURE §4.1), and packed into the frozen ``core.schemas.AnswerOutput``
plus a separate extensions dict for the additive §6 fields (the contract is never
subclassed or widened).

Presentation-only turns (§4.3, Example 3) re-render ``graph.active()`` in a new
shape. This module imports nothing from ``slrag.retrieve`` / ``slrag.decompose`` /
``slrag.controller`` or any retriever/pool (asserted by an ast test over its import
closure), so the corpus is structurally unreachable from here, and
``render_presentation`` hard-asserts ``citations(new) ⊆ citations(prior)``.

Translation and tone changes cannot be done deterministically. With an LLM backend
the engine restyles the claims (one ``present_only`` call, HC-5), verifies the result
and passes it in as ``claims``; otherwise, or if verification fails, they fall back
to a prose re-render of the same claims while keeping their suppression reason
(``translation`` / ``tone_change``).

Separators, prefixes, verb lexicons and reasons come from ``config/synth.yaml``
``renderer:`` / ``presentation:`` (HC-2); code values are fallbacks for missing keys.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from slrag.core.citations import find_markers, format_marker, normalize_label
from slrag.core.schemas import AnswerOutput, Claim, ControllerDecision
from slrag.synth.claims import ClaimGraph
from slrag.synth.config import load_synth_config
from slrag.synth.types import PresentationInvariantError, VersionLineage

STYLES = ("prose", "bullets", "numbered", "short")
_LIST_STYLES = ("bullets", "numbered")
_REQUIRED_KEYS = ("retrieval_events", "sub_queries", "answer", "citations", "uncertainty")
_SESSION_KEYS = ("session_id", "turn_id", "answer_version")
_EVENT_KEYS = ("timestamp_s", "query", "trigger")
# Fallbacks only; the source of truth is config (renderer.triggers / presentation.styles).
_FALLBACK_TRIGGERS = ("provisional", "multi_intent", "late_constraint", "clarification_followup", "final_confirm")
_FALLBACK_STYLE_VERBS = MappingProxyType(
    {
        "numbered": ("numbered",),
        "bullets": ("bullet", "bullets", "bulleted", "list"),
        "short": ("shorten", "shorter", "summarise", "summarize", "condense", "briefly"),
    }
)
_FALLBACK_REASON = "presentation_restructure"
_WORD_RE = re.compile(r"[a-z]+|\d+")


# ---------------------------------------------------------------------------
# Claim-list rendering
# ---------------------------------------------------------------------------
def render_claims(
    claims: Sequence[Claim],
    *,
    style: str = "prose",
    bullets: int | None = None,
    config: dict | None = None,
) -> str:
    """Project claims to text; claims grouped by facet in first-appearance order."""
    cfg = (config if config is not None else load_synth_config()).get("renderer", {})
    separator = cfg.get("claim_separator", " ")
    groups = _group_by_facet(claims)
    if style == "prose":
        return separator.join(_sentence(claim) for group in groups for claim in group)
    if style == "short":
        keep = int(cfg.get("short_max_claims_per_facet", 1))
        return separator.join(_sentence(claim) for group in groups for claim in group[:keep])
    if style in _LIST_STYLES:
        lines = []
        for n, piece in enumerate(_distribute(groups, bullets), start=1):
            prefix = (
                cfg.get("bullet_prefix", "- ")
                if style == "bullets"
                else cfg.get("numbered_format", "{n}. ").format(n=n)
            )
            lines.append(prefix + separator.join(_sentence(claim) for claim in piece))
        return "\n".join(lines)
    raise ValueError(f"unknown render style {style!r}; expected one of {STYLES}")


def answer_citations(claims: Sequence[Claim]) -> list[str]:
    """Ordered, de-duplicated union of the claims' citations."""
    return list(dict.fromkeys(label for claim in claims for label in claim.citations))


# ---------------------------------------------------------------------------
# Presentation-only path (Example 3)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PresentationRequest:
    style: str                 # prose | bullets | numbered | short
    bullets: int | None        # requested line count for list styles, else None
    reason: str                # suppression_reason (presentation_restructure | translation | tone_change)


def parse_presentation_request(utterance: str, config: dict | None = None) -> PresentationRequest:
    """"Can you repeat that in two bullets?" -> PresentationRequest("bullets", 2, "presentation_restructure").

    Style: first ``presentation.styles`` entry whose verbs appear (config order, so
    "numbered list" is numbered); none -> prose (repeat / rephrase / translate / tone).
    Reason: a ``presentation.reasons`` key (other than ``default``) used as a word.
    Count (list styles only): first digit run or ``presentation.number_words`` word.
    """
    cfg = (config if config is not None else load_synth_config()).get("presentation", {})
    tokens = _WORD_RE.findall(utterance.lower())
    words = set(tokens)
    styles = cfg.get("styles") or _FALLBACK_STYLE_VERBS
    style = next((name for name, verbs in styles.items() if words & set(verbs)), "prose")
    reasons = cfg.get("reasons", {})
    reason = next(
        (value for key, value in reasons.items() if key != "default" and key in words),
        reasons.get("default", _FALLBACK_REASON),
    )
    count = None
    if style in _LIST_STYLES:
        number_words = cfg.get("number_words", {})
        for token in tokens:
            value = int(token) if token.isdigit() else number_words.get(token)
            if value:
                count = int(value)
                break
    return PresentationRequest(style=style, bullets=count, reason=reason)


def render_presentation(
    graph: ClaimGraph,
    request: PresentationRequest,
    *,
    prior_citations: Sequence[str],
    config: dict | None = None,
    claims: Sequence[Claim] | None = None,
) -> tuple[str, list[str]]:
    """Re-render ONLY ``graph.active()`` (or ``claims``, restyled versions of them);
    never touches the corpus or mutates the graph.

    Raises PresentationInvariantError unless ``citations(new) ⊆ citations(prior)``,
    checked over the claims' citations and every marker in the rendered text.
    """
    claims = graph.active() if claims is None else list(claims)
    text = render_claims(claims, style=request.style, bullets=request.bullets, config=config)
    cited = [normalize_label(label) or label for label in answer_citations(claims)]
    for _, labels in find_markers(text):
        cited.extend(normalize_label(label) or label for label in labels)
    cited = list(dict.fromkeys(cited))
    allowed = {normalize_label(label) or label for label in prior_citations}
    extra = [label for label in cited if label not in allowed]
    if extra:
        raise PresentationInvariantError(
            f"presentation turn cites {extra} outside the prior turn's citations {list(prior_citations)}"
        )
    return text, cited


# ---------------------------------------------------------------------------
# Output assembly (A_FINAL_ARCHITECTURE §6)
# ---------------------------------------------------------------------------
def build_answer_output(
    *,
    session_id: str,
    turn_id: int,
    answer_version: int,
    answer: str,
    citations: Sequence[str],
    uncertainty: str,
    sub_queries: Sequence[str],
    retrieval_events: Sequence[Mapping[str, Any]],
    retrieval_required: bool = True,
    suppression_reason: str | None = None,
    controller_decisions: Sequence[ControllerDecision] = (),
    graph: ClaimGraph | None = None,
    lineage: VersionLineage | None = None,
    telemetry: Mapping[str, Any] | None = None,
    config: dict | None = None,
) -> AnswerOutput:
    """The frozen contract object, now widened with v1.1 fields. Each retrieval event must be exactly
    ``{timestamp_s, query, trigger}`` with ``trigger`` in the §6 enum; raises ValueError otherwise."""
    cfg = (config if config is not None else load_synth_config()).get("renderer", {})
    triggers = tuple(cfg.get("triggers", _FALLBACK_TRIGGERS))
    events = [_validate_event(index, event, triggers) for index, event in enumerate(retrieval_events)]
    return AnswerOutput(
        retrieval_events=events,
        sub_queries=list(sub_queries),
        answer=answer,
        citations=list(citations),
        uncertainty=uncertainty,
        session_id=session_id,
        turn_id=turn_id,
        answer_version=answer_version,
        retrieval_required=bool(retrieval_required),
        suppression_reason=suppression_reason,
        controller_decisions=list(controller_decisions),
        claims=graph.to_output() if graph else [],
        version_lineage=lineage,
        telemetry=telemetry,
    )


def build_extensions(
    *,
    retrieval_required: bool,
    suppression_reason: str | None,
    controller_decisions: Sequence[ControllerDecision],
    graph: ClaimGraph,
    lineage: VersionLineage | None,
    telemetry: Mapping[str, Any],
) -> dict[str, Any]:
    """Additive §6 fields, kept outside the frozen AnswerOutput."""
    return {
        "retrieval_required": bool(retrieval_required),
        "suppression_reason": suppression_reason,
        "controller_decisions": [
            {
                "timestamp_s": decision.t_s,
                "decision": decision.decision,
                "reason": decision.reason,
                "confidence": decision.confidence,
            }
            for decision in controller_decisions
        ],
        "claims": graph.to_output(),
        "version_lineage": lineage.to_dict() if lineage is not None else None,
        "telemetry": copy.deepcopy(dict(telemetry)),
    }


def render_output_json(output: AnswerOutput, extensions: Mapping[str, Any]) -> dict[str, Any]:
    """Five required keys first, then session_id / turn_id / answer_version, then extensions."""
    dumped = output.model_dump(mode="json")
    merged = {key: dumped[key] for key in _REQUIRED_KEYS + _SESSION_KEYS}
    clash = [key for key in extensions if key in merged]
    if clash:
        raise ValueError(f"extensions may not override contract fields {clash}")
    merged.update(copy.deepcopy(dict(extensions)))
    return merged


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _sentence(claim: Claim) -> str:
    marker = format_marker(claim.citations)
    return f"{claim.text} {marker}" if marker else claim.text


def _group_by_facet(claims: Sequence[Claim]) -> list[list[Claim]]:
    groups: dict[str, list[Claim]] = {}
    for claim in claims:
        groups.setdefault(claim.facet, []).append(claim)
    return list(groups.values())


def _distribute(groups: list[list[Claim]], bullets: int | None) -> list[list[Claim]]:
    """Exactly min(bullets, #claims) order-preserving pieces; None -> one per facet.

    Fewer bullets than facets merges whole facets (never splitting one); more bullets
    than facets splits the largest groups in half until the count is reached.
    """
    if bullets is None:
        return [list(group) for group in groups]
    if bullets < 1:
        raise ValueError(f"bullet count must be >= 1, got {bullets}")
    total = sum(len(group) for group in groups)
    target = min(bullets, total)
    if target == 0:
        return []
    if target <= len(groups):
        return _partition(groups, target)
    pieces = [list(group) for group in groups]
    while len(pieces) < target:
        index = max(range(len(pieces)), key=lambda i: len(pieces[i]))   # first largest
        piece = pieces[index]
        half = (len(piece) + 1) // 2
        pieces[index:index + 1] = [piece[:half], piece[half:]]
    return pieces


def _partition(groups: list[list[Claim]], n: int) -> list[list[Claim]]:
    """Contiguous split of whole facet groups into ``n`` bullets minimising the largest
    bullet (claim count); ties favour fuller earlier bullets. Linear-partition DP."""
    k = len(groups)
    prefix = [0]
    for group in groups:
        prefix.append(prefix[-1] + len(group))
    inf = float("inf")
    cost = [[inf] * (k + 1) for _ in range(n + 1)]
    cut = [[0] * (k + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for j in range(1, n + 1):
        for i in range(j, k + 1):
            for m in range(j - 1, i):
                if cost[j - 1][m] == inf:
                    continue
                candidate = max(cost[j - 1][m], prefix[i] - prefix[m])
                if candidate <= cost[j][i]:
                    cost[j][i], cut[j][i] = candidate, m
    pieces: list[list[Claim]] = []
    end = k
    for j in range(n, 0, -1):
        start = cut[j][end]
        pieces.insert(0, [claim for group in groups[start:end] for claim in group])
        end = start
    return pieces


def _validate_event(index: int, event: Any, triggers: tuple[str, ...]) -> dict[str, Any]:
    where = f"retrieval_events[{index}]"
    if not isinstance(event, Mapping):
        raise ValueError(f"{where} must be a dict, got {type(event).__name__}")
    if set(event) != set(_EVENT_KEYS):
        raise ValueError(f"{where} must have exactly keys {list(_EVENT_KEYS)}, got {sorted(event)}")
    timestamp, query, trigger = event["timestamp_s"], event["query"], event["trigger"]
    if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or timestamp < 0:
        raise ValueError(f"{where}.timestamp_s must be a non-negative number, got {timestamp!r}")
    if not isinstance(query, str) or not query.strip():
        raise ValueError(f"{where}.query must be a non-empty string, got {query!r}")
    if trigger not in triggers:
        raise ValueError(f"{where}.trigger {trigger!r} not in {list(triggers)}")
    return {"timestamp_s": float(timestamp), "query": query, "trigger": trigger}
