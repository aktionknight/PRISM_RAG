# Architecture Audit: Theme 4 Guide RAG requirements

## Audit metadata

- **Date:** 2026-09-30
- **Auditor:** Codex
- **Branch / source baseline:** `master`, `60f3194`.
- **Scope:** Whole-codebase review, including the current implementation, configuration, API/UI protocol, packaging, replay, tests and scoring. No PR number supplied.
- **Primary specification:** [Theme 4 Guide_RAG.pdf](../globals/Theme%204%20Guide_RAG.pdf), all six pages inspected as rendered images because the PDF has no extractable text.
- **Architecture references:** [A_FINAL_ARCHITECTURE.md](../globals/A_FINAL_ARCHITECTURE.md), [02_SOLUTION_DESIGN.md](../globals/02_SOLUTION_DESIGN.md), [B_FINAL_ENGINEERING_ROADMAP.md](../globals/B_FINAL_ENGINEERING_ROADMAP.md), and repository AGENTS.md.
- **Snapshot note:** Inspection began at `c91819f` with local modifications. Another actor committed these during the review as `60f3194`. Reviewed source/config subsequently matched that commit. This audit made no production changes or commits.
- **Method:** Source tracing, existing tests, and twelve offline reproduction probes. The architecture-auditor script was run; this reviewed report replaces its heuristic template.
- **Attachments:** [reproduction script](20260930_theme4_reproduce.py), [observed results](20260930_theme4_reproduction_results.json).

## Executive summary and verdict

**NEEDS_REVISION.** All five architectural components have substantial implementations, but the integrated system does not enforce several central Theme 4 requirements. Two independent paths publish unsupported facts. Intent deduplication can disconnect synthesis from retrieved evidence. Live refinement bypasses pool-first routing, while the evaluation CLI still uses a stub retriever.

The installed test suite reports **10 passed**, but seven tests contain only comments and `pass`. Component golden replay fails because `tests.helpers` is absent, and the mandatory held-out suite is missing. Twelve offline probes reproduced failures involving grounding, evidence association, cancellation, session isolation, scoring, provenance, quota allocation and API state handling.

### Requirement boundaries

The PDF requires early retrieval on **>=80%** of eligible queries, multi-intent identification on **>=70%** of compound queries, **>=85%** citation support with zero fabricated document IDs, verified session continuity, and **100%** trace coverage (pp. 4-5). This review does not establish measured pass rates for those gates.

The exact **<=3 LLM calls per turn**, 15 ms controller target, BM25 readiness probe and ClaimGraph are stricter repository commitments. The PDF requires parsimony, but does not prescribe those exact mechanisms or budgets. Likewise, it requires at least two ablations; hybrid-vs-dense and rule-vs-model are suggested examples.

## Requirement compliance matrix

| Requirement | Assessment | Findings |
|---|---|---|
| G1: clean-machine launch and unattended replay | Blocked by concrete implementation/package gaps | F06-F08 |
| G2: >=80% early retrieval, low false triggers | Not measured; dispatch timing and stream processing are unreliable | F05, F10-F11, F13 |
| G3: >=70% compound-query identification | Not measured; canonical intent/evidence handoff is broken | F03, F08, F15-F16 |
| G4: >=85% citation support, zero fabricated IDs | Grounding guarantees violated in reproduced cases | F01-F02, F14 |
| G5: preserve state and retrieve only necessary deltas | Live integration does not enforce pool-first targeted refinement | F04-F05, F11 |
| G6: 100% trace coverage | Incomplete and sometimes inaccurate accounting | F09, F12 |
| Corpus-only factual grounding | Corpus indexes exist; final factual output is unsafe | F01-F02 |
| Session-bound state | In-memory state exists, but transport leaks session data | F09 |
| No example hardcoding / generalisation | Active example-derived fallback; mandatory held-out tests absent | F08, F16 |

## Findings, severity and concrete improvements

### F01 — CRITICAL: failed grounding is accepted when a citation remains

**Requirement:** PDF p. 3 rigorous factual grounding; G4; architecture sections 4.4-4.6.

**Evidence:** `src/slrag/synth/verifier.py:478-483`. After entailment, polarity, value-copy and fabricated-ID checks record failures, the verifier sets `ok = True` whenever `citations` is nonempty. An allowlisted label is therefore sufficient to accept an unsupported sentence. Coverage then treats the committed claim as covered (`synth/uncertainty.py:63-78`).

