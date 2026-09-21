# Commit Context: 94be7d9 — feat(synth): ClaimGraph + Component 4 internal types (D1 mid)

## Metadata
- **Commit SHA**: `94be7d9ab8b7145b749748858f884073b2f499a3` (`94be7d9`)
- **Author**: Sivansh <sivansh.work2005@gmail.com>
- **Date**: `2026-09-22T02:12:19+05:30`
- **Branch**: `worktree-refine-ground-d1-d2`

## Commit Message
```text
feat(synth): ClaimGraph + Component 4 internal types (D1 mid)

Roadmap 4.2 — the answer as a data structure (Rule 3, S-4).

- src/slrag/synth/claims.py: ClaimGraph over the frozen core.schemas.Claim.
  Mutations only via a Revision (context manager, atomic commit, abort on
  exception); each committed revision bumps the version exactly once and
  records a VersionLineage {from,to,retained,superseded,added}. Superseding
  flips status only, so retained claims stay byte-for-byte identical.
  Claims may only cite labels admitted via register_evidence(): a closed
  allowlist at the data-structure level, so fabricated IDs cannot enter the
  graph even if every upstream check were bypassed. snapshot(v) and
  citations(version=v) drive the V1<->V2 slider and the presentation-only
  subset assertion. destroy() gives HC-4 session-end semantics.
- ClaimMeta carries what the frozen Claim cannot (confidence, superseded_by,
  supporting chunks) without widening the contract.
- src/slrag/synth/types.py: Component-4-internal contract shared by the
  delta engine, generator, verifier, uncertainty and renderer modules
  (DraftClaim, VerificationResult, StreamEvent, DeltaPlan, RefinementReport,
  CoverageRow, RetrieveFn / EvidencePoolView ports to Component 3).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

## Architectural Components Impacted
- Component 4: Session Refinement & Corpus Grounding
- General / Infrastructure

## File Changes
- **Added**: `src/slrag/synth/claims.py`
- **Added**: `src/slrag/synth/types.py`
- **Added**: `tests/synth/test_claims.py`

## Diff Statistics
```text
src/slrag/synth/claims.py  | 306 +++++++++++++++++++++++++++++++++++++++++++++
 src/slrag/synth/types.py   | 239 +++++++++++++++++++++++++++++++++++
 tests/synth/test_claims.py | 118 +++++++++++++++++
 3 files changed, 663 insertions(+)
```

## Description & Context
Roadmap 4.2 — the answer as a data structure (Rule 3, S-4).

- src/slrag/synth/claims.py: ClaimGraph over the frozen core.schemas.Claim.
  Mutations only via a Revision (context manager, atomic commit, abort on
  exception); each committed revision bumps the version exactly once and
  records a VersionLineage {from,to,retained,superseded,added}. Superseding
  flips status only, so retained claims stay byte-for-byte identical.
  Claims may only cite labels admitted via register_evidence(): a closed
  allowlist at the data-structure level, so fabricated IDs cannot enter the
  graph even if every upstream check were bypassed. snapshot(v) and
  citations(version=v) drive the V1<->V2 slider and the presentation-only
  subset assertion. destroy() gives HC-4 session-end semantics.
- ClaimMeta carries what the frozen Claim cannot (confidence, superseded_by,
  supporting chunks) without widening the contract.
- src/slrag/synth/types.py: Component-4-internal contract shared by the
  delta engine, generator, verifier, uncertainty and renderer modules
  (DraftClaim, VerificationResult, StreamEvent, DeltaPlan, RefinementReport,
  CoverageRow, RetrieveFn / EvidencePoolView ports to Component 3).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
