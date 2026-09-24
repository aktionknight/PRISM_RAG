# Architecture Audit: master — merge diya + aakrit into master via additive v1.1 contract

## Audit Metadata
- **Branch**: `master` (new integration branch = `sivansh` + `diya` + `aakrit`), range `9a63782..14cc396`
- **Commits**:
  - `a392110` merge diya (Component 1)
  - `5115cda` AGENTS.md rule 3
  - `14cc396` merge aakrit (Components 2–3)
- **Auditor**: Sivansh, agent-assisted
- **Reference**: `C_TEAM_COORDINATION.md` §2 (contract freeze), `A_FINAL_ARCHITECTURE.md` §6, AGENTS.md rules 1–3

---

## 1. Executive Summary & Verdict
- **Architecture Status**: **CONDITIONAL**: the v1.1 contract needs acknowledgement from all four owners.
- **What was merged**: all three existing components (controller, decomposition/retrieval, synthesis) now live on one branch with one contract.
- **The problem**: the branches had diverged at the root. Aakrit's branch carried its own `schemas.py` (enums, typed events, extra required fields) and its own `SessionState`. Diya's and Component 4's code used the Day-1 freeze.
- **The resolution (option A)**: an additive superset contract. Every frozen field is unchanged and first, and every addition is defaulted. So nobody's producer breaks, and `test_schemas_contract.py` pins those rules.

## 2. Invariant & Hard Constraint Compliance Matrix

| Rule | Status | Evidence |
|---|---|---|
| Rule 1: Corpus as oracle | COMPLIANT | Diya's BM25 discriminativeness probe merged unchanged. |
| Rule 2: Cheap cancellation / pooling | **PARTIAL** | Diya's `ControllerState.evidence_pool` (speculative demotion) and Aakrit's `SessionState.evidence_pool` are still two pools. See W-M1. |
| Rule 3: Answer as graph | COMPLIANT | ClaimGraph unchanged. `Claim` gains optional `confidence` / `superseded_by` / "retracted". |
| HC-1: No egress | **FIXED** | His decomposer downloaded spaCy at runtime. It now loads the baked pipeline. |
| HC-2: No hardcoding | PARTIAL | `rrf.py` hard-codes 0.8/0.2 bias weights (should be in `retrieval.yaml`). |
| HC-4: Ephemeral state | COMPLIANT | All session state is in-process; `SessionState.destroy()` also clears controller state. |
| HC-5: ≤ 3 LLM calls | COMPLIANT | Decomposer ≤ 1 + synthesis ≤ 1. |
| **Contract** | **CHANGED (additive)** | v1.1 superset. Needs all four owners' acknowledgement. |
| **AGENTS rule 3 (generalisation)** | COMPLIANT with notes | See §4. |

## 3. Automated Risk Scan
The script flagged `schemas.py` (correct: the contract changed, additively and deliberately) and LLM keyword density (a false positive).

## 4. Generalisation check (AGENTS.md rule 3), per component

| Component | Corpus/example-specific? | How checked |
|---|---|---|
| C1 controller | Thresholds are corpus-agnostic; self-correction markers and presentation verbs are English conversation words, not domain words. | Keyword scan of `controller.yaml` and `controller/`. |
| C2 decomposition | **Fixed**: `decompose.jinja` primed the LLM with the brief's domain. The facet tagger prefers the corpus-generated `.index/facets.yaml`. | Brief-vocabulary guard test (prompts). |
| C3 retrieval | Facet weights prefer Phase 0 `retrieval_bias`; the example-keyed weights in `retrieval.yaml` are fallback-only, and unknown facets get balanced 0.5/0.5. | Read `rrf.py`. |
| C4 synthesis | Corpus-independent (previous audit). **Now** also reads the Phase 0 facet taxonomy. | Held-out suite 7/7 plus two guards. |
| `config/facets.yaml` | Example-derived by nature; documented as fallback only. | Header comment; held-out guard. |
| Stubs | Golden-example data by design (test doubles). | Allowed by rule 3 (tests only). |

## 5. Weaknesses
- [ ] **W-M1 (MEDIUM, Rule 2)**: two evidence pools. The controller's speculative demotion writes to `ControllerState.evidence_pool`, not the session's `EvidencePoolEntry` pool, so cancelled speculation isn't reusable by refinement yet. Fix: have `ControllerState` write through to `SessionState.add_evidence` (Diya + Aakrit).
- [ ] **W-M2 (MEDIUM)**: the orchestrator runs the *stub* controller and retriever and `fake_synthesize`. The real Component 1/4 engines aren't wired into it yet (the harness is Matangi's job).
- [ ] **W-M3 (LOW)**: two pre-existing failures on the aakrit branch remain (Aakrit to fix):
  - `test_decomposer_call_llm`: its aiohttp mock doesn't support `async with`;
  - `test_quota_assemble_context`: the quota remainder allocation gives 2 chunks where 3 are expected.
- [ ] **W-M4 (LOW, HC-2)**: `rrf.py` hard-codes the 0.8/0.2 and 0.2/0.8 bias weights.
- [ ] **W-M5 (process)**: v1.1 widened `Claim` and `AnswerOutput`, but Component 4 still fills the extensions dict and not the new `AnswerOutput` fields; the output JSON is unchanged. Filling them is a one-commit follow-up once the team acknowledges v1.1.

## 6. Strengths
- [x] One contract, three components, zero producer breakage: pinned by `test_v1_0_producers_still_validate` and `test_enums_interchange_with_v1_0_strings`.
- [x] The merge removed committed build artefacts (62 `.pyc` files, a run output, a Windows-path debug script) and an undeclared dependency (`aiohttp`).
- [x] AGENTS.md rule 3 is in force and already caught one example-primed prompt during this merge.

## 7. Scope
`core/{schemas,session,orchestrator}.py`, `controller/{cascade,speculation,stability}.py` (rename), `decompose/decomposer.py`, `retrieve/dense.py`, `synth/config.py`, `config/{facets,app,retrieval,pricing,controller}.yaml`, `config/prompts/decompose.jinja`, `pyproject.toml`, `Makefile`, `AGENTS.md`, tests (`core/test_schemas_contract.py`, `core/test_stubs_and_fixtures.py`, `test_core.py`, `test_schemas.py`, `conftest.py`).

## 8. Verification
- [x] 371 passed, 2 failed (pre-existing, W-M3), 3 skipped (opt-in NLI).
- [x] Component 4 G4/G5 gate exits 0 on the merged tree; opt-in NLI suite 3/3.
- [x] Held-out generalisation suite and both vocabulary guards pass.
- [ ] Not pushed: `master` is local. Pushing it is the owner's call.
