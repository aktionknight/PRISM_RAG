# Commit Context: 56efbe2 — feat(synth): SynthesisEngine — wire delta engine -> ClaimGraph -> generator (D2 PM)

## Metadata
- **Commit SHA**: `56efbe24936dd6fd31be57012c6369755ddbfec5` (`56efbe2`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T11:34:34+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): SynthesisEngine — wire delta engine -> ClaimGraph -> generator (D2 PM)

The Component 4 entry point that replaces stubs.fake_synthesize behind
config/app.yaml use_stub_synthesis. One engine per session; all state lives on
the instance (HC-4) and destroy() ends it.

Per turn: classify ->
  NEW_INTENT            generate -> two-pass verify -> one ClaimGraph revision
  CONSTRAINT_REFINEMENT delta plan -> pool-first / concurrent targeted queries
                        (late_constraint retrieval_events) -> generate(refine)
                        -> verify -> delta apply (supersede + add, version++)
  PRESENTATION_ONLY     re-render active claims; no retriever reachable
-> coverage matrix -> uncertainty (+ clarification questions) -> frozen
AnswerOutput + additive extensions (claims, version_lineage,
controller_decisions, retrieval_required, suppression_reason, telemetry).

stream_turn() yields provisional/committed/retracted StreamEvents live for the
WS answer_token channel, then the SynthesisResult; per-stage frozen
TelemetryEvent records (synthesis.classify / generation / delta_plan /
refinement / answer_version / coverage / render) are ready for Matangi's bus.

Golden replay (tests/synth/test_engine_golden.py) reproduces the brief:
- Example 1: 3 sub_queries, 3 retrieval_events, citations
  [Doc_12 §2, Doc_31 §4, Doc_09 §1], uncertainty "Catering accommodation
  policies for Venue A could not be verified from the retrieved corpus."
- Example 2: V1 -> V2, retained 3 / superseded 1 / added 2, 2 targeted
  late_constraint queries, full_corpus_searches 0, session_cleared false,
  retained claims byte-identical.
- Example 3: 0 retrieval events (a retriever that raises is never called),
  2 bullets, citations ⊆ prior, answer_version unchanged, 0 LLM calls.
- LLM backend: exactly 1 call/turn, fabricated Doc_77 never reaches output,
  fabricated_id_count == 0 on every scenario.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `src/slrag/synth/__init__.py`
- **Added**: `src/slrag/synth/engine.py`
- **Added**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
src/slrag/synth/__init__.py       |  26 +++
 src/slrag/synth/engine.py         | 460 ++++++++++++++++++++++++++++++++++++++
 tests/synth/test_engine_golden.py | 204 +++++++++++++++++
 3 files changed, 690 insertions(+)
```

## Description & Context
The Component 4 entry point that replaces stubs.fake_synthesize behind
config/app.yaml use_stub_synthesis. One engine per session; all state lives on
the instance (HC-4) and destroy() ends it.

Per turn: classify ->
  NEW_INTENT            generate -> two-pass verify -> one ClaimGraph revision
  CONSTRAINT_REFINEMENT delta plan -> pool-first / concurrent targeted queries
                        (late_constraint retrieval_events) -> generate(refine)
                        -> verify -> delta apply (supersede + add, version++)
  PRESENTATION_ONLY     re-render active claims; no retriever reachable
-> coverage matrix -> uncertainty (+ clarification questions) -> frozen
AnswerOutput + additive extensions (claims, version_lineage,
controller_decisions, retrieval_required, suppression_reason, telemetry).

stream_turn() yields provisional/committed/retracted StreamEvents live for the
WS answer_token channel, then the SynthesisResult; per-stage frozen
TelemetryEvent records (synthesis.classify / generation / delta_plan /
refinement / answer_version / coverage / render) are ready for Matangi's bus.

Golden replay (tests/synth/test_engine_golden.py) reproduces the brief:
- Example 1: 3 sub_queries, 3 retrieval_events, citations
  [Doc_12 §2, Doc_31 §4, Doc_09 §1], uncertainty "Catering accommodation
  policies for Venue A could not be verified from the retrieved corpus."
- Example 2: V1 -> V2, retained 3 / superseded 1 / added 2, 2 targeted
  late_constraint queries, full_corpus_searches 0, session_cleared false,
  retained claims byte-identical.
- Example 3: 0 retrieval events (a retriever that raises is never called),
  2 bullets, citations ⊆ prior, answer_version unchanged, 0 LLM calls.
- LLM backend: exactly 1 call/turn, fabricated Doc_77 never reaches output,
  fabricated_id_count == 0 on every scenario.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
