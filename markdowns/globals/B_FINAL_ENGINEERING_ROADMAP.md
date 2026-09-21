# Streaming Live RAG — Final Engineering Roadmap
## Document B of 2 — Build Plan for the Committed Architecture (Samsung Theme 4)

> Builds exactly the design fixed in **A — Final Architecture**. No alternative options are listed here — every task below produces one specific, already-decided component.

---

## 1. Runtime Topology & Interfaces

```
┌──────────────────────────────────────────────────────────────────────────┐
│  INPUT ADAPTERS  (all implement TranscriptSource)                        │
│  ReplaySource (JSONL+clock) ← EVAL PATH   │  WebSocketSource ← UI PATH    │
│  MicSource (VAD→faster-whisper) ← DEMO PATH                              │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ TranscriptChunk{t_s, text, is_final}
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SLRAG ENGINE — single async process                                     │
│  [1] RetrievalController (cascade + speculation)                         │
│  [2] IntentSet + Decomposer (monotonic diff + overlap merge)             │
│  [3] HybridRetriever → facet-weighted RRF → rerank → quota+contradiction │
│  [4] SynthesisEngine (ClaimGraph + delta + 2-pass streaming + allowlist) │
│  ══ TelemetryBus taps every stage ═══════════════════════════════════════│
└──────────┬──────────────────────────┬────────────────────────────────────┘
           │ events (WS/SSE)          │ spans + metrics
           ▼                          ▼
   Frontend UI / CLI          events.jsonl (always on)
                               OTel→Tempo · Prom→Grafana (--profile obs)
```

**Evaluation path vs. demo path are strictly separated.** `ReplaySource` (JSONL playback against a virtual clock) is what the held-out benchmark runs against and what G1–G6 are scored on. Microphone input is a demo convenience only and must never sit on the critical/graded path.

### 1.1 Speech Input (demo path)
- **ASR**: `faster-whisper` (CTranslate2, `small.en`), local and offline — preserves the HC-1 posture (no external API calls) and keeps the whole system reproducible without network access.
- **VAD**: Silero VAD to detect pause boundaries.
- **Chunk emission**: on whichever comes first — ~0.8 s elapsed, a VAD pause > 250 ms, or ASR prefix stabilisation (LocalAgreement-2 style) — always closing with `is_final=true` at utterance end.
- `timestamp_s` in every event is **stream time from utterance start**, never wall-clock time.

### 1.2 Interfaces

**CLI**
```bash
slrag index  --corpus ./corpus --out ./.index          # explicit, reproducible build (HC-2)
slrag replay --corpus ./corpus --stream ./bench/data/suite.jsonl --out ./runs/events.jsonl
slrag chat   --corpus ./corpus                           # typed interactive session
slrag listen --corpus ./corpus --asr faster-whisper       # live mic demo
slrag score  --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl
```

**WebSocket** — `/ws/session`: client sends `{type:"chunk", t_s, text}` / `{type:"utterance_end"}`; server streams `controller_decision`, `retrieval_started`, `subqueries_updated`, `answer_token` (provisional/committed), `citation_attached`, `answer_version`, `uncertainty`, `telemetry_tick`.

**Frontend (React + Vite + Tailwind + Recharts, three panes)**

| Pane | Contents | Demonstrates |
|---|---|---|
| Left — Live Stream | Transcript with per-chunk timestamps; badge per chunk (WAIT grey / RETRIEVE green / SUPPRESS amber) + reason; live discriminativeness-margin meter | Early retrieval, suppression |
| Centre — Answer | Streaming answer, dimmed-then-solid sentences; clickable citation chips jumping to the highlighted source span; version slider V1↔V2 with claim-level diff | Decomposition, refinement, traceability |
| Right — Telemetry | Retrieval Gantt (stream-time axis, hatched speculative bars); latency histogram; cost counters; live G2–G4 gate readouts | Runtime telemetry |

---

## 2. Repository Layout

