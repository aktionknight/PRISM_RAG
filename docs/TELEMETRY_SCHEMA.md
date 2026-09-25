# Deliverable D5 — Telemetry & Observability Schema
## Streaming Live RAG (Samsung Theme 4) — Component 5 (Matangi)

---

## 1. Executive Summary & Design Posture

In **Streaming Live RAG**, telemetry is not passive logging—it is a **first-class architectural component** and the **automated proof engine** for Gates G1–G6.

To satisfy **HC-5 (Architectural Parsimony)** and ensure zero external failure modes can break scoring or clean-machine execution (**Gate G1**), the observability stack employs a **Dual-Sink Architecture**:
1. **Always-On JSONL Sink (`events.jsonl`)**: Append-only, schema-versioned, zero-dependency. This is the exact artifact scored by the benchmark harness and asserted by the trace-coverage suite.
2. **Opt-In OpenTelemetry & Grafana Stack (`--profile obs`)**: Hierarchical distributed spans exported to Tempo, metrics scraped by Prometheus, and visualized on a 3-pane Grafana dashboard during the scripted demo video (Beat 6).

---

## 2. Telemetry Event Contract (`TelemetryEvent`)

Every pipeline event emitted across the stream conforms strictly to the frozen Pydantic contract in `src/slrag/core/schemas.py`:

```json
{
  "event_id": "evt_01923058b8f0_7a9c14d9",
  "session_id": "sess_replay",
  "turn_id": 1,
  "ts_stream_s": 0.8,
  "ts_wall": "2026-09-25T01:20:00.123456+00:00",
  "component": "controller",
  "event_type": "controller_decision",
  "latency_ms": 1.45,
  "payload": {
    "decision": "RETRIEVE",
    "reason": "corpus_discriminative",
    "confidence": 0.88,
    "stage": 2
  }
}
```

### Field Definitions

| Field | Type | Description |
|---|---|---|
| `event_id` | `string` | Unique, sortable identifier (ULID or monotonic timestamp-prefixed hex). |
| `session_id` | `string` | Ephemeral session boundary identifier (HC-4 compliant). |
| `turn_id` | `integer` | 1-indexed turn counter within the session. |
| `ts_stream_s` | `float` | **Stream time** in seconds from utterance start (governed by `StreamClock`). |
| `ts_wall` | `string` | ISO-8601 UTC timestamp of event generation. |
| `component` | `string` | Originating component: `stream`, `controller`, `decomposer`, `retriever`, `synthesizer`, `verifier`, `orchestrator`. |
| `event_type` | `string` | Typed constant from `src/slrag/core/events.py`. |
| `latency_ms` | `float` | Execution duration of the generating step in milliseconds. |
| `payload` | `object` | Schema-specific key-value payload. |

---

## 3. Pipeline Event Vocabulary

| Phase | Event Type (`event_type`) | Component | Key Payload Fields |
|---|---|---|---|
| **Stream** | `chunk_received` | `stream` | `text`, `is_final` |
| **Controller** | `controller_decision` | `controller` | `decision` (WAIT/RETRIEVE/NO_RETRIEVAL), `reason`, `confidence`, `stage` |
| **Controller** | `speculation_started` | `controller` | `branch_id`, `sub_intent_id`, `query` |
| **Controller** | `speculation_confirmed` | `controller` | `branch_id` |
| **Controller** | `speculation_cancelled` | `controller` | `branch_id`, `reason` |
| **Decomposition** | `decomposition_started` | `decomposer` | `prefix` |
| **Decomposition** | `decomposition_completed` | `decomposer` | `total_candidates`, `novel_intents` |
| **Decomposition** | `intent_added` | `decomposer` | `intent_id`, `facet` |
| **Retrieval** | `retrieval_started` | `retriever` | `event_id`, `query`, `sub_intent_id`, `trigger` |
| **Retrieval** | `retrieval_completed` | `retriever` | `sub_intent_id`, `num_chunks` |
| **Retrieval** | `rerank_completed` | `retriever` | `num_candidates`, `top_score` |
| **Retrieval** | `contradiction_detected` | `retriever` | `facet`, `slot`, `values` |
| **Synthesis** | `synthesis_started` | `synthesizer` | — |
| **Synthesis** | `sentence_provisional` | `synthesizer` | `sentence_idx`, `text` |
| **Synthesis** | `sentence_committed` | `synthesizer` | `sentence_idx`, `citations` |
| **Synthesis** | `answer_version` | `synthesizer` | `version`, `citations`, `uncertainty`, `claims_count` |
| **Synthesis** | `answer_refined` | `synthesizer` | `from_version`, `to_version`, `claims_retained`, `claims_superseded`, `claims_added`, `delta_queries_issued`, `full_corpus_searches`, `session_cleared` |
| **Verification** | `citation_verified` | `verifier` | `citation_label`, `chunk_id` |
| **Verification** | `citation_fabricated` | `verifier` | `unresolved_id` (asserted count == 0 in CI) |
| **Accounting** | `llm_call` | `*` | `model`, `prompt_tokens`, `completion_tokens` |
| **Accounting** | `cost_record` | `*` | `item_type`, `cost_usd`, `model` |

---

## 4. Gate G6: The 6 Trace-Coverage Invariants

Gate G6 demands **100% trace coverage** across execution timestamps, retrieval triggers, citations, answer version lineage, and token costs. This is **asserted programmatically** via `bench/coverage.py`:

```bash
python bench/coverage.py --run runs/events.jsonl
```

| # | Invariant Name | Mathematical Assertion | Target Requirement |
|---|---|---|---|
| **1** | Chunk-Decision Parity | `count(chunks) == count(controller_decisions)` | Every chunk is evaluated without omission |
| **2** | Retrieval Parentage | Every `retrieval_started` has a preceding `RETRIEVE` decision | No spontaneous/uncontrolled queries |
| **3** | Citation Resolution | Every ID in `citations[]` $\in$ indexed chunk IDs | Strict grounding (Gate G4) |
| **4** | Version Lineage | Every answer with `version > 1` has `version_lineage` | State continuity proof (Gate G5) |
| **5** | Cost Accounting | `count(llm_calls) <= count(cost_records)` | Strict HC-5 parsimony tracking |
| **6** | Monotonic Stream Time | `ts_stream_s` present and strictly non-decreasing | Temporal integrity across stream |

`Coverage % = (Passed Invariants / 6) * 100.0` $\rightarrow$ must evaluate to **100.0%**.

---

## 5. Cost Accounting Model (`pricing.yaml`)

Token usage and compute costs are calculated dynamically using `config/pricing.yaml`:

$$\text{Turn Cost} = \sum_{\text{LLM Calls}} \left( \frac{\text{Prompt Tok}}{1000} \cdot R_p + \frac{\text{Comp Tok}}{1000} \cdot R_c \right) + \sum_{\text{Embeddings}} \left( \frac{\text{Items}}{1000} \cdot R_e \right) + \sum_{\text{Reranks}} \left( \frac{\text{Items}}{1000} \cdot R_r \right)$$

This metric is embedded directly into the final `AnswerOutput.telemetry.cost_usd` on every turn.
