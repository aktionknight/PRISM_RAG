# Commit Context: 60f3194 — Configure all DL and LLM models to execute on CUDA GPU

## Metadata
- **Commit SHA**: `60f31944785c565a07e6aeedf1807a13e4239dc4` (`60f3194`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T14:34:30+05:30`
- **Branch**: `master`

## Commit Message
```text
Configure all DL and LLM models to execute on CUDA GPU


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 3: Corpus Retrieval & Fusion
- General / Infrastructure

## File Changes
- **Modified**: `config/retrieval.yaml`
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/controller/stability.py`
- **Modified**: `src/slrag/decompose/decomposer.py`
- **Modified**: `src/slrag/decompose/facets.py`
- **Modified**: `src/slrag/decompose/intent_set.py`
- **Modified**: `src/slrag/ingest/facet_discovery.py`
- **Modified**: `src/slrag/ingest/indexer.py`
- **Modified**: `src/slrag/retrieve/contradiction.py`
- **Modified**: `src/slrag/retrieve/dense.py`
- **Modified**: `src/slrag/synth/generator.py`
- **Modified**: `src/slrag/synth/verifier.py`

## Diff Statistics
```text
config/retrieval.yaml               | 2 ++
 config/synth.yaml                   | 1 +
 src/slrag/api/app.py                | 3 ++-
 src/slrag/controller/cascade.py     | 1 +
 src/slrag/controller/stability.py   | 4 +++-
 src/slrag/decompose/decomposer.py   | 1 +
 src/slrag/decompose/facets.py       | 6 ++++--
 src/slrag/decompose/intent_set.py   | 6 ++++--
 src/slrag/ingest/facet_discovery.py | 6 ++++--
 src/slrag/ingest/indexer.py         | 6 ++++--
 src/slrag/retrieve/contradiction.py | 7 +++++--
 src/slrag/retrieve/dense.py         | 6 ++++--
 src/slrag/synth/generator.py        | 1 +
 src/slrag/synth/verifier.py         | 6 +++++-
 14 files changed, 41 insertions(+), 15 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
