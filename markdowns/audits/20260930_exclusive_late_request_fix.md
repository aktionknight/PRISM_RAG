# Explicit late request reconciliation audit

## Metadata and verdict
2026-09-30; local working tree; Codex; **CONDITIONAL**. References: Theme 4 Guide_RAG.pdf, final architecture, solution design and repository invariants. No commit or PR created.

## Findings and changes
- **HIGH:** The exclusion matcher captured the entire trailing phrase in “don't explain the project just list the techniques”. The narrow positive request was never enforced. A configurable closed-class pattern now recognizes “just/only” followed by a request verb and constructs the authoritative scoped request using the user's own words and original subject context. Model-generated broad paraphrases cannot override that scope.
- **HIGH:** A final failed/model-budget-limited decomposition previously caused provisional intents to survive. Explicitly reconciled final requests are now authoritative even with syntactic fallback.
- **HIGH:** Semantic deduplication could map a narrowed final question back to a broader provisional question. For explicit scoped final snapshots, obsolete provisional questions are retired before canonicalization. Unchanged exact questions retain their identities.

## Invariant and generalisation matrix
| Invariant/component | Assessment |
|---|---|
| Corpus oracle/controller | Retrieval controller order unchanged; no extra LLM call. |
| Evidence pooling/cancellation | Superseded intent evidence remains pooled; current synthesis scope excludes retired intents. |
| ClaimGraph | Answer generation and semantic claim verification unchanged. |
| Ephemeral state / HC-4 | In-process state only. |
| Call budget / HC-5 | Existing reserved early/final/synthesis calls unchanged. |
| Schema freeze | No core schema modification. |
| Decomposition/API generalisation | No project, content studio, technique domain lexicon or golden vocabulary added to production. Patterns use function words and request verbs; objects/context are derived from the current transcript. |

## Verification and limitations
- Final full Python suite: **35 passed in 41.94 seconds**. Parameterization checks both LLM and deterministic reconciliation snapshots.
- Held-out instrument/sensor queries test late exclusive narrowing against a deliberately incorrect broad model answer, plus API retirement and final-budget reservation.
- `git diff --check` passed.
- Existing golden replay tests are placeholders and do not establish real golden replay compliance.
- Live configured `llama3.2:1b` returned a single final question: **"list the techniques concerning the sensor project"**, reconciliation source `reconciled`, one decomposition call. Natural-response smoke check also produced three cited draft sentences with zero parse errors; this is not a complete uploaded-document answer verification.
- This handles explicit literal “just/only + request” narrowing. Arbitrary paraphrases, multiple scoped objects, pronouns, later reversals and negations still need broader semantic tests; it is not a universal correction parser. A scoped compound request remains one intent, and original-context noun selection can be ambiguous.
- Source relevance, measurement-aware contradiction detection and latency risks documented in the preceding audit remain open. No source-specific vocabulary was used to address this screenshot.
