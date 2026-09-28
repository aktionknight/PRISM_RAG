# Architecture Audit: HEAD — fix: streaming RAG engine self-correction and bounded negatives

## Audit Metadata
- **PR / Branch**: `diya` (`HEAD`)
- **Auditor**: aktionknight
- **Timestamp**: `2026-09-28T12:58:28.971118+05:30`
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
| **CRITICAL** | Core Contracts | Frozen schemas modified: src/slrag/core/schemas.py. Risk of interface drift across team components (C_TEAM_COORDINATION §2). |
| **HIGH** | HC-5 Parsimony & Budget | Significant LLM generation references detected (20 matches). Verify turn call count does NOT exceed 3. |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- [ ] **Risk**: Contract drift across module boundaries; all 4 module owners must approve schema changes.
- [ ] **Risk**: Potential violation of HC-5 (parsimony): more than 3 LLM calls per turn introduces unacceptable latency and cost.
- [ ] **Risk**: Controller changes must satisfy ≤15 ms p95 per-chunk budget to avoid blocking the event stream.

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Verify citation allowlist test coverage against fabricated chunk IDs.
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `all.patch`
- `config/controller.yaml`
- `config/prompts/decompose.jinja`
- `config/prompts/synthesize.jinja`
- `corpus/01_OBJECTIVES_AND_REQUIREMENTS.md`
- `markdowns/PR_context/20260928_020434_7a6c933_docs_architecture_audit_for_merge.md`
- `patch.py`
- `patch2.py`
- `patch3.py`
- `patch_synth.py`
- `patch_synth2.py`
- `src/slrag/api/app.py`
- `src/slrag/api/ws_server.py`
- `src/slrag/controller/cascade.py`
- `src/slrag/controller/content_floor.py`
- `src/slrag/core/schemas.py`
- `src/slrag/decompose/decomposer.py`
- `src/slrag/decompose/intent_set.py`
- `src/slrag/synth/uncertainty.py`
- `tests/test_golden_streaming.py`
- `ui/src/App.jsx`
- `ui/src/components/Icons.jsx`
- `ui/src/index.css`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
