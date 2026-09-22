# Streaming Live RAG — Phase 0: Corpus-Agnostic Facet Discovery
## Document D — Inserted Before Phase 1 (Samsung Theme 4)

> **Why this document exists:** the held-out benchmark corpus is private (HC-2) and the graded replay suite is not built from the brief's three printed examples — it will very likely run against a *different* document set entirely. A facet taxonomy authored by hand for one corpus, or a clustering pipeline with unresolved algorithm choices and an untested structure assumption, both fail the same way: silently, on the judges' machine, on a corpus none of us has seen. This document resolves the facet-discovery subsystem sketched in Doc B §1.2 into one fully decided, deterministic, corpus-agnostic pipeline, and fixes its place in the sprint so it stops sitting on the team's critical path.
>
> Read alongside **A — Final Architecture**, **B — Final Engineering Roadmap**, and **C — Team Coordination**. This document **replaces** Doc B's §1.2 (facet clustering) in full; everywhere else in Docs A–C references "the facet taxonomy," it now means the output contract defined in §4 below.

---

## 1. What Was Wrong, Restated as Requirements

The previous draft was correct to target generality but left three things undecided that a single build cannot leave undecided:

| Gap | Why It Blocks a Real Build | Requirement This Document Resolves |
|---|---|---|
| Two clustering algorithms offered, unresolved | Two teammates could pick differently and get incompatible facet counts on the same corpus | **R1:** exactly one clustering algorithm, deterministic, seed-pinned |
| Heading extraction assumed Markdown syntax | The brief itself is a PDF with numbered plain-text headings, not `#`/`##` — the extractor would find nothing on the one document we've actually seen | **R2:** structure detection must work on PDFs, numbered sections, bold-run headers, and — critically — documents with **no** extractable heading structure at all |
| Facet-discovery pipeline sat on Phase 1's critical path | Every teammate's typed interfaces (`Claim.facet`, retrieval routing, decomposer tagging) were blocked on code that didn't exist yet on Day 1 | **R3:** the pipeline is proven and frozen once, offline, before the sprint's coding hours start — never a live dependency between teammates |
| Retrieval-bias assignment was a heuristic guess (numeral density) | Contradicts the architecture's own stated principle ("ask the corpus, not a proxy") | **R4:** retrieval bias per facet is measured empirically, not inferred |
| No reproducibility guarantee | G1 requires the container to behave identically on every clean-machine run; non-deterministic clustering breaks that silently | **R5:** running facet discovery twice on the same corpus must produce byte-identical output |

Everything below is written to satisfy R1–R5 as one resolved pipeline — no options tables, matching the rest of the roadmap's convention.

---

## 2. Pipeline Overview

```
Phase 0 runs ONCE, offline, before Day 1 coding hours begin — never inside the live engine.

  RAW CORPUS
      │
      ▼
  [0.1] STRUCTURE-AGNOSTIC SEGMENTER   ── produces candidate topic units, whatever the format
      │
      ▼
  [0.2] EMBED + DETERMINISTIC CLUSTER  ── Agglomerative, silhouette-selected K, seeded
      │
      ▼
  [0.3] SMALL-CLUSTER FLOOR & MERGE    ── collapses noise clusters into neighbours
      │
      ▼
  [0.4] FACET NAMING                   ── deterministic TF-IDF keyphrase, tie-broken
      │
      ▼
  [0.5] EMPIRICAL RETRIEVAL-BIAS CALIBRATION  ── measured, not guessed
      │
      ▼
  [0.6] REPRODUCIBILITY GATE            ── rerun twice, diff, must match
      │
      ▼
  .index/facets.yaml   ←── FROZEN, versioned, read-only from here on
```

At runtime, the engine only ever does one thing with this subsystem: **load `facets.yaml` into memory at startup.** No clustering, no embedding of headings, no algorithm of any kind runs during the live stream. This preserves the ≤15 ms per-chunk controller budget untouched.

---

## 3. Stage-by-Stage Specification

### 3.1 Structure-Agnostic Segmenter — resolves R2

The brief's own PDF has no Markdown headings; the held-out corpus could be PDFs, plain text, Word docs, or a knowledge base export. A single extractor cannot assume any one syntax, so it runs a **cascade of detectors, most-structured to least-structured, and uses the first one that finds enough candidates**:

