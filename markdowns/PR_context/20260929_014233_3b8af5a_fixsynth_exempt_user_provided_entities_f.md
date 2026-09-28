# Commit Context: 3b8af5a — fix(synth): exempt user-provided entities from copy_check to prevent hallucination checker from rejecting valid claims

## Metadata
- **Commit SHA**: `3b8af5a29b6e45b1736331e025749126068612de` (`3b8af5a`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T01:42:33+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(synth): exempt user-provided entities from copy_check to prevent hallucination checker from rejecting valid claims


```

## Architectural Components Impacted
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/verifier.py`

## Diff Statistics
```text
src/slrag/synth/engine.py   | 15 ++++++++++-----
 src/slrag/synth/verifier.py | 11 ++++++++---
 2 files changed, 18 insertions(+), 8 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
