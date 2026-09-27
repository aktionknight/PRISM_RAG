# Commit Context: 42a7cbf — Remove hardcoded stub responses and tests, connect real LLM backend

> [!WARNING]
> **Interface Contract Impact**: This commit modifies schemas or contract files. Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.

## Metadata
- **Commit SHA**: `42a7cbf4d9aa8aad64ebda35d04cd9a09e4fe895` (`42a7cbf`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-28T00:40:00+05:30`
- **Branch**: `diya`

## Commit Message
```text
Remove hardcoded stub responses and tests, connect real LLM backend


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 3: Corpus Retrieval & Fusion
- Component 4: Session Refinement & Corpus Grounding
- Core Schemas & Contract (FROZEN)
- Documentation / Markdowns
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `markdowns/PR_context/20260928_001801_0f8b17c_docs_add_generated_architectural_audits.md`
- **Added**: `markdowns/PR_context/20260928_002634_5d176e9_fix_cascade_signals_and_connect_to_ollam.md`
- **Added**: `markdowns/audits/20260928_002644_diya_fix_cascade_signals_and_connect_to_ollam.md`
- **Modified**: `src/slrag/api/cli.py`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/core/orchestrator.py`
- **Deleted**: `src/slrag/stubs/__init__.py`
- **Deleted**: `src/slrag/stubs/fake_controller.py`
- **Deleted**: `src/slrag/stubs/fake_decomposer.py`
- **Deleted**: `src/slrag/stubs/fake_retriever.py`
- **Deleted**: `src/slrag/stubs/fake_synthesis.py`
- **Deleted**: `tests/__init__.py`
- **Deleted**: `tests/bench/__init__.py`
- **Deleted**: `tests/bench/test_ablation.py`
- **Deleted**: `tests/bench/test_latency_llm.py`
- **Deleted**: `tests/bench/test_metrics.py`
- **Deleted**: `tests/conftest.py`
- **Deleted**: `tests/core/__init__.py`
- **Deleted**: `tests/core/test_citations.py`
- **Deleted**: `tests/core/test_schemas_contract.py`
- **Deleted**: `tests/core/test_session.py`
- **Deleted**: `tests/core/test_stubs_and_fixtures.py`
- **Deleted**: `tests/fixtures/fixture_chunks.jsonl`
- **Deleted**: `tests/fixtures/golden_edge_self_correction_mixed.jsonl`
- **Deleted**: `tests/fixtures/golden_example.jsonl`
- **Deleted**: `tests/fixtures/golden_example2_refinement.jsonl`
- **Deleted**: `tests/fixtures/golden_example3_presentation.jsonl`
- **Deleted**: `tests/fixtures/golden_scenarios.json`
- **Deleted**: `tests/fixtures/heldout/chunks.jsonl`
- **Deleted**: `tests/fixtures/heldout/scenarios.json`
- **Deleted**: `tests/helpers.py`
- **Deleted**: `tests/synth/__init__.py`
- **Deleted**: `tests/synth/test_claims.py`
- **Deleted**: `tests/synth/test_conflicts.py`
- **Deleted**: `tests/synth/test_delta.py`
- **Deleted**: `tests/synth/test_engine_golden.py`
- **Deleted**: `tests/synth/test_generator.py`
- **Deleted**: `tests/synth/test_heldout.py`
- **Deleted**: `tests/synth/test_nli_backend.py`
- **Deleted**: `tests/synth/test_renderer.py`
- **Deleted**: `tests/synth/test_text.py`
- **Deleted**: `tests/synth/test_uncertainty.py`
- **Deleted**: `tests/synth/test_verifier.py`
- **Deleted**: `tests/test_cascade.py`
- **Deleted**: `tests/test_content_floor.py`
- **Deleted**: `tests/test_core.py`
- **Deleted**: `tests/test_decompose.py`
- **Deleted**: `tests/test_facet_discovery.py`
- **Deleted**: `tests/test_ingest.py`
- **Deleted**: `tests/test_probe.py`
- **Deleted**: `tests/test_retrieval.py`
- **Deleted**: `tests/test_retrieve_advanced.py`
- **Deleted**: `tests/test_schemas.py`
- **Deleted**: `tests/test_speculation.py`
- **Deleted**: `tests/test_stability.py`
- **Deleted**: `tests/test_suppression.py`
- **Added**: `ui/src/components/Icons.jsx`

## Diff Statistics
```text
...b17c_docs_add_generated_architectural_audits.md |  39 ++
 ...6e9_fix_cascade_signals_and_connect_to_ollam.md |  40 ++
 ...iya_fix_cascade_signals_and_connect_to_ollam.md |  67 +++
 src/slrag/api/cli.py                               |   5 +-
 src/slrag/api/ws_server.py                         | 182 +++----
 src/slrag/core/orchestrator.py                     |  19 +-
 src/slrag/stubs/__init__.py                        |  12 -
 src/slrag/stubs/fake_controller.py                 |  63 ---
 src/slrag/stubs/fake_decomposer.py                 |  73 ---
 src/slrag/stubs/fake_retriever.py                  |  65 ---
 src/slrag/stubs/fake_synthesis.py                  | 114 -----
 tests/__init__.py                                  |   1 -
 tests/bench/__init__.py                            |   0
 tests/bench/test_ablation.py                       |  18 -
 tests/bench/test_latency_llm.py                    |  55 ---
 tests/bench/test_metrics.py                        | 129 -----
 tests/conftest.py                                  |  53 --
 tests/core/__init__.py                             |   0
 tests/core/test_citations.py                       |  52 --
 tests/core/test_schemas_contract.py                | 116 -----
 tests/core/test_session.py                         | 199 --------
 tests/core/test_stubs_and_fixtures.py              |  56 ---
 tests/fixtures/fixture_chunks.jsonl                |  12 -
 .../golden_edge_self_correction_mixed.jsonl        |   6 -
 tests/fixtures/golden_example.jsonl                |   4 -
 tests/fixtures/golden_example2_refinement.jsonl    |   4 -
 tests/fixtures/golden_example3_presentation.jsonl  |   6 -
 tests/fixtures/golden_scenarios.json               | 174 -------
 tests/fixtures/heldout/chunks.jsonl                |  10 -
 tests/fixtures/heldout/scenarios.json              | 173 -------
 tests/helpers.py                                   | 119 -----
 tests/synth/__init__.py                            |   0
 tests/synth/test_claims.py                         | 118 -----
 tests/synth/test_conflicts.py                      |  83 ----
 tests/synth/test_delta.py                          | 395 ---------------
 tests/synth/test_engine_golden.py                  | 400 ---------------
 tests/synth/test_generator.py                      | 535 ---------------------
 tests/synth/test_heldout.py                        | 135 ------
 tests/synth/test_nli_backend.py                    |  75 ---
 tests/synth/test_renderer.py                       | 221 ---------
 tests/synth/test_text.py                           |  59 ---
 tests/synth/test_uncertainty.py                    | 144 ------
 tests/synth/test_verifier.py                       | 513 --------------------
 tests/test_cascade.py                              |  42 --
 tests/test_content_floor.py                        |  18 -
 tests/test_core.py                                 | 222 ---------
 tests/test_decompose.py                            | 154 ------
 tests/test_facet_discovery.py                      | 223 ---------
 tests/test_ingest.py                               | 133 -----
 tests/test_probe.py                                |  22 -
 tests/test_retrieval.py                            |  80 ---
 tests/test_retrieve_advanced.py                    | 247 ----------
 tests/test_schemas.py                              | 241 ----------
 tests/test_speculation.py                          |  33 --
 tests/test_stability.py                            |  17 -
 tests/test_suppression.py                          |  18 -
 ui/src/components/Icons.jsx                        | 185 +++++++
 57 files changed, 409 insertions(+), 5770 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
