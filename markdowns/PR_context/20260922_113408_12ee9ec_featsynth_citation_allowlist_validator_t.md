# Commit Context: 12ee9ec — feat(synth): citation allowlist validator + two-pass NLI verifier (D1 mid, D2 AM)

## Metadata
- **Commit SHA**: `12ee9ec7f06fd8bbbc037529cd115417aae0202e` (`12ee9ec`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T11:34:08+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): citation allowlist validator + two-pass NLI verifier (D1 mid, D2 AM)

Roadmap 4.7 (S-6 constrained citation vocabulary) and 4.8 (S-5 two-pass
provisional/committed streaming).

- CitationAllowlist: labels of exactly the chunks in this turn's context;
  strip_markers() / filter() are the unconditional post-hoc backstop (S-6
  layer 3) — every [.. § ..] marker is checked, malformed or out-of-list labels
  are fabricated; enum() feeds the generator's JSON-schema constraint (layer 2).
- ClaimVerifier.verify(): citation validity -> entailment (cited chunk |=
  sentence, threshold from config) -> numeral/proper-noun copy check.
  Per A §4.4 a sentence that cited a fabricated ID is stripped AND demoted to
  uncertainty (verifier.demote_on_fabricated, default on); other failures try
  re-attribution to an in-context chunk before RETRACT. No regeneration
  (HC-5). output_fabricated_count() is the fabricated_id_count == 0 CI metric.
- Scorers: deterministic LexicalEntailmentScorer (default, offline CI) and an
  optional CrossEncoderNLIScorer (nli-deberta-v3-small from a local, baked
  path only — never downloads; exposes contradiction() for Component 3).
- TwoPassStreamer: PROVISIONAL on arrival, verification in a worker thread
  concurrently with the next draft, COMMITTED/RETRACTED in arrival order;
  pending tasks are cancelled if the consumer stops early.
- config/synth.yaml: verifier.demote_on_fabricated,
  generator.openai_compatible.allow_remote.

23 tests (ordering + concurrency proofs, fabricated/numeral/entity cases).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Added**: `src/slrag/synth/verifier.py`
- **Added**: `tests/synth/test_verifier.py`

## Diff Statistics
```text
config/synth.yaml            |   2 +
 src/slrag/synth/verifier.py  | 430 +++++++++++++++++++++++++++++++++++++++++++
 tests/synth/test_verifier.py | 337 +++++++++++++++++++++++++++++++++
 3 files changed, 769 insertions(+)
```

## Description & Context
Roadmap 4.7 (S-6 constrained citation vocabulary) and 4.8 (S-5 two-pass
provisional/committed streaming).

- CitationAllowlist: labels of exactly the chunks in this turn's context;
  strip_markers() / filter() are the unconditional post-hoc backstop (S-6
  layer 3) — every [.. § ..] marker is checked, malformed or out-of-list labels
  are fabricated; enum() feeds the generator's JSON-schema constraint (layer 2).
- ClaimVerifier.verify(): citation validity -> entailment (cited chunk |=
  sentence, threshold from config) -> numeral/proper-noun copy check.
  Per A §4.4 a sentence that cited a fabricated ID is stripped AND demoted to
  uncertainty (verifier.demote_on_fabricated, default on); other failures try
  re-attribution to an in-context chunk before RETRACT. No regeneration
  (HC-5). output_fabricated_count() is the fabricated_id_count == 0 CI metric.
- Scorers: deterministic LexicalEntailmentScorer (default, offline CI) and an
  optional CrossEncoderNLIScorer (nli-deberta-v3-small from a local, baked
  path only — never downloads; exposes contradiction() for Component 3).
- TwoPassStreamer: PROVISIONAL on arrival, verification in a worker thread
  concurrently with the next draft, COMMITTED/RETRACTED in arrival order;
  pending tasks are cancelled if the consumer stops early.
- config/synth.yaml: verifier.demote_on_fabricated,
  generator.openai_compatible.allow_remote.

23 tests (ordering + concurrency proofs, fabricated/numeral/entity cases).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
