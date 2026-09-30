# Commit Context: 18f3976 — Finalize Docker evaluator stack, package Ollama, and implement environment fallbacks

## Metadata
- **Commit SHA**: `18f39766aa3b5799db78d159e1e6489aaf9d12e3` (`18f3976`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-10-01T04:44:03+05:30`
- **Branch**: `master`

## Commit Message
```text
Finalize Docker evaluator stack, package Ollama, and implement environment fallbacks


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 4: Session Refinement & Corpus Grounding
- Component 5: Telemetry & Integration Harness
- Documentation / Markdowns
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `BENCHMARK+EVAL.md`
- **Modified**: `Makefile`
- **Added**: `README.md`
- **Added**: `SYSTEM_ARCHITECTURE.md`
- **Added**: `bench/ui_test_suite.json`
- **Modified**: `config/controller.yaml`
- **Modified**: `config/prompts/decompose.jinja`
- **Modified**: `config/prompts/synthesize.jinja`
- **Modified**: `config/synth.yaml`
- **Deleted**: `corpus/campaign_launchpad_pitch_and_demo.md`
- **Added**: `corpus/sample_reference.md`
- **Modified**: `docker-compose.yml`
- **Added**: `markdowns/PR_context/20261001_014106_e3f4302_fixverifier_remove_bypass_for_fabricated.md`
- **Added**: `markdowns/PR_context/20261001_015400_3c56127_fix_strict_verifier_retracting_and_rewri.md`
- **Added**: `markdowns/PR_context/20261001_021327_025ccfe_fixmetrics_bound_citation_support_rate_e.md`
- **Added**: `markdowns/PR_context/20261001_022133_1d41027_fixsynth_keep_cited_claims_even_on_entai.md`
- **Added**: `markdowns/audits/20261001_005229_master_priority_correctness_fixes_preserving_re.md`
- **Added**: `markdowns/audits/20261001_014115_head_remove_verifier_bypass_for_fabricated_ci.md`
- **Added**: `markdowns/audits/20261001_015411_head_fix_verifier_and_rewrite_fallback.md`
- **Added**: `markdowns/audits/20261001_021339_head_fix_citation_support_rate_dashboard.md`
- **Added**: `markdowns/audits/20261001_022142_head_keep_cited_claims_on_entailment_failure.md`
- **Deleted**: `patch.py`
- **Deleted**: `patch2.py`
- **Deleted**: `patch3.py`
- **Deleted**: `patch_synth.py`
- **Deleted**: `patch_synth2.py`
- **Deleted**: `patch_yaml.py`
- **Modified**: `pyproject.toml`
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `src/slrag/api/cli.py`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/controller/suppression.py`
- **Modified**: `src/slrag/core/orchestrator.py`
- **Modified**: `src/slrag/decompose/decomposer.py`
- **Modified**: `src/slrag/decompose/intent_set.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/generator.py`
- **Modified**: `src/slrag/synth/renderer.py`
- **Modified**: `src/slrag/synth/verifier.py`
- **Modified**: `src/slrag/telemetry/cost.py`
- **Modified**: `src/slrag/telemetry/metrics.py`
- **Added**: `start.ps1`
- **Added**: `tests/synth/test_heldout.py`
- **Added**: `tests/test_controller_intent_regressions.py`
- **Added**: `tests/test_permanent_corpus.py`
- **Added**: `tests/test_replay_cli.py`
- **Added**: `tests/test_ws_session_state.py`
- **Modified**: `ui/src/App.jsx`
- **Modified**: `ui/src/components/MetricsPanel.jsx`

## Diff Statistics
```text
BENCHMARK+EVAL.md                                  |   63 +
 Makefile                                           |   13 +-
 README.md                                          |  103 ++
 SYSTEM_ARCHITECTURE.md                             |   60 +
 bench/ui_test_suite.json                           |    4 +
 config/controller.yaml                             |    2 +
 config/prompts/decompose.jinja                     |    1 +
 config/prompts/synthesize.jinja                    |    2 +
 config/synth.yaml                                  |    8 +-
 corpus/campaign_launchpad_pitch_and_demo.md        | 1674 --------------------
 corpus/sample_reference.md                         |   15 +
 docker-compose.yml                                 |   21 +-
 ...302_fixverifier_remove_bypass_for_fabricated.md |   35 +
 ...127_fix_strict_verifier_retracting_and_rewri.md |   37 +
 ...cfe_fixmetrics_bound_citation_support_rate_e.md |   38 +
 ...027_fixsynth_keep_cited_claims_even_on_entai.md |   35 +
 ...ter_priority_correctness_fixes_preserving_re.md |   78 +
 ...ead_remove_verifier_bypass_for_fabricated_ci.md |   66 +
 ...15411_head_fix_verifier_and_rewrite_fallback.md |   66 +
 ...339_head_fix_citation_support_rate_dashboard.md |   67 +
 ...head_keep_cited_claims_on_entailment_failure.md |   66 +
 patch.py                                           |   22 -
 patch2.py                                          |  154 --
 patch3.py                                          |  102 --
 patch_synth.py                                     |   15 -
 patch_synth2.py                                    |   16 -
 patch_yaml.py                                      |    2 -
 pyproject.toml                                     |    1 +
 src/slrag/api/app.py                               |   81 +-
 src/slrag/api/cli.py                               |   31 +-
 src/slrag/api/ws_server.py                         |   11 +
 src/slrag/controller/cascade.py                    |    6 +
 src/slrag/controller/suppression.py                |   21 +-
 src/slrag/core/orchestrator.py                     |    4 +-
 src/slrag/decompose/decomposer.py                  |   10 +-
 src/slrag/decompose/intent_set.py                  |   21 +
 src/slrag/synth/engine.py                          |   60 +-
 src/slrag/synth/generator.py                       |   18 +-
 src/slrag/synth/renderer.py                        |    8 +-
 src/slrag/synth/verifier.py                        |   78 +-
 src/slrag/telemetry/cost.py                        |   22 +-
 src/slrag/telemetry/metrics.py                     |   23 +-
 start.ps1                                          |   31 +
 tests/synth/test_heldout.py                        |  278 ++++
 tests/test_controller_intent_regressions.py        |   88 +
 tests/test_permanent_corpus.py                     |   73 +
 tests/test_replay_cli.py                           |   35 +
 tests/test_ws_session_state.py                     |  344 ++++
 ui/src/App.jsx                                     |  121 +-
 ui/src/components/MetricsPanel.jsx                 |    4 +-
 50 files changed, 2019 insertions(+), 2115 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
