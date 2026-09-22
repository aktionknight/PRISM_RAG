# Commit Context: 56762a7 — feat(synth): verified LLM restyle for translation/tone presentation turns (audit W-9, I-7)

## Metadata
- **Commit SHA**: `56762a76bee9b74c1058c9c0d090190f39f8d75f` (`56762a7`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T13:48:59+05:30`
- **Branch**: `refine-ground/day1-day2`

## Commit Message
```text
feat(synth): verified LLM restyle for translation/tone presentation turns (audit W-9, I-7)

Presentation turns whose reason is in presentation.llm_restyle_reasons (translation, tone_change) now make one present_only call when the generator supports restyle (LLM backend). The result is all-or-nothing: every sentence must cite only the prior answer's labels (fabricated or empty citations fail), carry only numbers/names found in the claims it restates (copy check), and together the sentences must still cite every prior label. Anything less falls back to the deterministic prose re-render, recorded as synthesis.render restyle=fallback:<reason>. render_presentation takes the restyled claims and keeps the citations-subset hard assertion; the graph and answer_version are untouched. Restructure requests (bullets/shorten) never call the LLM; the extractive backend is unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/renderer.py`
- **Modified**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
config/synth.yaml                 |  1 +
 src/slrag/synth/engine.py         | 59 +++++++++++++++++++++++++++++----
 src/slrag/synth/renderer.py       | 15 +++++----
 tests/synth/test_engine_golden.py | 69 +++++++++++++++++++++++++++++++++++++++
 4 files changed, 131 insertions(+), 13 deletions(-)
```

## Description & Context
Presentation turns whose reason is in presentation.llm_restyle_reasons (translation, tone_change) now make one present_only call when the generator supports restyle (LLM backend). The result is all-or-nothing: every sentence must cite only the prior answer's labels (fabricated or empty citations fail), carry only numbers/names found in the claims it restates (copy check), and together the sentences must still cite every prior label. Anything less falls back to the deterministic prose re-render, recorded as synthesis.render restyle=fallback:<reason>. render_presentation takes the restyled claims and keeps the citations-subset hard assertion; the graph and answer_version are untouched. Restructure requests (bullets/shorten) never call the LLM; the extractive backend is unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
