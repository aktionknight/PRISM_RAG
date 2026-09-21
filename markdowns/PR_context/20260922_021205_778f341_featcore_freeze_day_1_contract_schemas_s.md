# Commit Context: 778f341 — feat(core): freeze Day-1 contract — schemas, stubs, golden fixtures, facet taxonomy

> [!WARNING]
> **Interface Contract Impact**: This commit modifies schemas or contract files. Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.

## Metadata
- **Commit SHA**: `778f3410b6a05751d5793f3200cb7c3e866aaa5f` (`778f341`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T02:12:05+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(core): freeze Day-1 contract — schemas, stubs, golden fixtures, facet taxonomy

D1 AM contract-freeze deliverables (C_TEAM_COORDINATION §2–§3), laid down so
Component 4 (and every other owner) codes against the same fakes from hour one.

- src/slrag/core/schemas.py: the seven frozen Pydantic models transcribed
  verbatim from C §2; pinned by tests/core/test_schemas_contract.py (field
  names, order, types, required-ness) so any drift turns CI red.
- src/slrag/core/citations.py: ChunkID <-> "Doc_12 §2" label resolver
  (roadmap 1.4) + citation-marker parser; kept outside schemas.py so the
  frozen file stays verbatim.
- src/slrag/stubs/: fake_controller / fake_decompose / fake_retrieve /
  fake_synthesize exactly as specified in C §3.
- config/facets.yaml (8-facet taxonomy), config/app.yaml (stub/real flags),
  config/synth.yaml (all Component 4 thresholds, lexicons, templates — HC-2).
- tests/fixtures/: mini test corpus (12 chunks), golden Example 1 stream
  (golden_example.jsonl), Example 2 refinement and Example 3 presentation
  streams, and golden_scenarios.json with the expected outputs from
  A_FINAL_ARCHITECTURE §4.2 / §6.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 3: Corpus Retrieval & Fusion
- Component 4: Session Refinement & Corpus Grounding
- Core Schemas & Contract (FROZEN)
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `.gitignore`
- **Added**: `config/app.yaml`
- **Added**: `config/facets.yaml`
- **Added**: `config/synth.yaml`
- **Added**: `pyproject.toml`
- **Added**: `src/slrag/__init__.py`
- **Added**: `src/slrag/core/__init__.py`
- **Added**: `src/slrag/core/citations.py`
- **Added**: `src/slrag/core/schemas.py`
- **Added**: `src/slrag/stubs/__init__.py`
- **Added**: `src/slrag/stubs/fake_controller.py`
- **Added**: `src/slrag/stubs/fake_decomposer.py`
- **Added**: `src/slrag/stubs/fake_retriever.py`
- **Added**: `src/slrag/stubs/fake_synthesis.py`
- **Added**: `src/slrag/synth/__init__.py`
- **Added**: `src/slrag/synth/config.py`
- **Added**: `tests/__init__.py`
- **Added**: `tests/core/__init__.py`
- **Added**: `tests/core/test_citations.py`
- **Added**: `tests/core/test_schemas_contract.py`
- **Added**: `tests/core/test_stubs_and_fixtures.py`
- **Added**: `tests/fixtures/fixture_chunks.jsonl`
- **Added**: `tests/fixtures/golden_example.jsonl`
- **Added**: `tests/fixtures/golden_example2_refinement.jsonl`
- **Added**: `tests/fixtures/golden_example3_presentation.jsonl`
- **Added**: `tests/fixtures/golden_scenarios.json`
- **Added**: `tests/helpers.py`
- **Added**: `tests/synth/__init__.py`

## Diff Statistics
```text
.gitignore                                        |   8 ++
 config/app.yaml                                   |   7 ++
 config/facets.yaml                                |  70 ++++++++++++
 config/synth.yaml                                 | 131 ++++++++++++++++++++++
 pyproject.toml                                    |  28 +++++
 src/slrag/__init__.py                             |   3 +
 src/slrag/core/__init__.py                        |   1 +
 src/slrag/core/citations.py                       |  93 +++++++++++++++
 src/slrag/core/schemas.py                         |  38 +++++++
 src/slrag/stubs/__init__.py                       |  12 ++
 src/slrag/stubs/fake_controller.py                |   8 ++
 src/slrag/stubs/fake_decomposer.py                |   8 ++
 src/slrag/stubs/fake_retriever.py                 |   7 ++
 src/slrag/stubs/fake_synthesis.py                 |   8 ++
 src/slrag/synth/__init__.py                       |   0
 src/slrag/synth/config.py                         |  46 ++++++++
 tests/__init__.py                                 |   0
 tests/core/__init__.py                            |   0
 tests/core/test_citations.py                      |  52 +++++++++
 tests/core/test_schemas_contract.py               |  74 ++++++++++++
 tests/core/test_stubs_and_fixtures.py             |  50 +++++++++
 tests/fixtures/fixture_chunks.jsonl               |  12 ++
 tests/fixtures/golden_example.jsonl               |   4 +
 tests/fixtures/golden_example2_refinement.jsonl   |   4 +
 tests/fixtures/golden_example3_presentation.jsonl |   6 +
 tests/fixtures/golden_scenarios.json              | 130 +++++++++++++++++++++
 tests/helpers.py                                  |  86 ++++++++++++++
 tests/synth/__init__.py                           |   0
 28 files changed, 886 insertions(+)
```

## Description & Context
D1 AM contract-freeze deliverables (C_TEAM_COORDINATION §2–§3), laid down so
Component 4 (and every other owner) codes against the same fakes from hour one.

- src/slrag/core/schemas.py: the seven frozen Pydantic models transcribed
  verbatim from C §2; pinned by tests/core/test_schemas_contract.py (field
  names, order, types, required-ness) so any drift turns CI red.
- src/slrag/core/citations.py: ChunkID <-> "Doc_12 §2" label resolver
  (roadmap 1.4) + citation-marker parser; kept outside schemas.py so the
  frozen file stays verbatim.
- src/slrag/stubs/: fake_controller / fake_decompose / fake_retrieve /
  fake_synthesize exactly as specified in C §3.
- config/facets.yaml (8-facet taxonomy), config/app.yaml (stub/real flags),
  config/synth.yaml (all Component 4 thresholds, lexicons, templates — HC-2).
- tests/fixtures/: mini test corpus (12 chunks), golden Example 1 stream
  (golden_example.jsonl), Example 2 refinement and Example 3 presentation
  streams, and golden_scenarios.json with the expected outputs from
  A_FINAL_ARCHITECTURE §4.2 / §6.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
