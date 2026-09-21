# Streaming Live RAG — Final System Architecture
## Document A of 2 — Committed Design (Samsung Theme 4)

> This is the **decided** architecture: for every component, one solution has been selected from the option space and is specified here as the build target — no alternatives, no trade-off tables. Traceability back to the brief's requirements (O1–O4, C1–C5, G1–G6, P1–P5, HC-1–HC-5) is preserved in the margin notes. Companion document: **B — Final Engineering Roadmap**.

---

## 0. Design Statement

The engine is a single async process that treats an utterance as an **event stream**, not a request. Retrieval-readiness is decided by asking the corpus, not the sentence. Answers are held as a **graph of claims**, not a string, so refinement is a graph mutation rather than a regeneration. Citations are drawn from a **closed allowlist**, so fabrication is structurally impossible rather than statistically rare. Exactly three LLM calls occur per turn in the worst case (decompose, synthesise, optional controller tie-break); every other stage is deterministic code or a small non-generative model. This satisfies HC-5 (parsimony) by construction and is stated explicitly in the brief.

```
Incoming Stream: [Chunk 0.0s] → [Chunk 0.8s] → [Chunk 1.6s] → [Utterance End 2.1s]
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │ [1] RETRIEVAL CONTROLLER                  │  → §1
        │   5-stage cascade + speculation manager   │
        └──────────────────────────────────────────┘
                       │ (Retrieve Triggered)
                       ▼
        ┌──────────────────────────────────────────┐
        │ [2] MULTI-INTENT DECOMPOSER               │  → §2
        │   Monotonic IntentSet + overlap merge     │
        └──────────────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────┐
        │ [3] CORPUS RETRIEVAL & FUSION             │  → §3
        │   Facet-routed hybrid + quota + contradict│
        └──────────────────────────────────────────┘
                       │           ↕
                       │   ┌───────────────────┐
                       │   │ SESSION STATE      │  ephemeral, in-proc (HC-4)
                       │   │ IntentSet          │
                       │   │ EvidencePool        │
                       │   │ ClaimGraph + ver    │
                       │   └───────────────────┘
                       ▼
        ┌──────────────────────────────────────────┐
        │ [4] SESSION-AWARE SYNTHESIS               │  → §4
        │   Claim graph + delta engine + 2-pass     │
        │   streaming + citation allowlist          │
        └──────────────────────────────────────────┘
                       │
        ══ TELEMETRY BUS taps every stage ══════════│  → §5
                       ▼
Output: Streamed Answer + Grounded Citations + Observability Telemetry
```

---

## 1. Component 1 — Retrieval Controller

**Selected design: 5-stage cascading controller (cheap→expensive, early-exit) with a speculative-execution layer.**
Owns **O1**, Gate **G2**, and is the primary defence against pitfalls **P1** and **P4**. Runs in ≤15 ms p95 so it can execute on every chunk.

### 1.1 The Cascade

```
chunk arrives
  │
  ├─ Stage 0 — SUPPRESSION GATE                                  (~0.2 ms, regex + rules)
  │    Trigger: presentation verbs (repeat/shorten/rephrase/bullets/translate/tone)
  │             + zero new content entities + anaphora to prior answer
  │    → NO-RETRIEVAL {retrieval_required:false, reason:"presentation_restructure"}
  │
  ├─ Stage 1 — CONTENT FLOOR                                     (~3 ms, spaCy NER/POS)
  │    < 1 content anchor (GPE/ORG/PRODUCT/CARDINAL/domain noun) OR dangling preposition
  │    → WAIT {reason:"intent_unstable"}
  │
  ├─ Stage 2 — CORPUS DISCRIMINATIVENESS PROBE                   (~2 ms, BM25)
  │    margin = (s1 − mean(s2..s5)) / s1 ;  H = normalised entropy of top-10
  │    margin > τ_hi AND H < h_lo → RETRIEVE {reason:"corpus_discriminative"}
  │    margin < τ_lo               → WAIT     {reason:"corpus_ambiguous"}
  │    else                        → Stage 3
  │
  ├─ Stage 3 — EMBEDDING STABILITY                                (~8 ms, bge-small)
  │    drift(prefix_t, prefix_{t-1}) < ε AND content anchors ≥ 2 → RETRIEVE {reason:"intent_stabilised"}
  │
  └─ Stage 4 — LLM TIE-BREAK (async, <5% of chunks, non-blocking)  (~60 ms)
```

