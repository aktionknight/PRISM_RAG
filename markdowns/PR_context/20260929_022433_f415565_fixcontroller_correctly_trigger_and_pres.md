# Commit Context: f415565 — fix(controller): correctly trigger and preserve trailing text at internal sentence boundaries, and reset refractory cooldown on new turns

## Metadata
- **Commit SHA**: `f4155657be77f836e6b55e346c9087a1426ce588` (`f415565`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T02:24:33+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(controller): correctly trigger and preserve trailing text at internal sentence boundaries, and reset refractory cooldown on new turns


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/controller/content_floor.py`

## Diff Statistics
```text
src/slrag/api/ws_server.py            |  1 +
 src/slrag/controller/cascade.py       | 76 ++++++++++++++++++-----------------
 src/slrag/controller/content_floor.py | 45 ++++++++++++++++++++-
 3 files changed, 84 insertions(+), 38 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