```
streaming-live-rag/
├─ README.md                      # one-command quickstart
├─ docker-compose.yml             # profiles: core (default) | ui | obs
├─ Dockerfile
├─ Makefile                       # make up | index | replay | bench | ablate | score
├─ pyproject.toml + uv.lock        # pinned (D1)
├─ .env.example
│
├─ config/
│  ├─ app.yaml            controller.yaml        # τ_hi, τ_lo, ε, h_lo, refractory_ms
│  ├─ retrieval.yaml       facets.yaml
│  ├─ pricing.yaml
│  └─ prompts/  decompose.jinja  synthesize.jinja  refine.jinja  present_only.jinja
│
├─ corpus/                        # mounted read-only
├─ src/slrag/
│  ├─ core/        events.py · schemas.py · session.py · clock.py
│  ├─ ingest/      loader.py · chunker.py · contextualizer.py · indexer.py
│  ├─ stream/      source_replay.py · source_ws.py · source_mic.py · vad.py · asr.py
│  ├─ controller/  suppression.py · content_floor.py · probe.py · stability.py ·
│  │               cascade.py · speculation.py
│  ├─ decompose/   intent_set.py · decomposer.py · overlap.py · facets.py
│  ├─ retrieve/    sparse.py · dense.py · rrf.py · rerank.py · pool.py ·
│  │               quota.py · contradiction.py · density.py
│  ├─ synth/       claims.py · delta.py · generator.py · verifier.py ·
│  │               uncertainty.py · renderer.py
│  ├─ telemetry/   bus.py · jsonl_sink.py · otel_sink.py · cost.py · coverage.py
│  ├─ baseline/    batch_rag.py          # the D3 comparison denominator
│  └─ api/         cli.py · ws_server.py
│
├─ ui/                            # React + Vite frontend
├─ bench/          generate.py · data/ · metrics.py · ablate.py · coverage.py
├─ tests/          unit + golden replay + compliance tests
└─ docs/
   ├─ ARCHITECTURE_BRIEF.md · TELEMETRY_SCHEMA.md
   ├─ EVALUATION_REPORT.md · DEMO_SCRIPT.md
```

---

## 3. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Runtime | Python 3.11, `asyncio` | True parallel sub-query dispatch, one process — no broker |
| Packaging | `uv` + `uv.lock` | Pinned (D1), fast clean-machine installs (G1) |
| Serving | FastAPI + uvicorn | WS + REST + SSE in one app |
| Sparse index | `bm25s` | Sub-ms, in-process, feeds the S-1-equivalent discriminativeness probe directly |
| Dense index | FAISS `IndexFlatIP` | Exact search; corpus scale makes ANN unnecessary |
| Embeddings | `bge-small-en-v1.5` | CPU-viable, 384-d |
| Reranker | `bge-reranker-base` | Applied to ≤30 candidates |
| NLI verifier | `nli-deberta-v3-small` | Sentence entailment + contradiction gating |
| Generator LLM | Qwen2.5-7B-Instruct via local Ollama/vLLM (OpenAI-compatible) | Local = offline-reproducible, HC-1-clean; only synthesises from supplied context |
| Structured output | Outlines / GBNF / json-schema mode | Schema-valid decomposition + citation allowlist enforcement |
| NLP utilities | spaCy `en_core_web_sm` | Content-anchor NER, dependency splits |
| ASR (demo) | faster-whisper + Silero VAD | Local, offline, no API keys |
| Telemetry | JSONL (always on) + OTel→Tempo, Prom→Grafana (opt-in) | Scoring artifact vs. demo dashboard, decoupled |
| Frontend | React + Vite + Tailwind + Recharts | Gantt + version-diff views |
| Tests | pytest + pytest-asyncio + golden replay fixtures | Unattended CI run for G1 |

**Model weights are baked into the image at build time or fetched via `make setup`, never lazily downloaded at first request** — the single most common cause of G1 failure on a judge's clean/offline machine.

---

## 4. Phase-by-Phase Build Plan

### Phase 1 — Framing & Foundation

