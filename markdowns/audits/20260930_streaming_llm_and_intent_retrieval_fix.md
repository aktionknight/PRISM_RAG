# Streaming LLM and repeated-intent repair audit

## Audit metadata
- Branch: master; baseline HEAD: 2b624fa.
- Auditor: Codex; date: 2026-09-30.
- Scope: local working-tree fixes for blank answers, repeated sub-intent retrieval, and model warmup visibility. No commit or PR created.
- References: `markdowns/globals/Theme 4 Guide_RAG.pdf`, `A_FINAL_ARCHITECTURE.md`, `02_SOLUTION_DESIGN.md`, `C_TEAM_COORDINATION.md`, and repository AGENTS.md.
- Preserve existing user changes to ingestion, sparse retrieval, and indexing exception logging.

## Executive summary and verdict
**CONDITIONAL**. The repeated-dispatch and evidence identity defects are repaired, warmup failures are reported, and rejected-claim diagnostics are persisted. These changes do not establish full Theme 4 compliance. The previous comprehensive audit remains applicable outside this repair's scope.

The screenshot session generated eight claims in one synthesis call; all eight were retracted by verification. This was not a missing LLM invocation. Both `config/synth.yaml` and local Ollama inventory identify `llama3.2:1b`, rather than Qwen. The indexed document is `campaign_launchpad_pitch_and_demo`. Unsupported competitive superiority must remain uncertain.

## Changes and rationale
- Controller/API: avoid an extra empty final dispatch when the last client chunk already has `is_final`; cache unchanged-prefix decomposition; do not embed end markers or interpret their empty-vector drift as a contradiction; confirm remaining live speculative branches at completion. Reset refractory timestamps between turns.
- Decomposition: detect identical normalized questions/search strings before accepting changing slots, facets, or model supersession hints. Reuse canonical IDs; preserve pending first dispatches. Semantic deduplication failure retains exact identity checks and never dispatches all candidates blindly. Lazy package exports avoid loading heavy NLP dependencies for unrelated imports.
- Evidence/intent interaction: merge score associations into the canonical intent and filter merged/superseded candidates before synthesis. Preserve previously observed current-turn intents across prefix updates.
- LLM budget: wire session state into decomposition; count actual attempts; reserve one of the three calls for synthesis. Controller tie-breaks share the same pre-synthesis budget. Decomposition, tie-break, synthesis and warmup resolve the configured endpoint/model.
- Synthesis: remove prompt instructions that encouraged verification evasion through unsupported negatives or spelled-out counts. Prefer source wording, omit unsupported comparisons, persist rejection reasons, and render verified claims in the requested list style.
- API warmup: log preload before loading heavy models; move synchronous loads off the event loop; check HTTP/model errors and return an error status instead of unconditional success. Ensure application INFO logs have a handler under direct Uvicorn startup.
- UI: remove a history mutation nested in a state updater, which React may replay. Preserve answer version zero and distinguish successful/failed preload in console output.

## Invariant compliance matrix
| Invariant | Assessment |
| --- | --- |
| Rule 1: corpus as oracle | Controller cascade order preserved; no new premature text-model calls. |
| Rule 2: cheap cancellation and pooling | Empty-marker cancellation repaired; merged evidence retained. Existing broader cancellation/concurrency issues require separate review. |
| Rule 3: ClaimGraph answers | Verified graph claims remain the answer source; requested list rendering adds no facts. |
| HC-4: ephemeral in-process state | Prefix cache, intents, and evidence remain session memory. |
| HC-5: at most three calls per turn | Two shared pre-synthesis calls plus the existing single generation call; failed requests consume attempts. No added synthesis retry. |
| Frozen schemas | `core/schemas.py` unchanged. |
| Generalisation | No corpus vocabulary or golden-example domain vocabulary introduced into runtime logic/prompts. Held-out tests use unrelated sensor facts. |

