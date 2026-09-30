# Commit Context: 025ccfe — fix(metrics): Bound citation support rate explicitly and use avg() to prevent 200% on log dashboard

## Metadata
- **Commit SHA**: `025ccfe07f609816e1350b91789152c25eec4c64` (`025ccfe`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-10-01T02:13:27+05:30`
- **Branch**: `master`

## Commit Message
```text
fix(metrics): Bound citation support rate explicitly and use avg() to prevent 200% on log dashboard


```

## Architectural Components Impacted
- Component 5: Telemetry & Integration Harness
- General / Infrastructure

## File Changes
- **Modified**: `infra/grafana/dashboards/slrag.json`
- **Modified**: `src/slrag/api/ws_server.py`

## Diff Statistics
```text
infra/grafana/dashboards/slrag.json |   6 +-
 src/slrag/api/ws_server.py          | 118 ++++++++++++++++++++++++++++++++++--
 2 files changed, 115 insertions(+), 9 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
