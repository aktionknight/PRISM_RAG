# Theme 4 — Streaming Live RAG
## Document 2 of 3: Solution Design — Module Abstracts, Implementation Options & Novel Mechanisms

> Read alongside **01_OBJECTIVES_AND_REQUIREMENTS.md**. Requirement IDs (O1–O4, C1–C5, G1–G6, P1–P5, HC-1–HC-5) refer to that document.
>
> Each module below follows the same shape: **Abstract → Options (with trade-offs) → Recommended stack → Novel mechanisms → Failure modes → Metrics.**

---

## 0. Design Philosophy — Three Rules That Decide Every Trade-off

**Rule 1 — Let the corpus be the oracle, not the language model.**
Most teams will judge "is this intent complete?" by looking at the *text*. We judge it by looking at what the *index* says about the text. A prefix is complete when it becomes **discriminative against the corpus** — when BM25 scores go from flat to peaked. This is ~1 ms, needs no model, and is directly aligned with the thing we actually care about (will retrieval return something useful?). It is the single highest-leverage idea in this design.

**Rule 2 — Be aggressive, but make being wrong cheap.**
G2 rewards early retrieval; P1 punishes noisy retrieval. These only conflict if a wrong retrieval is expensive. So we make speculation **cancellable and reusable**: wrong branches are discarded before they touch the context window, and their retrieved chunks land in a session-level evidence pool where they cost nothing and may still be useful later. Borrowed directly from CPU branch prediction.

