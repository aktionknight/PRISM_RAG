# Commit Context: 85c62d0 — Fix controller oscillation leaking across turns and dangling the rule

## Metadata
- **Commit SHA**: `85c62d0b06011e41942d1032cff4717235790dc6` (`85c62d0`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T01:52:10+05:30`
- **Branch**: `master`

## Commit Message
```text
Fix controller oscillation leaking across turns and dangling the rule


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- General / Infrastructure

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/controller/content_floor.py`
- **Modified**: `src/slrag/controller/suppression.py`
- **Modified**: `src/slrag/decompose/decomposer.py`

## Diff Statistics
```text
config/synth.yaml                     |   2 +-
 src/slrag/api/app.py                  |  16 +-
 src/slrag/api/ws_server.py            |   2 +
 src/slrag/controller/cascade.py       |  26 +++-
 src/slrag/controller/content_floor.py |   7 +-
 src/slrag/controller/suppression.py   | 282 +++++++++++++++++++++++++++++-----
 src/slrag/decompose/decomposer.py     |   5 +-
 7 files changed, 290 insertions(+), 50 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
