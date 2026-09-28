# Theme 4 — Streaming Live RAG
## Document 1 of 3: Objectives, Requirements & Compliance Register

> **Source:** *Streaming Live RAG — Real-Time Incremental Retrieval, Multi-Intent Decomposition, and State-Preserving Answer Refinement* (Samsung Electronics, Theme 4 Guide).
> **Purpose of this document:** a lossless extraction of everything the brief demands, restated as testable requirements. Every later design decision in Documents 2 and 3 traces back to an ID here.

---

## 1. The Problem, Restated

Standard RAG is a **batch turn cycle**: user finishes → query submitted → knowledge base searched → answer synthesised → response. The brief argues this breaks down in conversational voice and real-time support along three axes:

| Failure Mode | What Actually Goes Wrong | Our Design Answer (forward ref) |
|---|---|---|
| **High conversational latency** | Waiting for a complete multi-sentence utterance before searching produces multi-second dead air. | Speculative retrieval on stable prefixes (§S-1, Doc 2) |
| **Compound / multi-intent requests** | One breath contains several implied needs — capacity *and* cancellation terms *and* catering. | Monotonic intent-set diffing (§S-2, Doc 2) |
| **Late-arriving constraints** | *"Actually, the trip was international."* Systems either discard prior context or restart the whole pipeline. | Claim-graph delta engine (§S-4, Doc 2) |

**The engine we must build is event-driven, not request-driven.** That single sentence is the architectural north star: there is no "the query". There is a stream of transcript chunks, and the system continuously decides what to do with the prefix it has so far.

---

## 2. The Four Primary Objectives

These are the brief's own numbered targets. Each is expanded into acceptance behaviour.

### O1 — Listens Incrementally
> *Processes timestamped transcript chunks in real time, predicting retrieval intent before the user finishes speaking.*

**Acceptance behaviour**
- Accepts a stream of `(timestamp_s, text_fragment)` events, not a finished string.
- Emits a **ternary decision per chunk**: `WAIT` | `RETRIEVE` | `NO-RETRIEVAL`.
- At least one retrieval is *dispatched* strictly before the `utterance_end` event on eligible queries.
- Records the decision, the reason, and the wall-clock timestamp for every chunk — including chunks where the decision was to do nothing.

### O2 — Decomposes Multi-Intent Queries
> *Identifies and parallelizes retrieval for multiple discrete sub-questions embedded within a single utterance.*

**Acceptance behaviour**
- Produces a `sub_queries[]` array of **self-contained, search-ready** questions (anaphora and ellipsis resolved — `"the cancellation policy"` must become `"cancellation terms and refund policies for Pune workshop venues"`).
- Dispatches sub-query retrievals **concurrently**, not sequentially.
- Does **not** re-issue a sub-query already dispatched earlier in the same utterance.
- Does **not** split a single atomic intent into near-duplicate fragments.

### O3 — Refines Rather Than Restarts
> *Selectively updates answers and citation graphs when late constraints arrive, preserving session state.*

**Acceptance behaviour**
- A follow-up that modifies an existing topic increments an **answer version**; it does not clear session memory.
- Only the **affected claims** are re-queried. Unaffected claims keep their original text and original citations.
- The citation set of version *n+1* = (retained citations from version *n*) ∪ (delta citations).
- No full-corpus re-execution on a refinement turn — this must be *provable from telemetry*.

### O4 — Guarantees Corpus Grounding
> *Enforces strict provenance and citation checks, returning explicit uncertainty indicators when evidence is insufficient.*

**Acceptance behaviour**
- Every factual assertion carries a `[Doc_ID §Section]` marker resolving to a real, retrieved chunk.
- Zero fabricated document IDs — structurally impossible, not merely improbable.
- When a sub-intent cannot be answered from the corpus, the system emits an explicit `uncertainty` string **or** asks a targeted clarifying question. Silence or a confident guess are both failures.

---

## 3. Mandated System Architecture

The brief prescribes the pipeline. **Do not deviate from these four stages** — deviation costs alignment marks and makes the demo harder to map to the rubric. Innovation belongs *inside* each stage.

