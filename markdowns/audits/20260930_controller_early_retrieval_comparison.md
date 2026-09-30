# Early retrieval comparison and repair

## Audit metadata
- Date: 2026-09-30; auditor: Codex; branch: master (working tree, no commit/PR).
- User reference commit: `e50016534437477731835c8b6dca4a957c9e9832`.
- References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md, AGENTS.md.

## Executive summary and verdict
**CONDITIONAL**. The screenshot is not sufficient evidence of correct streaming behavior: stability can fail to trigger before the last chunk, and differing percentages were falsely surfaced as conflicts without an NLI model. Early triggering is repaired and verified with the current index and embedding model. Full answer generation and performance targets remain separate validation work.

## Findings and changes
### HIGH: stability samples were inconsistent
`last_embedding` served both new-chunk drift and accumulated-prefix stability. It was updated on retrieval and stability fall-through, but not on earlier WAIT paths. This compared embeddings of different units or non-consecutive prefixes. Some of this design is also present in the reference commit; this audit does not attribute the entire flaw to a later regression.

The controller now embeds the accumulated active prefix once per chunk, records it even when content-floor/probe stages WAIT, and passes explicit previous/current embeddings to stability. Speculation and stability compare consistent prefixes. Thresholds, content-floor guards, and BM25-first evaluation remain unchanged. Empty end markers are not embedded.

### HIGH: tie-breaks could exhaust the decomposition budget
New asynchronous tie-breaks did not exist in the reference controller. They could use both pre-synthesis calls before any decomposition request. Tie-breaks now preserve a call for decomposition and one for synthesis, avoid launching duplicate pending tasks, and ignore stale-prefix answers. Failed requests still count toward the budget.

### MEDIUM: corpus calibration differs from the reference environment
The local calibration file reports `tau_hi=0.85`, `tau_lo=0.25`, `h_lo=0.6666`, overriding YAML thresholds. On the user's four prefixes the BM25 probe correctly fell through as intermediate evidence rather than declaring a discriminative hit. The probe implementation itself is unchanged from the reference commit. No thresholds were reduced or fitted to this query. Different indexed corpora can legitimately trigger at different times.

### HIGH: numeric differences were treated as confirmed contradictions
When NLI was unavailable, `_nli_check` returned 1.0 and marked unrelated percentage values as confirmed conflicts. It now returns 0.0 when unavailable, consistent with the existing disabled-gating warning. Numeric disagreements are candidate conflicts, not proof of contradictory facts. Semantic conflict detection is still unavailable without its model; this change does not prove that all conflicts are detected.

## Invariant compliance matrix
| Requirement | Result |
| --- | --- |
| Corpus as oracle | BM25 still precedes embedding stability and text tie-break. |
| Cancellation and pooling | Prefix drift is consistent; prior pooling repairs retained. |
| ClaimGraph answers | No rendering or graph mutation change in this repair. |
| HC-4 | Embeddings/tasks remain ephemeral per session. |
| HC-5 | At most two pre-synthesis calls; tie-break preserves decomposition capacity. |
| Frozen schemas | No changes to core/schemas.py. |
| Generalisation | No domain words, example-specific rules, or query-tuned thresholds introduced. Held-out sensor scenarios cover behavior. |

## Verification
- Full available pytest suite: **24 passed**, including seven pre-existing golden placeholders.
- New held-out scenarios: stability retrieval without punctuation after a dangling-prefix WAIT, discriminative BM25 retrieval before sentence end, and unrelated percentages without NLI.
- Python compilation passed.
- Live controller replay with cached BGE model and current index:
  - 0.0s: WAIT, content floor.
  - 0.8s: WAIT, content floor (dangling `in`).
  - 1.6s: RETRIEVE, `intent_stabilised`, Stage 3.
  - 2.4s: RETRIEVE, utterance-end safety.
- Replay script: `scratch/streaming_fix/check_controller.py` (local diagnostic, not runtime logic).
- No full browser/Qwen synthesis replay or p95 latency benchmark performed in this repair. Model cold-start time and synchronous encoding still violate the controller latency goal in cold runs; shared warmed encoders and asynchronous/batched inference remain recommended.

## Strengths and improvements
The cascade now supports early stability retrieval without relaxing corpus or incomplete-query guards. Cached embeddings avoid duplicate prefix encoding in the stability stage. Preserve held-out regression coverage and implement real golden replay assertions; evaluate warm latency separately from model loading. Restart the backend before testing the changes in the browser.
