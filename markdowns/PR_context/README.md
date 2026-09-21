# PR Context Directory

This directory stores structured Markdown summaries of all git commits produced in this repository.

## Purpose
- **Context Preservation**: Enables AI agents and human contributors to quickly inspect recent changes, rationale, and diff statistics without searching through raw git logs.
- **PR Readiness**: Serves as pre-formatted markdown blocks that can be directly pasted into GitHub PR descriptions and changelogs.
- **Contract Tracking**: Highlights whenever core interfaces (`core/schemas.py`) or inter-module contracts are modified, preventing coordination drift across components.

## File Naming Convention
Files in this directory follow the pattern:
```text
<YYYYMMDD_HHMMSS>_<short_sha>_<commit_slug>.md
```
Example: `20260921_183000_a1b2c3d_feat_retrieval_controller.md`

## Generation
- **Automated**: Automatically generated upon every commit via the git hook in `.git/hooks/post-commit`.
- **Manual / Agent Invocation**:
  ```bash
  python scripts/record_commit_pr_context.py --commit HEAD
  ```