```
Incoming Stream: [Chunk 0.0s] → [Chunk 0.8s] → [Chunk 1.6s] → [Utterance End 2.1s]
                       │
                       ▼
        ┌──────────────────────────────────┐
        │ [1] Retrieval Controller         │
        │   • Intent Stability Check       │
        │   • Decision: Wait|Retrieve|No-R │
        └──────────────────────────────────┘
                       │ (Retrieve Triggered)
                       ▼
        ┌──────────────────────────────────┐
        │ [2] Multi-Intent Decomposer      │
        │   • Extract Sub-Queries          │
        │   • Parallel Intent Routing      │
        └──────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │ [3] Corpus Retrieval & Fusion    │
        │   • Search Supplied Corpus       │
        │   • Dense/Sparse Hybrid Scoring  │
        │   • Re-rank & Deduplicate Chunks │
        └──────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │ [4] Session-Aware Synthesis      │
        │   • Incremental Answer Update    │
        │   • Grounding & Citation Check   │
        │   • Explicit Uncertainty Flag    │
        └──────────────────────────────────┘
                       │
                       ▼
Output: Streamed Answer + Grounded Citations + Observability Telemetry
```

### 3.1 Component Responsibilities & Named Engineering Challenges

| # | Component | Functional Responsibility (per brief) | Core Engineering Challenge (per brief) |
|---|---|---|---|
| C1 | **Retrieval Controller** | Evaluate incoming transcript fragments to decide when to retrieve, when to wait, and when to suppress search entirely (e.g. conversational formatting). | Balancing early-retrieval latency gains against premature, noisy searches triggered by incomplete thoughts. |
| C2 | **Multi-Intent Decomposition** | Parse compound, unsegmented utterances into discrete, search-ready sub-queries. | Extracting distinct orthogonal questions without losing conversational context or over-fragmenting search. |
| C3 | **Evidence Fusion & Reranking** | Collect candidate chunks across all sub-queries, reconcile redundant evidence, rank snippets for maximum relevance and factual density. | Merging multi-source evidence without diluting context windows or introducing contradictory facts. |
| C4 | **Session-Only Refinement** | Apply late-arriving constraints directly onto existing answer states without clearing session context. | Tracking answer versions and mutating only affected claims rather than re-running full-corpus retrieval. |
| C5 | **Observability Telemetry** | Emit real-time event logs capturing timestamps, retrieval decisions, source mappings, version transitions, and token costs. | Maintaining clean, structured telemetry under sub-second streaming constraints. |

> **Note on C5:** telemetry is a *first-class component in the architecture diagram*, not an afterthought. It is also its own evaluation gate (G6) and its own deliverable (D5). Budget real engineering time for it.

---

## 4. Hard Constraints (Compliance Register)

These are pass/fail. A violation can invalidate an otherwise excellent system.

| ID | Constraint | Exact Requirement | How We Prove Compliance |
|---|---|---|---|
| **HC-1** | **Corpus Isolation** | All retrieved evidence derives exclusively from the provided corpus. No external web scraping, no third-party knowledge bases, no unindexed parametric model memory used to answer factual claims. | Network egress disabled in the runtime container (`network_mode: none` for the engine service, or an explicit deny-all policy). Every factual sentence must resolve to a chunk ID. Add a CI test that fails if any outbound HTTP call is attempted during replay. |
| **HC-2** | **No Hardcoding / No Precomputation** | Benchmark replay is **held-out and private**. Prompts, queries, and canned responses must not be embedded in application code. | All prompts live in `config/prompts/*.jinja`, loaded at runtime. No test-set strings anywhere in `src/`. Index is *built by a command*, not shipped as a baked artifact. Add a lint rule banning long string literals in modules. |
| **HC-3** | **Rigorous Factual Grounding** | Every factual assertion attributed to verifiable corpus chunk IDs or section markers in the form `[Doc_ID §Section]`. Insufficient evidence → explicit uncertainty indicator **or** targeted clarification request. | Constrained citation vocabulary (generator can only emit IDs present in the assembled context) + post-hoc entailment verification. |
| **HC-4** | **Session-Bound State** | Cross-session profiling and persistent user tracking across independent test runs are **prohibited**. Memory is strictly ephemeral and scoped to the active conversation session. | In-process session store only, TTL + explicit destruction on session end. No disk/DB persistence of session content. Isolation test: same question in two sessions → provably independent state. |
| **HC-5** | **Architectural Parsimony** | Multi-agent frameworks and complex orchestration pipelines are evaluated on **cost-to-performance efficiency**. Every added component must justify its latency and compute overhead. | Each component ships with a measured latency and token-cost contribution; the ablation report shows what each component buys. Default to single-process, in-library retrieval (no extra network hops) unless measured gain justifies otherwise. |

