# Architecture Audits Directory

This directory stores formal Architectural Scrutiny Audits generated for every Pull Request (PR) in accordance with repository agent rules.

## Purpose
- **Architecture Invariant Enforcement**: Ensures every pull request conforms to core system invariants defined in `markdowns/globals/A_FINAL_ARCHITECTURE.md` and `02_SOLUTION_DESIGN.md`.
- **Systematic Weakness Detection**: Identifies latency bottlenecks, concurrency issues, hallucination risks, state leakage, and contract drift before code is merged.
- **Continuous Architectural Optimization**: Surfaces concrete improvements and refactoring opportunities across all 5 pipeline components.

## Core Invariants Audited
1. **Rule 1 — Corpus as Oracle**: Retrieval-readiness must be decided by corpus discriminativeness (BM25 probe), not speculative text LLM calls.
2. **Rule 2 — Cheap Cancellation**: Speculative branches must be discarded before polluting context; evidence must be pooled cleanly.
3. **Rule 3 — Answer as Data Structure**: Answers must be held as a `ClaimGraph`, not raw strings, enabling fine-grained delta updates without regeneration.
4. **HC-4 — Ephemeral In-Proc Session State**: Turn and session state must be held in-memory; no unauthorised external persistence layers.
5. **HC-5 — Parsimony**: Worst-case LLM call limit of ≤3 per turn; single-process execution; zero unnecessary agent frameworks or orchestration bloat.
6. **Contract Integrity**: No unilateral changes to `core/schemas.py`.

## File Naming Convention
```text
<YYYYMMDD_HHMMSS>_<pr_id_or_branch>_architecture_audit_<slug>.md
```
Example: `20260921_184500_pr_14_architecture_audit_cascade_controller.md`

## Generation
Run the architecture audit tool:
```bash
python scripts/audit_architecture.py --pr "PR-1" --title "feat: retrieval controller cascade"
```
