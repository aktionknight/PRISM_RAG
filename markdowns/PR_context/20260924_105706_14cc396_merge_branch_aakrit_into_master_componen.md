# Commit Context: 14cc396 — Merge branch 'aakrit' into master (Components 2-3) via an additive v1.1 contract (option A)

## Metadata
- **Commit SHA**: `14cc396a484da1d0433e31d3b8d11efd5f5567e7` (`14cc396`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T10:57:06+05:30`
- **Branch**: `master`

## Commit Message
```text
Merge branch 'aakrit' into master (Components 2-3) via an additive v1.1 contract (option A)

Brings in Aakrit's ingest (loader, segmenter, chunker, indexer, Phase 0 facet discovery), decomposition (decomposer, facet tagger, intent set, overlap), retrieval (sparse, dense, RRF, rerank, density, quota, contradiction, pool), orchestrator/events/clock, CLI, batch baseline and his tests.

Contract: src/slrag/core/schemas.py is now v1.1, an additive merge of the Day-1 freeze and his models.
- Every v1.0 field keeps its name, first position and type.
- The Literal value sets only grow: Claim.status gains "retracted".
- AnswerOutput.retrieval_events accepts typed RetrievalEvent items as well as the brief's plain dicts.
- Every new field is defaulted.
- His str-enums (ControllerDecisionType, ControllerReason, ClaimStatus, ...) interchange with the v1.0 strings, so Diya's controller, Component 4 and his code all validate.
- New models: RetrievalEvent, EvidencePoolEntry, FusedContext, VersionLineage, TelemetrySummary.
- AnswerOutput gains the A section 6 extension fields (the v1.1 proposal, option A).
- tests/core/test_schemas_contract.py now pins exactly these v1.1 rules.
- Needs acknowledgement from all four owners (C_TEAM_COORDINATION section 2).

Session: core/session.py keeps Component 4's SessionStore. Aakrit's SessionState (IntentSet, EvidencePool, ClaimGraph snapshot) is the per-session owner and now carries `controller: ControllerState`. Diya's former SessionState is renamed ControllerState (a rename only in her cascade/speculation/stability modules and conftest).

Rule 3 (generalisation) applied during the merge:
- Component 4 loads the corpus-generated .index/facets.yaml (Phase 0) before the example-derived config/facets.yaml, and accepts its list format and `display` labels.
- config/facets.yaml is rebuilt as a valid union fallback. His copy was corrupted by a spliced line, and it is documented as example-derived.
- decompose.jinja: the guidance examples no longer prime the LLM with the brief's domain ("venue capacity" vs "catering options" -> "eligibility criteria" vs "application deadline").

Other resolutions:
- Diya's controller.yaml, Component 4's prompts and synth/__init__, and the package docstrings kept.
- His stubs taken (richer, v1.1 types); the stub package re-exports restored.
- pyproject: union of dependencies on the setuptools build, plus aiohttp, which his decomposer imports but never declared.
- Makefile: union of targets.
- app.yaml: union of both structures.
- Dropped from the merge: 41 committed __pycache__ files, runs/events.jsonl (gitignored output) and src/slrag/list.py (a debug script with a hard-coded Windows path).

Fixes to his branch's pre-existing failures:
- The decomposer's in-function `import spacy.cli` shadowed `spacy` (UnboundLocalError for every decomposer test). It also downloaded the model at runtime (HC-1); it now uses the pipeline baked in models/.
- Dense encode tolerates list outputs.
- Test inputs were missing required fields (Claim.facet/citations, ControllerDecision.t_s).
- ControllerReason gains `new_intent`, which his test and Component 4 already use.

Still failing, left to the owner (both fail identically on his branch alone): test_decomposer_call_llm (its aiohttp mock doesn't support `async with`) and test_quota_assemble_context (quota remainder allocation gives 2 chunks where 3 are expected).

371 passed, 2 failed (above), 3 opt-in skipped; Component 4 G4/G5 gate passes; NLI suite green.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Core

## File Changes
- No files listed

## Diff Statistics
```text
Makefile                                           |  28 +-
 bench/data/golden_example.jsonl                    |   4 +
 config/app.yaml                                    |  25 +-
 config/facets.yaml                                 |  83 ++-
 config/pricing.yaml                                |  20 +
 config/prompts/decompose.jinja                     |  38 ++
 config/retrieval.yaml                              |  69 +++
 corpus/sample_doc_01.md                            |  19 +
 ...98a_docs_save_pr_context_for_architecture_au.md |  35 ++
 ...3_6c57270_initial_day_1_before_decomp_module.md | 142 +++++
 ...08a_featdecompose_build_component_2_decompos.md |  60 ++
 ...87c_need_to_implement_phase_0_tomorrow_for_g.md |  64 +++
 ...a8b_feat_implement_phase_0_facet_discovery_p.md |  52 ++
 ...akrit_phase_0_facet_discovery_implementation.md |  73 +++
 markdowns/audits/20260923_test_pipeline_audit.md   | 220 ++++++++
 markdowns/globals/D_PHASE_0_FACET_DISCOVERY.md     | 262 +++++++++
 pyproject.toml                                     |  37 +-
 src/slrag/api/__init__.py                          |   1 +
 src/slrag/api/cli.py                               | 145 +++++
 src/slrag/baseline/__init__.py                     |   1 +
 src/slrag/baseline/batch_rag.py                    | 145 +++++
 src/slrag/controller/cascade.py                    |   4 +-
 src/slrag/controller/speculation.py                |   4 +-
 src/slrag/controller/stability.py                  |   4 +-
 src/slrag/core/clock.py                            |  74 +++
 src/slrag/core/events.py                           |  54 ++
 src/slrag/core/orchestrator.py                     |  97 ++++
 src/slrag/core/schemas.py                          | 181 +++++-
 src/slrag/core/session.py                          | 115 +++-
 src/slrag/decompose/__init__.py                    |   8 +
 src/slrag/decompose/decomposer.py                  | 359 ++++++++++++
 src/slrag/decompose/facets.py                      | 182 ++++++
 src/slrag/decompose/intent_set.py                  | 150 +++++
 src/slrag/decompose/overlap.py                     | 132 +++++
 src/slrag/ingest/__init__.py                       |   1 +
 src/slrag/ingest/chunker.py                        | 158 ++++++
 src/slrag/ingest/facet_discovery.py                | 610 +++++++++++++++++++++
 src/slrag/ingest/indexer.py                        | 170 ++++++
 src/slrag/ingest/loader.py                         | 106 ++++
 src/slrag/ingest/segmenter.py                      | 442 +++++++++++++++
 src/slrag/retrieve/__init__.py                     |   1 +
 src/slrag/retrieve/contradiction.py                | 176 ++++++
 src/slrag/retrieve/dense.py                        | 137 +++++
 src/slrag/retrieve/density.py                      |  71 +++
 src/slrag/retrieve/pool.py                         | 137 +++++
 src/slrag/retrieve/quota.py                        | 156 ++++++
 src/slrag/retrieve/rerank.py                       | 121 ++++
 src/slrag/retrieve/rrf.py                          | 124 +++++
 src/slrag/retrieve/sparse.py                       | 104 ++++
 src/slrag/stream/__init__.py                       |   1 +
 src/slrag/stubs/fake_controller.py                 |  65 ++-
 src/slrag/stubs/fake_decomposer.py                 |  80 ++-
 src/slrag/stubs/fake_retriever.py                  |  64 ++-
 src/slrag/stubs/fake_synthesis.py                  | 118 +++-
 src/slrag/synth/config.py                          |  19 +-
 src/slrag/telemetry/__init__.py                    |   1 +
 tests/conftest.py                                  |   4 +-
 tests/core/test_schemas_contract.py                |  76 ++-
 tests/core/test_stubs_and_fixtures.py              |  20 +-
 tests/test_core.py                                 | 222 ++++++++
 tests/test_decompose.py                            | 152 +++++
 tests/test_facet_discovery.py                      | 223 ++++++++
 tests/test_ingest.py                               | 133 +++++
 tests/test_retrieval.py                            |  80 +++
 tests/test_retrieve_advanced.py                    | 247 +++++++++
 tests/test_schemas.py                              | 243 +++++++-
 66 files changed, 7040 insertions(+), 109 deletions(-)
```

## Description & Context
Brings in Aakrit's ingest (loader, segmenter, chunker, indexer, Phase 0 facet discovery), decomposition (decomposer, facet tagger, intent set, overlap), retrieval (sparse, dense, RRF, rerank, density, quota, contradiction, pool), orchestrator/events/clock, CLI, batch baseline and his tests.

Contract: src/slrag/core/schemas.py is now v1.1, an additive merge of the Day-1 freeze and his models.
- Every v1.0 field keeps its name, first position and type.
- The Literal value sets only grow: Claim.status gains "retracted".
- AnswerOutput.retrieval_events accepts typed RetrievalEvent items as well as the brief's plain dicts.
- Every new field is defaulted.
- His str-enums (ControllerDecisionType, ControllerReason, ClaimStatus, ...) interchange with the v1.0 strings, so Diya's controller, Component 4 and his code all validate.
- New models: RetrievalEvent, EvidencePoolEntry, FusedContext, VersionLineage, TelemetrySummary.
- AnswerOutput gains the A section 6 extension fields (the v1.1 proposal, option A).
- tests/core/test_schemas_contract.py now pins exactly these v1.1 rules.
- Needs acknowledgement from all four owners (C_TEAM_COORDINATION section 2).

Session: core/session.py keeps Component 4's SessionStore. Aakrit's SessionState (IntentSet, EvidencePool, ClaimGraph snapshot) is the per-session owner and now carries `controller: ControllerState`. Diya's former SessionState is renamed ControllerState (a rename only in her cascade/speculation/stability modules and conftest).

Rule 3 (generalisation) applied during the merge:
- Component 4 loads the corpus-generated .index/facets.yaml (Phase 0) before the example-derived config/facets.yaml, and accepts its list format and `display` labels.
- config/facets.yaml is rebuilt as a valid union fallback. His copy was corrupted by a spliced line, and it is documented as example-derived.
- decompose.jinja: the guidance examples no longer prime the LLM with the brief's domain ("venue capacity" vs "catering options" -> "eligibility criteria" vs "application deadline").

Other resolutions:
- Diya's controller.yaml, Component 4's prompts and synth/__init__, and the package docstrings kept.
- His stubs taken (richer, v1.1 types); the stub package re-exports restored.
- pyproject: union of dependencies on the setuptools build, plus aiohttp, which his decomposer imports but never declared.
- Makefile: union of targets.
- app.yaml: union of both structures.
- Dropped from the merge: 41 committed __pycache__ files, runs/events.jsonl (gitignored output) and src/slrag/list.py (a debug script with a hard-coded Windows path).

Fixes to his branch's pre-existing failures:
- The decomposer's in-function `import spacy.cli` shadowed `spacy` (UnboundLocalError for every decomposer test). It also downloaded the model at runtime (HC-1); it now uses the pipeline baked in models/.
- Dense encode tolerates list outputs.
- Test inputs were missing required fields (Claim.facet/citations, ControllerDecision.t_s).
- ControllerReason gains `new_intent`, which his test and Component 4 already use.

Still failing, left to the owner (both fail identically on his branch alone): test_decomposer_call_llm (its aiohttp mock doesn't support `async with`) and test_quota_assemble_context (quota remainder allocation gives 2 chunks where 3 are expected).

371 passed, 2 failed (above), 3 opt-in skipped; Component 4 G4/G5 gate passes; NLI suite green.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
