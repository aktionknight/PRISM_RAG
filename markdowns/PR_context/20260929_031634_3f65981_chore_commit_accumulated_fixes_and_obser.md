# Commit Context: 3f65981 — chore: commit accumulated fixes and observability setup

> [!WARNING]
> **Interface Contract Impact**: This commit modifies schemas or contract files. Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.

## Metadata
- **Commit SHA**: `3f659817a3b3ab57fb5cb746264c421bb8acc7d5` (`3f65981`)
- **Author**: aktionknight <aktionknight@gmail.com>
- **Date**: `2026-09-29T03:16:34+05:30`
- **Branch**: `diya`

## Commit Message
```text
chore: commit accumulated fixes and observability setup


```

## Architectural Components Impacted
- Component 1: Retrieval Controller (Cascade / Speculation)
- Component 3: Corpus Retrieval & Fusion
- Component 4: Session Refinement & Corpus Grounding
- Component 5: Telemetry & Integration Harness
- Core Schemas & Contract (FROZEN)
- Documentation / Markdowns
- General / Infrastructure

## File Changes
- **Modified**: `.gitignore`
- **Deleted**: `corpus/01_OBJECTIVES_AND_REQUIREMENTS.md`
- **Added**: `corpus/CURRENT_ARCHITECTURE_REVIEW.md`
- **Added**: `corpus/campaign_launchpad_pitch_and_demo.md`
- **Deleted**: `corpus/sample_doc_01.md`
- **Modified**: `infra/grafana/provisioning/dashboards/dashboard.yml`
- **Modified**: `infra/grafana/provisioning/datasources/datasource.yml`
- **Modified**: `infra/prometheus/prometheus.yml`
- **Added**: `markdowns/PR_context/20260928_134154_e7672db_almost_working_90_done_gg.md`
- **Added**: `markdowns/PR_context/20260929_003508_5b0f4b0_fixsynth_prevent_claim_duplication_and_s.md`
- **Added**: `markdowns/PR_context/20260929_005455_0a3abca_fixsynth_instruct_llm_to_spell_out_deriv.md`
- **Added**: `markdowns/PR_context/20260929_012033_ad40902_fixui_scope_sub_intents_retrieval_events.md`
- **Added**: `markdowns/PR_context/20260929_014233_3b8af5a_fixsynth_exempt_user_provided_entities_f.md`
- **Added**: `markdowns/PR_context/20260929_022433_f415565_fixcontroller_correctly_trigger_and_pres.md`
- **Added**: `markdowns/PR_context/20260929_024846_b9da4b4_fixcontroller_define_missing_anchors_var.md`
- **Added**: `markdowns/audits/20260929_003516_head_fix_claim_duplication_and_spurious_entit.md`
- **Added**: `markdowns/audits/20260929_005503_head_fix_empty_responses_on_counting_queries.md`
- **Added**: `markdowns/audits/20260929_012040_head_fix_sub_intents_carry_over_and_ui_glitch.md`
- **Added**: `markdowns/audits/20260929_014240_head_exempt_user_entities_from_copy_check.md`
- **Added**: `markdowns/audits/20260929_022441_head_fix_sentence_boundary_chunking_and_refra.md`
- **Added**: `markdowns/audits/20260929_024853_head_fix_nameerror_in_stabilitypy.md`
- **Modified**: `src/slrag/api/app.py`
- **Modified**: `src/slrag/controller/probe.py`
- **Modified**: `src/slrag/controller/suppression.py`
- **Modified**: `src/slrag/core/schemas.py`
- **Modified**: `src/slrag/ingest/indexer.py`
- **Modified**: `ui/src/components/MetricsPanel.jsx`
- **Modified**: `ui/src/index.css`

## Diff Statistics
```text
.gitignore                                         |   12 +
 corpus/01_OBJECTIVES_AND_REQUIREMENTS.md           |  312 ----
 corpus/CURRENT_ARCHITECTURE_REVIEW.md              |   67 +
 corpus/campaign_launchpad_pitch_and_demo.md        | 1674 ++++++++++++++++++++
 corpus/sample_doc_01.md                            |   19 -
 .../grafana/provisioning/dashboards/dashboard.yml  |    2 +-
 .../provisioning/datasources/datasource.yml        |    2 +-
 infra/prometheus/prometheus.yml                    |    2 +-
 ...928_134154_e7672db_almost_working_90_done_gg.md |   48 +
 ...4b0_fixsynth_prevent_claim_duplication_and_s.md |   42 +
 ...bca_fixsynth_instruct_llm_to_spell_out_deriv.md |   40 +
 ...902_fixui_scope_sub_intents_retrieval_events.md |   37 +
 ...f5a_fixsynth_exempt_user_provided_entities_f.md |   37 +
 ...565_fixcontroller_correctly_trigger_and_pres.md |   40 +
 ...4b4_fixcontroller_define_missing_anchors_var.md |   35 +
 ...ead_fix_claim_duplication_and_spurious_entit.md |   67 +
 ...head_fix_empty_responses_on_counting_queries.md |   67 +
 ...ead_fix_sub_intents_carry_over_and_ui_glitch.md |   67 +
 ...40_head_exempt_user_entities_from_copy_check.md |   67 +
 ...ead_fix_sentence_boundary_chunking_and_refra.md |   67 +
 ...929_024853_head_fix_nameerror_in_stabilitypy.md |   65 +
 src/slrag/api/app.py                               |   42 +-
 src/slrag/controller/probe.py                      |  167 +-
 src/slrag/controller/suppression.py                |    5 +-
 src/slrag/core/schemas.py                          |    5 +
 src/slrag/ingest/indexer.py                        |   90 ++
 ui/src/components/MetricsPanel.jsx                 |   17 +-
 ui/src/index.css                                   |  110 +-
 28 files changed, 2799 insertions(+), 406 deletions(-)
```

## Description & Context
*No extended description provided in commit message.*

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
