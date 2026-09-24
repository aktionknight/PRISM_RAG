# Commit Context: a392110 — Merge branch 'diya' into master (Component 1: retrieval controller)

## Metadata
- **Commit SHA**: `a392110b5903d3d13564b2cf46c7a48bc33f0695` (`a392110`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T10:39:35+05:30`
- **Branch**: `master`

## Commit Message
```text
Merge branch 'diya' into master (Component 1: retrieval controller)

Brings in Diya's 5-stage cascading retrieval controller (suppression, content floor, BM25 probe, embedding stability, speculation), core/config.py, controller.yaml and her tests.

Conflict resolutions:
- src/slrag/core/schemas.py: kept the frozen contract from 778f341 (C_TEAM_COORDINATION section 2, pinned by tests/core/test_schemas_contract.py). Diya's copy added Claim.status "retracted", superseded_by and confidence; that is the open C-1/C-2 team decision (markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md), so it is not merged unilaterally. Her models (TranscriptChunk, ControllerDecision) are identical, and her tests do not use the extra Claim fields.
- src/slrag/core/session.py: both kept. Component 4's SessionStore, plus Diya's EvidencePool and SessionState, which the controller imports.
- pyproject.toml: union of dependencies (adds bm25s, PyStemmer, sentence-transformers, numpy); kept the pytest pythonpath/asyncio settings.
- src/slrag/__init__.py, src/slrag/core/__init__.py: docstring-only conflicts; kept the existing ones.
- Dropped 21 committed __pycache__/*.pyc files that came with the branch (.gitignore excludes them).

306 tests pass (285 existing + 21 controller), 3 opt-in skipped.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Core

## File Changes
- No files listed

## Diff Statistics
```text
config/controller.yaml                             |  65 ++++++++++
 ...02e_featcontroller_implement_5_stage_cascadi.md | 141 +++++++++++++++++++++
 ...ler_featcontroller_implement_5_stage_cascadi.md | 115 +++++++++++++++++
 markdowns/globals/COMPONENT_1_SUMMARY.md           |  42 ++++++
 pyproject.toml                                     |   5 +
 src/slrag.egg-info/PKG-INFO                        |  15 +++
 src/slrag.egg-info/SOURCES.txt                     |  25 ++++
 src/slrag.egg-info/dependency_links.txt            |   1 +
 src/slrag.egg-info/requires.txt                    |  11 ++
 src/slrag.egg-info/top_level.txt                   |   1 +
 src/slrag/controller/__init__.py                   |   1 +
 src/slrag/controller/cascade.py                    |  99 +++++++++++++++
 src/slrag/controller/content_floor.py              |  94 ++++++++++++++
 src/slrag/controller/probe.py                      |  82 ++++++++++++
 src/slrag/controller/speculation.py                |  50 ++++++++
 src/slrag/controller/stability.py                  |  71 +++++++++++
 src/slrag/controller/suppression.py                |  45 +++++++
 src/slrag/core/config.py                           |  35 +++++
 src/slrag/core/session.py                          |  50 +++++++-
 tests/__init__.py                                  |   1 +
 tests/conftest.py                                  |  53 ++++++++
 tests/test_cascade.py                              |  42 ++++++
 tests/test_content_floor.py                        |  18 +++
 tests/test_probe.py                                |  22 ++++
 tests/test_schemas.py                              |  14 ++
 tests/test_speculation.py                          |  33 +++++
 tests/test_stability.py                            |  17 +++
 tests/test_suppression.py                          |  18 +++
 28 files changed, 1165 insertions(+), 1 deletion(-)
```

## Description & Context
Brings in Diya's 5-stage cascading retrieval controller (suppression, content floor, BM25 probe, embedding stability, speculation), core/config.py, controller.yaml and her tests.

Conflict resolutions:
- src/slrag/core/schemas.py: kept the frozen contract from 778f341 (C_TEAM_COORDINATION section 2, pinned by tests/core/test_schemas_contract.py). Diya's copy added Claim.status "retracted", superseded_by and confidence; that is the open C-1/C-2 team decision (markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md), so it is not merged unilaterally. Her models (TranscriptChunk, ControllerDecision) are identical, and her tests do not use the extra Claim fields.
- src/slrag/core/session.py: both kept. Component 4's SessionStore, plus Diya's EvidencePool and SessionState, which the controller imports.
- pyproject.toml: union of dependencies (adds bm25s, PyStemmer, sentence-transformers, numpy); kept the pytest pythonpath/asyncio settings.
- src/slrag/__init__.py, src/slrag/core/__init__.py: docstring-only conflicts; kept the existing ones.
- Dropped 21 committed __pycache__/*.pyc files that came with the branch (.gitignore excludes them).

306 tests pass (285 existing + 21 controller), 3 opt-in skipped.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