**Reproduced:** evidence says “The sensor limit is 12 volts.” A draft saying “900 volts” returns `ok: true` with `copy_check_failed:900`. A draft containing one real and one fabricated citation also returns `ok: true` despite `fabricated_citation`.

**Improvement:** remove the failure-to-success override. Commit only supported claims or successfully verified re-attributions; demote failures to uncertainty. Add unrelated-domain negative tests before repair.

### F02 — CRITICAL: final LLM rewrite bypasses the verified graph

**Requirement:** PDF grounding/G4; local Rule 3.

**Evidence:** `src/slrag/synth/engine.py:514-555,585`. `_finish()` renders verified claims, then calls the LLM again and replaces the answer with its unverified response. Claims/citations still describe the old graph. `fabricated_id_count` checks that old citation list instead of the rewritten answer.

**Reproduced:** a fake rewrite response changes a verified 12-volt fact to 900 volts and adds `[Doc_missing §9]`. The final answer publishes it; graph claims still say 12; `fabricated_id_count` is **0**. A fake response is sufficient to prove this untrusted-output bypass without calling a live model.

**Improvement:** render deterministically from verified claims, or verify every rewritten assertion and citation before publishing. Scan final visible prose and ensure it agrees with streamed committed claims.

### F03 — HIGH: deduplication disconnects candidate IDs from evidence

**Requirement:** Multi-intent decomposition/fusion; G3/G4.

**Evidence:** `src/slrag/decompose/intent_set.py:130-159`; `src/slrag/api/ws_server.py:335-367,564-567,600-608`. Decomposition creates fresh candidate IDs. Duplicate candidates are skipped without mapping them to canonical stored IDs. The API sends those fresh `current_candidates` to synthesis while evidence is keyed by stored IDs. Overlap merging only changes status (`decompose/overlap.py:73-79`), without producing a canonical active list for synthesis.

**Reproduced:** a second identical candidate produces no novel intents, retains `candidate-b`, and has zero evidence under that ID; the original canonical ID has a retrieved chunk.

**Improvement:** return canonical mappings from dedup, use canonical active intents at synthesis, and apply merge/supersession consistently to queries and evidence. Test a final duplicate-only decomposition after successful early retrieval.

### F04 — HIGH: live refinement lacks its pool and targeted-retrieval wiring

**Requirement:** PDF Example 2/G5; pool-first refinement architecture.

**Evidence:** `src/slrag/api/ws_server.py:319-452,558-560,600-612`; `src/slrag/synth/engine.py:144-158,268-299,606-615`. The API searches on RETRIEVE before classifying the turn. It constructs `SynthesisEngine(session_id)` without `retrieve_fn` or the full session pool. Pure refinement ignores upstream evidence; unresolved delta queries become an empty list when the callback is absent. The fallback engine pool only contains graph-admitted context.

**Reproduced:** engine construction passes only the session ID; a retrieval-triggering late-detail chunk decomposes and searches before classification. The omission of unresolved delta searches follows directly from the callback guard in `engine.py:278`.

**Improvement:** route before dispatch, inject targeted retrieval and a shared pool view, and allow mixed turns to search only new intents plus unresolved delta targets. Measure actual upstream searches in G5.

### F05 — HIGH: cancelled and superseded evidence can reach synthesis

**Requirement:** Early-retrieval noise control, G4/G5; local Rule 2.

**Evidence:** `controller/speculation.py:process_speculation`; `retrieve/pool.py:113-141`; `api/ws_server.py:523-526,564-567` (all under `src/slrag/`). Cancellation removes a branch but leaves speculative evidence in the pool. Selection never checks that flag. Context assembly includes every stored intent, including merged/superseded entries. End-of-turn also relabels historical provisional events `final_confirm`, regardless of cancellation.

**Reproduced:** after correction, no active branch remains and the chunk is still speculative, yet selection returns it.

**Improvement:** distinguish pool membership from admission to confirmed context. Filter inactive intents; re-rank/revalidate cancelled evidence before reuse. Preserve dispatch triggers and add separate lifecycle events.

### F06 — HIGH: evaluation replay uses a stub and collapses turns