**Unconditional overrides:**
- A new coordinating conjunction introducing a fresh content anchor (`"…and I need the cancellation policy"`) fires RETRIEVE immediately regardless of stability.
- `utterance_end` fires RETRIEVE as a safety net if nothing has fired yet.
- A 250 ms refractory period suppresses re-triggering unless a new content anchor has appeared, preventing thrashing.

**Stage 2 is the differentiator.** Instead of asking "has the sentence finished forming?" it asks "does the corpus now have an opinion about this prefix?" — a BM25 query against the already-built sparse index, ~2 ms, fully model-free, and directly auditable in the demo ("the margin bar crosses the threshold — that's the retrieval firing").

### 1.2 Speculative Execution Layer

Every provisional retrieval from Stage 2/3 is a speculative branch with an explicit lifecycle:

```
SPECULATIVE → (next chunk consistent)  → CONFIRMED → feeds synthesis context
            → (next chunk contradicts) → CANCELLED → chunks demoted to EvidencePool
```

Contradiction test: prefix embedding drift exceeds δ, **or** a self-correction marker appears (`"actually"`, `"no wait"`, `"sorry, I meant"`, `"scratch that"`). Cancelled branches never reach the synthesis context, so being wrong costs nothing in answer quality — but the chunks they retrieved are never discarded; they land in the session **EvidencePool** and remain eligible for reranking on later turns. This is what allows the controller to be tuned aggressively (target 90%+ early trigger) without inflating the false-trigger rate that P1 punishes.

### 1.3 Calibration
Thresholds (`τ_hi`, `τ_lo`, `ε`, `h_lo`, refractory window) live in `config/controller.yaml`, calibrated once against a labelled dev sweep (early-trigger-rate vs false-trigger-rate curve, knee selected), never hardcoded in application code (HC-2).

### 1.4 Metrics Owned
`early_retrieval_rate` (G2), `retrieval_lead_time_ms`, `false_trigger_rate`, `suppression_precision/recall`, `speculation_accuracy`, `controller_latency_p95`.

---

## 2. Component 2 — Multi-Intent Decomposer

**Selected design: syntactic-candidate proposal → LLM canonicalisation, gated by a monotonic, facet-keyed IntentSet with retrieval-overlap merging.**
Owns **O2** and Gate **G3**; primary defence against pitfall **P5**.

### 2.1 Decomposition Pass
1. **Syntactic candidate generation** (deterministic, ~5 ms): dependency-parse the current full prefix, split conjoined NPs/VPs sharing a governing head.
2. **LLM canonicalisation** (async, JSON-grammar constrained, ~80–150 ms, off the critical path): validates candidates, resolves ellipsis and anaphora into **self-contained** search-ready phrasing, and adds implicit intents the syntax pass cannot see (e.g. a stated headcount implies a capacity question even if never asked).
3. **Facet tagging**: every candidate intent is classified into the corpus-derived facet taxonomy (`config/facets.yaml`) — this taxonomy is the backbone of deduplication, routing (§3.2), and answer sectioning.

Output per candidate:
```json
{"facet":"venue_capacity","query_nl":"venue capacity for 30 attendees in Pune",
 "search_string":"Pune workshop venue capacity 30","novel":true}
```

### 2.2 Monotonic IntentSet
A per-utterance set that only ever grows:
```python
IntentSet = {
  intent_id: {facet, query_nl, search_string, first_seen_ts,
              dispatched: bool, retrieval_event_ids[], status}
}
```
On every RETRIEVE decision, the full current prefix is re-decomposed and the candidates are **diffed** against the existing set:
- Same facet key + embedding similarity > 0.88 → same intent; refine `search_string` in place, **do not re-dispatch** unless the refinement would change the top-5 BM25 result set by >50%.
- New facet / low similarity → genuinely new intent → dispatch retrieval.

This reproduces the brief's own event pattern exactly: at 0.8 s the set holds one intent (`venue_capacity`); at 1.6 s two more are added, and **only those two** generate new `retrieval_events` — the capacity intent is reused, not reissued.

### 2.3 Retrieval-Overlap Anti-Fragmentation
After dispatch, compute Jaccard overlap of the top-10 retrieved chunk-ID sets for every pair of intents:
```
overlap(q_i, q_j) = |top10(q_i) ∩ top10(q_j)| / |top10(q_i) ∪ top10(q_j)|
overlap > 0.7 (same facet only) → merge; union evidence; keep the more specific phrasing
```
This catches text-dissimilar-but-corpus-identical fragmentations (`"cancellation terms"` vs `"refund policy"`) that a text-only dedup misses, at zero extra retrieval cost since the searches already ran in parallel. Merging is **never** allowed across different facet types, even at high overlap.

