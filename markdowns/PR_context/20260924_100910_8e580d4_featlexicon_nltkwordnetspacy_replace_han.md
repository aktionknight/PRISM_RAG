# Commit Context: 8e580d4 — feat(lexicon): NLTK/WordNet/spaCy replace hand-written word lists (corpus-independent)

## Metadata
- **Commit SHA**: `8e580d4bb6d2be85941ddb5d7cc94e40f706791c` (`8e580d4`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T10:09:10+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
feat(lexicon): NLTK/WordNet/spaCy replace hand-written word lists (corpus-independent)

The lexical rules no longer depend on word lists written for the brief's examples; they come from general English resources, so they behave the same on any document set:
- stopwords: NLTK's English list (+ text.extra_stopwords for request/modal words NLTK omits); the hand-written list is gone.
- stemming: NLTK Porter stemmer in the shared tokeniser (reimbursed/reimbursement and cancelled/cancellations now share a stem); all goldens reproduce unchanged.
- negation cues: NLTK's nltk.sentiment.util.NEGATION list (+ verifier.negation_extra for closed-class cues it lacks: without, nor, neither, cannot, nobody).
- antonyms: WordNet direct antonyms plus adjective satellites (domestic/international, mandatory/optional, open/closed, eligible/ineligible). The 11 hand-picked verifier.antonym_pairs are removed; verifier.extra_antonym_pairs (empty by default) covers vocabulary WordNet lacks.

synth/lexicon.py loads everything from disk only (text.nltk_data_path, verifier.spacy.model_path). scripts/bake_nli_model.py --nltk --spacy bakes them at build time (make setup; the CI offline job now bakes them, cached). nltk and spacy become core dependencies; the [ner] extra is folded in.

Measured trade-off: the lexical fallback verifier goes from 7 to 9 false accepts on the 24 unsupported calibration pairs, because WordNet has no refund/forfeit pair and "optional" vs "must include" is not a lexical antonym. The hand list had been partly fitted to those very pairs. The NLI verifier stays at 45/45 with 0 false rejects. New tests show WordNet antonyms catching unseen vocabulary.

Constraint extraction (the example-shaped delta.slots) is replaced in a follow-up commit.

276 tests pass (3 opt-in skipped) with the models baked.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `.github/workflows/c4-ci.yml`
- **Modified**: `Makefile`
- **Modified**: `config/synth.yaml`
- **Modified**: `pyproject.toml`
- **Modified**: `scripts/bake_nli_model.py`
- **Added**: `src/slrag/synth/lexicon.py`
- **Modified**: `src/slrag/synth/text.py`
- **Modified**: `src/slrag/synth/verifier.py`
- **Modified**: `tests/synth/test_text.py`
- **Modified**: `tests/synth/test_verifier.py`

## Diff Statistics
```text
.github/workflows/c4-ci.yml  |  12 ++-
 Makefile                     |   7 +-
 config/synth.yaml            |  28 ++-----
 pyproject.toml               |   6 +-
 scripts/bake_nli_model.py    |  32 ++++++-
 src/slrag/synth/lexicon.py   | 193 +++++++++++++++++++++++++++++++++++++++++++
 src/slrag/synth/text.py      |  20 +++--
 src/slrag/synth/verifier.py  |  43 ++++++----
 tests/synth/test_text.py     |  14 ++--
 tests/synth/test_verifier.py |  28 +++++--
 10 files changed, 317 insertions(+), 66 deletions(-)
```

## Description & Context
The lexical rules no longer depend on word lists written for the brief's examples; they come from general English resources, so they behave the same on any document set:
- stopwords: NLTK's English list (+ text.extra_stopwords for request/modal words NLTK omits); the hand-written list is gone.
- stemming: NLTK Porter stemmer in the shared tokeniser (reimbursed/reimbursement and cancelled/cancellations now share a stem); all goldens reproduce unchanged.
- negation cues: NLTK's nltk.sentiment.util.NEGATION list (+ verifier.negation_extra for closed-class cues it lacks: without, nor, neither, cannot, nobody).
- antonyms: WordNet direct antonyms plus adjective satellites (domestic/international, mandatory/optional, open/closed, eligible/ineligible). The 11 hand-picked verifier.antonym_pairs are removed; verifier.extra_antonym_pairs (empty by default) covers vocabulary WordNet lacks.

synth/lexicon.py loads everything from disk only (text.nltk_data_path, verifier.spacy.model_path). scripts/bake_nli_model.py --nltk --spacy bakes them at build time (make setup; the CI offline job now bakes them, cached). nltk and spacy become core dependencies; the [ner] extra is folded in.

Measured trade-off: the lexical fallback verifier goes from 7 to 9 false accepts on the 24 unsupported calibration pairs, because WordNet has no refund/forfeit pair and "optional" vs "must include" is not a lexical antonym. The hand list had been partly fitted to those very pairs. The NLI verifier stays at 45/45 with 0 false rejects. New tests show WordNet antonyms catching unseen vocabulary.

Constraint extraction (the example-shaped delta.slots) is replaced in a follow-up commit.

276 tests pass (3 opt-in skipped) with the models baked.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
