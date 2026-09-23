# Commit Context: e4e4975 — feat(verifier): calibrated NLI backend, sentence-window entailment, antonym-aware polarity (audit I-4, N-1, W-2)

## Metadata
- **Commit SHA**: `e4e4975f12627232b00e4b933e815c4014b3c213` (`e4e4975`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:46:48+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(verifier): calibrated NLI backend, sentence-window entailment, antonym-aware polarity (audit I-4, N-1, W-2)

I-4: scripts/bake_nli_model.py fetches cross-encoder/nli-deberta-v3-small into verifier.cross_encoder.model_path at build time (never at runtime, G1) and refuses a model whose id2label order differs from verifier.cross_encoder.labels. models/ is gitignored.

Calibration on bench/data/nli_calibration.jsonl (45 pairs from the fixture corpus; verbatim, paraphrase, negation, antonym, value, swap, unrelated, unsupported-extra) exposed two defects, both fixed here:
- The cross-encoder scored a short claim against the whole multi-sentence chunk and rejected 4/9 verbatim sentences (P(entail) ~0.001 for "Venue A holds up to 40 people."). CrossEncoderNLIScorer now scores the whole chunk plus each window of premise_window_sentences sentences in one predict call and keeps the max. Shipped verifier on the cross-encoder: 45/45 correct at the new verifier.cross_encoder.entailment_threshold 0.5 (raw scorer flat from 0.25 to 0.95).
- The lexical verifier (CI default) accepted 12/24 unsupported pairs. PolarityCheck now XORs negation parity with antonym swaps from verifier.antonym_pairs (refund/forfeit, accept/reject, include/exclude, require/optional, ...), ignores verifier.negation_exempt phrases ("not only", "no more than") and aligns finer clauses split at verifier.clause_splitters (", and", "but", ...). Lexical false accepts 12 -> 7; the remaining ones (value/role swaps, extra detail) are why production should run the cross-encoder.

threshold_for(config) picks the per-backend threshold (NLI probabilities and lexical overlap are different scales).

W-2: the CrossEncoder lock is not a bottleneck. 8 sentences through concurrent threads take 185 ms vs 140 ms as one batch; per-sentence scoring is 22.7 ms p50 / 27.1 ms max on CPU, inside the 30 ms per-sentence budget.

Default backend stays lexical so CI and golden replay run offline.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `.gitignore`
- **Modified**: `config/synth.yaml`
- **Added**: `scripts/bake_nli_model.py`
- **Modified**: `src/slrag/synth/verifier.py`
- **Modified**: `tests/synth/test_verifier.py`

## Diff Statistics
```text
.gitignore                   |   1 +
 config/synth.yaml            |  20 ++++++++-
 scripts/bake_nli_model.py    |  67 +++++++++++++++++++++++++++
 src/slrag/synth/verifier.py  | 105 +++++++++++++++++++++++++++++++++++++------
 tests/synth/test_verifier.py |  85 +++++++++++++++++++++++++++++++++++
 5 files changed, 264 insertions(+), 14 deletions(-)
```

## Description & Context
I-4: scripts/bake_nli_model.py fetches cross-encoder/nli-deberta-v3-small into verifier.cross_encoder.model_path at build time (never at runtime, G1) and refuses a model whose id2label order differs from verifier.cross_encoder.labels. models/ is gitignored.

Calibration on bench/data/nli_calibration.jsonl (45 pairs from the fixture corpus; verbatim, paraphrase, negation, antonym, value, swap, unrelated, unsupported-extra) exposed two defects, both fixed here:
- The cross-encoder scored a short claim against the whole multi-sentence chunk and rejected 4/9 verbatim sentences (P(entail) ~0.001 for "Venue A holds up to 40 people."). CrossEncoderNLIScorer now scores the whole chunk plus each window of premise_window_sentences sentences in one predict call and keeps the max. Shipped verifier on the cross-encoder: 45/45 correct at the new verifier.cross_encoder.entailment_threshold 0.5 (raw scorer flat from 0.25 to 0.95).
- The lexical verifier (CI default) accepted 12/24 unsupported pairs. PolarityCheck now XORs negation parity with antonym swaps from verifier.antonym_pairs (refund/forfeit, accept/reject, include/exclude, require/optional, ...), ignores verifier.negation_exempt phrases ("not only", "no more than") and aligns finer clauses split at verifier.clause_splitters (", and", "but", ...). Lexical false accepts 12 -> 7; the remaining ones (value/role swaps, extra detail) are why production should run the cross-encoder.

threshold_for(config) picks the per-backend threshold (NLI probabilities and lexical overlap are different scales).

W-2: the CrossEncoder lock is not a bottleneck. 8 sentences through concurrent threads take 185 ms vs 140 ms as one batch; per-sentence scoring is 22.7 ms p50 / 27.1 ms max on CPU, inside the 30 ms per-sentence budget.

Default backend stays lexical so CI and golden replay run offline.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
