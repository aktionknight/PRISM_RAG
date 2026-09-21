# Repository Agent Guidelines & Rules

## 1. Mandatory Post-Commit PR Context Documentation

> [!IMPORTANT]
> **RULE FOR ALL AGENTS**:
> Upon **every git commit**, agents MUST create or ensure the creation of a structured Markdown summary of that recent commit and post it into `markdowns/PR_context/`.

### Why This Rule Exists
- Maintains an auditable, human-readable breadcrumb trail of all incremental agent changes.
- Pre-assembles pull request descriptions, diff summaries, and rationale for review.
- Alerts the team immediately if a commit touches frozen schemas or module contracts (per `markdowns/globals/C_TEAM_COORDINATION.md`).

---

### Execution Instructions for Agents

Whenever you perform a `git commit`:

1. **Automated Generation**:
   Immediately run the context recorder script:
   ```bash
   python scripts/record_commit_pr_context.py --commit HEAD
   ```
   This extracts commit metadata, diffstat, changed files, and architecture component mappings, writing the file directly to:
   `markdowns/PR_context/<YYYYMMDD_HHMMSS>_<short_sha>_<slug>.md`

2. **Manual / Direct Generation** (if running the script is not possible):
   Create a new file in `markdowns/PR_context/` named `<YYYYMMDD_HHMMSS>_<short_sha>_<slug>.md` adhering strictly to this format:

   ```markdown
   # Commit Context: <short_sha> — <commit_subject>

   ## Metadata
   - **Commit SHA**: `<full_sha>` (`<short_sha>`)
   - **Author**: <author_name_and_email>
   - **Date**: `<ISO-8601_timestamp>`
   - **Branch**: `<branch_name>`

   ## Commit Message
   ```text
   <full_commit_message>
   ```

   ## Architectural Components Impacted
   - <Component 1: Retrieval Controller | Component 2: Decomposition | Component 3: Corpus Retrieval & Fusion | Component 4: Session Refinement & Grounding | Component 5: Telemetry & Harness | Schemas | Docs>

   ## File Changes
   - **Added**: `path/to/file`
   - **Modified**: `path/to/file`
   - **Deleted**: `path/to/file`

   ## Diff Statistics
   ```text
   <diff_stat_output>
   ```

   ## Description & Context
   <Detailed explanation of why this change was made, technical decisions, and trade-offs>

   ## PR Integration & Alignment Checklist
   - [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
   - [ ] Golden replay test verified (if applicable)
   - [ ] Unit tests / verification executed
   - [ ] No contract drift introduced across component boundaries
   ```

3. **Verify**:
   Confirm that the markdown file exists in [markdowns/PR_context/](file:///d:/downloads/PRISM_RAG/markdowns/PR_context) before concluding your turn or proceeding to subsequent tasks.