> **Reading HC-2 carefully:** it forbids *baked answers and test-specific strings*, not machine learning. Training a small intent-stability classifier on **self-generated synthetic data derived from the supplied corpus** is legitimate and should be explicitly documented as such in the architecture brief. Externalising prompts into config files is the cheap defensive move that makes compliance obvious to a reviewer.

> **Reading HC-5 carefully:** this is a direct warning against an agent-framework swarm. A lean, mostly-deterministic pipeline with two or three small model calls will score better than a LangGraph mesh of eight agents. Parsimony is a *scored criterion*, not a suggestion.

---

## 5. Specified Behaviours (Worked Examples)

The brief supplies three canonical scenarios. These are effectively a behavioural spec — the held-out suite will almost certainly contain structural clones of all three.

### 5.1 Example 1 — Incremental Multi-Intent Utterance

| Timestamp | Incoming Transcript Chunk | Required Controller Decision & System Action |
|---|---|---|
| **0.0 s** | *"I need to plan a customer workshop in…"* | **Wait.** Intent incomplete and semantically unstable. No retrieval. |
| **0.8 s** | *"…Pune for 30 people, and I need…"* | **Provisional Retrieve.** Stable geographic and capacity entities identified. Issue early search for `"Pune workshop venue capacity 30"`. Log `retrieval_started`. |
| **1.6 s** | *"…the cancellation policy and the catering options."* | **Decompose & Parallel Retrieve.** Deconstruct into three sub-queries: (1) venue capacity, (2) cancellation terms, (3) catering options. Dispatch parallel searches and rerank candidate chunks. |
| **2.1 s** | `[Utterance End]` | **Synthesize.** Stream single unified response addressing all three sub-intents with citations, noting any unverified aspects. |

**Non-obvious implications to honour:**
1. At 1.6 s, the venue-capacity query is **not re-issued** — the 0.8 s provisional retrieval is *reused*. Only two new retrieval events appear at 1.6 s. Intent tracking is monotonic and additive.
2. The sub-query the controller *fires* (`"Pune workshop venue capacity 30"` — keyword-shaped) differs from the sub-query it *reports* (`"venue capacity for 30 attendees in Pune"` — natural-language-shaped). The schema has two distinct fields for a reason: `retrieval_events[].query` is the search string; `sub_queries[]` is the semantic intent.
3. The final answer is **one unified response**, not three stapled-together answers.
4. `uncertainty` is populated even in the happy path — partial coverage is the norm, and admitting it is rewarded.

### 5.2 Example 2 — Late-Arriving Detail (Refine, Do Not Restart)

| Step | User Utterance | Required System Behaviour |
|---|---|---|
| 1 — Initial request | *"Summarize the travel reimbursement rule for an employee trip."* | Retrieve base policy guidelines. Emit cited summary. **Store evidence context and Answer Version 1 in session memory.** |
| 2 — Late detail | *"The trip was international and the booking was made after travel."* | **Does not restart session.** Recognises a modification to an existing topic. Dispatches **targeted** queries for *international travel* and *post-travel booking exceptions*. |
| 3 — Refined response | *(generated)* | *"The standard reimbursement rule still applies. However, the late-booking exception requires senior director approval, and international travel introduces a mandatory foreign currency receipt verification requirement."* — **preserves prior citations, adds delta citations, increments to Answer Version 2.** |

