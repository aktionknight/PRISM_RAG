# Commit Context: bdbc634 — feat(synth): turn classifier + delta engine (D1 PM skeleton, D2 PM plan/apply)

## Metadata
- **Commit SHA**: `bdbc63405fdab8a7a54fe6df2292be8977982d28` (`bdbc634`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T11:27:16+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): turn classifier + delta engine (D1 PM skeleton, D2 PM plan/apply)

Roadmap 4.3 / 4.4, design S-4 — refinement is a ClaimGraph mutation, never a
regeneration.

- ConstraintExtractor: regex slot filling over config delta.slots (categorical
  values + numeric patterns). derive_preconditions() scopes a claim to its
  facet's constraint_slots: a categorical value in the claim's own text wins,
  else the session constraint; numeric slots never come from claim text
  ("holds up to 40 people" is not scoped to headcount=40).
- TurnClassifier: NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY.
  Presentation-only needs a presentation verb AND zero new content anchors
  (numerals, changed slot values, unseen proper nouns, keywords of facets the
  answer lacks, novel sub-intents) or the controller's NO_RETRIEVAL /
  presentation_restructure decision. A new slot the answer does not depend on
  needs a refinement cue.
- analyze_impact(): a claim is affected only if it is scoped to a delta slot
  with a different value; general claims are retained verbatim ("the standard
  reimbursement rule still applies").
- DeltaEngine.plan(): (affected facet x new constraint) targets, value-level
  facet overrides, templated targeted SubIntents, pool-first resolution over
  the EvidencePool (chunk must mention the new value and not already be cited).
  Additive targets (config delta.additive_targets, default on) also cover a new
  constraint no claim contradicts, so a V1 holding only the general rule still
  fetches the specific one; they dedupe onto conflict targets.
- DeltaEngine.apply(): ONE revision — add verified claims, supersede affected
  claims with superseded_by lineage, version++ — and the RefinementReport
  (answer_refined event, full_corpus_searches == 0, session_cleared == false).

Golden Example 2 reproduced: retained 3, superseded 1, added 2, 2 targeted
queries, 0 full-corpus searches. 23 tests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding

## File Changes
- **Added**: `src/slrag/synth/delta.py`
- **Added**: `tests/synth/test_delta.py`

## Diff Statistics
```text
src/slrag/synth/delta.py  | 430 ++++++++++++++++++++++++++++++++++++++++++++++
 tests/synth/test_delta.py | 329 +++++++++++++++++++++++++++++++++++
 2 files changed, 759 insertions(+)
```

## Description & Context
Roadmap 4.3 / 4.4, design S-4 — refinement is a ClaimGraph mutation, never a
regeneration.

- ConstraintExtractor: regex slot filling over config delta.slots (categorical
  values + numeric patterns). derive_preconditions() scopes a claim to its
  facet's constraint_slots: a categorical value in the claim's own text wins,
  else the session constraint; numeric slots never come from claim text
  ("holds up to 40 people" is not scoped to headcount=40).
- TurnClassifier: NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY.
  Presentation-only needs a presentation verb AND zero new content anchors
  (numerals, changed slot values, unseen proper nouns, keywords of facets the
  answer lacks, novel sub-intents) or the controller's NO_RETRIEVAL /
  presentation_restructure decision. A new slot the answer does not depend on
  needs a refinement cue.
- analyze_impact(): a claim is affected only if it is scoped to a delta slot
  with a different value; general claims are retained verbatim ("the standard
  reimbursement rule still applies").
- DeltaEngine.plan(): (affected facet x new constraint) targets, value-level
  facet overrides, templated targeted SubIntents, pool-first resolution over
  the EvidencePool (chunk must mention the new value and not already be cited).
  Additive targets (config delta.additive_targets, default on) also cover a new
  constraint no claim contradicts, so a V1 holding only the general rule still
  fetches the specific one; they dedupe onto conflict targets.
- DeltaEngine.apply(): ONE revision — add verified claims, supersede affected
  claims with superseded_by lineage, version++ — and the RefinementReport
  (answer_refined event, full_corpus_searches == 0, session_cleared == false).

Golden Example 2 reproduced: retained 3, superseded 1, added 2, 2 targeted
queries, 0 full-corpus searches. 23 tests.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
