# Commit Context: 4bb308a — feat(decompose): build Component 2 decomposition pipeline & orchestrator

## Metadata
- **Commit SHA**: `4bb308a0c5663d98e76dd12d5a0b8321985a544c` (`4bb308a`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-23T02:40:40+05:30`
- **Branch**: `aakrit`

## Commit Message
```text
feat(decompose): build Component 2 decomposition pipeline & orchestrator


```

## Architectural Components Impacted
- Component 2: Intent Decomposition
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/api/cli.py`
- **Added**: `src/slrag/baseline/batch_rag.py`
- **Added**: `src/slrag/core/orchestrator.py`
- **Modified**: `src/slrag/decompose/__init__.py`
- **Added**: `src/slrag/decompose/__pycache__/__init__.cpython-311.pyc`
- **Added**: `src/slrag/decompose/__pycache__/decomposer.cpython-311.pyc`
- **Added**: `src/slrag/decompose/__pycache__/facets.cpython-311.pyc`
- **Added**: `src/slrag/decompose/__pycache__/intent_set.cpython-311.pyc`
- **Added**: `src/slrag/decompose/__pycache__/overlap.cpython-311.pyc`
- **Added**: `src/slrag/decompose/decomposer.py`
- **Added**: `src/slrag/decompose/facets.py`
- **Added**: `src/slrag/decompose/intent_set.py`
- **Added**: `src/slrag/decompose/overlap.py`

## Diff Statistics
```text
src/slrag/api/cli.py                               |  53 ++-
 src/slrag/baseline/batch_rag.py                    | 145 +++++++++
 src/slrag/core/orchestrator.py                     |  96 ++++++
 src/slrag/decompose/__init__.py                    |   7 +
 .../decompose/__pycache__/__init__.cpython-311.pyc | Bin 0 -> 546 bytes
 .../__pycache__/decomposer.cpython-311.pyc         | Bin 0 -> 17551 bytes
 .../decompose/__pycache__/facets.cpython-311.pyc   | Bin 0 -> 10698 bytes
 .../__pycache__/intent_set.cpython-311.pyc         | Bin 0 -> 7948 bytes
 .../decompose/__pycache__/overlap.cpython-311.pyc  | Bin 0 -> 5586 bytes
 src/slrag/decompose/decomposer.py                  | 355 +++++++++++++++++++++
 src/slrag/decompose/facets.py                      | 238 ++++++++++++++
 src/slrag/decompose/intent_set.py                  | 150 +++++++++
 src/slrag/decompose/overlap.py                     | 132 ++++++++
 13 files changed, 1163 insertions(+), 13 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
