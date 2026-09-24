# Commit Context: 5115cda — docs(rules): AGENTS.md rule 3 - never tune to the golden examples; choose what works on any corpus

## Metadata
- **Commit SHA**: `5115cda560cd085f9c0c00d0c06969ae281f90af` (`5115cda`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T10:45:45+05:30`
- **Branch**: `master`

## Commit Message
```text
docs(rules): AGENTS.md rule 3 - never tune to the golden examples; choose what works on any corpus

Evaluation uses new documents and queries. Agents must prefer general language resources, models and corpus-derived data over domain lists, keep example vocabulary out of config/logic/prompts, prove changes on the held-out suite, and let generality win over golden-specific output.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure

## File Changes
- **Modified**: `AGENTS.md`

## Diff Statistics
```text
AGENTS.md | 38 ++++++++++++++++++++++++++++++++++++++
 1 file changed, 38 insertions(+)
```

## Description & Context
Evaluation uses new documents and queries. Agents must prefer general language resources, models and corpus-derived data over domain lists, keep example vocabulary out of config/logic/prompts, prove changes on the held-out suite, and let generality win over golden-specific output.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