**Non-obvious implications:**
- *"The standard reimbursement rule still applies"* is a **retained claim** surfaced verbatim in the new answer. Refinement is additive-and-corrective, not regenerative.
- Two targeted queries are issued, both scoped to the *new constraint dimensions* — not a re-run of the original query.
- Version lineage must be inspectable (V1 → V2 with a claim-level diff).

### 5.3 Example 3 — Query Suppression (No Retrieval Required)

| User Input | Controller Evaluation | Required Behaviour |
|---|---|---|
| *"Please repeat your last answer in two bullets."* | `retrieval_required: false`<br>`reason: presentation_restructure` | Transform existing session context into two concise bullet points. **No vector search or corpus queries executed.** Retains prior citations **without fabricating new ones.** |

**Non-obvious implications:**
- The controller must emit a **machine-readable reason code**, not just a boolean. `presentation_restructure` is a named value we must support verbatim; we extend the enum for translation, tone change, and acknowledgement.
- Citation set on a presentation turn must be a **subset of the prior turn's citations**. Assert this in code — a new citation appearing on a reformat turn is a grounding failure.

---

## 6. Required Output Schema

The brief prints an exact `Structured Output Event Record`. **These five top-level keys and their types are contractual.** Extensions go in additional keys; the required five keep their exact names, shapes, and value formats.

```json
{
  "retrieval_events": [
    { "timestamp_s": 0.8, "query": "Pune workshop venue capacity 30",        "trigger": "provisional"  },
    { "timestamp_s": 1.6, "query": "cancellation policy workshop venues Pune","trigger": "multi_intent" },
    { "timestamp_s": 1.6, "query": "catering service options workshop Pune",  "trigger": "multi_intent" }
  ],
  "sub_queries": [
    "venue capacity for 30 attendees in Pune",
    "cancellation terms and refund policies",
    "on-site and external catering options"
  ],
  "answer": "For a 30-person workshop in Pune, documented options include Venue A and Venue B. Venue A provide…",
  "citations": ["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"],
  "uncertainty": "Catering accommodation policies for Venue A could not be verified from the retrieved corpus."
}
```

### 6.1 Field Contract

| Field | Type | Contract Notes |
|---|---|---|
| `retrieval_events[].timestamp_s` | `float` | **Stream time** in seconds from utterance start, not wall clock. Multiple events may share a timestamp (parallel dispatch). |
| `retrieval_events[].query` | `string` | The *actual search string sent to the index* — keyword-dense, entity-bearing. |
| `retrieval_events[].trigger` | `enum` | Confirmed values from the brief: `provisional`, `multi_intent`. We extend with `late_constraint`, `clarification_followup`, `final_confirm`. `provisional` must appear on the early-retrieval path for G2 to be measurable. |
| `sub_queries[]` | `string[]` | Natural-language, **self-contained** intents. One entry per distinct sub-intent. Empty array is invalid whenever `retrieval_events` is non-empty. |
| `answer` | `string` | A single unified narrative with inline `[Doc_ID §Section]` markers. Not a list of per-sub-query answers. |
| `citations[]` | `string[]` | Format exactly `"Doc_12 §2"` — underscore in the doc ID, space before `§`, no brackets inside the array entries. Must be the deduplicated union of every ID cited inline. |
| `uncertainty` | `string` | Plain-language statement of what could **not** be verified. Use `""` or `null` only when coverage is genuinely complete — populate it whenever a sub-intent lacks support. |

### 6.2 Additive Extensions (safe, non-breaking)

