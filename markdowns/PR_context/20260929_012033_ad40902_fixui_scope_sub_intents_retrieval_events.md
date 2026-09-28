# Commit Context: ad40902 — fix(ui): scope sub-intents, retrieval events and uncertainties to the current turn, fix empty green box

## Metadata
- **Commit SHA**: `ad409023b2f007dba316be4de299a1777c02df23` (`ad40902`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T01:20:33+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(ui): scope sub-intents, retrieval events and uncertainties to the current turn, fix empty green box


```

## Architectural Components Impacted
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `ui/src/App.jsx`

## Diff Statistics
```text
src/slrag/api/ws_server.py |  32 +++++---
 ui/src/App.jsx             | 187 +++++++++++++++++++++++++++++++--------------
 2 files changed, 151 insertions(+), 68 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
