# Commit Context: 6d27593 — feat(generator): SSE token streaming with incremental claim parsing (audit W-1, I-3)

## Metadata
- **Commit SHA**: `6d275937a3b84bd048ce9b4be727a4186d743262` (`6d27593`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T13:54:17+05:30`
- **Branch**: `refine-ground/day1-day2`

## Commit Message
```text
feat(generator): SSE token streaming with incremental claim parsing (audit W-1, I-3)

With generator.openai_compatible.stream: true, OpenAICompatibleClient.stream() sends the same single request with stream: true (plus stream_options.include_usage) and yields content deltas as server-sent events arrive; usage comes from the final chunk or is estimated. ClaimStreamParser tracks JSON objects by brace depth outside strings and yields each claim the moment its object closes, so the two-pass streamer verifies and shows sentence 1 while the model is still generating sentence 2 - true sentence-level provisional -> committed streaming instead of waiting for the whole response. It matches parse_claim_objects on every output shape (wrapper, bare list, JSON lines, fences, nested keys, text-less objects, garbage) and counts a truncated claim exactly once. A dropped connection keeps the claims already streamed; no retry (HC-5: still one request per turn). GenerationUsage.first_draft_ms (reported in synthesis.generation telemetry) measures LLM start -> first complete claim for the 300 ms first-token budget. Clients without stream() (and stream: false) keep the blocking path unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/synth.yaml`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/generator.py`
- **Modified**: `src/slrag/synth/types.py`
- **Modified**: `tests/helpers.py`
- **Modified**: `tests/synth/test_engine_golden.py`
- **Modified**: `tests/synth/test_generator.py`

## Diff Statistics
```text
config/synth.yaml                 |   2 +
 src/slrag/synth/engine.py         |   1 +
 src/slrag/synth/generator.py      | 265 +++++++++++++++++++++++++++++++++-----
 src/slrag/synth/types.py          |   1 +
 tests/helpers.py                  |  33 +++++
 tests/synth/test_engine_golden.py |  36 +++++-
 tests/synth/test_generator.py     | 126 +++++++++++++++++-
 7 files changed, 429 insertions(+), 35 deletions(-)
```

## Description & Context
With generator.openai_compatible.stream: true, OpenAICompatibleClient.stream() sends the same single request with stream: true (plus stream_options.include_usage) and yields content deltas as server-sent events arrive; usage comes from the final chunk or is estimated. ClaimStreamParser tracks JSON objects by brace depth outside strings and yields each claim the moment its object closes, so the two-pass streamer verifies and shows sentence 1 while the model is still generating sentence 2 - true sentence-level provisional -> committed streaming instead of waiting for the whole response. It matches parse_claim_objects on every output shape (wrapper, bare list, JSON lines, fences, nested keys, text-less objects, garbage) and counts a truncated claim exactly once. A dropped connection keeps the claims already streamed; no retry (HC-5: still one request per turn). GenerationUsage.first_draft_ms (reported in synthesis.generation telemetry) measures LLM start -> first complete claim for the 300 ms first-token budget. Clients without stream() (and stream: false) keep the blocking path unchanged.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
