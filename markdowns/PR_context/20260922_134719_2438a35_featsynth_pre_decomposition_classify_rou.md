# Commit Context: 2438a35 — feat(synth): pre-decomposition classify() routing hook for the harness (audit C-3, I-2)

## Metadata
- **Commit SHA**: `2438a35d22aa5a9c09f85b4db1f42964019440c8` (`2438a35`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T13:47:19+05:30`
- **Branch**: `refine-ground/day1-day2`

## Commit Message
```text
feat(synth): pre-decomposition classify() routing hook for the harness (audit C-3, I-2)

SynthesisEngine.classify(utterance, controller_decisions) runs the turn classifier before Components 2-3. TurnClassification.needs_upstream_retrieval is False for CONSTRAINT_REFINEMENT and PRESENTATION_ONLY, so the harness can skip the full decompose+retrieve pass and full_corpus_searches: 0 holds system-wide, not just inside Component 4. The harness passes the result back via TurnInput.classification and the engine uses it instead of re-classifying (telemetry classify.precomputed). A golden test replays Examples 1-3 in harness order through SessionStore.turn(): outputs are identical to the post-decomposition run, upstream runs only on NEW_INTENT turns, and Example 2's refinement turn issues only its 2 targeted queries.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/types.py`
- **Modified**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
src/slrag/synth/engine.py         | 40 ++++++++++++++++++++++++++++++---------
 src/slrag/synth/types.py          |  9 +++++++++
 tests/synth/test_engine_golden.py | 35 ++++++++++++++++++++++++++++++++++
 3 files changed, 75 insertions(+), 9 deletions(-)
```

## Description & Context
SynthesisEngine.classify(utterance, controller_decisions) runs the turn classifier before Components 2-3. TurnClassification.needs_upstream_retrieval is False for CONSTRAINT_REFINEMENT and PRESENTATION_ONLY, so the harness can skip the full decompose+retrieve pass and full_corpus_searches: 0 holds system-wide, not just inside Component 4. The harness passes the result back via TurnInput.classification and the engine uses it instead of re-classifying (telemetry classify.precomputed). A golden test replays Examples 1-3 in harness order through SessionStore.turn(): outputs are identical to the post-decomposition run, upstream runs only on NEW_INTENT turns, and Example 2's refinement turn issues only its 2 targeted queries.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