**Requirement:** G1, incremental processing and G5; roadmap evaluation path.

**Evidence:** `src/slrag/core/orchestrator.py:55-71`; `src/slrag/api/cli.py:51-116`. The retriever returns `(sub_intent, [])`. Replay consumes the entire file and synthesizes once after EOF with `t_s_end=0.0`, without real retrieval events or proper session/turn boundaries. Input timestamps do not drive a replay clock. `--corpus` does not select the index; `index --out` is also accepted but ignored.

**Improvement:** share one real pipeline between WS and replay, with explicit turn/session boundaries, injectable corpus/index paths and a real/virtual clock. Add a real-retrieval smoke replay and multi-turn continuity test.

### F07 — HIGH: container does not reproduce the local environment

**Requirement:** G1/D1; roadmap build-time resource provisioning.

**Evidence:** `Dockerfile:21-35`, `docker-compose.yml:8-25`, `pyproject.toml:10-39`, `src/slrag/synth/lexicon.py:83-103`, `config/synth.yaml`.

- Upload routes require undeclared `python-multipart`; it happens to be installed locally.
- Docker downloads the spaCy package but does not create the configured `/app/models/en_core_web_sm` directory required by Component 4. It does not run the repository baking script or copy models. Download errors are swallowed.
- Embedding/reranker/contradiction models load lazily by name instead of being baked.
- Generation/decomposition point to container loopback port 11434, but compose provisions no LLM service there.
- Startup does not initialize an empty index. The corpus is mounted read-only although upload/reset write to it; Docker also copies corpus files that are untracked in this checkout.
- No Python dependency lockfile was found.

**Improvement:** declare runtime dependencies, bake resources at configured paths, configure/provision a reachable inference backend, initialize/validate indexes, resolve corpus write semantics and pin dependencies. **No clean container build was executed in this audit**; these are source-confirmed packaging gaps.

### F08 — HIGH: missing assurance and an empty benchmark passes

**Requirement:** G1-G6, evaluation deliverable, AGENTS generalisation tests.

**Evidence:** `tests/test_golden_streaming.py:5-45`; `.github/workflows/c4-ci.yml`; `bench/replay_c4.py:26`; `bench/metrics.py:91-118,158-190,212-231`.

Seven streaming tests are `pass` placeholders; only three suppression tests contain substantive assertions. Missing files include `tests.helpers`, fixtures, held-out tests, NLI tests and documented vocabulary/schema guard suites. No G2/G3 scorer or trace-coverage invariant runner was found. The G4 scorer checks graph claims rather than all final-answer assertions; G5 sums self-reported counters. Zero judged claims skips the support threshold, and zero refinement records produces zero violations.

**Measured:** existing suite: **10 passed in 7.71s**. Component golden replay: `ModuleNotFoundError: No module named 'tests.helpers'`. Held-out test command: file not found. Empty benchmark: zero turns, null citation-support rate, zero refinements, **no gate failures**.

**Improvement:** restore real tests/fixtures, reject missing denominators/scenario coverage, independently score final visible assertions and actual search events, and implement G2/G3/G6 evaluation.

### F09 — HIGH: telemetry leaks session data across clients

**Requirement:** PDF session-bound state; HC-4 isolation.

**Evidence:** `src/slrag/telemetry/bus.py:35-77`; `src/slrag/api/ws_server.py:254-261,764-771`. All sockets subscribe to the global bus, which sends every event to every subscriber without filtering by session. Chunk events contain raw transcripts. Sequential subscriber awaits also let slow clients delay other sessions.

**Reproduced:** an event from session A reaches both A and B subscribers, including its transcript payload.

**Improvement:** filter subscriptions by owning session, separate administrative observability, and use bounded per-client queues. In-memory graph storage does not by itself isolate the transport.

### F10 — HIGH: slow work blocks stream consumption and timestamps overstate earliness

**Requirement:** Incremental listening, G2, latency challenge.

**Evidence:** `src/slrag/api/ws_server.py:791-805,334-339,381-452`; `controller/cascade.py:86-95`; `controller/stability.py:evaluate_stability`; `decompose/decomposer.py:240-244` (latter paths under `src/slrag/`). The receive loop awaits full decomposition/retrieval before reading the next chunk. Decomposition can make two 60-second-timeout requests. Controller and intent embeddings run synchronously; every chunk is embedded before suppression/BM25 even without active speculation.

