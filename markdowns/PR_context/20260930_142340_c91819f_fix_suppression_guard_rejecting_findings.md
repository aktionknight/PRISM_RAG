# Commit Context: c91819f — Fix suppression guard rejecting findings/results as domain anchors

## Metadata
- **Commit SHA**: `c91819f06244df8ce5f2978ab5223483f9d0b37d` (`c91819f`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T14:23:40+05:30`
- **Branch**: `master`

## Commit Message
```text
Fix suppression guard rejecting findings/results as domain anchors


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)

## File Changes
- **Modified**: `src/slrag/controller/suppression.py`

## Diff Statistics
```text
src/slrag/controller/suppression.py | 5 ++++-
 1 file changed, 4 insertions(+), 1 deletion(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
