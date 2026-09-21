# Streaming Live RAG — Team Coordination & 3-Day Sprint Plan
## Document C — Parallel Work Distribution (Samsung Theme 4, Team of 4)

> Companion to **A — Final Architecture** and **B — Final Engineering Roadmap**. This document answers: who builds what, in what order, with what stubs, syncing how, and shipping to which surfaces.

---

## 1. Team → Architecture Mapping

The natural fault line in the committed architecture is between the **front half** (turn a stream into evidence) and the **back half** (turn evidence into a trustworthy, versioned answer) — not a three-way split by phrase. This keeps ownership boundaries clean and avoids two people editing the same files.

| Person | Owns | Why this boundary |
|---|---|---|
| **Diya** | **Component 1 — Retrieval Controller** (cascade + speculation) | Self-contained: consumes `TranscriptChunk`, emits `ControllerDecision`. Zero dependency on retrieval or synthesis internals. |
| **Aakrit** | **Component 2 — Decomposition** + **Component 3 — Corpus Retrieval & Fusion** | Decomposition's output (`sub_queries`) is only useful in the context of what gets retrieved with it — tight iteration loop, one owner avoids the interface being renegotiated daily. |
| **Sivansh** | **Component 4 — Session Refinement + Corpus Grounding** (ClaimGraph, delta engine, citation allowlist, verifier, uncertainty) | Refinement and grounding share the *same data structure* (the Claim, with its citations and preconditions) — splitting them would mean two people constantly editing `claims.py`. |
| **Matangi** | **Component 5 — Telemetry** + the **integration harness** (replay CLI, WS server shell, Grafana) | Telemetry taps every other module and has the least sequential dependency on any one person finishing first — the natural owner of the thing that wires everyone together. |

Matangi is therefore also the **de facto integration lead** for the sprint, not just the telemetry engineer.

---

## 2. The Enabling Move: Freeze Contracts Before Anyone Writes Logic

With 4 people and 3 days, the single biggest risk is **interface drift** — Diya changes a field name on day 2 and silently breaks Aakrit's code. The fix is a **2–3 hour Day-1-morning session, all four in one room**, producing frozen Pydantic schemas nobody edits alone afterward.

```python
# core/schemas.py — FROZEN after the Day 0 session. Changes require a ping to all 4.

class TranscriptChunk(BaseModel):
    t_s: float; text: str; is_final: bool

class ControllerDecision(BaseModel):        # Diya emits this
    t_s: float; decision: Literal["WAIT", "RETRIEVE", "NO_RETRIEVAL"]
    reason: str; confidence: float

class SubIntent(BaseModel):                 # Aakrit emits this
    intent_id: str; facet: str; query_nl: str; search_string: str; novel: bool

class RetrievedChunk(BaseModel):            # Aakrit emits this
    chunk_id: str; doc_id: str; section_id: str; text: str; score: float

class Claim(BaseModel):                     # Sivansh owns this
    claim_id: str; facet: str; text: str; citations: list[str]
    preconditions: dict; status: Literal["active", "superseded"]; introduced_in_version: int

class AnswerOutput(BaseModel):              # the 5 required keys + extensions — Sivansh renders this
    retrieval_events: list[dict]; sub_queries: list[str]
    answer: str; citations: list[str]; uncertainty: str
    session_id: str; turn_id: int; answer_version: int

class TelemetryEvent(BaseModel):            # Matangi consumes ALL of the above to log them
    event_id: str; session_id: str; turn_id: int; ts_stream_s: float
    component: str; latency_ms: float; payload: dict
```

**Also freeze at that session:**
- The **facet taxonomy** — 5–8 facets from a 20-minute corpus skim. Good enough for Day 1; refine later without breaking the interface.
- A **shared mini test corpus + one golden example** — transcribe the brief's own Example 1 into a JSONL fixture (`golden_example.jsonl`). All four people run against this from hour one.

---

## 3. Stub Strategy — Everyone Codes Against Fakes on Day 1

Immediately after the contract session, **Matangi builds a "walking skeleton"** — the full pipeline where every stage is a stub returning canned, schema-valid output. This is the single highest-leverage task on Day 1: it turns integration from a Day-3 surprise into a non-event.

```python
# stubs/fake_controller.py
def fake_controller(chunk: TranscriptChunk) -> ControllerDecision:
    # deterministic: fires RETRIEVE on the 2nd and 3rd chunk of the golden example
    return ControllerDecision(t_s=chunk.t_s, decision="RETRIEVE",
                               reason="stub", confidence=0.9)

# stubs/fake_decomposer.py
def fake_decompose(prefix: str) -> list[SubIntent]:
    return [SubIntent(intent_id="i1", facet="venue_capacity",
                       query_nl="venue capacity for 30 in Pune",
                       search_string="Pune venue capacity 30", novel=True)]

# stubs/fake_retriever.py
def fake_retrieve(sub_intent: SubIntent) -> list[RetrievedChunk]:
    return [RetrievedChunk(chunk_id="Doc_12#2#0", doc_id="Doc_12",
                            section_id="2", text="Venue A holds up to 40 people.", score=0.9)]

# stubs/fake_synthesis.py
def fake_synthesize(claims) -> AnswerOutput:
    return AnswerOutput(retrieval_events=[], sub_queries=["..."],
                         answer="Stub answer.", citations=["Doc_12 §2"],
                         uncertainty="", session_id="s1", turn_id=1, answer_version=1)
```

