"""SynthesisEngine — Component 4 entry point (roadmap §1 topology stage [4]).

Replaces ``stubs.fake_synthesize`` behind ``config/app.yaml: use_stub_synthesis``.
One engine per session; all state (ClaimGraph, constraints, intents) lives on the
instance and dies with it (HC-4). Per turn:

    classify ─┬─ NEW_INTENT            → generate → two-pass verify → graph revision
              ├─ CONSTRAINT_REFINEMENT → delta plan → pool-first / targeted queries
              │                          → generate(refine) → verify → delta apply
              └─ PRESENTATION_ONLY     → re-render active claims (no retrieval path)
    → coverage matrix → uncertainty → AnswerOutput (+ additive extensions)

LLM budget (HC-5): at most one generator call per turn from this component; the
classifier, delta engine, verifier, coverage matrix and renderer are deterministic.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterable, Mapping, Sequence

from slrag.core.schemas import (
    AnswerOutput,
    ControllerDecision,
    RetrievedChunk,
    SubIntent,
    TelemetryEvent,
)
from slrag.synth.claims import ClaimGraph
from slrag.synth.config import load_facets, load_synth_config
from slrag.synth.delta import DeltaEngine, merge_constraints
from slrag.synth.generator import make_generator
from slrag.synth.renderer import (
    answer_citations,
    build_answer_output,
    build_extensions,
    parse_presentation_request,
    render_claims,
    render_output_json,
    render_presentation,
)
from slrag.synth.types import (
    CoverageRow,
    EvidencePoolView,
    GenerationUsage,
    RefinementReport,
    RetrieveFn,
    StreamEvent,
    TurnClassification,
    TurnType,
    VerificationResult,
    VersionLineage,
)
from slrag.synth.uncertainty import CoverageMatrix
from slrag.synth.verifier import CitationAllowlist, ClaimVerifier, TwoPassStreamer, make_scorer

COMPONENT = "synthesis"


@dataclass
class TurnInput:
    """Everything upstream components hand Component 4 for one utterance."""

    turn_id: int
    utterance: str
    t_s_end: float
    sub_intents: Sequence[SubIntent] = ()
    evidence: Mapping[str, Sequence[RetrievedChunk]] = field(default_factory=dict)   # intent_id -> chunks
    retrieval_events: Sequence[dict] = ()
    controller_decisions: Sequence[ControllerDecision] = ()


@dataclass
class SynthesisResult:
    turn_type: TurnType
    classification: TurnClassification
    output: AnswerOutput
    extensions: dict[str, Any]
    stream_events: list[StreamEvent]
    verification: list[VerificationResult]
    coverage: list[CoverageRow]
    lineage: VersionLineage | None
    refinement: RefinementReport | None
    usage: GenerationUsage
    telemetry: list[TelemetryEvent]
    fabricated_id_count: int                      # labels outside the allowlist in the OUTPUT (must be 0)

    def to_json(self) -> dict[str, Any]:
        return render_output_json(self.output, self.extensions)


class SynthesisEngine:
    def __init__(
        self,
        session_id: str,
        *,
        config: dict | None = None,
        facets: dict | None = None,
        generator: Any | None = None,
        retrieve_fn: RetrieveFn | None = None,
        pool: EvidencePoolView | None = None,
        scorer: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.config = config if config is not None else load_synth_config()
        self.facets = facets if facets is not None else load_facets()
        self.graph = ClaimGraph(session_id)
        self.delta = DeltaEngine(self.config, self.facets)
        self.coverage = CoverageMatrix(self.config, self.facets)
        self.generator = generator if generator is not None else make_generator(self.config, self.facets)
        self.retrieve_fn = retrieve_fn
        self.pool = pool
        self.scorer = scorer if scorer is not None else make_scorer(self.config)
        self.session_constraints: dict[str, str] = {}
        self._intents: dict[str, SubIntent] = {}
        self._intent_evidence: dict[str, list[RetrievedChunk]] = {}
        self._uncertainty = ""

    # -- public API ------------------------------------------------------------
    async def handle_turn(self, turn: TurnInput) -> SynthesisResult:
        result = None
        async for item in self.stream_turn(turn):
            if isinstance(item, SynthesisResult):
                result = item
        assert result is not None
        return result

    async def stream_turn(self, turn: TurnInput) -> AsyncIterator[StreamEvent | SynthesisResult]:
        """Yields two-pass StreamEvents as sentences are generated/verified, then the result."""
        started = time.perf_counter()
        classification = self.delta.classifier.classify(
            turn.utterance,
            self.graph,
            session_constraints=self.session_constraints,
            controller_decisions=turn.controller_decisions,
            sub_intents=turn.sub_intents,
        )
        telemetry = _Telemetry(self.session_id, turn)
        telemetry.add(
            "classify",
            _ms(started),
            {"turn_type": classification.turn_type, "reason": classification.reason,
             "delta": dict(classification.delta.slots)},
        )

        if classification.turn_type == "PRESENTATION_ONLY":
            yield self._present(turn, classification, telemetry)
            return
        if classification.turn_type == "CONSTRAINT_REFINEMENT":
            path = self._refine(turn, classification, telemetry)
        else:
            path = self._new_intent(turn, classification, telemetry)
        async for item in path:
            yield item

    def destroy(self) -> None:
        """Session end (HC-4)."""
        self.graph.destroy()
        self.session_constraints.clear()
        self._intents.clear()
        self._intent_evidence.clear()
        self._uncertainty = ""

    # -- turn paths ------------------------------------------------------------
    async def _new_intent(self, turn: TurnInput, classification: TurnClassification, telemetry: _Telemetry):
        self.session_constraints = merge_constraints(
            self.session_constraints, self.delta.extractor.extract(turn.utterance)
        )
        evidence = {iid: list(chunks) for iid, chunks in turn.evidence.items()}
        for intent in turn.sub_intents:
            self._intents[intent.intent_id] = intent
            self._intent_evidence.setdefault(intent.intent_id, []).extend(evidence.get(intent.intent_id, []))

        verifier, streamer = self._verification(evidence)
        drafts = self.generator.generate(turn.sub_intents, evidence, constraints=self.session_constraints)
        started = time.perf_counter()
        events: list[StreamEvent] = []
        async for event in streamer.run(drafts):
            events.append(event)
            yield event
        telemetry.add_generation(self.generator.usage, verifier, streamer, _ms(started))

        with self.graph.revise() as revision:
            for result in streamer.committed_results():
                intent = self._intents.get(result.draft.intent_id or "")
                facet = intent.facet if intent else result.draft.facet
                revision.add(
                    facet=facet,
                    text=result.text,
                    citations=result.citations,
                    preconditions=self.delta.extractor.derive_preconditions(
                        result.text, facet, self.session_constraints
                    ),
                    confidence=result.draft.confidence,
                    intent_id=result.draft.intent_id,
                    supporting_chunk_ids=result.supporting_chunk_ids,
                )
        lineage = revision.lineage
        if lineage is not None:
            telemetry.add("answer_version", 0.0, lineage.to_dict())

        yield self._finish(
            turn,
            classification,
            telemetry,
            retrieval_events=list(turn.retrieval_events),
            sub_queries=[intent.query_nl for intent in turn.sub_intents],
            stream_events=events,
            streamer=streamer,
            lineage=lineage,
            refinement=None,
        )

    async def _refine(self, turn: TurnInput, classification: TurnClassification, telemetry: _Telemetry):
        started = time.perf_counter()
        merged = merge_constraints(self.session_constraints, classification.delta)
        plan = self.delta.plan(self.graph, classification.delta, pool=self._pool_chunks(), turn_id=turn.turn_id)

        # Pool-first: resolved targets reuse pooled evidence; the rest are dispatched
        # concurrently as targeted (affected facet x new constraint) queries only.
        evidence: dict[str, list[RetrievedChunk]] = {
            t.sub_intent.intent_id: list(t.pool_chunks) for t in plan.targets if t.resolved_from_pool
        }
        queries = plan.queries if self.retrieve_fn is not None else []
        fetched = await asyncio.gather(*(self._retrieve(q) for q in queries))
        retrieval_events = []
        for query, chunks in zip(queries, fetched):
            evidence[query.intent_id] = list(chunks)
            retrieval_events.append(
                {"timestamp_s": turn.t_s_end, "query": query.search_string, "trigger": "late_constraint"}
            )
        telemetry.add(
            "delta_plan",
            _ms(started),
            {"retained": plan.retained, "affected": plan.affected, "targets": len(plan.targets),
             "pool_resolved": sum(t.resolved_from_pool for t in plan.targets),
             "delta_queries": [q.search_string for q in queries]},
        )

        targeted = [t.sub_intent for t in plan.targets]
        for intent in targeted:
            self._intents[intent.intent_id] = intent
            self._intent_evidence.setdefault(intent.intent_id, []).extend(evidence.get(intent.intent_id, []))

        verifier, streamer = self._verification(evidence)
        drafts = self.generator.generate(
            targeted,
            evidence,
            constraints=merged,
            mode="refine",
            retained_claims=[self.graph.get(cid) for cid in plan.retained],
        )
        gen_started = time.perf_counter()
        events: list[StreamEvent] = []
        async for event in streamer.run(drafts):
            events.append(event)
            yield event
        telemetry.add_generation(self.generator.usage, verifier, streamer, _ms(gen_started))

        lineage, report = self.delta.apply(
            self.graph,
            plan,
            streamer.committed_results(),
            session_constraints=merged,
            delta_queries_issued=len(queries),
            latency_ms=_ms(started),
        )
        self.session_constraints = merged
        telemetry.add("refinement", report.latency_ms, report.to_event())
        if lineage is not None:
            telemetry.add("answer_version", 0.0, lineage.to_dict())

        yield self._finish(
            turn,
            classification,
            telemetry,
            retrieval_events=list(turn.retrieval_events) + retrieval_events,
            sub_queries=[q.query_nl for q in targeted],
            stream_events=events,
            streamer=streamer,
            lineage=lineage,
            refinement=report,
        )

    def _present(self, turn: TurnInput, classification: TurnClassification, telemetry: _Telemetry) -> SynthesisResult:
        """Presentation-only: claim list in, prose out. No retriever is reachable from here."""
        started = time.perf_counter()
        request = parse_presentation_request(turn.utterance, self.config)
        answer, citations = render_presentation(
            self.graph, request, prior_citations=self.graph.citations(), config=self.config
        )
        telemetry.add("render", _ms(started), {"style": request.style, "bullets": request.bullets,
                                                "retrieval_required": False})
        output = build_answer_output(
            session_id=self.session_id,
            turn_id=turn.turn_id,
            answer_version=self.graph.version,
            answer=answer,
            citations=citations,
            uncertainty=self._uncertainty,
            sub_queries=[],
            retrieval_events=[],
            config=self.config,
        )
        extensions = build_extensions(
            retrieval_required=False,
            suppression_reason=request.reason,
            controller_decisions=turn.controller_decisions,
            graph=self.graph,
            lineage=None,
            telemetry=telemetry.summary(),
        )
        return SynthesisResult(
            turn_type=classification.turn_type,
            classification=classification,
            output=output,
            extensions=extensions,
            stream_events=[],
            verification=[],
            coverage=[],
            lineage=None,
            refinement=None,
            usage=GenerationUsage(),
            telemetry=telemetry.events,
            fabricated_id_count=_fabricated(citations, self.graph.known_labels()),
        )

    # -- helpers ---------------------------------------------------------------
    def _verification(self, evidence: Mapping[str, Sequence[RetrievedChunk]]) -> tuple[ClaimVerifier, TwoPassStreamer]:
        """Allowlist = exactly the chunks in this turn's context (S-6 layer 1)."""
        chunks = [chunk for rows in evidence.values() for chunk in rows]
        self.graph.register_evidence(chunks)
        verifier = ClaimVerifier(CitationAllowlist.from_chunks(chunks), config=self.config, scorer=self.scorer)
        return verifier, TwoPassStreamer(verifier)

    def _finish(
        self,
        turn: TurnInput,
        classification: TurnClassification,
        telemetry: _Telemetry,
        *,
        retrieval_events: list[dict],
        sub_queries: list[str],
        stream_events: list[StreamEvent],
        streamer: TwoPassStreamer,
        lineage: VersionLineage | None,
        refinement: RefinementReport | None,
    ) -> SynthesisResult:
        active = self.graph.active()
        started = time.perf_counter()
        intents = list(self._intents.values())
        claim_intents = {
            claim.claim_id: self.graph.meta(claim.claim_id).intent_id
            for claim in active
            if self.graph.meta(claim.claim_id).intent_id
        }
        rows = self.coverage.build(intents, self._intent_evidence, active, claim_intents=claim_intents)
        uncertainty = " ".join(
            part for part in (self.coverage.uncertainty_text(rows), *self.coverage.clarifications(rows)) if part
        )
        self._uncertainty = uncertainty
        telemetry.add("coverage", _ms(started), self.coverage.to_telemetry(rows))

        citations = answer_citations(active)
        output = build_answer_output(
            session_id=self.session_id,
            turn_id=turn.turn_id,
            answer_version=self.graph.version,
            answer=render_claims(active, config=self.config),
            citations=citations,
            uncertainty=uncertainty,
            sub_queries=sub_queries,
            retrieval_events=retrieval_events,
            config=self.config,
        )
        extensions = build_extensions(
            retrieval_required=True,
            suppression_reason=None,
            controller_decisions=turn.controller_decisions,
            graph=self.graph,
            lineage=lineage,
            telemetry=telemetry.summary(),
        )
        # HC-3 alternate branch: ambiguous evidence asks instead of guessing. The frozen
        # AnswerOutput has no field for it, so it rides in `uncertainty` and is also exposed here.
        extensions["clarification_questions"] = self.coverage.clarifications(rows)
        return SynthesisResult(
            turn_type=classification.turn_type,
            classification=classification,
            output=output,
            extensions=extensions,
            stream_events=stream_events,
            verification=list(streamer.results),
            coverage=rows,
            lineage=lineage,
            refinement=refinement,
            usage=self.generator.usage,
            telemetry=telemetry.events,
            fabricated_id_count=_fabricated(citations, self.graph.known_labels()),
        )

    def _pool_chunks(self) -> list[RetrievedChunk]:
        """Session EvidencePool (Component 3) if wired, else everything this session has seen."""
        if self.pool is not None:
            return list(self.pool.chunks())
        return self.graph.evidence()

    async def _retrieve(self, query: SubIntent) -> Sequence[RetrievedChunk]:
        assert self.retrieve_fn is not None
        result = self.retrieve_fn(query)
        return await result if inspect.isawaitable(result) else result


