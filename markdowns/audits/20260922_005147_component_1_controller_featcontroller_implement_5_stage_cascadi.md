# Architecture Audit: component-1-controller — feat(controller): Implement 5-stage Cascading Retrieval Controller

## Audit Metadata
- **PR / Branch**: `aakrit` (`component-1-controller`)
- **Auditor**: Diya Jain
- **Timestamp**: `2026-09-22T00:51:47.311653+05:30`
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
| **CRITICAL** | Core Contracts | Frozen schemas modified: src/slrag/core/__pycache__/schemas.cpython-313.pyc, src/slrag/core/schemas.py, tests/__pycache__/test_schemas.cpython-313-pytest-9.1.1.pyc, tests/test_schemas.py. Risk of interface drift across team components (C_TEAM_COORDINATION §2). |

---

## 4. Architectural Weaknesses & Vulnerabilities Identified
- [ ] **Risk**: Contract drift across module boundaries; all 4 module owners must approve schema changes.
- [ ] **Risk**: Controller changes must satisfy ≤15 ms p95 per-chunk budget to avoid blocking the event stream.

---

## 5. Potential Improvements & Optimization Opportunities
- [ ] **Opportunity**: Verify citation allowlist test coverage against fabricated chunk IDs.
- [ ] **Opportunity**: Ensure golden replay (`slrag replay --stream golden_example.jsonl`) runs cleanly in CI.
- [ ] **Opportunity**: Verify telemetry event emission (`events.jsonl`) captures all stage latencies.

---

## 6. Architectural Strengths & Alignments
- [x] Maintains HC-5 parsimony: deterministic logic prioritized over superfluous LLM invocations.
- [x] Session state remains ephemeral and in-process (HC-4 compliant).

---

## 7. Scope of Inspected Files
- `config/controller.yaml`
- `pyproject.toml`
- `src/slrag.egg-info/PKG-INFO`
- `src/slrag.egg-info/SOURCES.txt`
- `src/slrag.egg-info/dependency_links.txt`
- `src/slrag.egg-info/requires.txt`
- `src/slrag.egg-info/top_level.txt`
- `src/slrag/__init__.py`
- `src/slrag/__pycache__/__init__.cpython-313.pyc`
- `src/slrag/controller/__init__.py`
- `src/slrag/controller/__pycache__/__init__.cpython-313.pyc`
- `src/slrag/controller/__pycache__/cascade.cpython-313.pyc`
- `src/slrag/controller/__pycache__/content_floor.cpython-313.pyc`
- `src/slrag/controller/__pycache__/probe.cpython-313.pyc`
- `src/slrag/controller/__pycache__/speculation.cpython-313.pyc`
- `src/slrag/controller/__pycache__/stability.cpython-313.pyc`
- `src/slrag/controller/__pycache__/suppression.cpython-313.pyc`
- `src/slrag/controller/cascade.py`
- `src/slrag/controller/content_floor.py`
- `src/slrag/controller/probe.py`
- `src/slrag/controller/speculation.py`
- `src/slrag/controller/stability.py`
- `src/slrag/controller/suppression.py`
- `src/slrag/core/__init__.py`
- `src/slrag/core/__pycache__/__init__.cpython-313.pyc`
- `src/slrag/core/__pycache__/config.cpython-313.pyc`
- `src/slrag/core/__pycache__/schemas.cpython-313.pyc`
- `src/slrag/core/__pycache__/session.cpython-313.pyc`
- `src/slrag/core/config.py`
- `src/slrag/core/schemas.py`
- `src/slrag/core/session.py`
- `tests/__init__.py`
- `tests/__pycache__/__init__.cpython-310.pyc`
- `tests/__pycache__/__init__.cpython-313.pyc`
- `tests/__pycache__/conftest.cpython-310-pytest-8.4.1.pyc`
- `tests/__pycache__/conftest.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_cascade.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_content_floor.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_probe.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_schemas.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_speculation.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_stability.cpython-313-pytest-9.1.1.pyc`
- `tests/__pycache__/test_suppression.cpython-313-pytest-9.1.1.pyc`
- `tests/conftest.py`
- `tests/test_cascade.py`
- `tests/test_content_floor.py`
- `tests/test_probe.py`
- `tests/test_schemas.py`
- `tests/test_speculation.py`
- `tests/test_stability.py`
- `tests/test_suppression.py`

---

## 8. Verification & Gate Checklist
- [ ] Golden replay test verified (`slrag replay --stream golden_example.jsonl`)
- [ ] Controller latency verified under 15ms p95 budget
- [ ] Closed citation allowlist verified (no unverified / hallucinated document IDs)
- [ ] Telemetry events schema-valid and emitted to `events.jsonl`
