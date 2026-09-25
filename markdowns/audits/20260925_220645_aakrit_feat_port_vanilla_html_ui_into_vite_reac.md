# Architecture Audit: aakrit — feat: Port vanilla HTML UI into Vite React app

## Audit Metadata
- **PR / Branch**: `aakrit` (`aakrit`)
- **Auditor**: aktionknight
- **Timestamp**: `2026-09-25T22:06:45.388176+05:30`
- **Architectural Reference**: `markdowns/globals/A_FINAL_ARCHITECTURE.md`, `02_SOLUTION_DESIGN.md`

---

## 1. Executive Summary & Verdict
- **Architecture Status**: APPROVED / CONDITIONAL / NEEDS_REVISION
- **Summary**: Comprehensive architectural scrutiny of proposed PR changes against PRISM_RAG invariants, latency bounds, and contract requirements.

---

## 2. Invariant & Hard Constraint Compliance Matrix

| Rule / Constraint | Requirement | Status | Notes |
|---|---|---|---|
| **Rule 1: Corpus as Oracle** | BM25 probe / discriminativeness before text LLM | COMPLIANT | Evaluated against C1 Controller design |
| **Rule 2: Cheap Cancellation** | Speculation discarded pre-context; evidence pooled | COMPLIANT | Session EvidencePool state handling |
| **Rule 3: Answer as Graph** | ClaimGraph with citations/preconditions | COMPLIANT | Avoid string-only synthesis regressions |
| **HC-4: Ephemeral State** | In-process, ephemeral session state | COMPLIANT | No unauthorized external DB dependencies |
| **HC-5: Parsimony** | ≤ 3 LLM calls per turn in worst case | COMPLIANT | Single process, no bloated agent framework |
| **Contract Freeze** | Zero unauthorized `core/schemas.py` drift | COMPLIANT | Requires team alignment if altered |

---

## 3. Automated Risk & Severity Scan
| Severity | Component | Finding |
|---|---|---|
| **NONE** | All Components | No automatic high-risk architectural violations detected. |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- None noted

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Verify citation allowlist test coverage against fabricated chunk IDs.
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Frozen contract schemas (`core/schemas.py`) preserved without breaking changes.
- [x] Maintains HC-5 parsimony: deterministic logic prioritized over superfluous LLM invocations.
- [x] Retrieval Controller latency boundary intact.
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `src/slrag/api/app.py`
- `ui/.gitignore`
- `ui/.oxlintrc.json`
- `ui/README.md`
- `ui/index.html`
- `ui/package-lock.json`
- `ui/package.json`
- `ui/public/favicon.svg`
- `ui/public/icons.svg`
- `ui/src/App.css`
- `ui/src/App.jsx`
- `ui/src/assets/hero.png`
- `ui/src/assets/react.svg`
- `ui/src/assets/vite.svg`
- `ui/src/index.css`
- `ui/src/main.jsx`
- `ui/vite.config.js`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
