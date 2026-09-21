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

---

## 2. Mandatory Architectural Scrutiny & Weakness Audit on Every PR

> [!IMPORTANT]
> **RULE FOR ALL AGENTS**:
> In **every Pull Request (PR)**, agents MUST scrutinize the current system architecture against repository invariants and generate an **Architecture Audit Markdown** posted into `markdowns/audits/`. The audit must systematically evaluate the design, identify potential weaknesses and failure modes, and propose concrete improvements.

### Why This Rule Exists
- Prevents architectural erosion and contract drift across the 5 core modules (`Controller`, `Decomposition`, `Retrieval & Fusion`, `Refinement & Grounding`, `Telemetry`).
- Proactively surfaces latency bottlenecks, concurrency flaws, hallucination loopholes, and budget violations before merging.
- Enforces hard constraints:
  - **Rule 1**: Corpus as oracle (BM25 discriminativeness probe; no premature text LLM calls).
  - **Rule 2**: Cheap cancellation & evidence pooling.
  - **Rule 3**: Answer as a `ClaimGraph` data structure (not raw string mutations).
  - **HC-4**: In-process, ephemeral session state.
  - **HC-5**: Parsimony (worst-case ≤ 3 LLM calls per turn; no bloated agent frameworks).
  - **Contract Freeze**: Zero uncoordinated alterations to `core/schemas.py`.

---

### Execution Instructions for Agents

Whenever creating, updating, or reviewing a Pull Request:

1. **Perform Architectural Scrutiny**:
   Examine changed files and system interactions against `markdowns/globals/A_FINAL_ARCHITECTURE.md` and `02_SOLUTION_DESIGN.md`.

2. **Automated Audit Generation**:
   Run the architecture auditor script:
   ```bash
   python scripts/audit_architecture.py --pr "<PR_NUMBER_OR_BRANCH>" --title "<PR_TITLE>"
   ```
   This generates an audit report at:
   `markdowns/audits/<YYYYMMDD_HHMMSS>_<pr_slug>_<audit_title_slug>.md`

3. **Audit Contents & Structure**:
   The generated audit document must contain:
   - **Audit Metadata**: PR ID, branch, auditor, reference specs.
   - **Executive Summary & Verdict**: `APPROVED`, `CONDITIONAL`, or `NEEDS_REVISION`.
   - **Invariant Compliance Matrix**: Evaluates Rules 1–3, HC-4, HC-5, and Schema freeze.
   - **Risk & Severity Scan**: Categorized findings (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
   - **Architectural Weaknesses & Vulnerabilities Identified**: Specific latency, concurrency, hallucination, or interface risks.
   - **Potential Improvements & Optimization Opportunities**: Concrete technical recommendations.
   - **Architectural Strengths & Alignments**: Validated sound engineering practices.
   - **Verification Checklist**: Golden replay test, latency budgets, closed citation allowlist.

4. **Verify**:
   Confirm that the audit markdown exists in [markdowns/audits/](file:///d:/downloads/PRISM_RAG/markdowns/audits) before marking PR work complete.

