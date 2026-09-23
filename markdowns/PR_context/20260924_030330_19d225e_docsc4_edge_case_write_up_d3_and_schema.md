# Commit Context: 19d225e — docs(c4): edge-case write-up (D3) and schema v1.1 proposal for the team (audit C-1/C-2/I-1)

> [!WARNING]
> **Interface Contract Impact**: This commit modifies schemas or contract files. Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.

## Metadata
- **Commit SHA**: `19d225ecf7037bac7c784765b78078e18c415a40` (`19d225e`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T03:03:30+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
docs(c4): edge-case write-up (D3) and schema v1.1 proposal for the team (audit C-1/C-2/I-1)

markdowns/edge_cases/C4_EDGE_CASES.md: Component 4 behaviour for self-correction, a self-correction mixed with a new question, contradicting sources, meaning inversions, fabricated citations, unseen names, unhonourable translation/tone requests, and turn concurrency. Each case names its config switch, its telemetry and the test that pins it, and known limitations are listed separately (additive slot phrasing, example-shaped slot lexicon pending the corpus audit, lexical-backend limits).

markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md: the two contract options that decide the CONDITIONAL audit verdict. Option A (recommended) adds optional, defaulted fields to AnswerOutput and Claim; Option B keeps v1.0 with a harness rule to always log SynthesisResult.to_json() plus a CI assertion. Proposal only: core/schemas.py is untouched and needs all four owners.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Core Schemas & Contract (FROZEN)
- Documentation / Markdowns

## File Changes
- **Added**: `markdowns/edge_cases/C4_EDGE_CASES.md`
- **Added**: `markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md`

## Diff Statistics
```text
markdowns/edge_cases/C4_EDGE_CASES.md       | 146 ++++++++++++++++++++++++++++
 markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md |  70 +++++++++++++
 2 files changed, 216 insertions(+)
```

## Description & Context
markdowns/edge_cases/C4_EDGE_CASES.md: Component 4 behaviour for self-correction, a self-correction mixed with a new question, contradicting sources, meaning inversions, fabricated citations, unseen names, unhonourable translation/tone requests, and turn concurrency. Each case names its config switch, its telemetry and the test that pins it, and known limitations are listed separately (additive slot phrasing, example-shaped slot lexicon pending the corpus audit, lexical-backend limits).

markdowns/proposals/SCHEMA_V1_1_PROPOSAL.md: the two contract options that decide the CONDITIONAL audit verdict. Option A (recommended) adds optional, defaulted fields to AnswerOutput and Claim; Option B keeps v1.0 with a harness rule to always log SynthesisResult.to_json() plus a CI assertion. Proposal only: core/schemas.py is untouched and needs all four owners.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
