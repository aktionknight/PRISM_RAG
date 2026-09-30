# Commit Context: 1bc3752 — Add unit tests for corpus-grounded suppression logic

## Metadata
- **Commit SHA**: `1bc3752d4c27e50df3bbb4fd98b01a5ffc08da6e` (`1bc3752`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T14:20:15+05:30`
- **Branch**: `master`

## Commit Message
```text
Add unit tests for corpus-grounded suppression logic


```

## Architectural Components Impacted
- Tests & Verification

## File Changes
- **Added**: `tests/test_suppression.py`

## Diff Statistics
```text
tests/test_suppression.py | 43 +++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 43 insertions(+)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