class _Telemetry:
    """Builds frozen ``TelemetryEvent`` records for Matangi's bus (component = synthesis.*)."""

    def __init__(self, session_id: str, turn: TurnInput) -> None:
        self.session_id = session_id
        self.turn = turn
        self.events: list[TelemetryEvent] = []

    def add(self, stage: str, latency_ms: float, payload: dict[str, Any]) -> None:
        self.events.append(
            TelemetryEvent(
                event_id=f"{self.session_id}:{self.turn.turn_id}:{COMPONENT}:{len(self.events)}",
                session_id=self.session_id,
                turn_id=self.turn.turn_id,
                ts_stream_s=self.turn.t_s_end,
                component=f"{COMPONENT}.{stage}",
                latency_ms=latency_ms,
                payload=payload,
            )
        )

    def add_generation(self, usage: GenerationUsage, verifier: ClaimVerifier, streamer: TwoPassStreamer,
                       latency_ms: float) -> None:
        results = streamer.results
        self.add(
            "generation",
            latency_ms,
            {"llm_calls": usage.llm_calls, "prompt_tokens": usage.prompt_tokens,
             "completion_tokens": usage.completion_tokens, "backend": usage.backend,
             "sentences": len(results), "committed": sum(r.ok for r in results),
             "retracted": sum(not r.ok for r in results),
             "fabricated_ids_stripped": verifier.fabricated_ids_stripped},
        )

    def summary(self) -> dict[str, Any]:
        return {"latency_ms": {e.component: round(e.latency_ms, 3) for e in self.events}}


def _ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0


def _fabricated(citations: Iterable[str], allowed: frozenset[str]) -> int:
    return sum(1 for label in citations if label not in allowed)