| # | Task | Output |
|---|---|---|
| 1.1 | Corpus audit — structure, headings, section-ID scheme, duplicate/conflicting versions | `docs/corpus_audit.md` |
| 1.2 | Derive facet taxonomy from section/topic clustering | `config/facets.yaml` |
| 1.3 | Structure-aware chunker (section-bounded, 250–400 tok, 15% overlap) | `ingest/chunker.py` |
| 1.4 | Citation label resolver `ChunkID ↔ "Doc_12 §2"` + round-trip test | `core/schemas.py` |
| 1.5 | Hybrid index build (bm25s + FAISS), `slrag index` command | `.index/` |
| 1.6 | Contextual chunk enrichment (situating summary per chunk, built via command) | enriched index |
| 1.7 | Event schema v1 — five required keys exact + additive fields, Pydantic + JSON Schema export | `core/events.py` |
| 1.8 | Baseline batch RAG (wait-for-final → single query → dense top-k → single-shot generate) | `baseline/batch_rag.py` |
| 1.9 | Telemetry bus + JSONL sink instrumented from day one | `telemetry/bus.py` |
| 1.10 | Repo scaffold, Docker, Makefile, CI | `docker compose up` runs empty |

**Exit criteria:** indexed corpus returns correctly-labelled `[Doc_ID §Section]` citations; `events.jsonl` populating; CI green.

---

### Phase 2 — Controller & Live Stream Simulation

| # | Task | Output |
|---|---|---|
| 2.1 | Replay harness — real-clock and virtual-clock JSONL player | `stream/source_replay.py` |
| 2.2 | Synthetic streaming benchmark generator — 4 strata: multi-intent (40%), refinement (25%), presentation-only (20%), adversarial (15%) | `bench/generate.py`, `bench/data/` |
| 2.3 | Stage 0 suppression gate | `controller/suppression.py` |
| 2.4 | Stage 1 content floor | `controller/content_floor.py` |
| 2.5 | Stage 2 corpus discriminativeness probe (BM25 margin + entropy) | `controller/probe.py` |
| 2.6 | Stage 3 embedding stability | `controller/stability.py` |
| 2.7 | Cascade assembly + refractory period + utterance-end safety net | `controller/cascade.py` |
| 2.8 | Speculation manager — branch lifecycle, contradiction detection, pool demotion | `controller/speculation.py` |
| 2.9 | Threshold calibration sweep → knee selection → `controller.yaml` | calibration notebook |
| 2.10 | G2 scorer (early_retrieval_rate, lead_time, false_trigger_rate) | `bench/metrics.py` |
| 2.11 | Stage 4 LLM tie-break (async, ambiguous-chunk fallback) | `controller/cascade.py` |

**Exit criteria:** G2 ≥ 80% (target 90%+) with false-trigger rate < 15% on the presentation-only stratum; the brief's four-chunk timeline (Example 1) reproduces exactly.

---

### Phase 3 — Multi-Intent Parsing & Evidence Fusion

| # | Task | Output |
|---|---|---|
| 3.1 | Syntactic candidate splitter (dependency parse) | `decompose/decomposer.py` |
| 3.2 | LLM canonicalisation under JSON grammar — ellipsis/anaphora resolution, self-containment validator with one re-prompt | `decompose/decomposer.py` |
| 3.3 | Facet tagging per candidate | `decompose/facets.py` |
| 3.4 | Monotonic IntentSet — facet + embedding diff (cos > 0.88), dispatch new intents only | `decompose/intent_set.py` |
| 3.5 | Retrieval-overlap merge (Jaccard top-10 > 0.7, facet-guarded) | `decompose/overlap.py` |
| 3.6 | Parallel hybrid retrieval (`asyncio.gather`, bounded concurrency) | `retrieve/` |
| 3.7 | Facet-routed weighted RRF (k=60) | `retrieve/rrf.py` |
| 3.8 | Cross-encoder rerank on fused top-30 | `retrieve/rerank.py` |
| 3.9 | Chunk dedup with citation-label union (cosine > 0.95) | `retrieve/pool.py` |
| 3.10 | Facet-quota context assembly + factual-density scoring + within-facet MMR | `retrieve/quota.py`, `density.py` |
| 3.11 | Contradiction gating — typed-slot extraction → NLI confirmation → surface-both/uncertainty | `retrieve/contradiction.py` |
| 3.12 | Session EvidencePool | `retrieve/pool.py` |
| 3.13 | G3 scorer + over-fragmentation rate | `bench/metrics.py` |

**Exit criteria:** G3 ≥ 70% (target 85%); Example 1 reproduces exactly (3 `sub_queries`, 3 `retrieval_events` split 1@0.8s / 2@1.6s with correct `trigger` values); the coordination trap (`"cancellation and refund terms"`) collapses to one intent, not two.

