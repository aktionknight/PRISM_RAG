# Commit Context: b94b655 — feat(delta): mixed refinement turns and safe self-correction (audit W-8)

## Metadata
- **Commit SHA**: `b94b655efcafd8b910e4fb3f95017b3f76d0300a` (`b94b655`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:51:54+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(delta): mixed refinement turns and safe self-correction (audit W-8)

Mixed turns: a CONSTRAINT_REFINEMENT that also asks something the answer does not cover ("Make it 40 people, and is AV equipment included?") is flagged TurnClassification.mixed, and needs_upstream_retrieval is true for it. Before decomposition, the flag comes from a question clause (delta.question_cues, split at delta.question_clause_splitters) carrying a content word that is not in the active claims, not in a constraint phrase and not a follow-up word like "change" or "apply" (delta.follow_up_neutral). After decomposition, a novel sub-intent on an unanswered facet sets it. _refine answers the upstream's novel sub-intents with their evidence in the same single generator call as the delta targets (HC-5). RefinementReport.new_intents counts them; full_corpus_searches stays 0 because the prior answer is never re-derived. Pure refinements ("Actually make it 40 people.", "does that change anything?") are unchanged, and Examples 1-3 reproduce byte for byte.

Self-correction fix found while building the edge case: a delta query that returned nothing used to supersede every affected claim. Catering claims that had only inherited headcount=30 from the session vanished on "make it 40". DeltaEngine.apply now keeps an affected claim when its targets produced nothing and its own text never states the old value (content_scoped), controlled by delta.keep_unreplaced_session_scoped; RefinementReport.affected_kept counts these. The engine also retires V1 intents a delta target has replaced, and targets that changed nothing, so coverage no longer reports a replaced intent as "could not be verified".

New golden scenario edge_self_correction_mixed (Example 1 + "Make it 40 people, and is AV equipment included?") runs through every parametrised golden test, the harness-order routing test (the mixed turn goes upstream) and the bench G4/G5 gates. 260 tests pass; the opt-in NLI tests pass too.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/synth/delta.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/types.py`
- **Modified**: `tests/bench/test_metrics.py`
- **Added**: `tests/fixtures/golden_edge_self_correction_mixed.jsonl`
- **Modified**: `tests/fixtures/golden_scenarios.json`
- **Modified**: `tests/synth/test_delta.py`
- **Modified**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
config/synth.yaml                                  |  6 ++
 src/slrag/synth/delta.py                           | 67 +++++++++++++++++++--
 src/slrag/synth/engine.py                          | 27 ++++++++-
 src/slrag/synth/types.py                           | 13 ++++-
 tests/bench/test_metrics.py                        |  5 +-
 .../golden_edge_self_correction_mixed.jsonl        |  6 ++
 tests/fixtures/golden_scenarios.json               | 43 ++++++++++++++
 tests/synth/test_delta.py                          | 68 ++++++++++++++++++++++
 tests/synth/test_engine_golden.py                  | 27 ++++++++-
 9 files changed, 251 insertions(+), 11 deletions(-)
```

## Description & Context
Mixed turns: a CONSTRAINT_REFINEMENT that also asks something the answer does not cover ("Make it 40 people, and is AV equipment included?") is flagged TurnClassification.mixed, and needs_upstream_retrieval is true for it. Before decomposition, the flag comes from a question clause (delta.question_cues, split at delta.question_clause_splitters) carrying a content word that is not in the active claims, not in a constraint phrase and not a follow-up word like "change" or "apply" (delta.follow_up_neutral). After decomposition, a novel sub-intent on an unanswered facet sets it. _refine answers the upstream's novel sub-intents with their evidence in the same single generator call as the delta targets (HC-5). RefinementReport.new_intents counts them; full_corpus_searches stays 0 because the prior answer is never re-derived. Pure refinements ("Actually make it 40 people.", "does that change anything?") are unchanged, and Examples 1-3 reproduce byte for byte.

Self-correction fix found while building the edge case: a delta query that returned nothing used to supersede every affected claim. Catering claims that had only inherited headcount=30 from the session vanished on "make it 40". DeltaEngine.apply now keeps an affected claim when its targets produced nothing and its own text never states the old value (content_scoped), controlled by delta.keep_unreplaced_session_scoped; RefinementReport.affected_kept counts these. The engine also retires V1 intents a delta target has replaced, and targets that changed nothing, so coverage no longer reports a replaced intent as "could not be verified".

New golden scenario edge_self_correction_mixed (Example 1 + "Make it 40 people, and is AV equipment included?") runs through every parametrised golden test, the harness-order routing test (the mixed turn goes upstream) and the bench G4/G5 gates. 260 tests pass; the opt-in NLI tests pass too.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
