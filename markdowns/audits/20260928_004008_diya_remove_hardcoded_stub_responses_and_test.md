# Architecture Audit: diya — Remove hardcoded stub responses and tests, connect real LLM backend

## Audit Metadata
- **PR / Branch**: `diya` (`diya`)
- **Auditor**: aktionknight
- **Timestamp**: `2026-09-28T00:40:08.652727+05:30`
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
| **CRITICAL** | Core Contracts | Frozen schemas modified: tests/core/test_schemas_contract.py, tests/test_schemas.py. Risk of interface drift across team components (C_TEAM_COORDINATION §2). |
| **HIGH** | HC-5 Parsimony & Budget | Significant LLM generation references detected (93 matches). Verify turn call count does NOT exceed 3. |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- [ ] **Risk**: Contract drift across module boundaries; all 4 module owners must approve schema changes.
- [ ] **Risk**: Potential violation of HC-5 (parsimony): more than 3 LLM calls per turn introduces unacceptable latency and cost.
- [ ] **Risk**: Controller changes must satisfy ≤15 ms p95 per-chunk budget to avoid blocking the event stream.

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Touches synthesis or citation verification logic; verify closed allowlist enforcement.
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `markdowns/PR_context/20260928_001801_0f8b17c_docs_add_generated_architectural_audits.md`
- `markdowns/PR_context/20260928_002634_5d176e9_fix_cascade_signals_and_connect_to_ollam.md`
- `markdowns/audits/20260928_002644_diya_fix_cascade_signals_and_connect_to_ollam.md`
- `src/slrag/api/cli.py`
- `src/slrag/api/ws_server.py`
- `src/slrag/core/orchestrator.py`
- `src/slrag/stubs/__init__.py`
- `src/slrag/stubs/fake_controller.py`
- `src/slrag/stubs/fake_decomposer.py`
- `src/slrag/stubs/fake_retriever.py`
- `src/slrag/stubs/fake_synthesis.py`
- `tests/__init__.py`
- `tests/bench/__init__.py`
- `tests/bench/test_ablation.py`
- `tests/bench/test_latency_llm.py`
- `tests/bench/test_metrics.py`
- `tests/conftest.py`
- `tests/core/__init__.py`
- `tests/core/test_citations.py`
- `tests/core/test_schemas_contract.py`
- `tests/core/test_session.py`
- `tests/core/test_stubs_and_fixtures.py`
- `tests/fixtures/fixture_chunks.jsonl`
- `tests/fixtures/golden_edge_self_correction_mixed.jsonl`
- `tests/fixtures/golden_example.jsonl`
- `tests/fixtures/golden_example2_refinement.jsonl`
- `tests/fixtures/golden_example3_presentation.jsonl`
- `tests/fixtures/golden_scenarios.json`
- `tests/fixtures/heldout/chunks.jsonl`
- `tests/fixtures/heldout/scenarios.json`
- `tests/helpers.py`
- `tests/synth/__init__.py`
- `tests/synth/test_claims.py`
- `tests/synth/test_conflicts.py`
- `tests/synth/test_delta.py`
- `tests/synth/test_engine_golden.py`
- `tests/synth/test_generator.py`
- `tests/synth/test_heldout.py`
- `tests/synth/test_nli_backend.py`
- `tests/synth/test_renderer.py`
- `tests/synth/test_text.py`
- `tests/synth/test_uncertainty.py`
- `tests/synth/test_verifier.py`
- `tests/test_cascade.py`
- `tests/test_content_floor.py`
- `tests/test_core.py`
- `tests/test_decompose.py`
- `tests/test_facet_discovery.py`
- `tests/test_ingest.py`
- `tests/test_probe.py`
- `tests/test_retrieval.py`
- `tests/test_retrieve_advanced.py`
- `tests/test_schemas.py`
- `tests/test_speculation.py`
- `tests/test_stability.py`
- `tests/test_suppression.py`
- `ui/src/components/Icons.jsx`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
