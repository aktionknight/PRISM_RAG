# Proposal: `core/schemas.py` v1.1 — additive fields for Component 4 (audit C-1 / C-2 / I-1)

**Author:** Sivansh (Component 4) · **Needs:** acknowledgement from Diya, Aakrit and Matangi (C_TEAM_COORDINATION §2: the contract changes only with all four) · **Status:** PROPOSED, not applied. `core/schemas.py` is unchanged on every branch.

## Why

Two audits (`markdowns/audits/20260922_113527_*`, `20260922_135454_*`) keep the Component 4 verdict at **CONDITIONAL** for one reason. Fields the architecture requires in the output (A_FINAL_ARCHITECTURE §6) have no home in the frozen models, so they travel in a side dict, `SynthesisResult.extensions`:

| Needed by | Field | Today |
|---|---|---|
| G5 on screen, demo beat 4 | `version_lineage` (`from`, `to`, `retained`, `superseded`, `added`) | `extensions["version_lineage"]` |
| Example 3, presentation-only | `retrieval_required`, `suppression_reason` | `extensions[...]` |
| UI citation chips, claim diff | `claims` (active claims with facet + citations) | `extensions["claims"]` |
| HC-3 clarification branch | `clarification_questions` | `extensions[...]`; also folded into `uncertainty` |
| Translation / tone UX (I-11) | `restyle_fallback` | `extensions[...]` |
| Claim-level trust, supersede chain | `Claim.confidence`, `Claim.superseded_by`, status `"retracted"` | `ClaimMeta` (Component 4 internal) |

`SynthesisResult.to_json()` already emits all of these after the five required keys. The risk is at the **boundary**:
- If the harness or WS server serialises `AnswerOutput` rather than `to_json()`, lineage and suppression silently disappear from `events.jsonl` and the UI.
- Nothing in the contract test would notice.

## Option A (recommended): v1.1, additive and optional only

Every new field has a default, so every existing producer, stub and fixture stays valid and nothing is renamed or retyped. The contract test gains the new fields at the end of each model; the first N fields keep their pinned order.

```python
class Claim(BaseModel):                     # Sivansh owns this
    claim_id: str; facet: str; text: str; citations: list[str]
    preconditions: dict; status: Literal["active", "superseded", "retracted"]; introduced_in_version: int
    # v1.1 (additive)
    confidence: float = 1.0
    superseded_by: list[str] = []

class AnswerOutput(BaseModel):              # the 5 required keys + extensions — Sivansh renders this
    retrieval_events: list[dict]; sub_queries: list[str]
    answer: str; citations: list[str]; uncertainty: str
    session_id: str; turn_id: int; answer_version: int
    # v1.1 (additive)
    retrieval_required: bool = True
    suppression_reason: str | None = None
    claims: list[dict] = []
    version_lineage: dict | None = None
    clarification_questions: list[str] = []
```

**Component 4 follow-up (one commit, after sign-off):**
- `build_answer_output` fills the new fields.
- `extensions` keeps only non-contract extras: `controller_decisions`, `telemetry`, `restyle_fallback`.
- `render_output_json` is unchanged; the key order is still the 5 required keys first.

**Impact per owner:**
- **Diya (C1), Aakrit (C2/C3):** none. You neither produce nor consume `Claim` / `AnswerOutput`.
- **Matangi (C5 + harness):** log `AnswerOutput.model_dump()` as before; lineage and suppression now arrive without special-casing. `bench/metrics.py` already reads either shape.
- **Stubs:** `fake_synthesize` stays valid because every new field has a default.

**Why not also `"retracted"` claims in the graph?** Retracted sentences never enter the `ClaimGraph` (they are demoted to uncertainty before commit). `"retracted"` on `Claim.status` exists so the UI can render a retracted sentence from the stream with the same model. It is optional; drop it if the team prefers.

## Option B: keep v1.0 and agree a harness rule

No schema change. The team agrees instead that:
1. the harness and WS server always serialise `SynthesisResult.to_json()`, never the bare `AnswerOutput`;
2. CI asserts `version_lineage` and `suppression_reason` appear in `events.jsonl` for the golden refinement and presentation turns (`bench.metrics` can host the assertion).

Cheaper today, but the invariant then lives in a convention plus a test instead of in the type.

## Decision needed

Pick **A** or **B** at the next sync. Component 4 is ready for either:
- **Option A** is one commit touching `schemas.py` (all four owners sign), `renderer.py` and the contract test.
- **Option B** needs no Component 4 change beyond the CI assertion.