Retrieval records use the input chunk timestamp after waiting for decomposition. A chunk timestamped 0.8 s can therefore produce a logged 0.8 s retrieval even when actual dispatch occurs after utterance completion at 2.1 s.

**Improvement:** decouple ingestion and dispatch with owned, cancellable tasks; move blocking model work off-loop; retain cheap gates before expensive work. Record input, decision, actual dispatch and completion times separately. Measure G2 from actual search start. No latency percentile was measured here.

### F11 — HIGH: end-of-turn handling leaves stale state and publishes a separate version

**Requirement:** Incremental interface, Example 3, G5/G6.

**Evidence:** `src/slrag/api/ws_server.py:515-526,688-707,741-751,801-805`; `controller/cascade.py:128-140`; `synth/engine.py:369-383` (under `src/slrag/`). The documented `utterance_end` message goes directly to synthesis without running a final controller decision. If earlier chunks WAIT, its final-retrieval safety net never runs. React sets `is_final` on its last chunk, masking this for that client.

The adapter clears its prefix but leaves controller prefix, embedding, force-retrieve signal and background tie-break tasks. It increments its own answer version on every utterance, including presentation-only turns, instead of using the graph version. Final WS output omits engine suppression and lineage fields; uncertainty is a separate event.

**Reproduced:** end processing calls no chunk handler, sends zero intents and leaves a seeded old controller prefix intact.

**Improvement:** implement one explicit end-turn transition, final decision if needed, task cleanup, canonical output, and per-turn reset. Publish graph version and suppression/lineage from engine output. Test the documented protocol without UI-specific extras.

### F12 — HIGH: telemetry accounting cannot establish G6

**Requirement:** 100% trace coverage and token/cost observability.

**Evidence:** `src/slrag/api/ws_server.py:254-290,428-446,518-541,670-685`; `synth/engine.py:626-668`; `telemetry/cost.py:48-50,80-85`; `config/pricing.yaml`.

Chunk/controller/retrieval events use the previous turn ID because it increments at synthesis. Decomposition/tie-break calls lack usage records. Per-query dispatch and call traces are incomplete. Synthesis events lack wall timestamps/event types. Prometheus retrieval latency is explicitly `0.0`; LLM/version metric helper functions have no runtime callers.

Cost loading passes the entire nested models table as rates, then looks for flat `prompt_per_1k`/`completion_per_1k` keys. Config uses per-model `prompt_per_1k_tokens`/`completion_per_1k_tokens`; the selected generator model is absent too. Presentation restyle telemetry omits token usage required by the summary.

**Reproduced:** 1,000 prompt plus 1,000 completion tokens produce cost `0.0` despite nonzero configured rates.

**Improvement:** allocate turn IDs at turn start; instrument provider calls and real search boundaries with parent IDs; reconcile call counts and usage. Validate pricing model/units and explicit unknown/local-model policy. Implement trace invariants rather than reporting default counters.

### F13 — HIGH: <=3 LLM calls/turn is not enforced

**Requirement:** PDF parsimony; stricter local call-count invariant.

**Evidence:** `src/slrag/decompose/decomposer.py:88-90,309-313`; `controller/cascade.py:189-195`; `synth/engine.py:225,529`; `config/app.yaml:17`.

The cap limits retries for each decomposition, not the entire turn. Each RETRIEVE may trigger two calls, each ambiguous chunk may start a tie-break, and synthesis can call generation plus rewrite. Two successful one-attempt decompositions plus generation and rewrite already total four calls.

**Improvement:** introduce a shared turn-level call budget/ledger, reuse canonicalization, coalesce obsolete tie-breaks and eliminate redundant rewriting. Resolve the architecture's repeated-canonicalization versus three-call claim explicitly.

### F14 — HIGH: ordinary document structures collide in citation identity

**Requirement:** Verifiable corpus provenance and G4.

**Evidence:** `src/slrag/ingest/loader.py:59,87-92`; `ingest/chunker.py:72-76`; `ingest/indexer.py:121-124`; `synth/claims.py:53-63`.

