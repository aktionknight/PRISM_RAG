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


---

## 3. Mandatory Generalisation: Never Tune to the Golden Examples

> [!IMPORTANT]
> **RULE FOR ALL AGENTS**:
> Nothing in PRISM (code, config, prompts, lexicons, thresholds, facet lists, stubs used at runtime) may be fitted to the three worked examples in the markdowns (Example 1 venues/Pune, Example 2 travel reimbursement, Example 3 presentation). The system is evaluated on **new, unseen documents and queries**. Whenever there is a design choice, **choose the option that works with any document set as the knowledge base**, even when a tuned option scores better on the goldens.

### Why This Rule Exists
- The golden examples are regression tests, not tuning targets. Rules shaped around them (domain slot lists, example-worded queries, venue-specific patterns, keyword lists from one corpus skim) silently fail on a new corpus.
- Component 4 once had such rules. A held-out corpus in a different domain failed every refinement scenario until they were replaced with corpus-independent mechanisms.

### Execution Instructions for Agents

1. **Prefer general mechanisms over domain lists**:
   - general language resources: NLTK stopwords/negation, WordNet, spaCy parses and NER;
   - models: NLI cross-encoder, embeddings;
   - data derived from whatever corpus is loaded (e.g. facet discovery at ingest);
   - generic templates built from the user's own words.
   Hand-written lists are allowed only for closed-class English words (function words, prepositions, request verbs), never for topic vocabulary.

2. **No domain vocabulary from the examples** in `config/`, `src/` logic or prompts:
   - no "venue", "Pune", "reimbursement", "trip", "catering" and similar;
   - no queries or patterns worded after an example;
   - no thresholds tuned until only the goldens pass.
   Examples may appear in docstrings and tests only.

3. **Prove generalisation with held-out data**:
   - Every behaviour change must pass the held-out suite (`tests/synth/test_heldout.py`, a corpus unrelated to the examples) as well as the goldens.
   - Add held-out scenarios for new behaviours. Write their expectations before changing the code.
   - Never add a held-out domain's words to config to make them pass. The vocabulary guard tests enforce this and must stay green.

4. **When the golden output and generality disagree, generality wins**:
   - Update the golden expectation, not the mechanism, as long as the behaviour is still correct.
   - Record the trade-off in the PR context / audit.

5. **Audit it**: the architecture audit (Rule 2) must state, for each changed component, whether anything is corpus- or example-specific, and how it was checked.
