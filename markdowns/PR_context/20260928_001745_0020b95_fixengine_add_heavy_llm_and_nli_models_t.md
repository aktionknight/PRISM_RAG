# Commit Context: 0020b95 — fix(engine): add heavy LLM and NLI models to preload endpoint to avoid first-query delay

## Metadata
- **Commit SHA**: `0020b957136712a7d57035281ff227232650b656` (`0020b95`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-28T00:17:45+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(engine): add heavy LLM and NLI models to preload endpoint to avoid first-query delay


```

## Architectural Components Impacted
- Component 3: Corpus Retrieval & Fusion
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `ui/index.html`
- **Modified**: `ui/src/App.jsx`
- **Modified**: `ui/src/components/MetricsPanel.jsx`
- **Modified**: `ui/src/index.css`

## Diff Statistics
```text
src/slrag/api/app.py               |   30 +
 ui/index.html                      |    8 +-
 ui/src/App.jsx                     |   94 +--
 ui/src/components/MetricsPanel.jsx |  269 ++-----
 ui/src/index.css                   | 1449 ++++++++++++++++++++++--------------
 5 files changed, 1031 insertions(+), 819 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
