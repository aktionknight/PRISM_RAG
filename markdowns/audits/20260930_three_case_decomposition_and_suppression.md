# Compound requests, streamed summaries and late corrections

## Audit metadata and verdict
2026-09-30; Codex; local working tree; **CONDITIONAL**. References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md and repository guidelines. No commit or PR created.

## Root causes and repairs
- **HIGH — Under-decomposition:** The prompt instructed the LLM to keep two aspects of the same item as one intent. It now separates distinct requested outputs even for one entity, while keeping noun phrases intact. A configurable request-clause boundary recognizes conjunctions introducing a new question or request. When the model undercounts these explicit clauses, the application splits them and resolves grammatical pronouns against the preceding subject. This also operates without the LLM or spaCy, with a simpler textual antecedent fallback.
- **HIGH — Semantic collapse:** High embedding similarity could combine enumeration and explanatory requests on the same facet. A corpus-independent request-operator guard prevents fuzzy matching across different request operations. Exact normalized NL/search identity remains reusable, including facet jitter.
- **HIGH — Suppression reversal:** The summary gate lacked “one”, “line” and “lines”. These presentation words no longer cause a streamed summary to fall through to final safety retrieval. Existing substantive-information guards remain; suppression is not permanently latched, so later new information can still require retrieval.
- **MEDIUM — Decomposition transport:** Live decomposition initially timed out. Requests previously had no output-token cap and used a hardcoded 60-second timeout. Decomposition now has its own configured 768-token limit, string-valued slot grammar, configured temperature and shared configured timeout. These settings bound generation and align it with the selected model integration; they do not establish latency-budget compliance.
- Existing final snapshot reconciliation, explicit “just/only” late narrowing, canonical intent IDs and final missing-grounding recovery remain in place.

## Three-case verification
| Case | Regression / live result |
|---|---|
| Compound same-topic request | Held-out request “List the sensor modules and what do they aim to do?” becomes two self-contained intents even when a stub model merges it. Live configured Qwen produced two intents through the explicit-clause safeguard; the output source was `split`. |
| Streamed presentation request | “summarize the previous answer” → “in one” → “line” remains NO_RETRIEVAL on every chunk. The API regression verifies no new retrieval events or LLM calls and a nonempty answer using prior citations. |
| Late constraint | Adding “Actually don't explain the purpose; just list the modules” leaves one scoped intent. The live output source was `reconciled`. Existing API snapshot tests verify retired questions stay out of the active set, including fallback paths. |

Live results: `markdowns/audits/20260930_three_case_live_results.json`. Local reproducer: `scratch/streaming_fix/verify_three_cases.py`. Earlier live attempts timed out and verified fallback behavior; after the bounded transport changes, the repeated live check completed without transport warnings. This is decomposition/controller integration verification, not full source-answer verification for the screenshot's uploaded document.

The final full suite passed **46 tests in 58.86 seconds**. Four targeted checks after transport changes also passed in **9.54 seconds**, covering compound splitting with late narrowing, operator separation, streamed summary suppression and configured transport limits. Scoped `git diff --check` passed for this turn's changed tracked files. The whole working tree has unrelated UI trailing whitespace, which was left intact. Existing golden replay tests have placeholder bodies; passing them is not substantive replay verification.

## Invariant compliance and generalisation
| Invariant/component | Assessment |
|---|---|
| Corpus oracle | Controller stages remain; clause handling is grammatical. No extra text LLM request introduced. |
| Cancellation / pooling | Existing cancellation and final-grounding recovery retained. |
| ClaimGraph | Summaries still render verified claims and retain citations; no unverified text rewrite. |
| HC-4 | In-process ephemeral state unchanged. |
| HC-5 | Shared early/final/synthesis budget unchanged; deterministic recovery does not spend another LLM call. |
| Schema freeze | No core schema change. Remote JSON slot grammar now matches string-valued slots. |
| Generalisation | Request operators, conjunctions, pronouns and format words are grammatical or closed-class request vocabulary. Topic words come from the user. No entity-recognition, sensor or golden-domain terms added to production logic/configuration. |

## Remaining limitations and opportunities
The operator guard may preserve paraphrases using different request verbs; it is not a full semantic equivalence classifier. Explicit-clause recovery handles conjunctions that introduce a request/question, not every coordinated noun phrase. Pronoun antecedent selection, correction reversals, compound scoped requests and numeric/date refinements need broader evaluation. Decomposition can still return irrelevant or under-specified questions; deterministic safeguards mitigate specific generic structures rather than retraining model weights. GPU/model contention and latency remain material concerns. Question relevance, measurement-aware conflicts and summarizing all information needs under coarse facets remain independent weaknesses.
