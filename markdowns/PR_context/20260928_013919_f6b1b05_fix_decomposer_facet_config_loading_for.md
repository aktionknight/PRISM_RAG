# Commit Context: f6b1b05 — fix: decomposer facet config loading for list vs dict

## Metadata
- **Commit SHA**: `f6b1b056a33ff250b1b1c2bf3b5c7db57cf9b2d0` (`f6b1b05`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-28T01:39:19+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix: decomposer facet config loading for list vs dict


```

## Architectural Components Impacted
- Component 2: Intent Decomposition

## File Changes
- **Modified**: `src/slrag/decompose/decomposer.py`

## Diff Statistics
```text
src/slrag/decompose/decomposer.py | 11 ++++++++---
 1 file changed, 8 insertions(+), 3 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
