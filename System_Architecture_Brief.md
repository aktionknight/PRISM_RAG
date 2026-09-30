# Deliverable 2: System Architecture Brief

**Project:** Streaming Live RAG (PRISM)
**Date:** September 2026

---

## 1. System Design Rationale

The Streaming Live RAG system is designed as a single, asynchronous process that treats user utterances as continuous event streams rather than discrete requests. The core architectural philosophy is guided by three principles:
1. **Let the corpus be the oracle, not the LLM.** We measure retrieval-readiness by checking whether a partial utterance is discriminative against the sparse index, rather than relying on an LLM to guess sentence completeness.
2. **Make being wrong cheap.** Speculative retrieval branches can be cancelled without impacting the user's context window. Cancelled chunks are demoted to a session-level Evidence Pool where they are essentially free to reuse later.
3. **The answer is a data structure, not a string.** We represent the final answer as a graph of typed claims. Refinement becomes a surgical graph mutation instead of a costly regeneration, ensuring maximum stability.

The architecture strictly adheres to hard parsimony constraints (HC-5) by running locally, minimizing LLM calls per turn, and utilizing deterministic algorithms where possible.

## 2. Retrieval Trigger Logic (Controller)

The system employs a 5-stage cascading controller designed for extreme speed (≤15 ms p95) and early-exit capabilities:

1. **Stage 0 - Suppression Gate:** Regex and rule-based (~0.2 ms). Suppresses presentation verbs and anaphoric references containing zero new entities.
2. **Stage 1 - Content Floor:** Fast NLP parsing (~3 ms). Prevents firing if the query lacks a content anchor.
3. **Stage 2 - Corpus Discriminativeness Probe:** BM25 scoring against the sparse index (~2 ms). Triggers retrieval if the top-10 score distribution shows high peakedness (margin > $\tau_{hi}$ and $H < h_{lo}$).
4. **Stage 3 - Embedding Stability:** bge-small drift analysis (~8 ms). Checks if semantic drift between contiguous prefix chunks has stabilized.
5. **Stage 4 - LLM Tie-Break:** Asynchronous fallback (<5% of chunks, ~60 ms). Resolves true ambiguity using an LLM JSON grammar constraint.

All provisional retrievals from Stages 2 and 3 are **speculative**. If the subsequent chunk contradicts the speculation (e.g., a self-correction marker like "actually"), the branch is cancelled and the retrieved chunks are demoted to the Evidence Pool.

## 3. Query Decomposition Strategy

To handle compound, multi-intent queries, the engine uses a facet-keyed, monotonic decomposition flow:

1. **Syntactic Splitting:** Deterministic parsing identifies conjunctions and candidate splits.
2. **LLM Canonicalization:** An LLM refines and canonicalizes the splits into self-contained search queries, resolving ellipsis and implicit intents under a constrained JSON schema.
3. **Facet Deduplication:** Intents are classified into the corpus-derived facet taxonomy (e.g., `venue_capacity`, `cancellation_terms`). New queries are diffed against the session's active `IntentSet`. Identical facets with > 0.88 cosine similarity merely update the in-place search string instead of initiating a duplicate retrieval.
4. **Retrieval-Overlap Anti-Fragmentation:** If two sub-queries retrieve a >70% identical Jaccard overlap of chunks within the same facet, they are automatically merged into a single intent, consolidating evidence without text duplication.

## 4. Data Provenance & Grounding

Data provenance is structurally enforced via a **Constrained Citation Vocabulary**:
- **Index Granularity:** Chunks are bounded by sections. `ChunkID` includes doc and section identifiers (`doc_id#section_id#ordinal`), emitting `CitationLabel = "Doc_ID §Section"`.
- **Allowlisting:** The LLM prompt restricts citation markers strictly to the chunk labels present in the retrieved context.
- **Verification (Two-Pass Streaming):** As the model generates text, it emits *provisional* tokens to the UI. Concurrently, an NLI entailment check and an entity copy-check confirm that the sentence is strictly supported by its cited chunks. Once verified, the sentence is committed.
- **Coverage Matrix:** Sub-intents that return no evidence or fail entailment checks are explicitly logged in an `uncertainty` block (e.g., "Catering accommodation policies could not be verified."). We never silently fabricate or drop missing facts.

## 5. Trade-Offs

- **Parsimony vs. LLM Intelligence:** We offload heavily to BM25 and traditional NLP for the controller rather than using an LLM for every chunk. While this requires manual calibration of thresholds ($\tau_{hi}$, $\tau_{lo}$), it provides <15ms latency per chunk, allowing true real-time streaming.
- **Speculative Waste vs. Early Delivery:** We intentionally over-trigger the retrieval engine. This trades local compute cycles (waste) for significantly lower retrieval lead times. Because the cancelled branches populate the Evidence Pool, the "waste" acts as prefetching for future turns.
- **In-Memory vs. Persistent DBs:** We do not use external vector databases like Elasticsearch. The system utilizes in-process `bm25s` and `FAISS` indexes. This limits extreme scalability (e.g., billion-scale corpora) but completely avoids network overhead and satisfies the deployment constraints (HC-4/HC-5).

## 6. Failure Mode Mitigations

| Failure Mode | Mitigation Strategy |
| :--- | :--- |
| **Premature Firing on Filler ("um, so...")** | Stage 1 content floor prevents firing; BM25 Stage 2 yields flat scores for stopwords. |
| **Over-fragmentation of Synonymous Intents** | Facet-keyed `IntentSet` deduplication + retrieval-overlap merging (S-3) combines intents. |
| **Context Window Dilution** | **Facet-Quota Fusion:** Context budget is allocated equally across active sub-intents (e.g., 2 chunks guaranteed per intent), preventing dominant facets from starving sparse ones. |
| **Contradictory Facts in Context** | Slot-level NLI contradiction gating. Conflicting facts (e.g., two different refund dates) are either surfaced explicitly with recency cues or pushed to uncertainty; never silently averaged. |
| **LLM Hallucinated Citations** | Post-hoc regex validator strips any `[Doc_* §*]` tag not in the exact context allowlist. |