### 2.4 Metrics Owned
`sub_intent_recall/precision` (G3), `distinct_intents_per_utterance`, `over_fragmentation_rate`, `merge_rate`, `self_containment_pass_rate`, `decomposition_latency_p95`.

---

## 3. Component 3 — Corpus Retrieval & Fusion

**Selected design: structure-aware chunking + facet-routed hybrid retrieval + RRF + cross-encoder rerank + facet-quota assembly with contradiction gating.**
Feeds Gate **G4**; directly answers the brief's named fusion challenge ("merging multi-source evidence without diluting context windows or introducing contradictory facts").

### 3.1 Index (built once, Phase 1)
- **Chunking**: section-bounded, 250–400 tokens, 15% overlap. Section identity is a primary key, not metadata — `ChunkID = doc_id#section_id#ordinal`, emitted as `CitationLabel = "Doc_ID §Section"`.
- **Contextual enrichment**: each chunk prefixed at index time with a one-sentence LLM-generated situating summary, built via `slrag index` (never shipped baked — HC-2 compliant).
- **Sparse index**: `bm25s`, in-process.
- **Dense index**: `bge-small-en-v1.5` embeddings → FAISS `IndexFlatIP` (exact search — approximate indexing buys nothing at this corpus scale and only costs recall).
- No standalone vector-DB service, no Elasticsearch — one process, justified under HC-5.

### 3.2 Retrieval & Fusion (per sub-query, dispatched concurrently via `asyncio.gather`)
1. BM25 top-50 ∥ Dense top-50.
2. **Facet-routed weighted RRF** (`k=60`): weights per facet come from `config/retrieval.yaml`. Policy/terms/eligibility facets weight sparse higher (exact numbers, qualifiers, obligations matter); descriptive/comparison/logistics facets weight dense higher (paraphrase-heavy). This routing table is itself the required hybrid-vs-dense ablation, made mechanistically interesting rather than a single global number.
3. Cross-encoder rerank (`bge-reranker-base`) on fused top-30 → top-8 per sub-query.
4. Near-duplicate chunk dedup (cosine > 0.95) with **citation-label union** — duplicates merge, provenance never drops.

### 3.3 Context Assembly — Facet-Quota Fusion
```
budget = 3000 tokens
guaranteed = 2 chunks per active sub-intent   # no facet starves another
remainder  = allocated by factual density score
             density = count(numerals, dates, currency, durations, modal-obligation words,
                              named entities) / token_count
MMR (λ≈0.7) applied within each facet for diversity
```
This directly prevents a dominant facet (e.g. venue capacity, which scores high everywhere) from crowding out a thin one (e.g. the single catering paragraph) — the brief's "diluting context windows" risk, solved by quota rather than global top-k.

### 3.4 Contradiction Gating
1. **Typed slot extraction** per facet (durations, percentages, currency, dates, approval roles) across candidate chunks.
2. Two chunks disagreeing on the same slot → candidate conflict → **NLI confirmation** (`nli-deberta-v3-small`, contradiction probability > 0.7).
3. Confirmed conflict is never silently resolved: both readings are surfaced with a recency/specificity cue, or the conflict is routed to the `uncertainty` field. This is the brief's "without introducing contradictory facts" requirement, answered structurally.

### 3.5 Session EvidencePool
```python
EvidencePool[chunk_id] = {text, doc_id, section_id, embeddings,
                           scores_by_subquery: {...}, first_retrieved_ts,
                           used_in_versions: [...], speculative: bool}
```
Every retrieval — confirmed, speculative, or cancelled — lands here. Refinement turns (§4.2) re-rank this pool before considering any new query, which is what allows many late-constraint turns to be answered with **zero** new retrievals.

### 3.6 Metrics Owned
`recall@k`, `nDCG@10`, `chunk_dedup_rate`, `facet_coverage_rate`, `contradiction_detection_count`, `context_tokens_per_turn`, `retrieval_latency_p95`, `pool_reuse_rate`.

---

## 4. Component 4 — Session-Aware Synthesis & Refinement

**Selected design: claim-graph answer representation + delta engine + constrained citation allowlist + two-pass provisional/committed streaming + coverage-matrix uncertainty.**
Owns **O3, O4**, Gates **G4, G5**; primary defence against **P2, P3**.

