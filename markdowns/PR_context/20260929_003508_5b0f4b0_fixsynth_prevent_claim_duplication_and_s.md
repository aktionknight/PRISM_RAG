# Commit Context: 5b0f4b0 — fix(synth): prevent claim duplication and spurious entity gaps

## Metadata
- **Commit SHA**: `5b0f4b01ca5db7a59e2046c301c28da39fb0982c` (`5b0f4b0`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T00:35:08+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(synth): prevent claim duplication and spurious entity gaps

- Update ExtractiveGenerator to properly mutate the retained sentence set across the intents loop, preventing the same sentence from being duplicated across multiple intents (which caused repeating LLM responses).
- Add missing break statement in _assign fallback logic in uncertainty.py.
- Modify CoverageMatrix._covered_row to only look for missing entities that are actually part of the sub-intent's query, preventing spurious entity_gap messages when a specific facet was asked about.
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure

## File Changes
- **Modified**: `src/slrag/synth/generator.py`
- **Modified**: `src/slrag/synth/uncertainty.py`

## Diff Statistics
```text
src/slrag/synth/generator.py   | 4 +++-
 src/slrag/synth/uncertainty.py | 5 ++++-
 2 files changed, 7 insertions(+), 2 deletions(-)
```

## Description & Context
- Update ExtractiveGenerator to properly mutate the retained sentence set across the intents loop, preventing the same sentence from being duplicated across multiple intents (which caused repeating LLM responses).
- Add missing break statement in _assign fallback logic in uncertainty.py.
- Modify CoverageMatrix._covered_row to only look for missing entities that are actually part of the sub-intent's query, preventing spurious entity_gap messages when a specific facet was asked about.

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
