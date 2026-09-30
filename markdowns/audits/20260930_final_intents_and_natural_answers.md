# Final intent reconciliation and natural answer audit

## Audit metadata
- Date: 2026-09-30
- Scope: local working tree; no commit or PR created.
- Auditor: Codex
- References: `markdowns/globals/Theme 4 Guide_RAG.pdf`, `A_FINAL_ARCHITECTURE.md`, `02_SOLUTION_DESIGN.md`, repository agent guidelines.

## Executive summary and verdict
**CONDITIONAL**. Streaming intent reconciliation, retrieval routing and answer display had implementation defects independent of model size. The changes reserve a final decomposition call, treat a validated final LLM decomposition as the authoritative current intent snapshot, remove explicitly excluded questions using user-derived words, retrieve novel questions in mixed refinements, prevent exact repeats of retained claims, and replace the active answer for independent questions while preserving ClaimGraph history. Synthesis now permits natural-language paraphrases with semantic NLI verification instead of forcing whole source sentences. Supporting claims remain inspectable behind a collapsed control, rather than appearing twice.

## Observed response flaws and root causes
- **HIGH:** Final intent candidates were unioned with provisional candidates, so omitted or withdrawn questions survived. LLM decomposition could consume both available calls early, leaving final corrections to a heuristic fallback. Final decomposition now gets a reserved call and reconciles the complete snapshot. Malformed response entries are rejected before treating a snapshot as authoritative.
- **HIGH:** A live Qwen 7B decomposition ignored an explicit informal exclusion even with the stronger prompt. A configurable, corpus-independent imperative-negation safeguard removes questions containing the excluded object's words. This handles literal exclusions, not all paraphrases or arbitrary conversational reversals.
- **HIGH:** Mixed constraint refinements skipped retrieval for novel questions. Their synthesis then lacked evidence for the newly requested information. Mixed turns now dispatch novel intents normally.
- **HIGH:** Independent questions could render old active graph claims. They now supersede the previous active answer through a graph revision; history remains available. Genuine refinements retain relevant prior claims.
- **MEDIUM:** Extractive claim mode and a copy-preferring prompt made raw corpus fragments the answer. Abstractive synthesis and refinement prompts now request ordered, self-contained sentences, direct relevance and accurate measurement names. NLI verifies paraphrases; numbers, entities and citation allowlists remain enforced.
- **MEDIUM:** UI rendered claim text and final answer as two visible copies. Supporting claims are now collapsed. List rendering produces one claim per bullet when no count is specified, and line breaks are preserved.
- **MEDIUM:** Refinement generation could re-add an unchanged retained claim. Normalized exact repeats are filtered before verification and graph insertion.
- **HIGH, remaining:** A supported sentence may still be irrelevant to the question. Prompting helps, but citation entailment is not a separate question-relevance/completeness gate. A green citation-support readout is not proof of a correct answer.
- **MEDIUM, remaining:** Numeric conflict detection compares typed numeric sets across whole chunks and may flag unrelated measurements as contradictory. The screenshot's percentages should not automatically be treated as competing values of the same measurement. This detector needs predicate/entity/measurement alignment before NLI confirmation.
- **MEDIUM, remaining:** Constraint extraction can mistake ordinary relational wording for a refinement slot. Mixed retrieval no longer starves novel questions, but classifier/constraint alignment needs broader semantic regression coverage.

## Invariant compliance matrix
| Invariant | Assessment |
|---|---|
| Rule 1: corpus as oracle | Existing controller stages retained; optional LLM tie-break disabled to preserve decomposition and synthesis budgets. |
| Rule 2: cheap cancellation and evidence pooling | Provisional evidence remains pooled; withdrawn questions are excluded from current intent scope. No pool/schema redesign. |
| Rule 3: ClaimGraph answer | Natural text remains a projection of verified claims. No unverified final rewrite or extra answer-generation call. Previous answers are superseded through revisions. |
| HC-4: ephemeral in-process state | No external session storage introduced. |
| HC-5: at most three calls | One early decomposition, one final decomposition, one synthesis. Intermediate prefixes use syntactic fallback once the early allowance is consumed. Tie-break is disabled by configuration. |
| Frozen schemas | `core/schemas.py` unchanged by this work. |

## Generalisation review
- Controller/decomposition: exclusion patterns contain closed-class negation and request verbs; excluded topic words come only from the user's transcript. No golden/domain keywords added.
- Synthesis/renderer: instructions concern evidence, measurements, repetition and sentence structure independent of corpus. NLI supports paraphrases without adding model calls.
- UI/API: snapshot reconciliation, mixed dispatch and collapsible evidence display are corpus-independent.
- Held-out expectations cover sensor/calibration questions, final withdrawals, call reservation, independent-answer isolation, repeated canonical IDs and unsupported values. No sensor terms were added to production configuration or logic.

## Verification
- Python suite: **33 passed in 78.23 seconds**, including held-out corrections and semantic NLI verification.
- UI production build: passed (`npm run build`); sandbox compiler spawn required approved escalation.
- `git diff --check`: passed (line-ending notices only).
- Live configured Qwen `qwen2.5:7b-instruct`: generated two concise cited sentences; zero parse errors and no transport error. Initial live exclusion test exposed the ignored withdrawal, prompting the explicit safeguard. Final live decomposition returned only **"explain the calibration purpose"**, with source `llm` and one decomposition call, correctly dropping the withdrawn voltage question. Reproducer: `scratch/streaming_fix/check_natural_response.py` (local scratch artifact).
- Golden test module contains placeholder `pass` bodies; passing it does not establish substantive golden replay compliance.
- Latency budgets and the complete screenshot document/session have not been re-benchmarked. NLI adds local inference cost and requires the baked model under `models/nli-deberta-v3-small`.

## Improvements and strengths
Add measurement-aware conflict comparison, semantic question relevance checks, real golden replay assertions and ordered correction/reintroduction tests. Existing citation allowlists, copy guards, graph lineage and shared call budgets remain useful safeguards. This is prompt/configuration and pipeline repair, not model-weight fine-tuning.
