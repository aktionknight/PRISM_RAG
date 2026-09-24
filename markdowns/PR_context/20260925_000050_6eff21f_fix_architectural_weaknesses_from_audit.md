# Commit Context: 6eff21f — Fix architectural weaknesses from audit: W-M1, W-M3, W-M4, W-M5

## Metadata
- **Commit SHA**: `6eff21f688a2d633567663cf193f8d2f9cfd8e1c` (`6eff21f`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-25T00:00:50+05:30`
- **Branch**: `aakrit`

## Commit Message
```text
Fix architectural weaknesses from audit: W-M1, W-M3, W-M4, W-M5


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 3: Corpus Retrieval & Fusion
- General / Infrastructure

## File Changes
- **Modified**: `config/retrieval.yaml`
- **Modified**: `src/slrag/controller/speculation.py`
- **Modified**: `src/slrag/core/session.py`
- **Modified**: `src/slrag/retrieve/quota.py`
- **Modified**: `src/slrag/retrieve/rrf.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/renderer.py`
- **Modified**: `tests/test_decompose.py`

## Diff Statistics
```text
config/retrieval.yaml               | 31 +++++++------------------------
 src/slrag/controller/speculation.py | 14 ++++++++++----
 src/slrag/core/session.py           |  1 +
 src/slrag/retrieve/quota.py         |  5 +++++
 src/slrag/retrieve/rrf.py           |  7 +++++--
 src/slrag/synth/engine.py           |  6 ++++++
 src/slrag/synth/renderer.py         | 14 +++++++++++++-
 tests/test_decompose.py             | 12 +++++++-----
 8 files changed, 54 insertions(+), 36 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
