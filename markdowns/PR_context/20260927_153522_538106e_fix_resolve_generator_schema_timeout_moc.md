# Commit Context: 538106e — fix: resolve generator schema timeout, mock golden tests, and route real intents

## Metadata
- **Commit SHA**: `538106e76fa49e482553eed09d7f608d276e68ca` (`538106e`)
- **Author**: Diya Jain <diya04jain@gmail.com>
- **Date**: `2026-09-27T15:35:22+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix: resolve generator schema timeout, mock golden tests, and route real intents


```

## Architectural Components Impacted
- Component 2: Intent Decomposition
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/decompose/decomposer.py`
- **Modified**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
config/synth.yaml                 |  6 +++---
 src/slrag/api/ws_server.py        | 17 ++++++++---------
 src/slrag/decompose/decomposer.py | 10 ++++++----
 tests/synth/test_engine_golden.py | 23 ++++++++++++++++++++++-
 4 files changed, 39 insertions(+), 17 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
