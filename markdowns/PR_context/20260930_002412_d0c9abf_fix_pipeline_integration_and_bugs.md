# Commit Context: d0c9abf — Fix pipeline integration and bugs

## Metadata
- **Commit SHA**: `d0c9abf2706081a031948dac2e3eaf4c4fcb1ba2` (`d0c9abf`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T00:24:12+05:30`
- **Branch**: `master`

## Commit Message
```text
Fix pipeline integration and bugs


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 5: Telemetry & Integration Harness
- General / Infrastructure

## File Changes
- **Modified**: `Makefile`
- **Modified**: `src/slrag/api/cli.py`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/core/orchestrator.py`
- **Modified**: `src/slrag/decompose/intent_set.py`
- **Modified**: `src/slrag/telemetry/cost.py`

## Diff Statistics
```text
Makefile                          |  6 ++--
 src/slrag/api/cli.py              |  2 ++
 src/slrag/api/ws_server.py        | 69 ++++++++++++++++++++++++++++++++-------
 src/slrag/controller/cascade.py   | 12 +++----
 src/slrag/core/orchestrator.py    |  2 +-
 src/slrag/decompose/intent_set.py |  1 +
 src/slrag/telemetry/cost.py       |  2 +-
 7 files changed, 71 insertions(+), 23 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
