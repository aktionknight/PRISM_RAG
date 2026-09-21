# Commit Context: 8d4e02e — feat(controller): Implement 5-stage Cascading Retrieval Controller and schemas

> [!WARNING]
> **Interface Contract Impact**: This commit modifies schemas or contract files. Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.

## Metadata
- **Commit SHA**: `8d4e02ebd78c19388fb48e73853e204d95bb293d` (`8d4e02e`)
- **Author**: Diya Jain <diya04jain@gmail.com>
- **Date**: `2026-09-22T00:51:36+05:30`
- **Branch**: `aakrit`

## Commit Message
```text
feat(controller): Implement 5-stage Cascading Retrieval Controller and schemas


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Core Schemas & Contract (FROZEN)
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `config/controller.yaml`
- **Added**: `pyproject.toml`
- **Added**: `src/slrag.egg-info/PKG-INFO`
- **Added**: `src/slrag.egg-info/SOURCES.txt`
- **Added**: `src/slrag.egg-info/dependency_links.txt`
- **Added**: `src/slrag.egg-info/requires.txt`
- **Added**: `src/slrag.egg-info/top_level.txt`
- **Added**: `src/slrag/__init__.py`
- **Added**: `src/slrag/__pycache__/__init__.cpython-313.pyc`
- **Added**: `src/slrag/controller/__init__.py`
- **Added**: `src/slrag/controller/__pycache__/__init__.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/cascade.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/content_floor.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/probe.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/speculation.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/stability.cpython-313.pyc`
- **Added**: `src/slrag/controller/__pycache__/suppression.cpython-313.pyc`
- **Added**: `src/slrag/controller/cascade.py`
- **Added**: `src/slrag/controller/content_floor.py`
- **Added**: `src/slrag/controller/probe.py`
- **Added**: `src/slrag/controller/speculation.py`
- **Added**: `src/slrag/controller/stability.py`
- **Added**: `src/slrag/controller/suppression.py`
- **Added**: `src/slrag/core/__init__.py`
- **Added**: `src/slrag/core/__pycache__/__init__.cpython-313.pyc`
- **Added**: `src/slrag/core/__pycache__/config.cpython-313.pyc`
- **Added**: `src/slrag/core/__pycache__/schemas.cpython-313.pyc`
- **Added**: `src/slrag/core/__pycache__/session.cpython-313.pyc`
- **Added**: `src/slrag/core/config.py`
- **Added**: `src/slrag/core/schemas.py`
- **Added**: `src/slrag/core/session.py`
- **Added**: `tests/__init__.py`
- **Added**: `tests/__pycache__/__init__.cpython-310.pyc`
- **Added**: `tests/__pycache__/__init__.cpython-313.pyc`
- **Added**: `tests/__pycache__/conftest.cpython-310-pytest-8.4.1.pyc`
- **Added**: `tests/__pycache__/conftest.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_cascade.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_content_floor.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_probe.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_schemas.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_speculation.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_stability.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/__pycache__/test_suppression.cpython-313-pytest-9.1.1.pyc`
- **Added**: `tests/conftest.py`
- **Added**: `tests/test_cascade.py`
- **Added**: `tests/test_content_floor.py`
- **Added**: `tests/test_probe.py`
- **Added**: `tests/test_schemas.py`
- **Added**: `tests/test_speculation.py`
- **Added**: `tests/test_stability.py`
- **Added**: `tests/test_suppression.py`

## Diff Statistics
```text
config/controller.yaml                             |  65 ++++++++++++++
 pyproject.toml                                     |  30 +++++++
 src/slrag.egg-info/PKG-INFO                        |  15 ++++
 src/slrag.egg-info/SOURCES.txt                     |  25 ++++++
 src/slrag.egg-info/dependency_links.txt            |   1 +
 src/slrag.egg-info/requires.txt                    |  11 +++
 src/slrag.egg-info/top_level.txt                   |   1 +
 src/slrag/__init__.py                              |   1 +
 src/slrag/__pycache__/__init__.cpython-313.pyc     | Bin 0 -> 200 bytes
 src/slrag/controller/__init__.py                   |   1 +
 .../__pycache__/__init__.cpython-313.pyc           | Bin 0 -> 204 bytes
 .../controller/__pycache__/cascade.cpython-313.pyc | Bin 0 -> 3900 bytes
 .../__pycache__/content_floor.cpython-313.pyc      | Bin 0 -> 3827 bytes
 .../controller/__pycache__/probe.cpython-313.pyc   | Bin 0 -> 2647 bytes
 .../__pycache__/speculation.cpython-313.pyc        | Bin 0 -> 2064 bytes
 .../__pycache__/stability.cpython-313.pyc          | Bin 0 -> 3011 bytes
 .../__pycache__/suppression.cpython-313.pyc        | Bin 0 -> 2039 bytes
 src/slrag/controller/cascade.py                    |  99 +++++++++++++++++++++
 src/slrag/controller/content_floor.py              |  94 +++++++++++++++++++
 src/slrag/controller/probe.py                      |  82 +++++++++++++++++
 src/slrag/controller/speculation.py                |  50 +++++++++++
 src/slrag/controller/stability.py                  |  71 +++++++++++++++
 src/slrag/controller/suppression.py                |  45 ++++++++++
 src/slrag/core/__init__.py                         |   1 +
 .../core/__pycache__/__init__.cpython-313.pyc      | Bin 0 -> 219 bytes
 src/slrag/core/__pycache__/config.cpython-313.pyc  | Bin 0 -> 1641 bytes
 src/slrag/core/__pycache__/schemas.cpython-313.pyc | Bin 0 -> 3137 bytes
 src/slrag/core/__pycache__/session.cpython-313.pyc | Bin 0 -> 2562 bytes
 src/slrag/core/config.py                           |  35 ++++++++
 src/slrag/core/schemas.py                          |  79 ++++++++++++++++
 src/slrag/core/session.py                          |  45 ++++++++++
 tests/__init__.py                                  |   1 +
 tests/__pycache__/__init__.cpython-310.pyc         | Bin 0 -> 177 bytes
 tests/__pycache__/__init__.cpython-313.pyc         | Bin 0 -> 184 bytes
 .../conftest.cpython-310-pytest-8.4.1.pyc          | Bin 0 -> 2168 bytes
 .../conftest.cpython-313-pytest-9.1.1.pyc          | Bin 0 -> 3269 bytes
 .../test_cascade.cpython-313-pytest-9.1.1.pyc      | Bin 0 -> 6448 bytes
 ...test_content_floor.cpython-313-pytest-9.1.1.pyc | Bin 0 -> 3931 bytes
 .../test_probe.cpython-313-pytest-9.1.1.pyc        | Bin 0 -> 4777 bytes
 .../test_schemas.cpython-313-pytest-9.1.1.pyc      | Bin 0 -> 2353 bytes
 .../test_speculation.cpython-313-pytest-9.1.1.pyc  | Bin 0 -> 4323 bytes
 .../test_stability.cpython-313-pytest-9.1.1.pyc    | Bin 0 -> 3451 bytes
 .../test_suppression.cpython-313-pytest-9.1.1.pyc  | Bin 0 -> 3944 bytes
 tests/conftest.py                                  |  53 +++++++++++
 tests/test_cascade.py                              |  42 +++++++++
 tests/test_content_floor.py                        |  18 ++++
 tests/test_probe.py                                |  22 +++++
 tests/test_schemas.py                              |  14 +++
 tests/test_speculation.py                          |  33 +++++++
 tests/test_stability.py                            |  17 ++++
 tests/test_suppression.py                          |  18 ++++
 51 files changed, 969 insertions(+)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
