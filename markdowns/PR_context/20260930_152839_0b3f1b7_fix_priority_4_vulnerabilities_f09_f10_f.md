# Commit Context: 0b3f1b7 — Fix Priority 4 vulnerabilities (F09, F10, F12, F13)

## Metadata
- **Commit SHA**: `0b3f1b7efd5328737c3308e963a9068b4edb8218` (`0b3f1b7`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T15:28:39+05:30`
- **Branch**: `master`

## Commit Message
```text
Fix Priority 4 vulnerabilities (F09, F10, F12, F13)


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 5: Telemetry & Integration Harness
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/core/session.py`
- **Modified**: `src/slrag/decompose/decomposer.py`
- **Modified**: `src/slrag/telemetry/bus.py`
- **Modified**: `src/slrag/telemetry/cost.py`

## Diff Statistics
```text
src/slrag/api/ws_server.py        | 62 +++++++++++++++++++++++++--------------
 src/slrag/controller/cascade.py   |  7 ++++-
 src/slrag/core/session.py         |  4 +++
 src/slrag/decompose/decomposer.py | 39 ++++++++++++------------
 src/slrag/telemetry/bus.py        | 22 ++++++++++----
 src/slrag/telemetry/cost.py       | 10 +++++--
 6 files changed, 92 insertions(+), 52 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
