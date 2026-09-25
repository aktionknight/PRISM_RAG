# Architecture Audit: HEAD — Implement End-to-End WebSocket API, Frontend UI, and Telemetry Stack

## Audit Metadata
- **PR / Branch**: `aakrit` (`HEAD`)
- **Auditor**: aktionknight
- **Timestamp**: `2026-09-25T00:27:31.701707+05:30`
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
| **HIGH** | HC-5 Parsimony & Budget | Significant LLM generation references detected (20 matches). Verify turn call count does NOT exceed 3. |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- [ ] **Risk**: Potential violation of HC-5 (parsimony): more than 3 LLM calls per turn introduces unacceptable latency and cost.

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Verify citation allowlist test coverage against fabricated chunk IDs.
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Frozen contract schemas (`core/schemas.py`) preserved without breaking changes.
- [x] Retrieval Controller latency boundary intact.
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `Dockerfile`
- `config/app.yaml`
- `docker-compose.yml`
- `infra/grafana/dashboards/slrag.json`
- `infra/grafana/provisioning/dashboards/dashboard.yml`
- `infra/grafana/provisioning/datasources/datasource.yml`
- `infra/prometheus/prometheus.yml`
- `markdowns/PR_context/20260924_004709_39ca3e8_final_test_added.md`
- `markdowns/PR_context/20260925_000050_6eff21f_fix_architectural_weaknesses_from_audit.md`
- `markdowns/audits/20260924_generalization_audit_rule_3.md`
- `markdowns/audits/20260925_000102_head_audit_of_architecture_fixes.md`
- `markdowns/globals/E_LOCAL_SETUP_DEMO_AND_TESTING (1).md`
- `src/slrag.egg-info/PKG-INFO`
- `src/slrag.egg-info/SOURCES.txt`
- `src/slrag.egg-info/requires.txt`
- `src/slrag/api/app.py`
- `src/slrag/api/cli.py`
- `src/slrag/api/ws_server.py`
- `src/slrag/telemetry/bus.py`
- `src/slrag/telemetry/cost.py`
- `src/slrag/telemetry/jsonl_sink.py`
- `src/slrag/telemetry/metrics.py`
- `ui/index.html`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