---

### Phase 4 — Session Refinement & State Management

| # | Task | Output |
|---|---|---|
| 4.1 | Ephemeral in-process session store, TTL + destruction, cross-session isolation test | `core/session.py` |
| 4.2 | ClaimGraph model — facet, citations, preconditions, status, version lineage | `synth/claims.py` |
| 4.3 | Turn classifier — NEW_INTENT / CONSTRAINT_REFINEMENT / PRESENTATION_ONLY | `synth/delta.py` |
| 4.4 | Delta engine — constraint extraction → impact analysis → pool-first resolution → targeted queries → merge → version++ | `synth/delta.py` |
| 4.5 | Presentation-only renderer — claim-list-only path, retrieval structurally unreachable, `citations(new) ⊆ citations(prior)` hard assertion | `synth/renderer.py` |
| 4.6 | Generator — unified narrative over active claims, prompts from `config/prompts/` | `synth/generator.py` |
| 4.7 | Constrained citation vocabulary — allowlist + grammar constraint + post-hoc stripper; CI asserts `fabricated_id_count == 0` | `synth/verifier.py` |
| 4.8 | Two-pass provisional/committed streaming — citation validity + NLI entailment + numeral/entity copy check per sentence | `synth/verifier.py` |
| 4.9 | Coverage matrix → uncertainty / clarification-question branch | `synth/uncertainty.py` |
| 4.10 | Refinement telemetry — `claims_retained/superseded/added`, `delta_queries_issued`, `full_corpus_searches:0`, `session_cleared:false` | telemetry events |
| 4.11 | G4 + G5 scorers | `bench/metrics.py` |

**Exit criteria:** G4 ≥ 85% citation support, 0 fabricated IDs; Example 2 reproduces (V1→V2, prior citations retained, delta citations added, 2 targeted queries, 0 full-corpus searches); Example 3 reproduces (0 retrieval events, citation subset).

---

### Phase 5 — Telemetry, Benchmarking & Packaging

| # | Task | Output | Deliverable |
|---|---|---|---|
| 5.1 | OTel spans + Prometheus + Grafana dashboard (`--profile obs`) | dashboards | D5 |
| 5.2 | Cost model — token accounting × `pricing.yaml` | telemetry field | D5, HC-5 |
| 5.3 | Trace-coverage invariant suite (6 invariants, CI-asserted) | `bench/coverage.py` | D5 / G6 |
| 5.4 | Full benchmark run vs. baseline, all 4 strata | results tables | D3 |
| 5.5 | Ablations: (A1) hybrid vs dense-only, (A2) rule-cascade vs +LLM-tiebreak, (A3) delta refinement vs full restart, (A4) with/without contextual enrichment | ablation tables | D3 |
| 5.6 | ≥3 edge-case failure analyses (self-correction, coordination trap, contradictory-facts) | write-ups | D3 |
| 5.7 | Single-command packaging, weights baked in, offline-verified on a clean machine | image + README | D1 / G1 |
| 5.8 | Architecture brief ≤6 pages | `docs/ARCHITECTURE_BRIEF.md` | D2 |
| 5.9 | Demo video ≤5 min, six scripted beats | recording | D4 |
| 5.10 | Frontend polish — version slider, citation-chip jump, retrieval Gantt | UI | D4 |

**Exit criteria:** clean-machine, offline, one-command rehearsal succeeds at least 24 hours before submission.

---

## 5. Ablation Plan (D3 requires two; all four are built)

| # | Ablation | Arms | Primary Metric |
|---|---|---|---|
| A1 *(required)* | Hybrid vs dense-only retrieval | facet-weighted RRF hybrid / dense-only / BM25-only | nDCG@10, citation_support_rate |
| A2 *(required)* | Cascade vs cascade+LLM-tiebreak | rules-only (Stages 0–3) / full cascade with Stage 4 | early_retrieval_rate × false_trigger_rate |
| A3 | Delta refinement vs full restart | claim-delta engine / naive full re-run | latency, tokens, cost, citation continuity |
| A4 | With/without contextual chunk enrichment | enriched / raw chunks | recall@10 |

---

## 6. Edge Cases (D3 requires ≥3 analysed)