```json
{
  "...required five keys...": "...",
  "session_id": "sess_a91c",
  "turn_id": 3,
  "answer_version": 2,
  "retrieval_required": true,
  "suppression_reason": null,
  "controller_decisions": [
    { "timestamp_s": 0.0, "decision": "WAIT",     "reason": "intent_unstable",       "confidence": 0.31 },
    { "timestamp_s": 0.8, "decision": "RETRIEVE", "reason": "entity_slots_saturated","confidence": 0.78 }
  ],
  "claims": [
    { "claim_id": "c1", "facet": "venue_capacity", "text": "...", "citations": ["Doc_12 §2"],
      "status": "active", "introduced_in_version": 1 }
  ],
  "version_lineage": { "from": 1, "to": 2, "retained": ["c1"], "superseded": ["c2"], "added": ["c5"] },
  "telemetry": { "latency_ms": { "first_retrieval": 812, "first_token_after_end": 287 },
                 "tokens": { "prompt": 2914, "completion": 318 }, "cost_usd": 0.0041 }
}
```

---

## 7. Evaluation Gates — The Scoring Surface

Six automated, quantitative acceptance gates. **This table is the optimisation target.**

| Gate | Criterion | Target Threshold | Validation Method | What It Really Measures |
|---|---|---|---|---|
| **G1** | Reproducibility | Pass / Fail | Container launches via a **single command** on a clean machine; automated replay suite completes **without manual intervention**. | Whether a judge on an unknown laptop can run you at all. Binary, and it gates everything else. |
| **G2** | Early Retrieval | **≥ 80%** of eligible queries | Retrieval commences **prior to final transcript completion** on held-out streaming prompts, maintaining **low false-trigger rates** on no-retrieval cases. | Aggressiveness *and* restraint. Two numbers, one gate. |
| **G3** | Multi-Intent Identification | **≥ 70%** of compound queries | Accurately identifies and isolates **at least two distinct sub-intents** in compound test utterances. | Recall of sub-intents — with "distinct" doing heavy lifting against over-fragmentation. |
| **G4** | Factual Grounding | **≥ 85%** citation support | All sampled factual assertions supported by cited corpus chunks; **zero** fabricated or hallucinated document IDs. | Two thresholds: 85% support, and an absolute zero on fabrication. |
| **G5** | Session Refinement | Verified state continuity | Late-arriving constraints narrow or update existing responses **without clearing session state or re-executing full-corpus search**. | Provable from telemetry, not from the answer text. |
| **G6** | Telemetry & Observability | **100%** trace coverage | Structured logs or metrics dashboards capture execution timestamps, retrieval triggers, citations, answer version lineage, and token cost. | Five named data classes, all present, on every single turn. |

### 7.1 Gate-to-Lever Map

| Gate | Primary Design Lever (detailed in Doc 2) | Secondary Lever | Target Margin |
|---|---|---|---|
| G1 | `docker compose up` single command + fully pinned lockfile | Model weights pre-baked into image or fetched at build time, never at run time | Pass on first attempt, offline |
| G2 | Speculative retrieval with corpus-grounded stability probe (S-1) | Branch cancellation so aggression doesn't cost accuracy | Aim **90%+** early trigger, **<10%** false trigger |
| G3 | Monotonic intent-set diffing (S-2) + retrieval-overlap anti-fragmentation (S-3) | Facet typing for orthogonality | Aim **85%+** sub-intent recall |
| G4 | Constrained citation vocabulary (S-6) — makes fabrication structurally impossible | Sentence-level NLI verification before commit | Aim **93%+** support, **0** fabricated IDs |
| G5 | Claim-graph answer representation + delta engine (S-4) | Telemetry that proves queries_issued ≪ full-corpus | Retain **≥70%** of claims across a refinement |
| G6 | OpenTelemetry spans + JSONL event log + coverage invariant test | Grafana dashboard for the demo video | **100%**, asserted in CI |

---

## 8. Common Pitfalls (Explicit Anti-Requirements)

The brief names five. Treat each as a test case we must *demonstrate passing* in the video.

