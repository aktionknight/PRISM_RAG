# Rule: Mandatory Architecture Scrutiny & Weakness Audit on Every PR

> **Trigger**: Every Pull Request (creation, update, or review)
> **Target**: `markdowns/audits/`

## Instructions

Whenever an agent creates, modifies, or reviews a Pull Request:

1. **Scrutinize Current Architecture**:
   - Compare proposed PR diffs against architecture baselines in `markdowns/globals/A_FINAL_ARCHITECTURE.md`, `02_SOLUTION_DESIGN.md`, and `C_TEAM_COORDINATION.md`.
   - Verify compliance with Core Invariants:
     - **Rule 1**: Corpus as oracle (BM25 probe for retrieval readiness)
     - **Rule 2**: Cheap cancellation & evidence pooling
     - **Rule 3**: Answer as graph (`ClaimGraph`, not strings)
     - **HC-4**: In-proc, ephemeral session state
     - **HC-5**: Parsimony (worst-case ≤3 LLM calls per turn, no framework bloat)
     - **Contract Freeze**: Zero unauthorized edits to `core/schemas.py`

2. **Generate Audit Document**:
   - Save the audit report to: `markdowns/audits/<YYYYMMDD_HHMMSS>_<pr_id_or_branch>_architecture_audit_<slug>.md`.
   - Preferred command:
     ```bash
     python scripts/audit_architecture.py --pr "<PR_ID>" --title "<PR_TITLE>"
     ```
   - Complete the audit sections:
     - Invariant & Hard Constraint Compliance Matrix
     - Automated Risk & Severity Scan (CRITICAL / HIGH / MEDIUM / LOW)
     - Architectural Weaknesses & Vulnerabilities Identified
     - Potential Improvements & Optimization Opportunities
     - Verification & Gate Checklist (Golden Replay, latency, closed citation allowlist)