```
Detector A — Native document outline/bookmarks (PDF TOC, DOCX heading styles)
    → use if present and count ≥ 3

Detector B — Numbered/lettered section patterns
    ("^\d+\.\s", "^[A-Z]\.\s", "^§\s*\d", "^Section \d+")
    → use if present and count ≥ 3

Detector C — Typographic heading heuristic (works on raw extracted PDF text)
    Candidate line if: short (< 12 words) · followed by a longer paragraph ·
    title-cased or bold-run-flagged (from PDF layout metadata, e.g. pdfplumber
    font-size/weight deltas) · not ending in sentence punctuation
    → use if present and count ≥ 3

Detector D — Markdown headings ("#", "##", "###")
    → use if present and count ≥ 3 (kept as a detector, not the only path)

Detector E — FALLBACK: unsupervised topic segmentation
    No structural signal found at all. Slide a fixed-size window (≈500 tokens,
    50% overlap) across the corpus; embed each window; this is the candidate
    set instead of headings. Guarantees the pipeline never has zero input,
    even on a single wall of unstructured text.
```

**This is what makes the subsystem actually corpus-agnostic**: every corpus produces *some* set of candidate units, from a well-bookmarked PDF down to one raw text file with no structure whatsoever. The cascade is deterministic — same corpus always hits the same detector first, so there's no run-to-run ambiguity about which path was taken.

### 3.2 Embedding + Deterministic Clustering — resolves R1

**Chosen algorithm: Agglomerative clustering with average linkage, cosine distance, K selected by silhouette score sweep.** (Not HDBSCAN — HDBSCAN cannot be constrained to a target cluster-count range and can leave candidates unclustered as "noise," which is the wrong behavior here: every candidate unit must end up in exactly one facet.)

```python
embeddings = bge_small_en_v1_5.encode(candidate_units, normalize=True)  # seeded, pinned checksum

best_k, best_score = None, -1
for k in range(5, 11):                          # K ∈ [5, 10], inclusive
    labels = AgglomerativeClustering(
        n_clusters=k, metric="cosine", linkage="average"
    ).fit_predict(embeddings)
    score = silhouette_score(embeddings, labels, metric="cosine")
    if score > best_score:
        best_k, best_score, best_labels = k, score, labels
```

