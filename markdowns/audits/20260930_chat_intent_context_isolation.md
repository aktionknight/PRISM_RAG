# Chat intent context isolation audit

## Metadata and verdict
2026-09-30; Codex; local working tree; **CONDITIONAL**. References: Theme 4 Guide_RAG.pdf, A_FINAL_ARCHITECTURE.md, 02_SOLUTION_DESIGN.md and repository invariants. No commit or PR created.

## Findings and changes
- **HIGH:** Decomposition received the complete session IntentSet, including questions from previous chats, even after current candidates were reset. The model could consequently return historical questions as current intents. Decomposition now receives current-turn candidates; prior answer intents are included only when the pre-decomposition classifier identifies a presentation follow-up or constraint refinement. Historical intents remain internal for evidence reuse and lineage, not automatically active questions.
- **HIGH:** A final syntactic fallback previously unioned current final questions with earlier partial-prefix questions. Every completed final decomposition now reconciles the active candidate snapshot, including fallback results; obsolete provisional candidates become superseded. A fallback's completeness depends on the syntactic splitter and remains weaker than successful semantic decomposition.
- **MEDIUM:** Independent questions inherited prior session constraints during synthesis. NEW_INTENT now derives fresh constraints from the current utterance; refinements retain their dedicated merge behavior.
- **MEDIUM:** The UI retained the previous turn's chips and streaming drafts until another update arrived. New queries clear those fields immediately, and final answer events synchronize chips with the server's final sub_queries.

## Invariant compliance and generalisation
| Invariant/component | Assessment |
|---|---|
| Corpus oracle | Controller ordering unchanged; no additional text LLM request. |
| Cancellation and evidence pool | Historical evidence remains pooled; current intent scope is separate. |
| ClaimGraph | Prior answer history retained; independent answers retain the existing graph revision behavior. |
| HC-4 | All state remains ephemeral and in process. |
| HC-5 | Call budget unchanged; context classification uses existing local mechanisms. |
| Schema freeze | No core schema change. |
| API/synthesis/UI generalisation | Uses turn IDs, classification and active answer intents; no project/domain vocabulary or golden-example tuning. |

## Verification
- **36 tests passed in 47.37 seconds.** Held-out API test exercises a successful sensor answer, a bullet follow-up retaining citations, then an independent controller question whose decomposition context is empty and whose active sub_queries contain only that question.
- Snapshot retirement is parameterized over LLM, explicit reconciliation and fallback sources.
- UI production build passed.
- Existing golden replay tests remain placeholders, so their passing status is not substantive replay validation.

## Remaining risks and opportunities
Follow-up/context routing depends on classifier accuracy; ambiguous references can still be classified incorrectly. The API reads the engine's internal intent mapping for active-answer context; a dedicated read-only interface would reduce coupling. Literal exclusive correction handling, question relevance, measurement-specific contradiction detection and latency risks from prior audits remain. Test short pronoun follow-ups, mixed new/refinement requests and incomplete final fallback snapshots more extensively before declaring universal context resolution.
