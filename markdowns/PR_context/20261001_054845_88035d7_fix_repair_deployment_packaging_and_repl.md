# Commit Context: 88035d7 — fix: repair deployment packaging and replace unsupported evaluation claims

## Metadata
- **Commit SHA**: `88035d7aaba4f4782cea72fc780196e280297191` (`88035d7`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-10-01T05:48:45+05:30`
- **Branch**: `master`

## Commit Message
```text
fix: repair deployment packaging and replace unsupported evaluation claims

Fix Compose service placement and local model endpoints; bake and check engine model resources at image build time. Replace placeholder correction tests with held-out intent-store and synthesis regressions, restore the opt-in NLI check, repair README links and Make targets, and remove obsolete files. Runtime source, schemas, prompts and thresholds are unchanged. Validation: 47 tests passed; opt-in NLI test skipped; changed-test lint, README links and YAML structure passed. Docker build and Compose execution were not run at the user's request.
```

## Architectural Components Impacted
- Component 3: Corpus Retrieval & Fusion
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `.dockerignore`
- **Modified**: `BENCHMARK+EVAL.md`
- **Modified**: `Dockerfile`
- **Modified**: `Makefile`
- **Modified**: `README.md`
- **Deleted**: `all.patch`
- **Modified**: `docker-compose.yml`
- **Deleted**: `scratch_generator.py`
- **Added**: `tests/synth/test_nli_backend.py`
- **Modified**: `tests/test_golden_streaming.py`
- **Deleted**: `ui-old/index.html`

## Diff Statistics
```text
.dockerignore                   |   17 +
 BENCHMARK+EVAL.md               |  126 ++---
 Dockerfile                      |   20 +-
 Makefile                        |   37 +-
 README.md                       |   70 ++-
 all.patch                       |  Bin 80920 -> 0 bytes
 docker-compose.yml              |   33 +-
 scratch_generator.py            |   13 -
 tests/synth/test_nli_backend.py |   19 +
 tests/test_golden_streaming.py  |  125 ++++-
 ui-old/index.html               | 1107 ---------------------------------------
 11 files changed, 300 insertions(+), 1267 deletions(-)
```

## Description & Context
Fix Compose service placement and local model endpoints; bake and check engine model resources at image build time. Replace placeholder correction tests with held-out intent-store and synthesis regressions, restore the opt-in NLI check, repair README links and Make targets, and remove obsolete files. Runtime source, schemas, prompts and thresholds are unchanged. Validation: 47 tests passed; opt-in NLI test skipped; changed-test lint, README links and YAML structure passed. Docker build and Compose execution were not run at the user's request.

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