Silhouette selection means K is **chosen by the data**, not forced — a corpus with 3 genuinely distinct topics is allowed to collapse toward the low end of the range rather than being pried apart into artificial splits (which was the previous draft's over-fragmentation risk, R-analogous to pitfall P5 one layer up).

### 3.3 Small-Cluster Floor & Merge — new, closes a gap in the previous draft

```python
MIN_UNITS_PER_FACET = max(3, 0.03 * len(candidate_units))   # scales with corpus size

for cluster in clusters_by_ascending_size:
    if len(cluster) < MIN_UNITS_PER_FACET:
        nearest = argmax_cosine(cluster.centroid, other_cluster_centroids)
        merge(cluster, nearest)
```

Any cluster too small to support stable naming or bias calibration is folded into its nearest neighbour by centroid similarity, deterministically, before naming ever runs.

### 3.4 Facet Naming — deterministic, tie-broken

```python
keyphrase = tfidf_top_ngram(cluster.texts, ngram_range=(1, 3))
facet_id  = slugify(keyphrase)                                  # e.g. "cancellation_terms"
# Tie-break rule (only fires on exact TF-IDF ties, which are rare but must be resolved):
#   prefer the shorter keyphrase; if still tied, prefer the lexicographically first
```

`display` and `description` fields are generated from the same keyphrase plus the two nearest sentences to the cluster centroid, for use in decomposition prompts and the UI.

### 3.5 Empirical Retrieval-Bias Calibration — resolves R4

Instead of guessing sparse-vs-dense from numeral density, **measure it**, using exactly the retrieval stack that will run in production:

```
For each facet:
  1. Sample up to 5 of its own source chunks as synthetic "queries"
     (self-retrieval probe — no LLM call needed).
  2. Run BM25-only top-10 and dense-only top-10 for each probe query
     against the FULL index (not just this facet's chunks).
  3. Score: does the probe's own source chunk appear in top-10, and at what rank?
  4. retrieval_bias = "sparse" if BM25's mean reciprocal rank beats dense's
                        by > 0.1, "dense" if the reverse, else "balanced"
     (balanced → equal RRF weighting, not a forced pick)
```

This is consistent with the architecture's own founding principle (Doc 2, Rule 1 — "let the corpus be the oracle") and it produces a genuine, reportable finding rather than an assumption: it becomes ablation **A5 — heuristic-assigned vs. measured facet bias**, strengthening D3 instead of just adding a subsystem to justify under HC-5.

### 3.6 Reproducibility Gate — resolves R5

```bash
slrag index --corpus ./corpus --out ./.index          # run 1
mv .index/facets.yaml .index/facets.run1.yaml
slrag index --corpus ./corpus --out ./.index          # run 2 (same machine, same seed)
diff .index/facets.yaml .index/facets.run1.yaml        # MUST be empty
```

This check is added to CI (see §6) and to the pre-submission compliance checklist. All embedding calls are seeded; the embedding model is pinned by checksum, not just by name, in `config/app.yaml`.

---

## 4. Output Contract — `facets.yaml`

This is the frozen artifact everything downstream depends on. Its schema does not change after Phase 0 completes:

```yaml
generated_at: "2026-09-24T04:12:00Z"
corpus_checksum: "sha256:9f2a..."
clustering: {algorithm: agglomerative, linkage: average, metric: cosine, k: 7, silhouette: 0.41, seed: 42}
facets:
  - facet_id: cancellation_terms
    display: "Cancellation & Refund Terms"
    description: "Policy language governing cancellation windows, refund tiers, and exceptions."
    retrieval_bias: sparse            # measured, per §3.5
    bias_confidence: 0.83
    unit_count: 14
  - facet_id: venue_logistics
    display: "Venue Logistics & Capacity"
    description: "Room capacity, layout, and facility specifications."
    retrieval_bias: dense
    bias_confidence: 0.71
    unit_count: 9
  - facet_id: general
    display: "General / Unclassified"
    description: "Fallback bucket for content that did not cluster cleanly."
    retrieval_bias: balanced
    bias_confidence: null
    unit_count: 3
fallback_used: false                   # true if Detector E (unstructured) was triggered
detector_used: "B"                     # which of A–E actually fired
```

**A `general` facet is always present, even when clustering is clean.** Any content that fails to fit any cluster confidently, or a genuinely miscellaneous residual, lands here rather than being forced into a semantically wrong bucket — this is what lets the decomposer and retrieval router degrade gracefully instead of mis-tagging content on a corpus with unusual structure.

`config/facets.yaml` is *not* a fallback for a missing `.index/facets.yaml` — the index build always produces one, even in the worst case (Detector E). A manual `config/facets.yaml` may still be hand-provided to **override** the generated one for local dev/testing against the shared golden example, but production and grading always run the generated path.

---

## 5. Where This Sits in the Sprint — resolves R3

**Phase 0 runs on Day 0, before the contract-freeze session, by whoever is fastest to set up the corpus locally — not gated on any teammate's other work, and not blocking any teammate's other work.**

| Step | When | Who | Blocks whom |
|---|---|---|---|
| Write the Phase 0 pipeline (§3.1–3.6) | Built in the weeks before the sprint, or as the very first task of Day 0 morning, in parallel with the contract-freeze conversation | Whoever is free first — this is a solo, mechanical task, not a group one | Nobody — it runs against the real corpus the moment it's available |
| Run it once against the real corpus | Day 0, before coding hours | Same person | Produces `.index/facets.yaml` |
| Freeze `facets.yaml` | Immediately after a successful run + reproducibility gate pass | Whole team acknowledges in the contract-freeze session | Everyone's `Claim.facet`, retrieval routing config, and decomposer tagging now target this fixed list for the rest of the sprint |
| Re-run only if the corpus itself changes | Not expected mid-sprint | — | — |

This is the key correction from the previous draft: **the generalization mechanism is real and runs for real**, but it is treated as a **one-shot, pre-sprint artifact-production step**, exactly like building the golden example fixture — not as ongoing Phase 1 engineering that the other three components wait on. Nobody's typed interfaces are blocked on code being *written*; they're blocked for at most the minutes it takes to *run* an already-written pipeline once.

If, on Day 0 morning, this pipeline isn't ready in time (e.g., PDF layout metadata proves fiddly), the fallback is **not** "everyone waits" — it's "run Detector E (unstructured sliding-window) immediately, accept a slightly worse facet split, and move on." A mediocre-but-frozen taxonomy by 10am beats a perfect one that arrives at 4pm and reopens everyone else's interfaces.

---

## 6. Testing & CI Additions

| Test | Asserts |
|---|---|
| `test_reproducibility` | Two consecutive `slrag index` runs on the same corpus produce byte-identical `facets.yaml` |
| `test_detector_cascade_order` | Given synthetic fixtures for each of the 5 document types, the correct detector fires (including Detector E on a plain-text-only fixture with zero structure) |
| `test_small_cluster_merge` | A synthetic corpus with one deliberately tiny topic cluster ends up merged, never surviving under `MIN_UNITS_PER_FACET` |
| `test_general_facet_always_present` | `facets.yaml` always contains a `general` entry, even on a perfectly-clustering corpus |
| `test_retrieval_bias_measured_not_guessed` | `bias_confidence` is present and non-null wherever `retrieval_bias` ≠ `balanced` |
| `test_facets_yaml_schema` | Output validates against the Pydantic model for `facets.yaml` |
| `test_pdf_no_markdown_fixture` | Run against the actual Theme 4 brief PDF as a fixture — regression test proving the pipeline works on the one real document we've seen, not just on Markdown toy examples |

---

## 7. Updates This Document Requires in Docs A–C

| Document | Change |
|---|---|
| **A — Final Architecture**, §2 (Decomposer) and §3 (Retrieval & Fusion) | Add a line: "facets are loaded from `.index/facets.yaml`, produced by the Phase 0 discovery pipeline (Doc D), never hardcoded and never computed at runtime." |
| **A — Final Architecture**, Novel Mechanism Index | Add **S-11 — Corpus-Agnostic Facet Discovery**: deterministic, structure-cascade, empirically-calibrated, reproducibility-gated. Serves generalization to the held-out corpus directly — the brief's own three examples are not the test set. |
| **B — Final Engineering Roadmap**, §1 runtime diagram | Add a `.index/facets.yaml` input arrow into the engine's startup, alongside the BM25/FAISS index load. |
| **B — Final Engineering Roadmap**, §4 Phase 1 table | Remove the old 1.2 row; replace with: "1.2 — Load and validate frozen `.index/facets.yaml` from Phase 0 (Doc D); confirm reproducibility gate already passed." This makes Phase 1 a *consumer* of Phase 0's output, not a producer. |
| **B — Final Engineering Roadmap**, §5 Ablation Plan | Add **A5 — heuristic vs. measured facet retrieval-bias** (§3.5 of this document already frames it). |
| **B — Final Engineering Roadmap**, §8 Compliance Checklist | Add: "Facet discovery reproducibility gate passes (`test_reproducibility` green)." |
| **B — Final Engineering Roadmap**, §10 Risk Register | Add: *"Phase 0 structure detection fails on an unusual held-out corpus format → Detector E (unstructured fallback) guarantees a non-empty, valid facet set regardless of document format → Checkpoint: Day 0 AM."* |
| **C — Team Coordination**, §2 (Contract Freeze session) | Replace "20-minute manual skim" facet step with: "Confirm Phase 0 has completed and `facets.yaml` has passed its reproducibility gate; review the generated facet list together (5 minutes) before freezing schemas." |

---

## 8. Why This Is Now Actually General

The previous draft's generality claim rested entirely on "we cluster instead of hand-labeling" — but a clustering pipeline that only knows how to read Markdown headings is not more general than a hand-labeled taxonomy; it's differently narrow, and untested against the one real document available. This version is general in the sense that matters for a held-out, unseen corpus:

- **Format-general**: five-detector cascade means a PDF with bookmarks, a PDF with only numbered sections, a PDF with no structure at all, a Markdown export, and a DOCX all resolve to a valid candidate set.
- **Topology-general**: silhouette-selected K means a 3-topic corpus and a 15-topic corpus each get a facet count that fits them, not a number picked in advance.
- **Bias-general**: measuring sparse-vs-dense performance per facet on *this* corpus's actual retrieval behaviour means the routing table is correct regardless of what kind of language the held-out corpus uses.
- **Failure-general**: the `general` fallback facet and Detector E's unstructured path mean there is no corpus shape that produces an empty or invalid `facets.yaml`.
- **Reproducibility-general**: because it's deterministic and gated, running it on the judges' exact held-out corpus produces a taxonomy the team never saw, without introducing behavioural randomness into the graded run.

What changed is not the goal — it's that every previously-unresolved choice (which algorithm, what counts as a heading, how bias is assigned, when it runs, how it's verified) now has exactly one answer, so it can actually be built by one person in the hours available, on Day 0, without becoming the thing four other people are waiting on.

---

*This document supersedes Doc B §1.2 in full. Docs A, B, and C should be patched per §7 above; ping the team once patched so nobody is coding against the stale version.*