**Rule 3 — The answer is a data structure, not a string.**
Everything hard in O3 (refine, don't restart), O4 (grounding), G5 (state continuity), and G6 (version lineage) becomes easy once the answer is a **graph of Claims**, each carrying its own citations, facet, preconditions, and version. Rendering to prose is the last step, and it is the only step that needs a language model. Teams that store answers as strings will fight the refinement requirement for the entire hackathon.

**A note on HC-5 (parsimony):** the design below uses **exactly three LLM calls per turn in the worst case** (decompose, synthesise, and an optional controller tie-break), plus small encoder models. No agent framework, no orchestration mesh, one process. Everything else is deterministic code and index lookups. State this explicitly in the architecture brief — it is a scored criterion, and most competing submissions will fail it.

---

# Module C1 — Retrieval Controller

### Abstract
A per-chunk ternary decision function. Given the transcript prefix so far and the session state, it emits `WAIT`, `RETRIEVE`, or `NO-RETRIEVAL` with a machine-readable reason and a confidence. It is the latency/noise valve of the entire system, it owns Gate G2 outright, and it is the sole defence against pitfalls P1 and P4. It must run in **under 15 ms** so it can execute on every chunk without becoming the bottleneck it exists to prevent.

---

### Implementation Options

**Option A — Pure rule/heuristic (entity-slot saturation)**
Run fast NER + POS over the prefix (spaCy `en_core_web_sm`, ~3 ms). Trigger when the prefix contains at least one *content anchor* (GPE / ORG / PRODUCT / CARDINAL / domain noun) **and** closes a syntactic boundary (completed prepositional phrase, clause boundary, or a conjunction signalling a new coordinate).

- *Pros:* microseconds-to-milliseconds, fully deterministic, trivially explainable in the brief, zero training data.
- *Cons:* brittle across phrasings; "in Pune" and "in the Pune office next quarter" behave differently; poor at implicit intent.
- *Verdict:* excellent as **one signal**, insufficient alone.

**Option B — Embedding drift / prefix stability**
Embed the prefix after every chunk (bge-small, ~8 ms). Compute cosine between consecutive prefix embeddings. Large drift = intent still forming; drift falling below ε = intent crystallised → retrieve.

- *Pros:* phrasing-agnostic, captures semantic settling, cheap.
- *Cons:* drift is also low during filler ("um, so, basically, I was wondering") — stability is not the same as informativeness. Needs a *content* floor to avoid firing on nothing.
- *Verdict:* good second signal; must be paired with an informativeness test.

**Option C — Corpus-grounded discriminativeness probe** ⭐ *(novel — S-1)*
Run a **BM25 probe** of the current prefix against the sparse index (using `bm25s`, ~1–3 ms on a hackathon-scale corpus). Look at the *shape* of the score distribution over the top-k:
- Flat / low-entropy-free distribution (top-1 ≈ top-10) ⇒ the prefix doesn't select anything in particular ⇒ **WAIT**.
- Peaked distribution (large top1−top5 margin, low normalised entropy) ⇒ the prefix now points at specific documents ⇒ **RETRIEVE**.

- *Pros:* measures the only thing that matters — *will a search right now return something better than noise?* Free (reuses the index we already built), model-free, and it makes the controller's decision directly auditable ("we fired because margin crossed 0.34"). Naturally resistant to filler, because filler words are stopwords with no discriminative power.
- *Cons:* thresholds need calibration per corpus; must be normalised (score magnitudes vary with prefix length). Blind to intent *type* (can't tell a question from a command).
- *Verdict:* **the primary signal.** This is the design's differentiator.

**Option D — Trained intent-stability classifier**
Fine-tune a MiniLM/DistilBERT 3-way head (`WAIT` / `RETRIEVE` / `SUPPRESS`) on synthetic streamed prefixes generated from the corpus (see §Benchmark Generation). ~10 ms CPU.

- *Pros:* highest ceiling on accuracy; handles suppression and question-type elegantly; gives calibrated confidence.
- *Cons:* needs a training pipeline and data generation; a labelling bug silently degrades G2; adds a model to justify under HC-5.
- *Verdict:* **build as the ablation arm** ("rule-based vs model-based controller" is literally a suggested ablation in D3). Ship whichever wins; report both.

**Option E — Small LLM controller with constrained JSON**
Qwen2.5-0.5B / Llama-3.2-1B emitting `{decision, reason, confidence}` under a JSON grammar.

- *Pros:* zero-shot, handles weird cases, human-legible reasons.
- *Cons:* 40–150 ms — too slow to run on *every* chunk; a parsimony liability.
- *Verdict:* **escalation tier only**, invoked on ambiguity (<5% of chunks).

---

### ⭐ Recommended: Cascading Controller (cheap → expensive, early exit)

```
chunk arrives
  │
  ├─ Stage 0: SUPPRESSION GATE                                  (~0.2 ms, regex+rules)
  │    presentation verbs (repeat/shorten/rephrase/bullets/translate/tone)
  │    + zero new content entities + anaphora to prior answer ("that", "your last answer")
  │    → NO-RETRIEVAL {retrieval_required:false, reason:"presentation_restructure"}   [P4, Ex.3]
  │
  ├─ Stage 1: CONTENT FLOOR                                     (~3 ms, NER/POS)
  │    < 1 content anchor OR open dangling preposition → WAIT {reason:"intent_unstable"}
  │
  ├─ Stage 2: CORPUS DISCRIMINATIVENESS PROBE  ⭐ S-1            (~2 ms, BM25)
  │    margin = (s1 - mean(s2..s5)) / s1 ;  H = normalised entropy of top-10
  │    margin > τ_hi AND H < h_lo → RETRIEVE {reason:"corpus_discriminative"}
  │    margin < τ_lo                → WAIT     {reason:"corpus_ambiguous"}
  │    else                         → Stage 3
  │
  ├─ Stage 3: EMBEDDING STABILITY                               (~8 ms)
  │    drift(prefix_t, prefix_{t-1}) < ε AND content anchors ≥ 2 → RETRIEVE {reason:"intent_stabilised"}
  │
  └─ Stage 4: LLM TIE-BREAK (optional, <5% of chunks)           (~60 ms, async, non-blocking)
```

**Also fires RETRIEVE unconditionally on:** a new coordinating conjunction introducing a fresh content anchor (`"…and I need the cancellation policy"` → new intent, retrieve regardless of stability), and on `utterance_end` if nothing has fired yet (safety net guaranteeing we never return empty-handed).

**Threshold calibration is a phase-2 task, not a guess.** Sweep `τ_hi`, `τ_lo`, `ε`, `h_lo` on the synthetic dev set, plot the early-trigger-rate vs false-trigger-rate curve, and pick the knee. Put the chosen values in `config/controller.yaml` (satisfies HC-2 — no magic numbers in code).

---

### ⭐ Novel Mechanism S-1: Corpus-Grounded Intent Stability
> *Instead of asking "has the sentence finished forming?", ask "does the corpus now have an opinion about this prefix?"*

Implementation is ~30 lines. Per chunk, BM25 the prefix, take top-10 raw scores, compute normalised margin and entropy, compare to calibrated thresholds. Cost ≈ 2 ms. The result is a controller whose decisions are *explainable in terms of the corpus itself*, which plays extremely well in both the architecture brief and the demo video ("watch the margin bar cross the line — that's the retrieval firing").

### ⭐ Novel Mechanism S-7: Speculative Retrieval with Branch Cancellation
Every provisional retrieval is a **speculative branch** with a lifecycle:

```
SPECULATIVE → (next chunk consistent)  → CONFIRMED → feeds synthesis context
            → (next chunk contradicts) → CANCELLED → chunks demoted to EvidencePool (not context)
```

Contradiction test: prefix embedding drift > δ **or** the new chunk contains a negation/self-correction marker (`"actually"`, `"no wait"`, `"sorry, I meant"`, `"scratch that"`). Cancelled branches never enter the context window, so aggression costs nothing in quality — but their retrieved chunks stay in the session **EvidencePool**, already fetched and scored, ready to be re-ranked later for free.

**Why this matters for scoring:** it dissolves the G2-vs-P1 tension. We can push the early-trigger rate toward 95% *because* a wrong trigger is recoverable. Report `speculation_accuracy` and `wasted_retrieval_ratio` in telemetry — this converts an apparent risk into a headline metric.

---

### Failure Modes & Mitigations

| Failure | Mitigation |
|---|---|
| Fires on filler ("so basically, um…") | Stage 1 content floor + stopword-only prefixes score flat in the BM25 probe |
| Never fires on a vague but eligible query | `utterance_end` safety-net trigger; `τ_lo` floor tuned for recall |
| Suppresses a turn that actually needed retrieval ("repeat that, and also for Mumbai") | Stage 0 requires **zero new content entities**; "Mumbai" is a new GPE → falls through to normal path and the turn is split into presentation + new intent |
| Thrashing on rapid chunks | Refractory period: no second RETRIEVE within 250 ms unless a new content anchor appeared |

### Metrics Owned
`early_retrieval_rate` (G2), `retrieval_lead_time_ms` (mean Δ before utterance end), `false_trigger_rate` on no-retrieval cases, `suppression_precision/recall`, `speculation_accuracy`, `controller_latency_p95`.

---

# Module C2 — Multi-Intent Decomposition

### Abstract
Converts a compound, unsegmented, partially-complete utterance into a set of **distinct, orthogonal, self-contained sub-queries**, incrementally and without duplication. Owns Gate G3; primary defence against pitfall P5. The hard part is not splitting — it is *knowing when not to split*, and *not re-splitting what you already split one chunk ago*.

---

### Implementation Options

**Option A — Syntactic coordination splitting**
Dependency parse; split conjoined VPs/NPs that share a governing head. `"the cancellation policy and the catering options"` → two NPs under `need`.
- *Pros:* deterministic, ~5 ms, no model cost.
- *Cons:* misses implicit intents ("plan a workshop for 30" implies a capacity question nobody uttered); splits `"cancellation and refund terms"` into two near-identical queries — **straight into P5**.

**Option B — LLM structured decomposition with constrained JSON** ⭐
Small instruct model under a JSON grammar (Outlines / llama.cpp GBNF / json-schema mode) emitting:
```json
{"sub_intents":[{"facet":"venue_capacity","query":"venue capacity for 30 attendees in Pune",
                 "search_string":"Pune workshop venue capacity 30","novel":true}]}
```
- *Pros:* handles implicit intents and ellipsis resolution — the thing rules cannot do. Grammar constraint means it cannot produce malformed output.
- *Cons:* 80–150 ms; must run **off the critical path** (async, concurrent with retrieval of already-known intents).

**Option C — Hybrid: syntactic candidates → LLM canonicalisation** ⭐ *(recommended)*
Rules propose splits cheaply; the LLM validates, merges, resolves anaphora, and adds implicit intents. Rules give recall, the model gives precision and self-containment.

**Option D — Facet classification instead of free-form splitting**
Classify the prefix into a fixed facet taxonomy (capacity / policy-terms / pricing / logistics / eligibility / procedure / comparison) and emit one sub-query per detected facet.
- *Pros:* structurally cannot over-fragment — the facet set is finite. Facets also drive retrieval routing and answer sectioning.
- *Cons:* a corpus-specific taxonomy must be derived in Phase 1 (do this during the corpus audit — cluster section headings, it takes an hour).
- *Verdict:* use facets as **the deduplication key**, layered on top of Option C.

---

### ⭐ Recommended: Monotonic Intent Set with Facet-Keyed Diffing (S-2)

Maintain a per-utterance **IntentSet** that only ever grows:

```python
IntentSet = {
  intent_id: {
    facet, query_nl, search_string,
    first_seen_ts, dispatched: bool, retrieval_event_ids[], status
  }
}
```

On every RETRIEVE decision:
1. Decompose the **current full prefix** (not just the new chunk — context matters).
2. **Diff** the candidate intents against the existing IntentSet using the facet key + embedding similarity (cos > 0.88 = same intent).
3. Dispatch retrieval **only for genuinely new intents**.
4. Refine existing intents in place if the new chunk adds a qualifier — update `search_string`, but do not re-dispatch unless the qualifier changes the retrieval meaningfully (test: does the updated BM25 top-5 differ by >50%?).

**This is exactly what Example 1 demands.** At 0.8 s the set is `{venue_capacity}`. At 1.6 s the decomposer proposes three intents; two are new (`cancellation_terms`, `catering_options`), one already exists — so only **two** new `retrieval_events` are emitted at 1.6 s, matching the brief's printed schema precisely. Most submissions will re-issue all three and silently mismatch the expected output.

---

### ⭐ Novel Mechanism S-3: Retrieval-Overlap Anti-Fragmentation
> *Decide whether two sub-queries are really one intent by looking at what they retrieve, not at what they say.*

Text similarity is a weak proxy for intent identity: `"cancellation terms"` and `"refund policy"` look different and mean the same thing *in this corpus*. So after dispatching, compute **Jaccard overlap of the top-10 chunk ID sets**:

```
overlap(q_i, q_j) = |top10(q_i) ∩ top10(q_j)| / |top10(q_i) ∪ top10(q_j)|
overlap > 0.7  →  merge intents; union their evidence; keep the more specific NL phrasing
```

This is a **post-hoc, evidence-grounded merge** that catches over-fragmentation the text-level dedup misses, and it costs nothing because the retrievals already happened in parallel. Report `over_fragmentation_rate` before and after the merge as an ablation datapoint — it is a clean, quantitative story for D3.

**Guardrail against under-merging:** never merge intents with different facet types even at high overlap (a capacity question and a pricing question can hit the same venue doc while being genuinely distinct sub-intents that G3 wants counted separately).

---

### Failure Modes & Mitigations

| Failure | Mitigation |
|---|---|
| Over-fragmentation ("cancellation **and** refund terms" → 2 queries) | Facet-key dedup → embedding dedup → retrieval-overlap merge (three layers) |
| Under-segmentation (compound treated as one) | Rule layer always proposes coordination splits; LLM must justify a merge |
| Sub-query not self-contained ("the cancellation policy" with no venue) | Mandatory ellipsis resolution in the decomposition prompt; validator rejects sub-queries containing a bare definite NP with no entity, and re-prompts once |
| Decomposition latency blocks retrieval | Run async: already-known intents retrieve immediately while the decomposer works on the new prefix |

### Metrics Owned
`sub_intent_recall` / `precision` (G3), `distinct_intents_per_compound_utterance`, `over_fragmentation_rate`, `merge_rate`, `self_containment_pass_rate`, `decomposition_latency_p95`.

---

# Module C3 — Corpus Retrieval, Fusion & Reranking

### Abstract
Turns a set of sub-queries into a compact, high-factual-density, non-redundant, non-contradictory evidence bundle with intact provenance. Owns the raw material for G4; primary defence against the "diluting context windows / contradictory facts" challenge the brief names explicitly.

---

### 3.1 Indexing Strategy (Phase 1 — do this first, everything depends on it)

**Chunking — structure-aware, provenance-preserving.**
The citation format is `[Doc_ID §Section]`, so **section identity is not metadata, it is a primary key.** Parse document structure (headings, numbered sections) first; chunk *within* section boundaries; never let a chunk straddle two sections.

```python
ChunkID = f"{doc_id}#{section_id}#{ordinal}"     # internal
CitationLabel = f"{doc_id} §{section_id}"        # emitted, e.g. "Doc_12 §2"
```
Target 250–400 tokens with ~15% overlap; keep a parent-document pointer for parent-expansion at synthesis time.

**Contextual chunk enrichment** *(strongly recommended)*: at index time, prepend each chunk with a one-sentence LLM-generated situating summary ("This section of the Pune Venue Agreement covers cancellation windows and refund tiers."). This is a well-documented large retrieval win and is fully legal under HC-2 — it is *corpus indexing*, explicitly named in Phase 1, not query precomputation. **But:** build it via `make index`, never ship a baked artifact, or a reviewer may read it as precomputation.

**Index structure — hybrid, in-process.**
- Sparse: `bm25s` (very fast, pure-Python-friendly, no server)
- Dense: `bge-small-en-v1.5` or `e5-small-v2` → FAISS `IndexFlatIP` (exact search; at hackathon corpus scale, approximate indexes buy nothing and cost recall)
- **No Elasticsearch / no standalone vector DB service.** Two extra containers is a direct HC-5 parsimony cost with no measurable benefit at this scale. Say this out loud in the architecture brief.

---

### 3.2 Retrieval & Fusion

**Per sub-query (all sub-queries concurrently, `asyncio.gather`):**
1. BM25 top-50 ∥ Dense top-50
2. **Reciprocal Rank Fusion** (named explicitly in the brief's Phase 3): `score(d) = Σ 1/(k + rank_i(d))`, `k=60`
3. Cross-encoder rerank the fused top-30 (`bge-reranker-base`) → top-8 per sub-query

**⭐ Novel Mechanism S-8: Facet-Routed Hybrid Weighting**
Different facets want different retrievers, and we can prove it:
- **Policy / terms / eligibility** facets → boost **sparse**. Policy language is exact-match-y ("48 hours prior", "non-refundable", "senior director approval"). Dense embeddings blur exactly the numbers and qualifiers that matter.
- **Descriptive / comparison / logistics** facets → boost **dense**. Paraphrase-heavy, synonym-rich.

Implement as a facet→weight table in `config/retrieval.yaml` (`{policy: {bm25: 0.7, dense: 0.3}, ...}`), applied as a weighted RRF. **This doubles as your required hybrid-vs-dense-only ablation** (D3) and gives a far more interesting result than the naive version: not just "hybrid wins", but "hybrid wins *and here is which facets drive the win*."

---

### ⭐ Novel Mechanism S-9: Facet-Quota Fusion with Contradiction Gating

Two distinct problems the brief calls out, solved in one pass.

**(a) Quota allocation — "without diluting context windows."**
Naively concatenating top-k across sub-queries lets a dominant facet starve the others: the venue-capacity docs score high on everything and crowd out the single catering paragraph. So allocate the context budget by **quota, not by global score**:

```
budget = 3000 tokens
guaranteed = 2 chunks per active sub-intent    # nobody gets starved
remainder  = allocated by marginal factual density
```

**Factual density score** — prefer chunks that *assert* things over chunks that *describe* them. Cheap proxy, no model needed: density = (count of numerals, dates, currency amounts, durations, modal obligations like *must/shall/required*, and named entities) / token count. This measurably raises citation support rate because dense chunks are the ones that actually entail specific claims.

Apply MMR (λ≈0.7) *within* each facet for diversity, dedup near-identical chunks across facets via embedding cosine > 0.95 — and when two chunks are duplicates, **union their citation labels** rather than dropping one, so provenance survives deduplication.

**(b) Contradiction gating — "without introducing contradictory facts."**
Before assembling the context, scan for conflicts inside each facet:
1. **Slot-level check (cheap, deterministic):** extract typed values per facet (durations, percentages, currency, dates, approval roles). Two chunks giving different values for the same slot = candidate conflict.
2. **NLI check (on candidates only):** `nli-deberta-v3-small` cross-encoder, contradiction probability > 0.7 confirms it.

On confirmed conflict, do **not** silently pick one. Either surface both with a recency/specificity cue (*"The 2024 policy states X [Doc_12 §2]; an earlier revision states Y [Doc_08 §1]"*) or route it to the `uncertainty` field. Almost no competing submission will handle this, it directly answers a challenge the brief names by name, and it is a 20-second beat in the demo video that looks like real engineering maturity.

---

### ⭐ The Session EvidencePool (enables S-7 and C4)
A session-scoped, chunk-ID-keyed store:
```python
EvidencePool[chunk_id] = {
  text, doc_id, section_id, embeddings,
  scores_by_subquery: {intent_id: score},
  first_retrieved_ts, used_in_versions: [1, 2], speculative: bool
}
```
Speculative retrievals, cancelled branches, and confirmed evidence all land here. Consequences: cancelled speculation is never wasted work; refinement turns re-rank the existing pool before considering new queries (often answering a late constraint with **zero** new retrievals — a spectacular G5 result); and the pool is the single source of truth for the citation allowlist.

### Metrics Owned
`recall@k`, `nDCG@10` vs gold chunks, `chunk_dedup_rate`, `facet_coverage_rate`, `contradiction_detection_count`, `context_tokens_per_turn`, `retrieval_latency_p95`, `pool_reuse_rate`.

---

# Module C4 — Session-Aware Synthesis & Refinement

### Abstract
Turns evidence into a single unified, fully grounded, versioned answer — and mutates it surgically when late constraints arrive. Owns G4 and G5; primary defence against P2 and P3. This is where the "answer as data structure" rule pays for itself.

---

### ⭐ Novel Mechanism S-4: The Claim Graph & Delta Engine

**The core data structure:**

```python
Claim = {
  "claim_id": "c3",
  "facet": "cancellation_terms",
  "text": "Cancellations made more than 14 days before the event receive a full refund.",
  "citations": ["Doc_31 §4"],
  "preconditions": {"trip_type": "domestic", "booking_timing": "advance"},  # constraint context
  "confidence": 0.91,
  "introduced_in_version": 1,
  "status": "active" | "superseded" | "retracted",
  "superseded_by": null
}
```

The session holds `claims[]`; the rendered `answer` string is a **projection** of the active claims, produced last.

**Refinement flow when a late constraint arrives ("The trip was international and booked after travel"):**

```
1. CLASSIFY turn → NEW_INTENT | CONSTRAINT_REFINEMENT | PRESENTATION_ONLY
2. EXTRACT constraint deltas → {trip_type: international, booking_timing: post_travel}
3. IMPACT ANALYSIS: for each active claim, does the delta conflict with its preconditions?
      no conflict  → RETAIN  (text and citations preserved byte-for-byte)
      conflict     → MARK AFFECTED
4. POOL-FIRST RESOLUTION: can the EvidencePool already answer the affected facets?
      yes → resolve with zero new retrievals
      no  → dispatch TARGETED delta queries, scoped to (affected facet × new constraint) only
            e.g. "international travel reimbursement exception",
                 "post-travel booking approval requirement"
5. MERGE: retained claims kept · affected claims superseded · new claims appended
6. VERSION++ , citations(v2) = citations(retained) ∪ citations(delta)
7. RENDER active claims → unified prose
```

Step 3 is the whole trick. *"The standard reimbursement rule still applies"* in the brief's Example 2 is literally a retained claim being surfaced — the system says it **because it did not have to re-derive it**. And step 4's pool-first resolution is what lets telemetry prove "no full-corpus re-execution" for G5.

**Telemetry emitted on every refinement (this *is* the G5 evidence):**
```json
{"event":"answer_refined","from_version":1,"to_version":2,
 "claims_retained":3,"claims_superseded":1,"claims_added":2,
 "delta_queries_issued":2,"full_corpus_searches":0,
 "citations_preserved":["Doc_12 §2","Doc_31 §4"],"citations_added":["Doc_44 §7"],
 "session_cleared":false,"latency_ms":410}
```
Put `"full_corpus_searches": 0` and `"session_cleared": false` on screen in the demo video. Those two fields *are* Gate G5.

---

### ⭐ Novel Mechanism S-6: Constrained Citation Vocabulary
> *G4 demands **zero** fabricated document IDs. "Zero" is a structural requirement, not a quality target — so solve it structurally.*

Three layers, cheapest first:
1. **Allowlist by construction.** Before generation, build `allowed_ids = {citation labels of chunks in this context}`. The prompt presents chunks with their exact labels and forbids any other.
2. **Grammar/logit constraint.** Where the serving stack supports it (Outlines, llama.cpp GBNF, vLLM guided decoding), constrain citation-marker positions to the allowlist. Fabrication becomes *literally undecodable*.
3. **Post-hoc validator (always on, the backstop).** Regex every `[Doc_* §*]` marker; any ID ∉ allowlist is stripped and the owning sentence is demoted to the uncertainty section. Assert `fabricated_id_count == 0` in CI over the whole replay suite — a hard test failure, not a warning.

Layer 3 alone guarantees the "zero fabricated IDs" half of G4 even if the model misbehaves. Layers 1–2 keep the answer from being shredded by layer 3.

### ⭐ Novel Mechanism S-5: Two-Pass Provisional/Committed Streaming
Verification and streaming appear to conflict: you cannot check a sentence you haven't generated, but you want tokens on screen immediately. Resolve it by **streaming at two confidence levels**:

```
generate sentence → emit as PROVISIONAL (rendered dimmed / italic in UI)
                  → verify (~20-30 ms)  → emit COMMITTED event (rendered solid, citation chip appears)
                                        → or emit RETRACT + regenerate that sentence
```

Verification per sentence, in parallel with generating the next one:
- **Citation validity:** every marker ∈ allowlist (S-6).
- **Entailment:** NLI cross-encoder, cited chunk ⊨ sentence, threshold ~0.6. Fails → attempt re-attribution against the pool; still fails → demote to uncertainty.
- **Numeric/entity copy check** (cheapest and highest-yield): every numeral, date, currency amount, duration and proper noun in the sentence must appear in a cited chunk, after normalisation. This single check catches the majority of realistic hallucinations for almost no cost.

The UX is a genuinely novel demo beat — the viewer *watches grounding happen*, sentence by sentence — and it means G4 verification adds ~0 ms to perceived latency.

### ⭐ Novel Mechanism S-10: Coverage Matrix → Principled Uncertainty
Maintain a `sub_intent × evidence` coverage matrix:

| Sub-intent | Best rerank score | Entailed claim? | State |
|---|---|---|---|
| venue_capacity | 0.91 | yes | **covered** |
| cancellation_terms | 0.84 | yes | **covered** |
| catering_options | 0.31 | no | **uncovered** |

Rules:
- `score < floor` **and** no entailed claim → **uncovered** → contributes a sentence to `uncertainty`, phrased in the brief's own register: *"Catering accommodation policies for Venue A could not be verified from the retrieved corpus."*
- Evidence exists but is **ambiguous between readings** → emit a *targeted clarification question* instead (HC-3 explicitly permits this branch, and using it demonstrates you read the constraint closely).
- Full coverage → `uncertainty` may be empty, but prefer an honest caveat over an empty string; the brief's own happy-path example populates it.

**Never let an uncovered sub-intent silently vanish from the answer.** Dropping it looks identical to never having decomposed it — and it would cost G3 *and* G4 in one move.

### Presentation-Only Turns (Example 3)
Renders **from the claim list only**, with retrieval structurally unreachable:
- Context = active claims + their citations. The corpus index is not even passed to this code path.
- Citations by construction = the citation sets of the reused claims.
- **Hard assertion:** `citations(new) ⊆ citations(prior)`. Any superset is a bug and fails the build.
- Emits `{"retrieval_required": false, "reason": "presentation_restructure"}` — matching the brief's literal field names.
- Reason enum extended: `presentation_restructure`, `translation`, `tone_change`, `acknowledgement`, `chitchat`.

### Metrics Owned
`citation_support_rate` (G4), `fabricated_id_count` (must be 0), `unsupported_claim_rate`, `claims_retained_pct` (G5), `delta_queries_per_refinement`, `full_corpus_searches_on_refinement` (must be 0), `uncertainty_precision` (flagged-uncovered that truly were), `time_to_first_token_after_utterance_end`.

---

# Module C5 — Observability & Telemetry

### Abstract
G6 demands **100% trace coverage** across five named data classes: execution timestamps, retrieval triggers, citations, answer version lineage, and token cost. It is also deliverable D5 and a component in the mandated architecture. Treat it as a product surface, not logging.

### Design
- **Dual sink.** (a) `events.jsonl` — append-only, schema-versioned, the artifact the replay harness scores. (b) **OpenTelemetry** spans → OTLP → Tempo/Jaeger, metrics → Prometheus → **Grafana dashboard**. The brief says "structured logs **or** metrics dashboards" — ship both; the dashboard is what makes the video look finished.
- **Parsimony (HC-5):** JSONL is always on and dependency-free; the OTel/Grafana stack is a `docker compose --profile obs` opt-in so the core engine stays lean and G1 can't be broken by an observability container failing to start.
- **Span tree:** `session → turn → chunk → controller_decision → {retrieval(sub_query) → rerank} → synthesis → verification(sentence) → answer_version`.
- **Every event carries:** `event_id, session_id, turn_id, ts_wall, ts_stream_s, component, latency_ms, payload`.
- **Cost model:** count prompt/completion tokens per call; multiply by a configurable `config/pricing.yaml` table → `cost_usd` per turn, per component, per session. Also track embedding and rerank FLOPs-proxy (items encoded) so the parsimony argument in D2 is quantitative.

### ⭐ The Trace-Coverage Invariant (how you actually *earn* 100%)
Don't claim 100% — **assert** it. Ship `bench/coverage.py`, run in CI over the full replay suite, checking:

| Invariant | Assertion |
|---|---|
| Every chunk has a decision | `count(chunks) == count(controller_decisions)` |
| Every retrieval has a parent | every `retrieval_event` has a preceding `controller_decision` with `RETRIEVE` |
| Every citation resolves | every ID in `citations[]` ∈ indexed chunk IDs |
| Every answer has lineage | every version > 1 has a `version_lineage` record |
| Every LLM call is costed | `count(llm_calls) == count(cost_records)` |
| Every turn is timed | `ts_stream_s` present and monotonic on all events |

`coverage = passed_invariants / total_invariants` → print it in the report as a measured number. That is a far stronger G6 answer than a screenshot.

---

# Cross-Cutting: Benchmark Generation (you must build your own dev set)

The held-out suite is private (HC-2), so build a synthetic streaming benchmark from the supplied corpus. This is legitimate dev data, not hardcoding — state that explicitly in D2.

```
1. Sample 2–3 sections from the corpus
2. Generate a compound question grounded in those sections (LLM, offline, dev-time only)
3. Rewrite into spoken register (disfluencies, "um", self-correction, trailing "and I need…")
4. Simulate chunking: ~150 wpm, emit a chunk every 0.8 s, mark utterance_end
5. Auto-label gold: earliest_retrievable_ts · sub_intent list + facets · gold chunk IDs · expected uncertainty
```

Generate four strata, mirroring the brief's examples plus the pitfalls:
- **A. Multi-intent streaming** (Example 1 clones) — 40%
- **B. Late-constraint refinement** (Example 2 clones) — 25%
- **C. Presentation-only / no-retrieval** (Example 3 clones) — 20% ← *this is the false-trigger denominator for G2, do not skimp*
- **D. Adversarial** — self-corrections, empty-evidence sub-intents, contradictory corpus facts, coordination traps (`"cancellation and refund terms"`), mixed presentation+new-intent — 15%

**Keep the generator's outputs in `bench/data/` and the generator itself in the repo.** Never let a generated question or answer string reach `src/`.

---

# Ablation Plan (D3 requires two; ship four, report the two strongest)

| # | Ablation | Arms | Primary Metric | Expected Story |
|---|---|---|---|---|
| **A1** *(required)* | Hybrid vs dense-only retrieval | weighted-RRF hybrid / dense-only / BM25-only | nDCG@10, citation_support_rate | Hybrid wins overall; the win concentrates in *policy/terms* facets — evidence for S-8 |
| **A2** *(required)* | Rule-based vs model-based controller | Stage 0–2 rules only / trained classifier / full cascade | early_retrieval_rate × false_trigger_rate | Cascade dominates the frontier; publish the ROC-style curve |
| **A3** | Delta refinement vs full restart | claim-delta / naive re-run | latency, tokens, cost, citation continuity | The G5 headline: ~3–5× cheaper refinement with higher citation stability |
| **A4** | With/without contextual chunk enrichment | enriched / raw chunks | recall@10 | Quantifies the index-time investment |

Every ablation runs off one config flag and the same replay harness — that is the whole reason the config layer exists.

---

# Consolidated Novel-Mechanism Index

| ID | Mechanism | Serves | Why It's Differentiating |
|---|---|---|---|
| **S-1** | Corpus-grounded intent stability (BM25 discriminativeness probe) | O1, G2, P1 | Measures retrieval-readiness rather than sentence-completeness; ~2 ms, model-free, auditable |
| **S-2** | Monotonic intent-set diffing | O2, G3 | Produces exactly the brief's event pattern; eliminates duplicate retrievals |
| **S-3** | Retrieval-overlap anti-fragmentation | G3, P5 | Merges intents on evidence, not wording — catches what text dedup misses |
| **S-4** | Claim graph + delta engine | O3, G5, P2 | Makes "refine, don't restart" a data-structure property instead of a prompt instruction |
| **S-5** | Two-pass provisional/committed streaming | G4 | Full verification at ~zero perceived latency; the best visual beat in the demo |
| **S-6** | Constrained citation vocabulary | G4, P3 | Makes fabricated IDs structurally impossible, not statistically rare |
| **S-7** | Speculative retrieval with branch cancellation | G2, P1 | Dissolves the aggression/noise trade-off; wrong guesses become free |
| **S-8** | Facet-routed hybrid weighting | G4, C3 | Turns the required ablation into a genuine finding |
| **S-9** | Facet-quota fusion + contradiction gating | G4, C3 | Directly answers the brief's named fusion challenge; almost nobody else will |
| **S-10** | Coverage matrix → principled uncertainty | O4, G4 | Uncertainty becomes derived and measurable, not vibes |

---

*Next: **03_ENGINEERING_ROADMAP.md** — repository layout, tech stack, interfaces (CLI · WebSocket · frontend · speech), phase-by-phase build plan, and the deliverables production schedule.*
