# Commit Context: 593f639 — feat(synth): coverage-matrix uncertainty + claim renderer / presentation path (D2 mid)

## Metadata
- **Commit SHA**: `593f6398275d5201e25ec69afb8b8099ca206bfb` (`593f639`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T11:27:31+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): coverage-matrix uncertainty + claim renderer / presentation path (D2 mid)

Roadmap 4.9 (S-10) and 4.5, plus the final projection of the ClaimGraph into
the frozen AnswerOutput (Rule 3: the answer string is rendered last).

- uncertainty.py — CoverageMatrix: one row per sub-intent with best rerank
  score and committed claims -> covered | partial | ambiguous | uncovered.
  Entity x facet gaps name the missing anchor entity; bimodal evidence from two
  documents within ambiguity_margin yields a targeted clarification question
  (HC-3 alternate branch) whose options are the differing phrase ("14 days" vs
  "7 days"). An uncovered sub-intent is never silently dropped. Golden
  Example 1 reproduces the brief's sentence exactly: "Catering accommodation
  policies for Venue A could not be verified from the retrieved corpus."
- renderer.py — prose / bullets(N) / numbered / short renderings of active
  claims with [Doc §Sec] markers; parse_presentation_request(); the
  presentation-only path renders graph.active() only and hard-asserts
  citations(new) ⊆ citations(prior) (PresentationInvariantError). An ast test
  proves no retrieval/decompose/controller/pool module is reachable from it.
  build_answer_output() validates the retrieval_events trigger enum;
  build_extensions() / render_output_json() carry the additive §6 fields
  (claims, version_lineage, controller_decisions, ...) without widening the
  frozen schema.
- config/synth.yaml: presentation.styles, renderer.triggers,
  uncertainty.clarification_max_words, delta.additive_targets.

33 tests (13 uncertainty, 20 renderer).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Added**: `src/slrag/synth/renderer.py`
- **Added**: `src/slrag/synth/uncertainty.py`
- **Added**: `tests/synth/test_renderer.py`
- **Added**: `tests/synth/test_uncertainty.py`

## Diff Statistics
```text
config/synth.yaml               |   7 +
 src/slrag/synth/renderer.py     | 310 ++++++++++++++++++++++++++++++++++++++++
 src/slrag/synth/uncertainty.py  | 221 ++++++++++++++++++++++++++++
 tests/synth/test_renderer.py    | 221 ++++++++++++++++++++++++++++
 tests/synth/test_uncertainty.py | 144 +++++++++++++++++++
 5 files changed, 903 insertions(+)
```

## Description & Context
Roadmap 4.9 (S-10) and 4.5, plus the final projection of the ClaimGraph into
the frozen AnswerOutput (Rule 3: the answer string is rendered last).

- uncertainty.py — CoverageMatrix: one row per sub-intent with best rerank
  score and committed claims -> covered | partial | ambiguous | uncovered.
  Entity x facet gaps name the missing anchor entity; bimodal evidence from two
  documents within ambiguity_margin yields a targeted clarification question
  (HC-3 alternate branch) whose options are the differing phrase ("14 days" vs
  "7 days"). An uncovered sub-intent is never silently dropped. Golden
  Example 1 reproduces the brief's sentence exactly: "Catering accommodation
  policies for Venue A could not be verified from the retrieved corpus."
- renderer.py — prose / bullets(N) / numbered / short renderings of active
  claims with [Doc §Sec] markers; parse_presentation_request(); the
  presentation-only path renders graph.active() only and hard-asserts
  citations(new) ⊆ citations(prior) (PresentationInvariantError). An ast test
  proves no retrieval/decompose/controller/pool module is reachable from it.
  build_answer_output() validates the retrieval_events trigger enum;
  build_extensions() / render_output_json() carry the additive §6 fields
  (claims, version_lineage, controller_decisions, ...) without widening the
  frozen schema.
- config/synth.yaml: presentation.styles, renderer.triggers,
  uncertainty.clarification_max_words, delta.additive_targets.

33 tests (13 uncertainty, 20 renderer).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