Document IDs use filename stems, so matching names in different directories or extensions collide. Only the leading integer of a numbered heading becomes its section ID: 1.1 and 1.2 both become 1. Chunk ordinals restart per section, so separate evidence gets identical chunk IDs. Dictionaries/pools then overwrite or skip distinct records. The loader also discards text before the first heading.

**Reproduced:** two sensor sections headed 1.1 and 1.2 both produce `collision#1#0`.

**Improvement:** derive stable corpus-relative document IDs, preserve hierarchical/unique section IDs, reject duplicates during ingestion and retain preambles. Test nested headings and same-name files in unrelated corpora.

### F15 — MEDIUM: quota allocation duplicates chunks and starves intents

**Requirement:** Fusion without context dilution; facet coverage.

**Evidence:** `src/slrag/retrieve/quota.py:105-119,135-141`; `api/ws_server.py:412-423`. Guaranteed allocation appends the same chunk once per intent and charges each copy to the budget. A later intent can be starved even when unique evidence fits. Remainder allocation stops at an oversized chunk rather than trying smaller ones. Near-duplicate pool dedup requires embeddings, but the live API does not supply them.

**Reproduced:** a shared 133-token chunk is added twice under a 270-token budget; a third intent gets no evidence although its unique 133-token chunk could fit alongside the first unique chunk.

**Improvement:** budget unique chunk IDs, assign shared coverage to all relevant intents, allocate fairly, skip oversized candidates and wire/validate semantic dedup.

### F16 — HIGH: example-derived taxonomy remains a runtime fallback

**Requirement:** PDF no-hardcoding and explicit AGENTS generalisation rule.

**Evidence:** `config/facets.yaml:1-90`; `src/slrag/decompose/decomposer.py:80-86,342-345`; `synth/config.py:40-48`. The fallback explicitly says it came from the example corpus and contains venue, catering and travel vocabulary. When generated taxonomy is unavailable it actively constrains decomposition; unknown LLM facets collapse to `general`. Successful Phase 0 reduces exposure but does not make the fallback corpus-independent. Existing engine/decomposer instances retain cached taxonomy after reindexing.

**Improvement:** move example taxonomy to fixtures, use a neutral fallback or validated active-corpus discovery, and version taxonomy with the corpus. Restore held-out/vocabulary guards. Do not add audit sensor vocabulary to production configuration.

### F17 — MEDIUM: contradiction handling misses conflicts and can silently prefer rank

**Requirement:** Evidence reconciliation and uncertainty; architecture section 3.4.

**Evidence:** `src/slrag/retrieve/contradiction.py:detect_contradictions`; `synth/conflicts.py:67-92`. Component 3 calls NLI only when enumerated typed values differ; opposite permissions with equal values or unsupported measurement types can be skipped. Component 4 skips same-document pairs and, when rankings differ, drops the lower-ranked claim with no clarification. Retrieval relevance does not establish authority or recency. If Component 3 did not surface the conflict, the user receives no explanation. A hand-written approval-role list further narrows generality.

**Improvement:** detect entity/relation/scope conflicts with corpus-independent extraction, include same-document and polarity cases, retain provenance and surface unresolved conflict. Validate NLI label mapping and paired-input tokenization. Model prediction accuracy was not benchmarked here.

## Repository invariant matrix

| Invariant | Verdict | Evidence |
|---|---|---|
| Rule 1: corpus oracle, cheap readiness cascade | PARTIAL / NOT PROVEN | BM25 exists; eager embedding and overrides complicate the cascade; no measured trigger/latency sweep |
| Rule 2: cheap cancellation and evidence pooling | FAIL | Cancelled evidence still selected; lifecycle history overwritten (F05) |
| Rule 3: answer as ClaimGraph | FAIL at output boundary | Unverified prose replaces graph projection (F02) |
| HC-4: ephemeral in-process state | PARTIAL / isolation failure | Stores/destroy methods exist; transport leaks data; live manager does not use TTL/locking SessionStore |
| HC-5: local <=3 LLM calls per turn | FAIL | No shared budget (F13) |
| Frozen schemas | NOT CHANGED BY AUDIT | No production edits; historical approval not inferred; referenced contract test absent |
| Generalisation | FAIL on fallback | Active example vocabulary and absent held-out checks (F08/F16) |

## Generalisation assessment by component

No production component was changed by this audit.

