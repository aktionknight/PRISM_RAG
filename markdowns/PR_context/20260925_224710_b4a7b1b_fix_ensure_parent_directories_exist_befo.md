# Commit Context: b4a7b1b — fix: ensure parent directories exist before baking spacy model

## Metadata
- **Commit SHA**: `b4a7b1b9ce3a3429b97c0a44cc6c3cf3eb6e366b` (`b4a7b1b`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-25T22:47:10+05:30`
- **Branch**: `aakrit`

## Commit Message
```text
fix: ensure parent directories exist before baking spacy model


```

## Architectural Components Impacted
- General / Infrastructure

## File Changes
- **Modified**: `scripts/bake_nli_model.py`

## Diff Statistics
```text
scripts/bake_nli_model.py | 1 +
 1 file changed, 1 insertion(+)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
