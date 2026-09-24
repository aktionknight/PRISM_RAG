# Commit Context: cc4f47a — feat(delta): corpus-independent constraints from a dependency parse; no example-tuned config

## Metadata
- **Commit SHA**: `cc4f47aa4c3343812bc7065aa271d78c2c1ce42e` (`cc4f47a`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T10:22:09+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(delta): corpus-independent constraints from a dependency parse; no example-tuned config

Component 4 no longer carries rules fitted to the brief's three examples.

Removed:
- delta.slots (trip_type, booking_timing, headcount, and a city list with Pune/Mumbai/...);
- the two hand-written delta queries worded after Example 2;
- the "the trip was" refinement cue;
- facets.yaml constraint_slots, and every use of facet keywords (classifier, pool-first resolution, extractive relevance);
- the venue-noun entity pattern;
- "venue" in the LLM synthesis prompt.

synth/constraints.py reads constraints off spaCy's dependency parse, keyed by WordNet lemmas, for any corpus:
- noun modifiers: "domestic trips" -> trip=domestic; "the laptop is refurbished" -> laptop=refurbished;
- number + unit: "40 people" -> count:person=40. Nouns with the WordNet supersense noun.person (attendees, guests, delegates) share one class;
- verb + preposition: "booked after travel" -> book=after travel;
- the user's role: "I'm a staff member" -> role=staff member;
- places: NER GPE/LOC, plus a proper noun after in/at/near when NER misses it.

A claim's preconditions are its own grammatical scope; counts are inherited from the session only when the claim mentions that unit. A constraint is a delta only if the answer depends on it: a session value, a claim scope, or a claim mentioning the constrained noun or a WordNet-related one (trip -> journey -> travel). Phrases made of presentation words, and counts that just point at a number already in the answer, are not constraints. Targeted queries use the generic template over the user's own phrase ("international trip Travel reimbursement").

Evidence:
- New held-out suite tests/synth/test_heldout.py on a library/IT corpus with facets absent from facets.yaml: new intent, role change, count change with nothing found, presentation, contradiction, adjective change, follow-up. It was written before the refactor and failed 5/8 on the old code (every refinement); it now passes 7/7.
- Two guard tests assert no held-out-domain word and no brief-domain word appears in Component 4 config or prompts.
- Examples 1-3 and the edge case still reproduce (Example 2: 3 retained, 1 superseded, 2 added, 2 targeted queries, 0 full-corpus searches). G4/G5 gates pass; NLI suite green; 285 tests pass.

Cost: every claim is now parsed, so Component 4 latency p50 rises to 29 ms (NEW_INTENT) and 12 ms (refinement), from about 3 ms; still inside the 300 ms first-token budget.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `bench/ablate_refinement.py`
- **Modified**: `config/facets.yaml`
- **Modified**: `config/prompts/synthesize.jinja`
- **Modified**: `config/synth.yaml`
- **Added**: `src/slrag/synth/constraints.py`
- **Modified**: `src/slrag/synth/delta.py`
- **Modified**: `src/slrag/synth/generator.py`
- **Modified**: `src/slrag/synth/lexicon.py`
- **Modified**: `src/slrag/synth/types.py`
- **Modified**: `tests/fixtures/golden_scenarios.json`
- **Added**: `tests/fixtures/heldout/chunks.jsonl`
- **Added**: `tests/fixtures/heldout/scenarios.json`
- **Modified**: `tests/synth/test_delta.py`
- **Modified**: `tests/synth/test_engine_golden.py`
- **Added**: `tests/synth/test_heldout.py`

## Diff Statistics
```text
bench/ablate_refinement.py            |   3 +-
 config/facets.yaml                    |  10 --
 config/prompts/synthesize.jinja       |   2 +-
 config/synth.yaml                     |  47 ++------
 src/slrag/synth/constraints.py        | 214 ++++++++++++++++++++++++++++++++++
 src/slrag/synth/delta.py              | 209 +++++++++++----------------------
 src/slrag/synth/generator.py          |   4 +-
 src/slrag/synth/lexicon.py            |  19 +++
 src/slrag/synth/types.py              |   3 +-
 tests/fixtures/golden_scenarios.json  |  13 ++-
 tests/fixtures/heldout/chunks.jsonl   |  10 ++
 tests/fixtures/heldout/scenarios.json | 173 +++++++++++++++++++++++++++
 tests/synth/test_delta.py             |  94 ++++++++-------
 tests/synth/test_engine_golden.py     |   8 +-
 tests/synth/test_heldout.py           | 135 +++++++++++++++++++++
 15 files changed, 693 insertions(+), 251 deletions(-)
```

## Description & Context
Component 4 no longer carries rules fitted to the brief's three examples.

Removed:
- delta.slots (trip_type, booking_timing, headcount, and a city list with Pune/Mumbai/...);
- the two hand-written delta queries worded after Example 2;
- the "the trip was" refinement cue;
- facets.yaml constraint_slots, and every use of facet keywords (classifier, pool-first resolution, extractive relevance);
- the venue-noun entity pattern;
- "venue" in the LLM synthesis prompt.

synth/constraints.py reads constraints off spaCy's dependency parse, keyed by WordNet lemmas, for any corpus:
- noun modifiers: "domestic trips" -> trip=domestic; "the laptop is refurbished" -> laptop=refurbished;
- number + unit: "40 people" -> count:person=40. Nouns with the WordNet supersense noun.person (attendees, guests, delegates) share one class;
- verb + preposition: "booked after travel" -> book=after travel;
- the user's role: "I'm a staff member" -> role=staff member;
- places: NER GPE/LOC, plus a proper noun after in/at/near when NER misses it.

A claim's preconditions are its own grammatical scope; counts are inherited from the session only when the claim mentions that unit. A constraint is a delta only if the answer depends on it: a session value, a claim scope, or a claim mentioning the constrained noun or a WordNet-related one (trip -> journey -> travel). Phrases made of presentation words, and counts that just point at a number already in the answer, are not constraints. Targeted queries use the generic template over the user's own phrase ("international trip Travel reimbursement").

Evidence:
- New held-out suite tests/synth/test_heldout.py on a library/IT corpus with facets absent from facets.yaml: new intent, role change, count change with nothing found, presentation, contradiction, adjective change, follow-up. It was written before the refactor and failed 5/8 on the old code (every refinement); it now passes 7/7.
- Two guard tests assert no held-out-domain word and no brief-domain word appears in Component 4 config or prompts.
- Examples 1-3 and the edge case still reproduce (Example 2: 3 retained, 1 superseded, 2 added, 2 targeted queries, 0 full-corpus searches). G4/G5 gates pass; NLI suite green; 285 tests pass.

Cost: every claim is now parsed, so Component 4 latency p50 rises to 29 ms (NEW_INTENT) and 12 ms (refinement), from about 3 ms; still inside the 300 ms first-token budget.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