| Edge Case | Handling in This Architecture |
|---|---|
| Self-correction mid-utterance | Speculation manager cancels on negation marker / drift; chunks demoted to pool, never reach context |
| Coordination trap (`"cancellation and refund terms"`) | Facet-key dedup → retrieval-overlap merge collapses to one intent |
| Mixed presentation + new intent | Stage 0 requires zero new content entities; turn splits into a presentation op + a genuine new intent |
| Empty-evidence sub-intent | Coverage matrix forces an explicit `uncertainty` sentence, never silent drop |
| Contradictory corpus facts | Contradiction gate surfaces both readings with citations, or routes to uncertainty |
| Ambiguous entity (city vs. venue name) | Bimodal retrieval score distribution triggers a targeted clarification question |

---

## 7. Performance Budget

| Stage | Target p95 |
|---|---|
| Controller decision per chunk | ≤ 15 ms |
| BM25 discriminativeness probe | ≤ 3 ms |
| Decomposition (async, off critical path) | ≤ 150 ms |
| Single sub-query hybrid retrieval | ≤ 60 ms |
| Cross-encoder rerank (30 candidates) | ≤ 120 ms CPU |
| Per-sentence verification | ≤ 30 ms (parallel to next-sentence generation) |
| **Time to first answer token after utterance end** | **≤ 300 ms** |
| Baseline batch RAG (same metric) | ~1.8–3.0 s |

---

## 8. Compliance Checklist

| Check | Status |
|---|---|
| No network egress from engine container; CI fails on outbound HTTP during replay | ☐ |
| Zero prompts/query strings in `src/`; all in `config/prompts/`; index built by command | ☐ |
| `fabricated_id_count == 0` asserted in CI; citation support ≥ 85% | ☐ |
| No disk persistence of session data; cross-session isolation test passes | ☐ |
| ≤3 LLM calls/turn documented; per-component latency/cost published; single process | ☐ |
| Output validates against the five required schema keys, exact names/types/format | ☐ |
| Clean-machine, offline, one-command rehearsal completed | ☐ |
| Trace-coverage invariants all pass; coverage % printed in report | ☐ |
| D1–D5 all produced and linked from README | ☐ |

---

## 9. Demo Video Storyboard (≤5 minutes, six beats)

| # | Beat | Screen | Time |
|---|---|---|---|
| 0 | Cold start | `docker compose up` on a clean, offline machine | 0:20 |
| 1 | Early retrieval triggering | Badges flip WAIT→RETRIEVE mid-utterance; discriminativeness meter crosses threshold | 0:50 |
| 2 | Multi-intent decomposition | Three sub-queries appear; Gantt shows parallel bars, capacity bar not re-issued | 0:45 |
| 3 | Citation traceability | Answer streams dimmed→solid; citation chip click opens highlighted source span | 0:45 |
| 4 | Late-detail refinement | Version slider V1→V2; retained claims stay plain, superseded amber, added green; `full_corpus_searches: 0` on screen | 0:50 |
| 5 | Query suppression | "Repeat that in two bullets" → amber SUPPRESS badge, empty Gantt, unchanged citations | 0:35 |
| 6 | Runtime telemetry | Grafana dashboard, then the G1–G6 gate readout board | 0:35 |

---

## 10. Risk Register

| Risk | Mitigation | Checkpoint |
|---|---|---|
| Corpus lacks clean section structure | Derive synthetic section IDs from heading hierarchy; document mapping | Phase 1, day 1 |
| Controller thresholds overfit to dev set | Calibrate on a held-out split; keep utterance-end safety net | Phase 2 exit |
| Decomposition latency blocks retrieval | Runs async; already-known intents retrieve immediately | Phase 3 |
| LLM ignores citation allowlist | Post-hoc validator is the unconditional backstop | Phase 4 |
| Model weights fetched at first run | Bake into image / fetch in `make setup`; rehearse offline | Phase 5, T-24h |
| Obs stack breaks `docker compose up` | Opt-in profile only; core path never depends on it | Phase 5 |
| Scope creep toward multi-agent framework | ≤3-LLM-calls-per-turn budget enforced in review | Continuous |

---

*This is the final, decided build. Document A specifies what is built and why it was chosen; this document specifies when and in what order.*
