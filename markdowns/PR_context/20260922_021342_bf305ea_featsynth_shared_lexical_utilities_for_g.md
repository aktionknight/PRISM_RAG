# Commit Context: bf305ea — feat(synth): shared lexical utilities for generator, verifier and delta engine

## Metadata
- **Commit SHA**: `bf305ea59a94d3b7906bc4de3df55595c6322ead` (`bf305ea`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T02:13:42+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): shared lexical utilities for generator, verifier and delta engine

One tokeniser (light stemming, numeral normalisation), sentence splitter, numeral and proper-noun extractors in synth/text.py so relevance, lexical entailment, copy check and pool-first resolution can never disagree on token identity. Stopwords move to a shared text: section of config/synth.yaml; YAML-1.1 boolean traps (on/no) quoted and guarded by a test.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Added**: `src/slrag/synth/text.py`
- **Added**: `tests/synth/test_text.py`

## Diff Statistics
```text
config/synth.yaml        | 16 +++++++----
 src/slrag/synth/text.py  | 74 ++++++++++++++++++++++++++++++++++++++++++++++++
 tests/synth/test_text.py | 55 +++++++++++++++++++++++++++++++++++
 3 files changed, 140 insertions(+), 5 deletions(-)
```

## Description & Context
One tokeniser (light stemming, numeral normalisation), sentence splitter, numeral and proper-noun extractors in synth/text.py so relevance, lexical entailment, copy check and pool-first resolution can never disagree on token identity. Stopwords move to a shared text: section of config/synth.yaml; YAML-1.1 boolean traps (on/no) quoted and guarded by a test.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
