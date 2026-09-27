# Commit Context: 900cdde — Fix retrieval_event schema in ws_server and intent deduplication logic in intent_set

## Metadata
- **Commit SHA**: `900cdde3c4e38d84ffdeb8d4263bd7d156a45039` (`900cdde`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-28T00:54:59+05:30`
- **Branch**: `diya`

## Commit Message
```text
Fix retrieval_event schema in ws_server and intent deduplication logic in intent_set


```

## Architectural Components Impacted
- Component 2: Intent Decomposition
- Documentation / Markdowns
- General / Infrastructure

## File Changes
- **Added**: `markdowns/PR_context/20260928_004000_42a7cbf_remove_hardcoded_stub_responses_and_test.md`
- **Added**: `markdowns/audits/20260928_004008_diya_remove_hardcoded_stub_responses_and_test.md`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/decompose/intent_set.py`

## Diff Statistics
```text
...cbf_remove_hardcoded_stub_responses_and_test.md | 157 +++++++++++++++++++++
 ...iya_remove_hardcoded_stub_responses_and_test.md | 122 ++++++++++++++++
 src/slrag/api/ws_server.py                         |   3 -
 src/slrag/decompose/intent_set.py                  |   7 +
 4 files changed, 286 insertions(+), 3 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
