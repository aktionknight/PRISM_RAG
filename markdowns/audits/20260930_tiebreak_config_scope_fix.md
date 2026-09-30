# Tie-break configuration scope audit

## Metadata and verdict
2026-09-30; Codex; local working tree; **APPROVED for the exception fix**. References: Theme 4 Guide_RAG.pdf, final architecture, solution design and repository invariants. No commit or PR created.

## Finding and repair
**HIGH:** `_do_tiebreak` called `get_controller_config` before a redundant function-local import of the same name. Python therefore bound that name locally and raised UnboundLocalError, even when the feature was disabled. Removed the redundant import so the existing module-level import serves every lookup. Disabled and shared-budget skip paths now return without a request or budget change.

## Invariant and generalisation review
| Invariant/component | Assessment |
|---|---|
| Corpus oracle / controller | No routing, threshold or model-setting changes. |
| Evidence pooling / cancellation | Unchanged. |
| ClaimGraph | Unchanged. |
| HC-4 | No state-storage changes. |
| HC-5 | Disabled and budget-exhausted paths still spend no LLM call. |
| Schema freeze | No schema changes. |
| Generalisation | Python name-binding repair; no topic, corpus or golden vocabulary added to runtime. |

## Verification
Held-out sensor-query regression was written first and reproduced the exact exception for both disabled tie-break and enabled-but-budget-exhausted cases. Final suite: **40 passed in 56.84 seconds**. `git diff --check` passed. Existing golden tests contain placeholder bodies and do not provide substantive golden replay coverage.

## Remaining weaknesses
The preceding log's `eligible_chunks=0` and `citation_labels=0` describe a separate evidence-association/eligibility problem. This repair prevents the background exception; it does not make missing evidence available or change the deliberate no-grounding synthesis skip. Prior relevance, contradiction and latency limitations remain. No PR or commit documentation workflow was invoked.
