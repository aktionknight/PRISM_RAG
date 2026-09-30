# Final grounding recovery audit

## Metadata and verdict
2026-09-30; Codex; local working tree; **CONDITIONAL**. References: Theme 4 Guide_RAG.pdf, final architecture, solution design and repository invariants. No commit or PR created.

## Reproduced failure
**HIGH:** A Stage 3 early retrieval populated the pool with speculative evidence. A later prefix drift cancelled its speculation branches, leaving the evidence ineligible. The intent remained marked dispatched, and canonical deduplication returned no novel intents at the final trigger. Consequently, retrieval did not run again, the current synthesis context was empty and the LLM deliberately skipped generation with no citation labels. This reproduced the screenshot's symptom without changing model configuration or citation thresholds.

## Repair
- At a final retrieval trigger, collect current active intents with no finite-score confirmed pool evidence, alongside genuinely novel intents. Dispatch this set once per canonical intent ID.
- Final retrieval results are confirmed regardless of the triggering controller stage. Final facts are fresh retrieval results; cancelled evidence is not automatically promoted or borrowed from unrelated historical questions.
- Existing confirmed evidence continues to be reused without another retrieval. No additional text LLM call or lower citation-verification threshold was introduced.
- Log final recovery intent IDs with the explicit reason “no confirmed grounding”.

## Invariant compliance and generalisation
| Invariant/component | Assessment |
|---|---|
| Corpus oracle | Final synthesis still requires actual corpus retrieval evidence. |
| Cheap cancellation / pooling | Cancelled evidence stays pooled and ineligible until independently retrieved again; no blanket confirmation of cancelled branches. |
| ClaimGraph | Verified cited drafts still enter graph revisions; unsupported answers remain rejected. |
| HC-4 | Existing in-process session pool only. |
| HC-5 | Text model call budget unchanged. Recovery costs a corpus query per missing current intent, not an LLM call. |
| Schema freeze | No core schema modification. |
| Generalisation | Dispatch depends on finality, canonical intent identity and confirmed evidence membership. No project names, domain words or golden-example tuning in production. |

## Verification
The held-out API regression deliberately retrieves sensor facts speculatively, cancels the branches through drift, repeats canonical intents, and finishes the utterance. Before implementation it reproduced `Synthesis LLM skipped: intents=2 citation_labels=0`. The repaired test verifies final re-retrieval, one synthesis call, two verified claims and two citations; no duplicated intents. Ordinary confirmed retrieval and subsequent presentation suppression are also exercised. **41 tests passed in 309.80 seconds** with the current local model configuration. `git diff --check` passed. This test duration is not a production latency benchmark or a validation of the screenshot's complete uploaded corpus response.

## Remaining weaknesses and improvements
Fresh retrieval can return no relevant evidence; a skip in that case remains correct and must not be replaced with invented citations. Recovery adds final retrieval latency, which has not been benchmarked against HC-5 latency targets. Branch cancellation telemetry and the pool's chunk-level speculative flag are broader than per-intent provenance; finer association bookkeeping would improve observability. Semantic question relevance, coarse facet coverage and measurement-specific contradictions remain independent limitations. Existing golden tests are placeholders and do not establish substantive replay validation.
