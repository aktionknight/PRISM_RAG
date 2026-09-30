# Architecture Audit: fix-vulnerabilities — Fix Priority 4 vulnerabilities

## Audit Metadata
- **PR / Branch**: `master` (`fix-vulnerabilities`)
- **Auditor**: aktionknight
- **Timestamp**: `2026-09-30T15:23:49.277057+05:30`
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
| **HIGH** | HC-5 Parsimony & Budget | Significant LLM generation references detected (21 matches). Verify turn call count does NOT exceed 3. |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- [ ] **Risk**: Potential violation of HC-5 (parsimony): more than 3 LLM calls per turn introduces unacceptable latency and cost.
- [ ] **Risk**: Controller changes must satisfy ≤15 ms p95 per-chunk budget to avoid blocking the event stream.

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Verify citation allowlist test coverage against fabricated chunk IDs.
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Frozen contract schemas (`core/schemas.py`) preserved without breaking changes.
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `config/synth.yaml`
- `corpus/campaign_launchpad_pitch_and_demo.md`
- `diff.txt`
- `fix_chunker.py`
- `fix_indexer.py`
- `fix_loader.py`
- `markdowns/PR_context/20260929_190025_b0ba27e_fix_retrieval_over_fragmentation_specula.md`
- `markdowns/PR_context/20260930_002412_d0c9abf_fix_pipeline_integration_and_bugs.md`
- `markdowns/PR_context/20260930_005859_b26d5ba_fix_final_pipeline_integration_issues_an.md`
- `markdowns/PR_context/20260930_010927_7fab97c_fix_evidencepoolentry_validation_error_i.md`
- `markdowns/PR_context/20260930_015210_85c62d0_fix_controller_oscillation_leaking_acros.md`
- `markdowns/PR_context/20260930_142015_1bc3752_add_unit_tests_for_corpus_grounded_suppr.md`
- `markdowns/PR_context/20260930_142340_c91819f_fix_suppression_guard_rejecting_findings.md`
- `markdowns/PR_context/20260930_143430_60f3194_configure_all_dl_and_llm_models_to_execu.md`
- `markdowns/PR_context/20260930_145913_078d428_remove_hard_3_llm_call_limit_from_archit.md`
- `markdowns/PR_context/20260930_151101_fb7daec_fix_priority_1_vulnerabilities_f01_and_f.md`
- `markdowns/PR_context/20260930_151415_6c800af_fix_priority_2_vulnerabilities_f03_f04_f.md`
- `markdowns/audits/20260929_190035_head_fix_issues.md`
- `markdowns/audits/20260930_005908_head_fix_pipeline_integration_and_bugs.md`
- `markdowns/audits/20260930_theme4_reproduce.py`
- `markdowns/audits/20260930_theme4_reproduction_results.json`
- `markdowns/audits/master_theme_4_guide_requirements_audit.md`
- `markdowns/globals/Theme 4 Guide_RAG.pdf`
- `old_synth.yaml`
- `scratch_diff.txt`
- `src/slrag/api/ws_server.py`
- `src/slrag/controller/cascade.py`
- `src/slrag/decompose/decomposer.py`
- `src/slrag/ingest/chunker.py`
- `src/slrag/ingest/loader.py`
- `src/slrag/retrieve/quota.py`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
