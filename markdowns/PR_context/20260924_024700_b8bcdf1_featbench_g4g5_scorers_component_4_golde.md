# Commit Context: b8bcdf1 — feat(bench): G4/G5 scorers, Component 4 golden replay, NLI calibration harness (roadmap 4.11)

## Metadata
- **Commit SHA**: `b8bcdf180f4b6d47ab5d5fe03c9b20b033e44bc4` (`b8bcdf1`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:47:00+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(bench): G4/G5 scorers, Component 4 golden replay, NLI calibration harness (roadmap 4.11)

bench/metrics.py (G4/G5 section; G2/G3 owners add theirs) scores run records - one JSON object per turn with the output JSON, the turn's citation allowlist and its synthesis.* telemetry - so Matangi's events.jsonl can be scored by mapping onto the same keys:
- G4: fabricated_id_count over every emitted label (citations, answer markers, claim citations) against the turn's allowlist; citation_support_rate / unsupported_claim_rate with each claim judged once per session by a lexical or cross-encoder judge; uncertainty_precision / recall against an optional gold file.
- G5: full_corpus_searches_on_refinement, sessions cleared, claims_retained_pct, delta_queries_per_refinement, pool-resolved targets; presentation-only turns must issue no retrieval, keep answer_version and cite a subset of the prior answer.
- --gate exits non-zero on any failure (fabricated IDs, support < 0.85, full-corpus search, cleared session, presentation violations).

bench/replay_c4.py replays the golden scenarios in harness order (SessionStore, classify(), upstream only when routed) and writes the records; stands in for `slrag replay` until the harness lands.

Golden results: lexical judge 20/20 claims supported, 0 fabricated IDs, 0 full-corpus searches, claims_retained_pct 0.75, 2 delta queries per refinement, uncertainty precision/recall 1.0. The independent cross-encoder judge also scores 20/20 on the lexical path's output.

bench/calibrate_nli.py sweeps the threshold per backend, scores the shipped verifier per pair kind, and times the NLI lock. Makefile: setup, setup-nli, test, test-nli, bench-c4, calibrate-nli, ablate-a3.

tests/bench/test_metrics.py covers the scorers and the gate exit code; tests/synth/test_nli_backend.py (opt-in, SLRAG_NLI=1 with the model baked) asserts 45/45 calibration pairs and G4/G5 gates on the golden replay under the cross-encoder - both pass locally.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 5: Telemetry & Integration Harness
- General / Infrastructure
- Tests & Verification

## File Changes
- **Added**: `Makefile`
- **Added**: `bench/__init__.py`
- **Added**: `bench/calibrate_nli.py`
- **Added**: `bench/data/c4_gold.jsonl`
- **Added**: `bench/data/nli_calibration.jsonl`
- **Added**: `bench/metrics.py`
- **Added**: `bench/replay_c4.py`
- **Added**: `tests/bench/__init__.py`
- **Added**: `tests/bench/test_metrics.py`
- **Added**: `tests/synth/test_nli_backend.py`

## Diff Statistics
```text
Makefile                         |  26 ++++
 bench/__init__.py                |  11 ++
 bench/calibrate_nli.py           | 157 ++++++++++++++++++++++
 bench/data/c4_gold.jsonl         |   3 +
 bench/data/nli_calibration.jsonl |  45 +++++++
 bench/metrics.py                 | 281 +++++++++++++++++++++++++++++++++++++++
 bench/replay_c4.py               | 104 +++++++++++++++
 tests/bench/__init__.py          |   0
 tests/bench/test_metrics.py      | 128 ++++++++++++++++++
 tests/synth/test_nli_backend.py  |  61 +++++++++
 10 files changed, 816 insertions(+)
```

## Description & Context
bench/metrics.py (G4/G5 section; G2/G3 owners add theirs) scores run records - one JSON object per turn with the output JSON, the turn's citation allowlist and its synthesis.* telemetry - so Matangi's events.jsonl can be scored by mapping onto the same keys:
- G4: fabricated_id_count over every emitted label (citations, answer markers, claim citations) against the turn's allowlist; citation_support_rate / unsupported_claim_rate with each claim judged once per session by a lexical or cross-encoder judge; uncertainty_precision / recall against an optional gold file.
- G5: full_corpus_searches_on_refinement, sessions cleared, claims_retained_pct, delta_queries_per_refinement, pool-resolved targets; presentation-only turns must issue no retrieval, keep answer_version and cite a subset of the prior answer.
- --gate exits non-zero on any failure (fabricated IDs, support < 0.85, full-corpus search, cleared session, presentation violations).

bench/replay_c4.py replays the golden scenarios in harness order (SessionStore, classify(), upstream only when routed) and writes the records; stands in for `slrag replay` until the harness lands.

Golden results: lexical judge 20/20 claims supported, 0 fabricated IDs, 0 full-corpus searches, claims_retained_pct 0.75, 2 delta queries per refinement, uncertainty precision/recall 1.0. The independent cross-encoder judge also scores 20/20 on the lexical path's output.

bench/calibrate_nli.py sweeps the threshold per backend, scores the shipped verifier per pair kind, and times the NLI lock. Makefile: setup, setup-nli, test, test-nli, bench-c4, calibrate-nli, ablate-a3.

tests/bench/test_metrics.py covers the scorers and the gate exit code; tests/synth/test_nli_backend.py (opt-in, SLRAG_NLI=1 with the model baked) asserts 45/45 calibration pairs and G4/G5 gates on the golden replay under the cross-encoder - both pass locally.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