### 4.1 The Claim Graph
The answer is never a string until the final rendering step. It is a set of typed claims:
```json
{"claim_id":"c3","facet":"cancellation_terms",
 "text":"Cancellations made more than 14 days before the event receive a full refund.",
 "citations":["Doc_31 §4"],
 "preconditions":{"trip_type":"domestic","booking_timing":"advance"},
 "confidence":0.91,"introduced_in_version":1,"status":"active","superseded_by":null}
```

### 4.2 Delta Engine (Refinement Flow)
```
1. CLASSIFY turn → NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY
2. EXTRACT constraint deltas from the new utterance
3. IMPACT ANALYSIS: for each active claim, does the delta conflict with its preconditions?
      no conflict → RETAIN claim verbatim, citations untouched
      conflict    → mark AFFECTED
4. POOL-FIRST RESOLUTION: try to resolve affected facets from the EvidencePool
      resolved   → zero new retrievals
      unresolved → dispatch TARGETED delta queries (affected facet × new constraint only)
5. MERGE: retained + superseded + newly-added claims
6. VERSION++;  citations(v_n+1) = citations(retained) ∪ citations(delta)
7. RENDER active claims → one unified narrative
```
Telemetry emitted on every refinement is the direct proof of Gate G5:
```json
{"event":"answer_refined","from_version":1,"to_version":2,
 "claims_retained":3,"claims_superseded":1,"claims_added":2,
 "delta_queries_issued":2,"full_corpus_searches":0,"session_cleared":false}
```

### 4.3 Presentation-Only Path
Rendered from the claim list only; the corpus index is structurally unreachable from this code path. Citations of the new turn are, by construction, a subset of the prior turn's citations — asserted as a build-breaking test. Emits `{"retrieval_required": false, "reason": "presentation_restructure"}`.

### 4.4 Constrained Citation Vocabulary
1. **Allowlist by construction**: `allowed_ids` = the citation labels of chunks actually in context; the generation prompt forbids any other.
2. **Grammar/logit constraint** (Outlines / GBNF / guided decoding) makes off-allowlist citation markers undecodable where supported.
3. **Post-hoc validator** (always on, the unconditional backstop): every `[Doc_* §*]` marker is checked; anything outside the allowlist is stripped and its sentence demoted to `uncertainty`. CI asserts `fabricated_id_count == 0` over the entire replay suite.

### 4.5 Two-Pass Provisional/Committed Streaming
```
generate sentence → emit PROVISIONAL (dimmed)
                  → verify in parallel with generating next sentence:
                      · citation ∈ allowlist
                      · NLI entailment (cited chunk ⊨ sentence, threshold ~0.6)
                      · numeral/date/currency/entity copy check against cited chunk
                  → emit COMMITTED (solid, citation chip) or RETRACT + regenerate
```
This gives full sentence-level grounding verification at effectively zero perceived latency.

