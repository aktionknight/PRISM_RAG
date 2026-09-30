# Llama 1B live integration audit

## Metadata
- Date: 2026-09-30; auditor: Codex; branch: master, working tree; no commit or PR.
- References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md, AGENTS.md.
- User request: run lightweight Llama, diagnose missing responses/timeouts, and make grounded output work.

## Verdict
**CONDITIONAL**. Real Llama inference and the complete streaming API orchestration now produce committed, cited answers. This establishes live integration, not comprehensive answer quality or full architectural compliance.

## Root causes established
1. The active Ollama service reported an empty model inventory and returned immediate HTTP 404 for `llama3.2:1b`; this was not a timeout. Existing model files were in the user's C-drive cache, whereas the active service used `D:\ollama\models`. After filesystem approval, the exact cached model manifest and referenced blobs were copied into the active store. The unnecessary pull started for this investigation was canceled; no other model download was stopped.
2. With the model available, warmup succeeded and a direct completion returned `OK.`. A live pipeline generated 700 completion tokens but returned no complete usable claim. Raw inspection separately showed repeated question echoes and truncated structured output. Raising timeouts would not fix this.
3. Model-generated changing slots/supersession hints could incorrectly retire an earlier information need. Such retirement now requires a user correction marker; exact duplicates remain canonicalized first. Added information needs are retained.

## Implemented changes
- Configured `llama3.2:1b` consistently in synthesis, decomposition/controller defaults, and batch baseline.
- Added `claim_text_mode: extractive` for LLM-backed evidence selection. This remains a real single LLM request, distinct from the zero-call deterministic extractive backend. Source sentences are derived from currently retrieved evidence, ranked with generic content-token overlap and retrieval scores, and bounded per intent.
- Structured claim schema constrains selected text, its real citation, facet, and intent together. Question echoes and invented statements cannot be selected in this mode. The original citation/copy/entailment verifier still runs; no threshold reduction or bypass was introduced.
- Bounded claim count and raised the completion budget to 1600 tokens; timeout remains 120 seconds. Repeated statement text is filtered before verification.
- Preload retries a previously failed warmup after model installation rather than permanently reusing an error result.
- Kept unrelated user changes, including root cleanup and documentation, intact.

## Invariant matrix
| Requirement | Assessment |
| --- | --- |
| Corpus as oracle | Model selects only retrieved evidence; cascade ordering retained. |
| Cheap cancellation/pooling | No additional retrieval or LLM retry for synthesis; current evidence reused. |
| ClaimGraph answer | Selected sentences still pass two-pass verification and become graph claims. |
| HC-4 | Generated schema and candidate sentences remain per-request memory. |
| HC-5 | Existing two pre-synthesis attempts plus one synthesis request; no additional model fallback call. |
| Schema freeze | core/schemas.py unchanged. |
| Generalisation | No corpus/domain/example vocabulary in runtime changes. Source candidates are rebuilt from whichever corpus is loaded; held-out sensor facts validate the schema. |

## Live validation
- Warmup: `ready`, model `llama3.2:1b`, endpoint `http://127.0.0.1:11434/v1`.
- Direct model request: `OK.`, 3 completion tokens, about 12.27 seconds while sharing the server with other diagnostic work; not a clean latency benchmark.
- Final real streaming replay through `_process_chunk` and `_process_utterance_end`, using actual decomposition, hybrid retrieval, reranking, pooling, generation and verification:
  - Two canonical intent IDs and two corpus searches; final update dispatched no duplicate intent.
  - 12 grounding chunks.
  - One synthesis LLM call; 2109 prompt / 525 completion tokens.
  - Generation about 10.71 seconds; total cold replay about 67.24 seconds.
  - Two committed claims, two actual source citations, nonempty answer version 1.
  - Zero parse errors and no generator transport error.
- Earlier bounded replay also committed three claims in about 6 seconds of generation.
- Full regression suite: **30 passed** (includes seven pre-existing golden placeholders). Python compilation and whitespace checks passed.
- Held-out source-selection regression verifies sentence enum, maximum claim count, and binding to the real source citation/intent. Existing API regression verifies streamed chunks produce a grounded answer, with mocked inference boundaries.

## Risks and limitations
- **HIGH: answer completeness/relevance.** The 1B model still decomposes imperfectly and can select broad or incomplete source facts. The final replay retained a generic `Describe the document` intent instead of explicitly identifying the limitations question. Nonempty output is not proof that every requested model/technique was enumerated. Extractive selection favors factual grounding over fluent paraphrasing or derived conclusions/counts. `claim_text_mode: abstractive` remains available for larger models, but needs evaluation.
- **MEDIUM: contradiction alignment.** The loaded NLI model still flagged differing percentages from separate source paragraphs as a conflict (about 0.72 contradiction probability). The earlier unavailable-NLI fallback repair does not solve this model false positive. Compare facts with matching entities/measurement roles before confirming numeric conflicts in a future repair.
- **MEDIUM: cold latency.** Embedding/reranker/NLI loading dominates cold execution. No p95 timing or browser replay performed here.
- **MEDIUM: implicit corrections.** Supersession now requires explicit correction markers. This protects added information needs but may retain an older constraint when an implicit revision lacks a marker; record that tradeoff rather than silently trusting arbitrary model slots.

## Artifacts and use
- Latest real answer: `scratch/streaming_fix/live_llama_result.json`.
- Runtime log: `scratch/streaming_fix/live_llama.log`.
- Replay script: `scratch/streaming_fix/live_llama.py`.
- Raw output diagnostic: `scratch/streaming_fix/raw_llama_output.txt`.
- Restart the backend and use a new session so generator configuration and intent state refresh. `/api/llm/status` should identify Llama and report `ready`; the UI reports generation calls, context size, parse errors, and transport failures.
