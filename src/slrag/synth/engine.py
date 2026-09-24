"""SynthesisEngine — Component 4 entry point (roadmap §1 topology stage [4]).

Replaces ``stubs.fake_synthesize`` behind ``config/app.yaml: use_stub_synthesis``.
One engine per session, held in ``core.session.SessionStore``; all state (ClaimGraph,
constraints, intents) lives on the instance and dies with it (HC-4). The harness
routes each turn with ``classify()`` before decomposition. Per turn:

    classify ─┬─ NEW_INTENT            → generate → two-pass verify → graph revision
              ├─ CONSTRAINT_REFINEMENT → delta plan → pool-first / targeted queries
              │                          → generate(refine) → verify → delta apply
              └─ PRESENTATION_ONLY     → re-render active claims (no retrieval path);
                                         translation/tone: one verified LLM restyle
    → coverage matrix → uncertainty → AnswerOutput (+ additive extensions)

LLM budget (HC-5): at most one generator call per turn from this component; the
classifier, delta engine, verifier, coverage matrix and renderer are deterministic.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field, replace
from typing import Any, AsyncIterator, Iterable, Mapping, Sequence

from slrag.core.schemas import (
    AnswerOutput,
    Claim,
    ControllerDecision,
    RetrievedChunk,
    SubIntent,
    TelemetryEvent,
)
from slrag.synth.claims import ClaimGraph
from slrag.synth.conflicts import ContradictionGate, retracted
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
from slrag.synth.verifier import (
    CitationAllowlist,
    ClaimVerifier,
    TwoPassStreamer,
    copy_check,
    make_entity_extractor,
    make_scorer,
)

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
    # From SynthesisEngine.classify() at utterance end; None -> classified here.
    classification: TurnClassification | None = None


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
        entities: Any | None = None,
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
        self.entities = entities if entities is not None else make_entity_extractor(self.config)
        presentation = self.config.get("presentation", {}) or {}
        self._restyle_reasons = frozenset(map(str, presentation.get("llm_restyle_reasons", ()) or ()))
        self.session_constraints: dict[str, str] = {}
        self._intents: dict[str, SubIntent] = {}
        self._intent_evidence: dict[str, list[RetrievedChunk]] = {}
        self._uncertainty = ""
        self._epoch = 0          # turns started on this session; stamps classifications (audit N-3)
        self.conflicts = ContradictionGate(self.config)
        self._turn_questions: list[str] = []

    # -- public API ------------------------------------------------------------
    def classify(
        self,
        utterance: str,
        controller_decisions: Sequence[ControllerDecision] = (),
        sub_intents: Sequence[SubIntent] = (),
    ) -> TurnClassification:
        """Route a turn before decomposition runs (audit C-3).

        Call at ``utterance_end``. When ``needs_upstream_retrieval`` is False the
        harness skips Components 2-3 and hands the classification back in
        ``TurnInput.classification``, so a refinement turn never triggers a full
        corpus search upstream. Run classify and ``handle_turn`` inside the same
        ``SessionStore.turn()`` so no other turn changes the session in between; if
        one does anyway, ``handle_turn`` detects the stale classification and
        re-classifies against the current session.
        """
        classification = self.delta.classifier.classify(
            utterance,
            self.graph,
            session_constraints=self.session_constraints,
            controller_decisions=controller_decisions,
            sub_intents=sub_intents,
        )
        return replace(classification, session_epoch=self._epoch)

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
        precomputed = turn.classification is not None
        stale = precomputed and turn.classification.session_epoch not in (None, self._epoch)
        classification = (
            turn.classification
            if precomputed and not stale
            else self.classify(turn.utterance, turn.controller_decisions, turn.sub_intents)
        )
        self._epoch += 1
        telemetry = _Telemetry(self.session_id, turn)
        telemetry.add(
            "classify",
            _ms(started),
            {"turn_type": classification.turn_type, "reason": classification.reason,
             "delta": dict(classification.delta.slots), "precomputed": precomputed, "stale": stale},
        )

        if classification.turn_type == "PRESENTATION_ONLY":
            yield await self._present(turn, classification, telemetry)
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
        committed = []
        async for event in self._gate_conflicts(streamer, evidence, telemetry, committed):
            events.append(event)
            yield event

        with self.graph.revise() as revision:
            for result in committed:
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

        # Mixed turn (W-8): the upstream pass ran for the new question only; its novel
        # sub-intents are answered in the same single generator call as the delta.
        new_intents = [s for s in turn.sub_intents if s.novel] if classification.mixed else []
        for intent in new_intents:
            evidence[intent.intent_id] = list(turn.evidence.get(intent.intent_id, ()))
        targeted = [t.sub_intent for t in plan.targets] + new_intents
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
        committed = []
        async for event in self._gate_conflicts(streamer, evidence, telemetry, committed):
            events.append(event)
            yield event

        lineage, report = self.delta.apply(
            self.graph,
            plan,
            committed,
            session_constraints=merged,
            delta_queries_issued=len(queries),
            latency_ms=_ms(started),
        )
        report.new_intents = len(new_intents)
        self._retire_replaced_intents(plan, targeted)
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

    async def _present(
        self, turn: TurnInput, classification: TurnClassification, telemetry: _Telemetry
    ) -> SynthesisResult:
        """Presentation-only: claim list in, prose out. No retriever is reachable from here."""
        started = time.perf_counter()
        request = parse_presentation_request(turn.utterance, self.config)
        restyled, restyle, usage = None, None, GenerationUsage()
        if request.reason in self._restyle_reasons:
            if callable(getattr(self.generator, "restyle", None)):
                restyled, restyle = await self._restyle(turn.utterance)
                usage = self.generator.usage
            else:
                restyle = "fallback:no_llm_backend"
        answer, citations = render_presentation(
            self.graph, request, prior_citations=self.graph.citations(), config=self.config, claims=restyled
        )
        telemetry.add("render", _ms(started), {"style": request.style, "bullets": request.bullets,
                                                "retrieval_required": False, "restyle": restyle,
                                                "llm_calls": usage.llm_calls})
        output = build_answer_output(
            session_id=self.session_id,
            turn_id=turn.turn_id,
            answer_version=self.graph.version,
            answer=answer,
            citations=citations,
            uncertainty=self._uncertainty,
            sub_queries=[],
            retrieval_events=[],
            retrieval_required=False,
            suppression_reason=request.reason,
            controller_decisions=turn.controller_decisions,
            graph=self.graph,
            lineage=None,
            telemetry=telemetry.summary(),
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
        # Audit N-4 / I-11: a translation or tone request answered with the unchanged
        # prose render says so, instead of silently showing the original wording.
        extensions["restyle_fallback"] = restyle.split(":", 1)[1] if restyle and restyle.startswith("fallback:") else None
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
            usage=usage,
            telemetry=telemetry.events,
            fabricated_id_count=_fabricated(citations, self.graph.known_labels()),
        )

    async def _restyle(self, instruction: str) -> tuple[list[Claim] | None, str]:
        """One LLM call (HC-5) rewriting the active claims for a translation/tone turn.

        All-or-nothing: every sentence must cite only the prior answer's labels and
        copy its numbers and names from the claims it restates, and together the
        sentences must still cite every prior label. Anything less returns None and
        the caller re-renders deterministically, so a restyle can never drop or
        invent content. Returns (claims or None, outcome for telemetry).
        """
        active = self.graph.active()
        prior = answer_citations(active)
        drafts = [draft async for draft in self.generator.restyle(active, instruction)]
        if not drafts:
            return None, "fallback:no_output"
        allowlist = CitationAllowlist.from_chunks(
            chunk for label in prior for chunk in self.graph.chunks_for_label(label)
        )
        restyled: list[Claim] = []
        for draft in drafts:
            text, in_text, in_text_fabricated = allowlist.strip_markers(draft.text)
            kept, fabricated = allowlist.filter((*draft.citations, *in_text, *in_text_fabricated))
            if fabricated or not kept or not text:
                return None, "fallback:citation_outside_prior"
            sources = [claim.text for claim in active if set(claim.citations) & set(kept)]
            if copy_check(text, sources, self.entities):
                return None, "fallback:copy_check_failed"
            restyled.append(
                Claim(claim_id=f"r{len(restyled) + 1}", facet=draft.facet, text=text, citations=list(kept),
                      preconditions={}, status="active", introduced_in_version=self.graph.version)
            )
        if set(prior) - {label for claim in restyled for label in claim.citations}:
            return None, "fallback:content_dropped"
        return restyled, "llm"

    # -- helpers ---------------------------------------------------------------
    async def _gate_conflicts(self, streamer: TwoPassStreamer, evidence: Mapping[str, Sequence[RetrievedChunk]],
                              telemetry: _Telemetry, committed: list[VerificationResult]):
        """Contradiction gate over this turn's committed sentences; yields RETRACTED events
        for the sentences it removes and fills ``committed`` with the survivors."""
        scores: dict[str, float] = {}
        for rows in evidence.values():
            for chunk in rows:
                scores[chunk.chunk_id] = max(scores.get(chunk.chunk_id, 0.0), chunk.score)
        kept, conflicts = self.conflicts.resolve(streamer.committed_results(), scores)
        committed.extend(kept)
        self._turn_questions = [c.question for c in conflicts if c.question]
        if conflicts:
            telemetry.add("conflicts", 0.0, {
                "pairs": len(conflicts),
                "retracted": [r.text for c in conflicts for r in c.dropped],
                "kept": [c.kept.text for c in conflicts if c.kept is not None],
                "clarifications": self._turn_questions,
            })
        for conflict in conflicts:
            for result in conflict.dropped:
                result = retracted(result)
                yield StreamEvent(kind="retracted", seq=result.draft.seq, text=result.text,
                                  citations=result.citations, facet=result.draft.facet,
                                  intent_id=result.draft.intent_id, verification=result)

    def _verification(self, evidence: Mapping[str, Sequence[RetrievedChunk]]) -> tuple[ClaimVerifier, TwoPassStreamer]:
        """Allowlist = exactly the chunks in this turn's context (S-6 layer 1)."""
        chunks = [chunk for rows in evidence.values() for chunk in rows]
        self.graph.register_evidence(chunks)
        verifier = ClaimVerifier(CitationAllowlist.from_chunks(chunks), config=self.config, scorer=self.scorer,
                                 entities=self.entities)
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
        questions = list(dict.fromkeys([*self.coverage.clarifications(rows), *self._turn_questions]))
        uncertainty = " ".join(part for part in (self.coverage.uncertainty_text(rows), *questions) if part)
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
        extensions["clarification_questions"] = questions
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

    def _retire_replaced_intents(self, plan: Any, targeted: Sequence[SubIntent]) -> None:
        """A delta target succeeds earlier intents on its facet that no longer back any
        active claim, so coverage reports the target's outcome instead of flagging the
        superseded V1 intent as unverified."""
        active = {c.claim_id for c in self.graph.active()}
        backing = {self.graph.meta(claim_id).intent_id for claim_id in active}
        # A target that found nothing while every claim it affected was kept changed nothing;
        # its facet is still answered, so it must not add an "unverified" line either.
        idle = {t.sub_intent.intent_id for t in plan.targets
                if t.affected_claim_ids and t.sub_intent.intent_id not in backing
                and set(t.affected_claim_ids) <= active}
        current = {intent.intent_id for intent in targeted} - idle
        facets = {t.facet for t in plan.targets}
        for intent_id, intent in list(self._intents.items()):
            if intent_id in idle or (intent.facet in facets and intent_id not in current and intent_id not in backing):
                del self._intents[intent_id]
                self._intent_evidence.pop(intent_id, None)

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
             "first_draft_ms": usage.first_draft_ms,
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