### 4.6 Coverage Matrix → Uncertainty
For every sub-intent, track best rerank score and whether an entailed claim exists:
- No coverage and no entailed claim → contributes a sentence to `uncertainty`.
- Evidence present but ambiguous between readings → emit a targeted clarification question instead (the brief's permitted alternate branch).
- An uncovered sub-intent is **never** silently dropped from the answer — that would fail G3 and G4 simultaneously.

### 4.7 Metrics Owned
`citation_support_rate` (G4), `fabricated_id_count` (must be 0), `unsupported_claim_rate`, `claims_retained_pct` (G5), `delta_queries_per_refinement`, `full_corpus_searches_on_refinement` (must be 0), `uncertainty_precision`, `time_to_first_token_after_utterance_end`.

---

## 5. Component 5 — Observability & Telemetry

**Selected design: always-on structured JSONL log + optional OpenTelemetry/Grafana stack, scored via an assertable trace-coverage invariant suite.**
Owns Gate **G6** and deliverable D5.

### 5.1 Dual Sink
- **`events.jsonl`** — append-only, schema-versioned. Always on, dependency-free. This is the artifact the replay harness actually scores, and it must never depend on external services (HC-5, G1 resilience).
- **OpenTelemetry spans → Tempo; metrics → Prometheus → Grafana** — opt-in via a `--profile obs` Docker Compose profile, purely for the human-facing dashboard used in the demo video. Failure of this stack must never break the core engine or `docker compose up`.

### 5.2 Span Tree
```
session → turn → chunk → controller_decision
                        → { retrieval(sub_query) → rerank }
                        → synthesis → verification(sentence) → answer_version
```
Every event carries `event_id, session_id, turn_id, ts_wall, ts_stream_s, component, latency_ms, payload`.

### 5.3 Cost Model
Token counts per LLM call × `config/pricing.yaml` → `cost_usd`, tracked per turn, per component, per session. Embedding/rerank item counts tracked as a compute-proxy for the parsimony argument.

### 5.4 Trace-Coverage Invariant Suite
Coverage is **asserted**, not claimed:

| Invariant | Assertion |
|---|---|
| Every chunk has a decision | `count(chunks) == count(controller_decisions)` |
| Every retrieval has a parent | every `retrieval_event` follows a `RETRIEVE` controller decision |
| Every citation resolves | every ID in `citations[]` ∈ indexed chunk IDs |
| Every answer has lineage | every version > 1 has a `version_lineage` record |
| Every LLM call is costed | `count(llm_calls) == count(cost_records)` |
| Every turn is timed | `ts_stream_s` present and monotonic |

`coverage = passed / total`, printed as a measured percentage in the evaluation report — not a screenshot claim.

---

## 6. Output Schema (Contractual)

The five required top-level keys, exact names and types, plus the additive fields the committed design produces:

```json
{
  "retrieval_events": [
    { "timestamp_s": 0.8, "query": "Pune workshop venue capacity 30",         "trigger": "provisional" },
    { "timestamp_s": 1.6, "query": "cancellation policy workshop venues Pune","trigger": "multi_intent" },
    { "timestamp_s": 1.6, "query": "catering service options workshop Pune",  "trigger": "multi_intent" }
  ],
  "sub_queries": [
    "venue capacity for 30 attendees in Pune",
    "cancellation terms and refund policies",
    "on-site and external catering options"
  ],
  "answer": "For a 30-person workshop in Pune, documented options include Venue A and Venue B...",
  "citations": ["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"],
  "uncertainty": "Catering accommodation policies for Venue A could not be verified from the retrieved corpus.",

  "session_id": "sess_a91c", "turn_id": 3, "answer_version": 2,
  "retrieval_required": true, "suppression_reason": null,
  "controller_decisions": [
    {"timestamp_s":0.0,"decision":"WAIT","reason":"intent_unstable","confidence":0.31},
    {"timestamp_s":0.8,"decision":"RETRIEVE","reason":"corpus_discriminative","confidence":0.78}
  ],
  "claims": [
    {"claim_id":"c1","facet":"venue_capacity","text":"...","citations":["Doc_12 §2"],
     "status":"active","introduced_in_version":1}
  ],
  "version_lineage": {"from":1,"to":2,"retained":["c1"],"superseded":["c2"],"added":["c5"]},
  "telemetry": {"latency_ms":{"first_retrieval":812,"first_token_after_end":287},
                "tokens":{"prompt":2914,"completion":318},"cost_usd":0.0041}
}
```

`trigger` enum: `provisional`, `multi_intent`, `late_constraint`, `clarification_followup`, `final_confirm`.
`controller reason` enum includes at minimum: `intent_unstable`, `corpus_ambiguous`, `corpus_discriminative`, `intent_stabilised`, `presentation_restructure`.

---

## 7. Hard Constraint Compliance (as built)

| ID | Constraint | How This Architecture Satisfies It |
|---|---|---|
| HC-1 | Corpus isolation | No network egress from the engine container; every citation resolves to an indexed chunk; the generator is only ever shown retrieved context, never asked to answer from parametric memory |
| HC-2 | No hardcoding | All prompts in `config/prompts/*.jinja`; all thresholds in `config/*.yaml`; index built by an explicit command, never shipped baked |
| HC-3 | Rigorous grounding | Allowlist-constrained citation emission (§4.4) + coverage-matrix uncertainty (§4.6) |
| HC-4 | Session-bound state | In-process, TTL-bound `IntentSet`/`EvidencePool`/`ClaimGraph`; no disk persistence; destroyed on session end |
| HC-5 | Parsimony | Single process; ≤3 LLM calls per turn; no agent framework; no extra network-hop services; every component's latency/cost is measured and published |

---

*Companion document: **B — Final Engineering Roadmap** (phase plan, repo layout, stack, interfaces, deliverables, demo storyboard, built for exactly this architecture).*
