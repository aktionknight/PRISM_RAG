# Commit Context: a122b69 — fix(engine): resolve LLM timeouts, hardcoded prompts, and tuning issues

## Metadata
- **Commit SHA**: `a122b69294b4ae52f3f73d68969d5de13e79f2e6` (`a122b69`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-27T22:55:23+05:30`
- **Branch**: `diya`

## Commit Message
```text
fix(engine): resolve LLM timeouts, hardcoded prompts, and tuning issues


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 5: Telemetry & Integration Harness
- General / Infrastructure

## File Changes
- **Modified**: `config/controller.yaml`
- **Modified**: `config/prompts/decompose.jinja`
- **Modified**: `config/synth.yaml`
- **Added**: `markdowns/PR_context/20260925_234040_a7f5a8a_idk_claude_changed_smthn_in_grafana_appa.md`
- **Modified**: `src/slrag.egg-info/SOURCES.txt`
- **Modified**: `src/slrag/controller/suppression.py`
- **Modified**: `src/slrag/decompose/decomposer.py`

## Diff Statistics
```text
config/controller.yaml                             |  6 ++--
 config/prompts/decompose.jinja                     |  5 ++--
 config/synth.yaml                                  |  2 +-
 ...a8a_idk_claude_changed_smthn_in_grafana_appa.md | 35 ++++++++++++++++++++++
 src/slrag.egg-info/SOURCES.txt                     |  6 ++++
 src/slrag/controller/suppression.py                |  4 ++-
 src/slrag/decompose/decomposer.py                  | 14 +++++++--
 7 files changed, 61 insertions(+), 11 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
