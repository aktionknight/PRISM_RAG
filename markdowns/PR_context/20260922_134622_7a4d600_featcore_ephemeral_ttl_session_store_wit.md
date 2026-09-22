# Commit Context: 7a4d600 — feat(core): ephemeral TTL session store with per-session turn serialisation (audit W-7, W-3)

## Metadata
- **Commit SHA**: `7a4d600150d8314a95c563b5f0514c207e46ac6c` (`7a4d600`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T13:46:22+05:30`
- **Branch**: `refine-ground/day1-day2`

## Commit Message
```text
feat(core): ephemeral TTL session store with per-session turn serialisation (audit W-7, W-3)

Roadmap 4.1 / HC-4. SessionStore holds any destroy()-able session object (SynthesisEngine in practice) in process memory only. Sessions are destroyed on end(), on idle expiry past ttl_s (swept lazily on every access, or via sweep()), on LRU eviction beyond max_sessions, and on close(). store.turn(session_id) serialises turns within a session - ClaimGraph allows one open revision - while other sessions run concurrently; a session with a running or queued turn is never expired or evicted, and end() mid-turn defers destroy() until the turn leaves. Settings in config/app.yaml session: (ttl_s, max_sessions).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- General / Infrastructure
- Tests & Verification

## File Changes
- **Modified**: `config/app.yaml`
- **Added**: `src/slrag/core/session.py`
- **Added**: `tests/core/test_session.py`

## Diff Statistics
```text
config/app.yaml            |   6 ++
 src/slrag/core/session.py  | 153 ++++++++++++++++++++++++++++++++++++++++++
 tests/core/test_session.py | 161 +++++++++++++++++++++++++++++++++++++++++++++
 3 files changed, 320 insertions(+)
```

## Description & Context
Roadmap 4.1 / HC-4. SessionStore holds any destroy()-able session object (SynthesisEngine in practice) in process memory only. Sessions are destroyed on end(), on idle expiry past ttl_s (swept lazily on every access, or via sweep()), on LRU eviction beyond max_sessions, and on close(). store.turn(session_id) serialises turns within a session - ClaimGraph allows one open revision - while other sessions run concurrently; a session with a running or queued turn is never expired or evicted, and end() mid-turn defers destroy() until the turn leaves. Settings in config/app.yaml session: (ttl_s, max_sessions).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