By **end of Day 1**, `slrag replay --stream golden_example.jsonl` runs the *entire* pipeline end-to-end on stub logic and produces a schema-valid `events.jsonl`. From then on, each person swaps **their own stub for real logic** and re-runs the same golden replay to confirm they haven't broken the contract — nobody needs anybody else's code finished to make progress.

---

## 4. 3-Day Timeline

| When | Diya (Controller) | Aakrit (Decompose + Retrieve) | Sivansh (Refine + Ground) | Matangi (Telemetry + Integration) |
|---|---|---|---|---|
| **D1 AM** | *(all 4)* Contract freeze session + facet taxonomy + golden example fixture | | | |
| **D1 mid** | Stage 0–1 (suppression + content floor) against fake corpus | Chunker + BM25/dense index build on shared corpus | ClaimGraph model + citation allowlist validator (against fixture chunks) | Walking-skeleton CLI wiring all 4 stubs together |
| **D1 PM** | Stage 2 BM25 discriminativeness probe | RRF fusion + cross-encoder rerank (real, against real index) | Delta engine skeleton (turn classifier + impact analysis, fixture claims) | JSONL sink + event bus instrumented into the skeleton |
| **D1 EOD sync (30 min)** | **Checkpoint 1:** run golden replay end-to-end on stubs. Confirm schema compliance. Flag any contract gaps now, while cheap to fix. | | | |
| **D2 AM** | Stage 3 embedding stability + cascade assembly | Monotonic IntentSet (facet + embedding diff) | Two-pass streaming + NLI/citation verifier | Swap real controller into skeleton as Diya finishes; OTel spans |
| **D2 mid** | Speculation manager (branch cancel / pool demotion) | Retrieval-overlap merge (anti-fragmentation) | Uncertainty coverage matrix | Grafana dashboard scaffold; WS server shell + frontend skeleton |
| **D2 PM** | Threshold calibration sweep against golden + adversarial cases | Facet-quota context assembly + contradiction gating | Wire delta engine → real ClaimGraph → real generator prompt | Swap real decomposer + retriever into skeleton |
| **D2 EOD sync (30 min)** | **Checkpoint 2:** full real pipeline (no stubs left except maybe LLM tie-break) runs on golden Examples 1–3. Freeze scope for D3 — no new features. | | | |
| **D3 AM** | Bug-fix + tune false-trigger rate | Bug-fix + build baseline batch RAG for comparison | Fabricated-ID CI assertion + refinement telemetry fields | Trace-coverage invariant suite + cost model |
| **D3 mid** | Help with ablations (A2: cascade vs +LLM-tiebreak) | Help with ablations (A1: hybrid vs dense-only) | Help with edge-case write-ups (self-correction, contradiction) | Assemble benchmark report + package `docker compose up`; rehearse offline |
| **D3 PM** | *(all 4)* Storyboard + record the 6-beat demo video together — each person narrates their own component's beat | | | |
| **D3 EOD** | Submit: repo, architecture brief, eval report, video, telemetry schema | | | |

**Sync cadence:** two 30-minute syncs per day (end of D1, end of D2) plus a shared channel where any contract change is posted *before* it's merged, not after.

---

## 5. Git & Process

- **Trunk-based**, short-lived branches: `controller/`, `decompose-retrieve/`, `refine-ground/`, `telemetry/`.
- One PR per module per day minimum — small, reviewable diffs, not one giant Day-3 merge.
- **CI runs the golden replay on every PR** — if a change breaks `events.jsonl`'s schema or the Example-1/2/3 reproduction, the PR is red. This is what makes 4 people editing one pipeline in parallel survivable.
- **Feature-flag stub vs. real**: `config/app.yaml` → `use_stub_controller: true/false` (and equivalents for the other 3 modules). If someone's module isn't ready by an integration checkpoint, the skeleton keeps running on their stub instead of blocking the other three.

---

## 6. Final Output Projection — Three Surfaces

| Surface | Purpose | Built by | First usable |
|---|---|---|---|
| **CLI** (`slrag replay / chat / score`) | The graded path — scoring, CI, ablations | Matangi (harness) + everyone wires their module in | End of Day 1 (on stubs); real by Day 2 evening |
| **Local server + frontend** (FastAPI WS + React 3-pane UI) | The demo path — live typing/mic, video recording | Matangi builds the WS shell + mocked messages Day 1; Diya/Aakrit/Sivansh's real events replace the mocks as each lands | Skeleton Day 1 PM; fully real Day 2 PM |
| **Grafana dashboard** (OTel/Prometheus, opt-in profile) | Telemetry beat in the demo video, gate readouts | Matangi | Scaffolded Day 2 AM; populated with real spans by Day 2 PM |

**Priority order:** the CLI is what actually gets scored, so it must be real first. The frontend and Grafana exist purely to make the six demo beats visually obvious in one frame; they can lag the CLI by half a day without risk, since both consume the same `events.jsonl` / WS stream the CLI already produces.

---

*Read alongside: **A_FINAL_ARCHITECTURE.md** (what is built) and **B_FINAL_ENGINEERING_ROADMAP.md** (the full 5-phase plan this sprint compresses into 3 days).*
