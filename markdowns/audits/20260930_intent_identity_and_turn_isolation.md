# Intent identity and turn isolation audit

## Metadata
- Date: 2026-09-30; auditor: Codex; branch: master, working tree.
- Scope: duplication and cross-turn stale coverage from session `sess_4b65b71e`.
- References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md, AGENTS.md.
- No commit or PR created. Existing unrelated user edits preserved.

## Executive summary and verdict
**CONDITIONAL**. Intent duplication and stale question coverage are repaired and verified with held-out and streaming API regressions. The complete API orchestration reaches a verified cited answer with a simulated model response. Live Qwen inference is not verified while the model is unavailable.

## Findings and repairs
### HIGH: identical evidence does not mean identical questions
OverlapMerger merged unrelated intents whenever their top chunks overlapped and their facet was the generic fallback. On a small corpus this repeatedly merged the current question into a historical question. Since merged intents are excluded from identity matching, subsequent chunks allocated new IDs and repeated the same retrieval.

Overlap merging now requires matching normalized question text in addition to the existing facet, slot, and retrieval-overlap checks. IntentSet still performs semantic deduplication before retrieval. This deliberately favors retaining distinct information needs over aggressively merging merely related questions. No embedding threshold changes or query/domain-specific rules were added.

### HIGH: historical candidates contaminated the current turn
Overlap comparisons now consider only current-turn candidate IDs. Semantic deduplication is limited to IDs observed in the current turn; exact matches may still reuse session identity and confirmed evidence. Historical failed questions no longer replace a new question through a fuzzy embedding match.

### HIGH: failed-question coverage persisted into new questions
SynthesisEngine now resets its tracked intents and per-intent coverage evidence on NEW_INTENT turns. Session ClaimGraph and refinement behavior are retained. An unrelated prior failed question no longer appears in the new answer's uncertainty text.

### MEDIUM: controller decision state crossed turns
Controller reset now clears `last_decision` and `has_retrieved_this_intent`. A new turn cannot inherit an earlier RETRIEVE flag and trigger clause-oscillation retrieval solely because of that stale state.

## Invariant compliance
| Requirement | Assessment |
| --- | --- |
| Corpus as oracle | Controller ordering unchanged. |
| Cancellation/evidence pooling | Canonical evidence associations retained; distinct questions may share source chunks. |
| ClaimGraph answer | Verified claims remain the answer source; session graph retained. |
| HC-4 | Turn bookkeeping stays in session memory. |
| HC-5 | No new model call or retry introduced. |
| Schema freeze | core/schemas.py unchanged. |
| Generalisation | Normalized text identity and turn IDs are corpus independent. Tests use held-out sensor/controller facts; no runtime domain vocabulary added. |

## Verification
- **28 tests passed** across the full available suite, including seven pre-existing golden placeholders.
- Streaming API regression feeds three chunks through `_process_chunk` and `_process_utterance_end`, with deterministic controller/decomposition/retriever/model boundaries. Two distinct questions retrieve the same negative-scored passages. Assertions verify two stable IDs, exactly two searches, one synthesis call, two committed claims, two citations, and a nonempty grounded answer. Later decomposition updates have no new intents.
- Held-out regressions verify that distinct questions sharing all evidence do not merge, repeated questions reuse IDs, new-turn fuzzy matching does not alias a historical question, and prior failed-question uncertainty disappears.
- Existing tests retain numeric-copy rejection, evidence merge provenance, finite signed reranker scores, budget accounting, and pre-punctuation retrieval.
- Python compilation and `git diff --check` passed.

## Remaining risks and improvements
- Live model weights/endpoint are an external dependency. Config remains `qwen2.5:7b-instruct`; warmup readiness is exposed at `/api/llm/status`. Backend logs and UI diagnostics distinguish skipped, failed, completed, and rejected generation.
- The configured lexical verifier does not prove semantic entailment. Existing NLI configuration and earlier audit recommendations remain relevant.
- Golden tests still require real replay assertions. No full browser or live Qwen answer replay was performed in this repair; simulated inference validates orchestration, not Qwen response quality or latency.
- Restart the backend and create a new session after loading changes so historical IDs from the flawed merger are not carried forward.

## Root artifact question
`pyproject.toml` is required for Python packaging, dependency declarations, and the CLI entry point. No root `.patch` files were present when checked. Saved patch diffs are not runtime dependencies once their changes are applied; no files were deleted.
