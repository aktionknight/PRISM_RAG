# Commit Context: e230789 — fix: resolve Ollama IPv6 timeouts and ws_server intent regeneration bug

## Metadata
- **Commit SHA**: `e230789053a37e66e395d63feed909af2e203c17` (`e230789`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-28T01:19:47+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix: resolve Ollama IPv6 timeouts and ws_server intent regeneration bug


```

## Architectural Components Impacted
- Component 2: Intent Decomposition
- General / Infrastructure

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/decompose/decomposer.py`

## Diff Statistics
```text
config/synth.yaml                 |  2 +-
 src/slrag/api/app.py              |  2 +-
 src/slrag/api/ws_server.py        | 10 +---------
 src/slrag/decompose/decomposer.py |  3 +--
 4 files changed, 4 insertions(+), 13 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
