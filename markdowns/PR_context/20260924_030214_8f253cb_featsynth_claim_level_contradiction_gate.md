# Commit Context: 8f253cb — feat(synth): claim-level contradiction gate with clarification branch (D3 edge case: contradiction)

## Metadata
- **Commit SHA**: `8f253cb69b539bafb0a30a654a39d5da0d8c493e` (`8f253cb`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T03:02:14+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(synth): claim-level contradiction gate with clarification branch (D3 edge case: contradiction)

Found while writing the contradiction edge case: two strong chunks that disagree (Doc_31 §4 "more than 14 days ... full refund" at 0.84, Doc_08 §1 "more than 7 days ..." at 0.82) each pass verification against their own chunk, so the answer asserted both and reported no uncertainty.

synth/conflicts.py ContradictionGate runs after verification and before the graph revision, on both the new-intent and refinement paths. Two committed sentences conflict when they cite different documents, share a frame (Jaccard >= conflicts.frame_overlap over non-numeral content tokens) and differ in numerals or negation polarity. If their evidence scores are within uncertainty.ambiguity_margin, both are retracted and the existing clarification template asks "Could you clarify whether you mean 14 days or 7 days?"; otherwise the claim from the higher-ranked chunk is kept. Retracted sentences are re-emitted as RETRACTED stream events with reason "contradiction". The UI must accept a RETRACTED after a COMMITTED for the same seq (interface note for the WS server). synthesis.conflicts telemetry records the pairs. uncertainty.differing_options is factored out of CoverageMatrix so both paths word the question identically.

This is the last line behind Component 3's S-9 contradiction gating, not a replacement for it. Goldens unchanged; 273 tests pass, NLI suite green.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Added**: `src/slrag/synth/conflicts.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/uncertainty.py`
- **Added**: `tests/synth/test_conflicts.py`

## Diff Statistics
```text
config/synth.yaml              |   8 ++++
 src/slrag/synth/conflicts.py   | 104 +++++++++++++++++++++++++++++++++++++++++
 src/slrag/synth/engine.py      |  47 ++++++++++++++++---
 src/slrag/synth/uncertainty.py |  48 ++++++++++---------
 tests/synth/test_conflicts.py  |  83 ++++++++++++++++++++++++++++++++
 5 files changed, 263 insertions(+), 27 deletions(-)
```

## Description & Context
Found while writing the contradiction edge case: two strong chunks that disagree (Doc_31 §4 "more than 14 days ... full refund" at 0.84, Doc_08 §1 "more than 7 days ..." at 0.82) each pass verification against their own chunk, so the answer asserted both and reported no uncertainty.

synth/conflicts.py ContradictionGate runs after verification and before the graph revision, on both the new-intent and refinement paths. Two committed sentences conflict when they cite different documents, share a frame (Jaccard >= conflicts.frame_overlap over non-numeral content tokens) and differ in numerals or negation polarity. If their evidence scores are within uncertainty.ambiguity_margin, both are retracted and the existing clarification template asks "Could you clarify whether you mean 14 days or 7 days?"; otherwise the claim from the higher-ranked chunk is kept. Retracted sentences are re-emitted as RETRACTED stream events with reason "contradiction". The UI must accept a RETRACTED after a COMMITTED for the same seq (interface note for the WS server). synthesis.conflicts telemetry records the pairs. uncertainty.differing_options is factored out of CoverageMatrix so both paths word the question identically.

This is the last line behind Component 3's S-9 contradiction gating, not a replacement for it. Goldens unchanged; 273 tests pass, NLI suite green.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
