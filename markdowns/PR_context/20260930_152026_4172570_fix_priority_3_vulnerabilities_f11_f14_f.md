# Commit Context: 4172570 — Fix Priority 3 vulnerabilities F11, F14, F15

## Metadata
- **Commit SHA**: `4172570f7d7f7e6721d1d5bd1f21d70eef4bf366` (`4172570`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-30T15:20:26+05:30`
- **Branch**: `master`

## Commit Message
```text
Fix Priority 3 vulnerabilities F11, F14, F15


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 2: Intent Decomposition
- Component 3: Corpus Retrieval & Fusion
- Component 4: Session Refinement & Corpus Grounding
- Documentation / Markdowns
- General / Infrastructure

## File Changes
- **Modified**: `config/synth.yaml`
- **Added**: `corpus/campaign_launchpad_pitch_and_demo.md`
- **Added**: `diff.txt`
- **Added**: `fix_chunker.py`
- **Added**: `fix_indexer.py`
- **Added**: `fix_loader.py`
- **Added**: `markdowns/PR_context/20260929_190025_b0ba27e_fix_retrieval_over_fragmentation_specula.md`
- **Added**: `markdowns/PR_context/20260930_002412_d0c9abf_fix_pipeline_integration_and_bugs.md`
- **Added**: `markdowns/PR_context/20260930_005859_b26d5ba_fix_final_pipeline_integration_issues_an.md`
- **Added**: `markdowns/PR_context/20260930_010927_7fab97c_fix_evidencepoolentry_validation_error_i.md`
- **Added**: `markdowns/PR_context/20260930_015210_85c62d0_fix_controller_oscillation_leaking_acros.md`
- **Added**: `markdowns/PR_context/20260930_142015_1bc3752_add_unit_tests_for_corpus_grounded_suppr.md`
- **Added**: `markdowns/PR_context/20260930_142340_c91819f_fix_suppression_guard_rejecting_findings.md`
- **Added**: `markdowns/PR_context/20260930_143430_60f3194_configure_all_dl_and_llm_models_to_execu.md`
- **Added**: `markdowns/PR_context/20260930_145913_078d428_remove_hard_3_llm_call_limit_from_archit.md`
- **Added**: `markdowns/PR_context/20260930_151101_fb7daec_fix_priority_1_vulnerabilities_f01_and_f.md`
- **Added**: `markdowns/PR_context/20260930_151415_6c800af_fix_priority_2_vulnerabilities_f03_f04_f.md`
- **Added**: `markdowns/audits/20260929_190035_head_fix_issues.md`
- **Added**: `markdowns/audits/20260930_005908_head_fix_pipeline_integration_and_bugs.md`
- **Added**: `markdowns/audits/20260930_theme4_reproduce.py`
- **Added**: `markdowns/audits/20260930_theme4_reproduction_results.json`
- **Added**: `markdowns/audits/master_theme_4_guide_requirements_audit.md`
- **Added**: `markdowns/globals/Theme 4 Guide_RAG.pdf`
- **Added**: `old_synth.yaml`
- **Added**: `scratch_diff.txt`
- **Modified**: `src/slrag/api/ws_server.py`
- **Modified**: `src/slrag/controller/cascade.py`
- **Modified**: `src/slrag/decompose/decomposer.py`
- **Modified**: `src/slrag/ingest/chunker.py`
- **Modified**: `src/slrag/ingest/loader.py`
- **Modified**: `src/slrag/retrieve/quota.py`

## Diff Statistics
```text
config/synth.yaml                                  |    2 +-
 corpus/campaign_launchpad_pitch_and_demo.md        | 1674 ++++++++++
 diff.txt                                           | 3488 ++++++++++++++++++++
 fix_chunker.py                                     |   77 +
 fix_indexer.py                                     |   27 +
 fix_loader.py                                      |  116 +
 ...27e_fix_retrieval_over_fragmentation_specula.md |   58 +
 ...12_d0c9abf_fix_pipeline_integration_and_bugs.md |   50 +
 ...5ba_fix_final_pipeline_integration_issues_an.md |   50 +
 ...97c_fix_evidencepoolentry_validation_error_i.md |   38 +
 ...2d0_fix_controller_oscillation_leaking_acros.md |   49 +
 ...752_add_unit_tests_for_corpus_grounded_suppr.md |   35 +
 ...19f_fix_suppression_guard_rejecting_findings.md |   35 +
 ...194_configure_all_dl_and_llm_models_to_execu.md |   64 +
 ...428_remove_hard_3_llm_call_limit_from_archit.md |   45 +
 ...aec_fix_priority_1_vulnerabilities_f01_and_f.md |   37 +
 ...0af_fix_priority_2_vulnerabilities_f03_f04_f.md |   41 +
 .../audits/20260929_190035_head_fix_issues.md      |   74 +
 ...05908_head_fix_pipeline_integration_and_bugs.md |   72 +
 markdowns/audits/20260930_theme4_reproduce.py      |  194 ++
 .../20260930_theme4_reproduction_results.json      |  100 +
 .../master_theme_4_guide_requirements_audit.md     |  290 ++
 markdowns/globals/Theme 4 Guide_RAG.pdf            |  Bin 0 -> 1996121 bytes
 old_synth.yaml                                     |  Bin 0 -> 20294 bytes
 scratch_diff.txt                                   |  Bin 0 -> 251456 bytes
 src/slrag/api/ws_server.py                         |   24 +-
 src/slrag/controller/cascade.py                    |   14 +-
 src/slrag/decompose/decomposer.py                  |   31 +-
 src/slrag/ingest/chunker.py                        |    8 +-
 src/slrag/ingest/loader.py                         |    7 +-
 src/slrag/retrieve/quota.py                        |   42 +-
 31 files changed, 6720 insertions(+), 22 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
