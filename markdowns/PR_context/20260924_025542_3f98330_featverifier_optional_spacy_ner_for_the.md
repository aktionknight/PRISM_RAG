# Commit Context: 3f98330 — feat(verifier): optional spaCy NER for the copy check (audit W-6)

## Metadata
- **Commit SHA**: `3f98330afa39de30ff64b3ff7bc4ee5f9034dd40` (`3f98330`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:55:42+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(verifier): optional spaCy NER for the copy check (audit W-6)

verifier.entity_backend: regex | spacy. The regex proper-noun heuristic skips a lone sentence-initial word, so "Marriott holds up to 40 people." passed the copy check against a chunk about Venue A. SpacyEntityExtractor adds NER spans with verifier.spacy.labels (PERSON, ORG, GPE, ...) to the regex names and strips possessives ("Venue B's" names "Venue B"). The model loads from verifier.spacy.model_path, baked by `scripts/bake_nli_model.py --spacy` (make setup-nli; new [ner] extra) and never downloaded at runtime; a missing model raises with the fix. spaCy calls are serialised behind a lock because verification runs in worker threads. SynthesisEngine accepts a shared `entities` extractor, like `scorer`, so the model loads once per process, and the restyle copy check uses the same extractor.

Measured with en_core_web_sm: the 45 calibration pairs stay 45/45 correct with the cross-encoder plus spaCy entities (the possessive strip fixed the one false reject found while testing). It catches Marriott, Deloitte and Mumbai at sentence start, but misses "Pune offers ..." - NER is additive coverage, not a guarantee. Default stays regex (offline CI).

Also: test_cross_encoder_missing_model_raises_without_importing_dependency no longer depends on test order.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `Makefile`
- **Modified**: `config/synth.yaml`
- **Modified**: `pyproject.toml`
- **Modified**: `scripts/bake_nli_model.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/verifier.py`
- **Modified**: `tests/synth/test_nli_backend.py`
- **Modified**: `tests/synth/test_verifier.py`

## Diff Statistics
```text
Makefile                        |  4 +--
 config/synth.yaml               |  4 +++
 pyproject.toml                  |  2 ++
 scripts/bake_nli_model.py       | 22 +++++++++++++++
 src/slrag/synth/engine.py       | 16 +++++++++--
 src/slrag/synth/verifier.py     | 61 +++++++++++++++++++++++++++++++++++++----
 tests/synth/test_nli_backend.py | 14 ++++++++++
 tests/synth/test_verifier.py    | 32 +++++++++++++++++++--
 8 files changed, 142 insertions(+), 13 deletions(-)
```

## Description & Context
verifier.entity_backend: regex | spacy. The regex proper-noun heuristic skips a lone sentence-initial word, so "Marriott holds up to 40 people." passed the copy check against a chunk about Venue A. SpacyEntityExtractor adds NER spans with verifier.spacy.labels (PERSON, ORG, GPE, ...) to the regex names and strips possessives ("Venue B's" names "Venue B"). The model loads from verifier.spacy.model_path, baked by `scripts/bake_nli_model.py --spacy` (make setup-nli; new [ner] extra) and never downloaded at runtime; a missing model raises with the fix. spaCy calls are serialised behind a lock because verification runs in worker threads. SynthesisEngine accepts a shared `entities` extractor, like `scorer`, so the model loads once per process, and the restyle copy check uses the same extractor.

Measured with en_core_web_sm: the 45 calibration pairs stay 45/45 correct with the cross-encoder plus spaCy entities (the possessive strip fixed the one false reject found while testing). It catches Marriott, Deloitte and Mumbai at sentence start, but misses "Pune offers ..." - NER is additive coverage, not a guarantee. Default stays regex (offline CI).

Also: test_cross_encoder_missing_model_raises_without_importing_dependency no longer depends on test order.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
