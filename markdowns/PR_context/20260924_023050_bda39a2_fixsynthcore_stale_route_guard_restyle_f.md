# Commit Context: bda39a2 — fix(synth,core): stale-route guard, restyle_fallback, queued-turn and sweeper fixes (audit N-3, N-4/I-11, N-5/I-10)

## Metadata
- **Commit SHA**: `bda39a26f4ab8a6bf9f6eafa8f3a349db8d18b5a` (`bda39a2`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-24T02:30:50+05:30`
- **Branch**: `sivansh`

## Commit Message
```text
fix(synth,core): stale-route guard, restyle_fallback, queued-turn and sweeper fixes (audit N-3, N-4/I-11, N-5/I-10)

N-3: SynthesisEngine.classify() stamps TurnClassification.session_epoch with the engine's turn counter. handle_turn() re-classifies a precomputed classification whose epoch is stale (another turn ran on the session between classify and handle_turn) instead of trusting a route computed against old state; the classify telemetry payload gains "stale". Unstamped classifications (session_epoch None) are still trusted as before.

N-4 / I-11: PRESENTATION_ONLY results carry extensions["restyle_fallback"] (None, or the fallback reason: no_output, citation_outside_prior, copy_check_failed, content_dropped, no_llm_backend) so the UI can say "translation unavailable, showing original" instead of silently showing English. A translation/tone turn on the extractive backend now reports no_llm_backend.

N-5: a turn waiting on SessionStore.turn() when its session is end()ed now runs on a fresh session rather than on the retired one.

I-10: SessionStore.sweep_forever(interval_s=ttl_s/4) - a cancellable task the harness can run so idle sessions are reclaimed without traffic.

Frozen contract untouched (TurnClassification is a Component 4 internal type). 228 tests pass.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `src/slrag/core/session.py`
- **Modified**: `src/slrag/synth/engine.py`
- **Modified**: `src/slrag/synth/types.py`
- **Modified**: `tests/core/test_session.py`
- **Modified**: `tests/synth/test_engine_golden.py`

## Diff Statistics
```text
src/slrag/core/session.py         | 49 ++++++++++++++++++++++++++++-----------
 src/slrag/synth/engine.py         | 32 ++++++++++++++++++-------
 src/slrag/synth/types.py          |  3 +++
 tests/core/test_session.py        | 38 ++++++++++++++++++++++++++++++
 tests/synth/test_engine_golden.py | 33 ++++++++++++++++++++++++++
 5 files changed, 133 insertions(+), 22 deletions(-)
```

## Description & Context
N-3: SynthesisEngine.classify() stamps TurnClassification.session_epoch with the engine's turn counter. handle_turn() re-classifies a precomputed classification whose epoch is stale (another turn ran on the session between classify and handle_turn) instead of trusting a route computed against old state; the classify telemetry payload gains "stale". Unstamped classifications (session_epoch None) are still trusted as before.

N-4 / I-11: PRESENTATION_ONLY results carry extensions["restyle_fallback"] (None, or the fallback reason: no_output, citation_outside_prior, copy_check_failed, content_dropped, no_llm_backend) so the UI can say "translation unavailable, showing original" instead of silently showing English. A translation/tone turn on the extractive backend now reports no_llm_backend.

N-5: a turn waiting on SessionStore.turn() when its session is end()ed now runs on a fresh session rather than on the retired one.

I-10: SessionStore.sweep_forever(interval_s=ttl_s/4) - a cancellable task the harness can run so idle sessions are reclaimed without traffic.

Frozen contract untouched (TurnClassification is a Component 4 internal type). 228 tests pass.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