## Risk and severity scan
### HIGH: lexical verification is not semantic entailment
The configured lexical verifier can accept unsupported sentences with sufficient shared words. The live 1B-model check exposed this, including invented relationships between concepts in one source section. Rejection diagnostics and strict prompting improve observability but do not repair semantic entailment. Use and evaluate the existing NLI scorer on unrelated corpora before asserting hallucination resistance; never lower verification thresholds to fill the answer pane.

### MEDIUM: small-model response quality and output truncation
The live check completed without a generator transport error and committed some claims, but still showed one parse error at the configured 700-token limit. Model-generated pronouns, repetition, and extraneous intents remain possible. Compare model sizes with held-out grounded-answer evaluations; do not assume any 1B model is interchangeable with a 7B model.

### MEDIUM: warmup request lifecycle
Preload is invoked by the frontend rather than automatically completing at backend startup. Each request can repeat heavy initialization; a shared single-flight readiness task is a future improvement. Warmup failures now appear in API status, backend logs, and frontend console; no dedicated readiness-error UI was added.

### MEDIUM: broader integration validation
The repository's seven golden streaming tests are placeholders, so a green full pytest run is not proof of golden replay, live websocket end-to-end behavior, or latency targets. No browser replay or complete websocket/model pipeline replay was performed for this repair.

## Architectural strengths
Closed citation allowlists, two-pass verification, ClaimGraph-based rendering, canonical session intents, and strict numeric-copy rejection remain intact. Merge evidence now follows canonical identity, and exact dedup works without the embedding service.

## Verification checklist
- [x] Held-out intent-repeat, facet/slot jitter, evidence merge, unsupported numeric-value rejection, empty-marker confirmation, refractory reset, and actual-attempt budget tests.
- [x] Full available pytest suite: 17 passed (includes seven existing placeholder golden tests).
- [x] Python source compilation.
- [x] Frontend production build.
- [x] Live configured Ollama model: repeated decomposition changed from repeated novel intents to `NOVEL 3 TOTAL 3`, then `NOVEL 0 TOTAL 3`; generated claims and no transport error.
- [x] No schema changes or corpus-specific runtime heuristics.
- [ ] Full golden replay with real assertions.
- [ ] Browser/websocket end-to-end regression and latency budget measurements.
- [ ] Semantic hallucination resistance with NLI on unseen documents.

Diagnostic logs are local scratch artifacts at `scratch/streaming_fix/diagnose.log` and `diagnose_after.log`. Earlier diagnostic selected a small source subset for inspection; it is not a retrieval-quality benchmark. Restart the backend and refresh the frontend to load these changes. Switching to Qwen requires installing the intended model and setting its exact Ollama tag in `config/synth.yaml`.


## Follow-up: restore original Qwen integration
- Git history at `85c62d0^:config/synth.yaml` confirms the original model tag was `qwen2.5:7b-instruct`.
- Restored that exact tag in synthesis config, decomposition/controller fallbacks, and batch baseline. Warmup reads synthesis config, so it uses the same Qwen model. Existing 120-second synthesis timeout and 700-token limit retained.
- Follow-up screenshot session `sess_98c30fd6` had zero synthesis calls and zero evidence in coverage, unlike the earlier session which generated rejected claims. A pool filter incorrectly discarded non-positive raw reranker logits; the fix retains finite signed scores for explicitly associated confirmed evidence. Verification remains strict.
- LLM warmup now runs independently at startup, reports readiness through `/api/llm/status`, and logs configured model/endpoint and completion or failure. Context, intent post-processing, and synthesis call diagnostics are logged; final responses expose call/context/error diagnostics in the UI.
- Local Ollama inventory checked during this follow-up contained only `llama3.2:1b`. Qwen must be installed before successful warmup; changing code configuration does not install model weights.
- No schema changes or domain-specific heuristics introduced. Follow-up live inference validation was interrupted by the user; do not interpret the model switch as proof of successful Qwen inference.

- Final follow-up validation: full pytest suite **21 passed**, frontend production build passed, Python compilation passed. The new held-out checks cover negative/zero/positive logits reaching context and a mocked single LLM call producing a verified cited fact from negative-scored evidence. This does not validate live Qwen inference before its model weights are installed.
