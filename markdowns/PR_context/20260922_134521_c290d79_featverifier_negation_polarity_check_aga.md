# Commit Context: c290d79 — feat(verifier): negation-polarity check against the entailing clause (audit W-4)

## Metadata
- **Commit SHA**: `c290d796ad09c53eba9745183ba8797e31aff69c` (`c290d79`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T13:45:21+05:30`
- **Branch**: `refine-ground/day1-day2`

## Commit Message
```text
feat(verifier): negation-polarity check against the entailing clause (audit W-4)

The lexical entailment scorer drops not/no as stopwords, so 'card statements alone are accepted' scored 1.0 against a chunk saying they are NOT accepted and committed. Each clause of a sentence is now aligned to the premise clause covering most of its content tokens, and the two must agree on negation parity (verifier.negation_cues + n't). Failures are retracted with reason negation_mismatch; re-attribution applies the same check. Config-gated by verifier.polarity_check (default on). No LLM calls, no new dependencies.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/synth/text.py`
- **Modified**: `src/slrag/synth/verifier.py`
- **Modified**: `tests/synth/test_verifier.py`

## Diff Statistics
```text
config/synth.yaml            |  2 ++
 src/slrag/synth/text.py      |  6 ++++
 src/slrag/synth/verifier.py  | 66 ++++++++++++++++++++++++++++++++++++++++----
 tests/synth/test_verifier.py | 47 +++++++++++++++++++++++++++++++
 4 files changed, 115 insertions(+), 6 deletions(-)
```

## Description & Context
The lexical entailment scorer drops not/no as stopwords, so 'card statements alone are accepted' scored 1.0 against a chunk saying they are NOT accepted and committed. Each clause of a sentence is now aligned to the premise clause covering most of its content tokens, and the two must agree on negation parity (verifier.negation_cues + n't). Failures are retracted with reason negation_mismatch; re-attribution applies the same check. Config-gated by verifier.polarity_check (default on). No LLM calls, no new dependencies.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
