# Commit Context: 0c997f4 — fix: index mounted corpus before serving and restore Ollama GPU

## Metadata
- **Commit SHA**: `0c997f417bf4a02f88fcdaa87c6486407acbe427` (`0c997f4`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-10-01T06:04:35+05:30`
- **Branch**: `master`

## Commit Message
```text
fix: index mounted corpus before serving and restore Ollama GPU

Add an image entrypoint that rebuilds the current mounted corpus index before server exec and blocks startup on empty input, missing artifacts, or an invalid/empty FAISS index. Restore NVIDIA GPU reservations for Ollama and document startup indexing, GPU requirements and actual device placement checks. Publish measured regression counts and JUnit evidence instead of unsupported streaming gate claims. Seven startup regressions use real loader/FAISS operations with a stubbed indexing boundary. Updated full suite: 54 passed, 1 opt-in skipped; separately enabled NLI test: 1 passed. Changed-file lint and static Compose/entrypoint checks passed. Docker execution remains skipped per user instruction. Retrieval/synthesis source, schemas, prompts and request timeouts are unchanged.
```

## Architectural Components Impacted
- Documentation / Markdowns
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `BENCHMARK+EVAL.md`
- **Modified**: `Dockerfile`
- **Modified**: `README.md`
- **Added**: `bench/results/20261001_deployment_regressions.xml`
- **Added**: `bench/results/20261001_focused_regressions.xml`
- **Added**: `bench/results/20261001_full_regressions.xml`
- **Added**: `bench/results/20261001_nli_regression.xml`
- **Modified**: `docker-compose.yml`
- **Added**: `markdowns/PR_context/20261001_054906_01b65c4_docs_record_deployment_and_regression_fi.md`
- **Added**: `scripts/docker_start.py`
- **Added**: `tests/test_docker_start.py`

## Diff Statistics
```text
BENCHMARK+EVAL.md                                  |  90 ++++++++++++++++++-
 Dockerfile                                         |   2 +
 README.md                                          |  15 +++-
 bench/results/20261001_deployment_regressions.xml  |   1 +
 bench/results/20261001_focused_regressions.xml     |   1 +
 bench/results/20261001_full_regressions.xml        |   1 +
 bench/results/20261001_nli_regression.xml          |   1 +
 docker-compose.yml                                 |   9 +-
 ...5c4_docs_record_deployment_and_regression_fi.md |  35 ++++++++
 scripts/docker_start.py                            |  64 +++++++++++++
 tests/test_docker_start.py                         | 100 +++++++++++++++++++++
 11 files changed, 314 insertions(+), 5 deletions(-)
```

## Description & Context
Add an image entrypoint that rebuilds the current mounted corpus index before server exec and blocks startup on empty input, missing artifacts, or an invalid/empty FAISS index. Restore NVIDIA GPU reservations for Ollama and document startup indexing, GPU requirements and actual device placement checks. Publish measured regression counts and JUnit evidence instead of unsupported streaming gate claims. Seven startup regressions use real loader/FAISS operations with a stubbed indexing boundary. Updated full suite: 54 passed, 1 opt-in skipped; separately enabled NLI test: 1 passed. Changed-file lint and static Compose/entrypoint checks passed. Docker execution remains skipped per user instruction. Retrieval/synthesis source, schemas, prompts and request timeouts are unchanged.

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
