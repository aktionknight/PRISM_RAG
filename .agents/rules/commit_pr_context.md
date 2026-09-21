# Rule: Commit PR Context Documentation

> **Trigger**: On every git commit
> **Target**: `markdowns/PR_context/`

## Instructions

Whenever an agent creates or executes a git commit:

1. A markdown document recording the recent commit MUST be generated and placed in `markdowns/PR_context/`.
2. File naming convention: `<YYYYMMDD_HHMMSS>_<short_sha>_<commit_slug>.md`.
3. Preferred execution command:
   ```bash
   python scripts/record_commit_pr_context.py --commit HEAD
   ```
4. Key elements required in the document:
   - Commit metadata (SHA, author, branch, timestamp)
   - Commit message (subject and body)
   - Architectural component classification
   - Changed files list and diff statistics
   - Technical rationale and context
   - Schema & contract drift safety checklist