| Component | Assessment / check |
|---|---|
| Controller | Mostly generic language cues and corpus probing; source/config inspection, suppression tests; no threshold tuning performed |
| Decomposition | Example-derived fallback is active; canonical-ID failure reproduced with synthetic sensor queries |
| Retrieval/fusion/ingestion | Corpus indexes are general; role lists and ID assumptions restrict robustness; sensor quota/provenance/cancellation probes |
| Refinement/grounding | Generic language resources and graph exist; domain-independent verification/rewrite failures and missing adapters confirmed |
| Telemetry/harness | Domain-neutral mechanisms, but session isolation and evaluation completeness fail; bus/empty-run probes and missing-suite checks |

## Deliverable readiness (PDF p. 6)

| Deliverable | Status / remaining gap |
|---|---|
| D1 reproducible repository | Source/UI lockfile/compose exist; Python lockfile, environment template and clean replay not established |
| D2 architecture brief <=6 pages | Extensive plans exist; finalized bounded submission brief not found; reconcile claimed and actual behavior |
| D3 evaluation report | Baseline code and one refinement-ablation script exist; completed baseline comparison plus two ablations not found. Edge-case write-ups reference missing tests |
| D4 demo video <=5 minutes | No artifact/link identified during repository inspection; could exist outside checkout, therefore unverified |
| D5 observability schema | Schema classes/planning examples exist; actual records/accounting remain incomplete (F12) |

Documentation needs reconciliation: architecture A says the three-call limit is explicit in the brief, but it is a local decision. Repeated canonicalization plus retry conflicts with that limit. The older coordination plan's manual example taxonomy conflicts with later corpus-derived discovery/generalisation instructions. Plans and historical audit assertions are not evidence that acceptance gates pass.

## Architectural strengths and alignments

- Local sparse/dense indexes, reranking and section metadata provide a useful corpus-based retrieval foundation.
- ClaimGraph supports transactional revisions, citation admission, snapshots and lineage; output paths need to respect those invariants.
- Component 4 already exposes routing, pool-view and targeted-retrieval interfaces needed to repair integration.
- Deterministic presentation rendering, coverage uncertainty and explicit verification outcomes exist.
- Generic TTL/serialized SessionStore and real/virtual StreamClock implementations exist, though live/replay paths do not consistently use them.
- Corpus-derived facet discovery and standard language resources are sound directions once tuned fallbacks are removed.

## Prioritized improvements

1. Restore the factual trust boundary (F01-F02), adding negative held-out assertions before repairs.
2. Unify orchestration, canonical intent identity, shared evidence, delta routing and version output (F03-F06/F11).
3. Restore real tests and independent scoring; reject empty gates; instrument all dispatches/calls (F08/F12).
4. Repair session isolation, scheduling and turn-level budgets (F09-F10/F13).
5. Fix provenance, quota and corpus-independent fallbacks; complete clean packaging (F07/F14-F17).
6. Run golden/held-out and clean-container replay, baseline comparison and two ablations; then finalize the brief and demo.

## Verification checklist and limitations

- [x] Read all six pages of the actual PDF and compared requirements with implementation/plans.
- [x] Existing suite executed: 10 passed; seven empty tests identified.
- [x] Twelve offline probes executed; script and results attached.
- [x] Golden Component 4 replay attempted: missing `tests.helpers`.
- [x] Mandatory held-out suite attempted: target file absent.
- [x] Two independent factual-output failures confirmed using unrelated synthetic facts.
- [x] Cancellation selection, quota starvation, source-ID collision and session telemetry leak reproduced.
- [x] Audit and supporting artifacts saved under `markdowns/audits/`.
- [ ] Clean-machine Docker build/replay: not executed; static packaging gaps documented.
- [ ] Real-model G2/G3/G4 rates and p95 latency: not measured.
- [ ] Full trace coverage, integrated multi-turn continuity and completed benchmark deliverables: not established.

Reproduce from repository root with `python markdowns/audits/20260930_theme4_reproduce.py`. The script uses existing local language resources plus synthetic documents and fake network/model collaborators. It makes no external inference calls and changes no production source; its output is written to `scratch/theme4_audit/`. Those isolated collaborators test control flow and untrusted-output handling, not real-model retrieval/decomposition accuracy. The private evaluation suite is unavailable. No passing acceptance percentages should be inferred from the ten-test result.
