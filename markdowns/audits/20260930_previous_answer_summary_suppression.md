# Previous-answer summary suppression audit

## Metadata and verdict
2026-09-30; Codex; local working tree; **CONDITIONAL**. References: Theme 4 Guide_RAG.pdf, final architecture, solution design and repository guidelines. No commit or PR created.

## Findings and fixes
- **HIGH:** “describe the previous answer in short (summarize it)” was rejected by the information-query guard because of “describe”, and “previous”/“short” were not treated as presentation reference words. A prior-answer restyle containing only grammatical/presentation vocabulary now suppresses retrieval before question/document probing. Requests adding substantive information still use the existing retrieval guards.
- **HIGH:** Stage 0 suppression ran after encoder initialization. The new real-controller regression initially attempted remote embedding-model initialization even for a pure restyle. Suppression now runs before embedding/speculation work; the regression explicitly makes encoder access fail and verifies it is never invoked.
- **MEDIUM:** Synthesis assembled evidence and checked contradictions for all historical active intents even on presentation-only turns. Final classification is recomputed before assembly; evidence is restricted to current candidate IDs, and presentation-only turns assemble no corpus context. These requests reuse the existing verified ClaimGraph.
- **MEDIUM:** Classifier trusted any earlier NO_RETRIEVAL event, even if later streamed text added an information request. Only the latest controller decision can directly establish presentation suppression.
- **LOW:** “in short” now selects short rendering. UI labels these turns as previous-answer reformatting with retrieval suppressed rather than implying generation failed or skipped for lack of evidence.

## Invariant compliance and generalisation
| Invariant/component | Assessment |
|---|---|
| Corpus oracle | Pure restyles bypass corpus and text LLM; substantive information queries retain retrieval. |
| Evidence pooling / cheap cancellation | Pool retained; historical evidence excluded from unrelated final answer context. Suppression avoids encoder initialization. |
| ClaimGraph | Summary is a projection of existing verified claims, retaining source citations. No unverified rewrite. |
| HC-4 | State remains ephemeral and in process. |
| HC-5 | Ordinary summaries use zero decomposition, retrieval and synthesis LLM calls. Existing optional translation/tone paths unchanged. |
| Schema freeze | No core schema change. |
| Generalisation | Added words are grammatical, presentation and reference vocabulary. No project/domain terms added to production. |

## Verification
- API regression parameterized over bullet reformatting and the reported short-summary wording: follow-up answer is nonempty, citations remain within prior allowlist, retrieval events are empty, suppression reason is presentation_restructure, and LLM call count does not increase. Independent question routing is also exercised afterward.
- Suppression regression includes polite question punctuation and a mixed request adding an unrelated sensor fact that must not suppress.
- Final Python suite: **38 passed in 50.97 seconds**. UI production build passed. `git diff --check` passed.
- Golden replay module contains placeholder tests and is not substantive replay validation.

## Remaining limitations
The gate is deliberately conservative for vocabulary outside known grammatical/presentation words, so some paraphrased restyles may still retrieve. Short rendering keeps one claim per facet rather than performing semantic compression of every information need; coarse facets may omit useful details. Ambiguous follow-ups, multi-clause correction routing, semantic question relevance, measurement-aware contradictions and latency budgets need further independent evaluation. No model-weight fine-tuning was performed.
