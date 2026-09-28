# Commit Context: 0a3abca — fix(synth): instruct LLM to spell out derived counts as words to pass copy_check

## Metadata
- **Commit SHA**: `0a3abca853e163c62b3394206360619d72e71cde` (`0a3abca`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T00:54:55+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(synth): instruct LLM to spell out derived counts as words to pass copy_check

- Updates synthesis and refinement prompts to spell out counts instead of using digits
- Resolves issue where counting queries failed copy verification and resulted in empty answers
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure

## File Changes
- **Modified**: `config/prompts/refine.jinja`
- **Modified**: `config/prompts/synthesize.jinja`

## Diff Statistics
```text
config/prompts/refine.jinja     | 1 +
 config/prompts/synthesize.jinja | 1 +
 2 files changed, 2 insertions(+)
```

## Description & Context
- Updates synthesis and refinement prompts to spell out counts instead of using digits
- Resolves issue where counting queries failed copy verification and resulted in empty answers

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