| # | Pitfall | Consequence | Our Countermeasure |
|---|---|---|---|
| P1 | **Eager / premature retrieval on noise** — triggering vector search on every incremental token | System thrashing, high compute cost, noisy context windows. Controller must wait for semantic intent boundaries. | Corpus-grounded stability probe + minimum-entity gate + cancellable speculation |
| P2 | **Context loss on late constraints** — resetting conversation state on clarification | Discards retrieved context, doubles latency, causes disjointed replies. | Claim graph persists across turns; delta engine mutates in place |
| P3 | **Citation hallucination** — generating fabricated IDs (`[Doc_999]`) or citing chunks that don't explicitly contain the stated facts | Fails automated grounding gates. | Allowlist-constrained citation emission + per-sentence entailment check + numeric/entity copy verification |
| P4 | **Ignoring presentation-only turns** — querying the vector DB when the user asks to reformat, shorten, or translate | Wastes tokens and risks introducing drift. | Suppression gate as **stage 0** of the controller, before any embedding is computed |
| P5 | **Over-fragmenting sub-queries** — splitting one simple question into multiple near-identical queries | Pollutes the reranker, exhausts token limits. | Semantic dedup on sub-queries + retrieval-overlap merge (if two sub-queries return >80% of the same chunks, they were one intent) |

---

## 9. Deliverables Checklist

| ID | Deliverable | Explicit Requirements | Owner Phase |
|---|---|---|---|
| **D1** | **Reproducible Repository** | Source code, **pinned dependency lockfiles**, environment configuration templates, one-command run instructions (`docker compose up` or a clean CLI runner). | Phase 5 (scaffolded Phase 1) |
| **D2** | **System Architecture Brief (≤ 6 pages)** | System design rationale, retrieval trigger logic, query decomposition strategy, data provenance, trade-offs, failure-mode mitigations. | Phase 5 (drafted continuously) |
| **D3** | **Benchmarking & Evaluation Report** | Quantitative performance comparison **against the baseline pipeline**; **at least three** analysed edge-case failures; **two** architectural ablation experiments (e.g. hybrid vs dense-only retrieval; rule-based vs model-based controller). | Phase 5 |
| **D4** | **System Demonstration Video (≤ 5 min)** | Walkthrough demonstrating: early retrieval triggering, multi-intent decomposition, late-detail refinement, presentation query suppression, citation traceability, runtime telemetry. **Six named beats.** | Phase 5 |
| **D5** | **Telemetry & Observability Schema** | Structured logs capturing end-to-end request latencies, retrieval trigger events, answer version updates, and inference cost estimations. | Phase 5 (instrumented Phase 1) |

> **D4 is a scripted deliverable.** Six beats in ≤300 seconds = ~45 s each with titles. Storyboard it in Phase 4, don't improvise it on the last night. The UI in Doc 3 exists primarily to make these six beats *visually obvious in one frame*.

> **D3's word "baseline" implies you must also build a baseline.** A classic batch RAG path (wait for final transcript → single query → dense top-k → single-shot generate) must exist behind a config flag. Build it in Phase 1 — it is nearly free then, and it is the denominator for every number in your report.

---

## 10. Requirement Traceability Index

| Req ID | Summary | Gate(s) | Pitfall(s) | Solution (Doc 2) | Phase (Doc 3) |
|---|---|---|---|---|---|
| O1 | Incremental listening, pre-completion retrieval | G2 | P1, P4 | S-1, S-7 | 2 |
| O2 | Multi-intent decomposition, parallel routing | G3 | P5 | S-2, S-3 | 3 |
| O3 | Refine, never restart | G5 | P2 | S-4, S-5 | 4 |
| O4 | Strict corpus grounding + uncertainty | G4 | P3 | S-6, S-8, S-9 | 4 |
| C3 | Evidence fusion without contradiction | G4 | P3, P5 | S-3, S-9 | 3 |
| C5 | Telemetry under sub-second constraints | G6 | — | S-10 | 5 (cont. from 1) |
| HC-1…5 | Isolation, no hardcoding, grounding, ephemerality, parsimony | all | all | §Compliance, Doc 3 | all |
| D1…D5 | Repo, brief, report, video, schema | G1, G6 | — | — | 5 |

---

*Next: **02_SOLUTION_DESIGN.md** — per-module implementation options, trade-offs, novel mechanisms (S-1 … S-10), and selected approach.*
