# Controller decision contract repair

## Audit metadata
- Date: 2026-09-30; auditor: Codex; branch: master, working tree.
- Trigger: `sess_2d419530`, AttributeError in TurnClassifier._presentation_reason.
- References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md, AGENTS.md.
- No commit or PR created.

## Executive summary and verdict
**APPROVED for this contract repair**. The API incorrectly passed UI event dictionaries into the synthesis classifier, whose contract requires ControllerDecision objects. The defect appeared on follow-up turns after active claims existed; first-turn success did not exercise the failing branch.

## Changes
- PipelineSession retains original typed controller results separately from serialized UI decision events.
- Classification receives the typed results. TurnInput also receives those same objects, so reclassification uses the correct contract.
- Both lists reset at utterance end. UI messages and decision-count telemetry remain intact.
- No changes to core/schemas.py or classifier contract; no accepting arbitrary dictionaries inside core logic.

## Invariant compliance
| Invariant | Assessment |
| --- | --- |
| Corpus as oracle | Controller cascade and retrieval behavior unchanged. |
| Cancellation and pooling | Unchanged. |
| ClaimGraph answer | Existing graph and presentation behavior retained. |
| HC-4 | Typed results are ephemeral session memory and reset per turn. |
| HC-5 | No added model calls. |
| Schema freeze | core/schemas.py unchanged. |
| Generalisation | No corpus vocabulary or example-specific rules introduced. Follow-up regression uses held-out sensor facts. |

## Verification
- Extended streaming API regression: generate a verified two-citation answer, then submit `Repeat that in bullets.` through the actual chunk/end handlers in the same session.
- Regression reproduced a failure before the fix and passes after it. Checks follow-up turn ID, nonempty answer, citation preservation, and no extra corpus searches.
- Full suite: **30 passed** (seven existing golden tests remain placeholders).
- Python compilation and git diff whitespace checks performed.

## Remaining limitations and strengths
This repair restores the typed module boundary without changing schemas, rendering facts, or adding fallback behavior. It does not alter the Llama quality, contradiction alignment, or latency limitations recorded in prior audits. A full browser replay is separate from the deterministic two-turn API regression.

Restart the backend and open a new session to load the corrected PipelineSession state.
