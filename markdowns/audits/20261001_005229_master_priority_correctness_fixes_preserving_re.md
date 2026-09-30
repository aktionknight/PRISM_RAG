# Architecture Audit: master — Priority correctness fixes preserving retrieval behavior

## Audit Metadata
- **Branch**: `master`; working-tree fixes based on `e50016534437477731835c8b6dca4a957c9e9832`.
- **Auditor**: Codex with controller/deduplication, live-session, and CLI subagents.
- **Date**: 2026-10-01.
- **References**: `markdowns/globals/A_FINAL_ARCHITECTURE.md`, `markdowns/globals/02_SOLUTION_DESIGN.md`, `AGENTS.md`.
- **Scope**: source changes listed below; existing user corpus edits excluded.
- **Method**: generated with `scripts/audit_architecture.py --pr master --title "Priority correctness fixes preserving retrieval behavior" --base HEAD --head HEAD`, then replaced its empty committed-diff template with this manual audit of the uncommitted patch. No PR or commit created.

## Executive Summary & Verdict
**CONDITIONAL**. Confirmed crash and state-loss bugs are repaired. Initial answer rendering, model settings, prompts, ranking, dense retrieval, sequential dispatch, and schemas retain their existing behavior. Broken follow-ups intentionally change: they now retain claims, suppress presentation-only retrieval, and support the existing delta refinement mechanism. The patch is not full compliance with the design; inherited retrieval integration, verification and budget gaps remain explicit below.

## Invariant Compliance Matrix
| Invariant | Assessment | Evidence / limitation |
|---|---|---|
| Rule 1: corpus as oracle | Partial, unchanged | Existing BM25 probe remains; ordinary final-content safety still retrieves. No new controller text LLM calls. |
| Rule 2: cheap cancellation and pooling | Partial | Refinement can reuse the session pool; speculative branches still have no creation path. |
| Rule 3: ClaimGraph answers | Improved, partial | One engine/graph per live session, destroyed on end/reset. Existing claim/lineage fields are populated. Final paragraph rewrite still operates on rendered strings. |
| HC-4: ephemeral state | Preserved | Session state and engines remain in-process; no persistence framework added. |
| HC-5: at most three LLM calls | Not proven; inherited risk | No additional calls introduced by fixes. Existing paragraph rewrite is now accounted for, but repeated upstream decomposition plus synthesis/rewrite lacks a shared per-turn budget. |
| Frozen schemas | Preserved | `core/schemas.py` unchanged. Dataclass lineage is adapted to existing Pydantic field names. |
| Generalisation | Checked in held-out tests | No domain vocabulary, example-specific thresholds, prompts or model changes added to runtime logic. |

## Risk & Severity Scan
| Severity | Finding | Disposition |
|---|---|---|
| HIGH | Missing `re` breaks near-duplicate detection; fail-open handler redispatches every candidate. | Fixed import and fail-closed dispatch; duplicate candidates reuse canonical IDs to retain evidence. |
| HIGH | New engine each turn discards prior graph and breaks refinement/presentation. | Fixed session lifecycle; existing delta retrieval uses the same dense retriever. |
| HIGH | Final safety bypasses suppression; format counts are treated as new content. | Fixed final gate precedence and discounting existing presentation controls/counts. Substantive sensor requests still retrieve. |
| HIGH | Ordinary output omits graph, lineage and telemetry metadata. | Fixed frozen output population and lineage adapter; answer text remains unchanged. |
| HIGH | Unverified final paragraph rewrite can invent content or markers after claim verification. | Deferred: replacing or verifying this output can change current prose or latency. Closed citation guarantees apply to claims, not this legacy final rewrite. |
| HIGH | Live retrieval excludes BM25 fusion, reranking, quota assembly, contradiction gating, OverlapMerger and BatchRAG. | Deferred under the instruction to preserve retrieval output/performance. |
| HIGH | Per-turn LLM budget is not coordinated across repeated decomposition and final synthesis/rewrite. | Deferred; accounting now exposes existing synthesis/render calls without adding calls. |
| MEDIUM | Orchestrator compares `.decision` on a string and returns a string incompatible with replay serialization. | Fixed comparison and full decision return. |
| MEDIUM | Score omits required corpus and Makefile references nonexistent suite/gold. | Fixed CLI forwarding and explicit RUN/CORPUS/GOLD inputs; `bench` honestly scores supplied answered-turn records. |
| MEDIUM | Replay still uses stub retrieval and produces controller decisions, not answers. | Explicitly documented, not marketed as a synthesis benchmark. |
| MEDIUM | Historical Component 4 golden replay imports absent `tests/helpers.py` and fixture data. | Full historical golden verification unavailable on this checkout. Existing golden pytest functions are placeholders. |
| MEDIUM | Token/cost fields remain empty and pricing table shape differs from loader. | Fixed synthesis/restyle/render usage totals and configured-model pricing selection; decomposition usage and embedding/rerank proxies remain incomplete. |
| LOW | WebSocket loop retains ended-session object until a new session is requested. | Existing lifecycle edge case deferred; normal end/reset/disconnect destruction tested. |

## Architectural Weaknesses & Concrete Improvements
1. Add a session-scoped turn budget before enabling new speculative or tie-break calls; count decomposition, synthesis and legacy rewrite together.
2. Restore missing golden fixture loaders and answered-turn benchmark data, then compare outputs and p95 latency before integrating the hybrid stack/concurrency.
3. Ground final prose through the existing verified-claim rendering/restyle path; ensure text markers and claims share the closed allowlist.
4. Give speculative branches an explicit creation/confirmation/cancellation lifecycle before connecting Stage 4.
5. Complete decomposition and compute-proxy accounting, and reject post-end messages until a new session exists.

## Architectural Strengths & Alignments
- Dense result ranking, top-k values and sequential dispatch are unchanged.
- No new model inference, frameworks, storage services, prompts or schema fields are introduced.
- Duplicate suppression retains the evidence identity already held by the pool.
- Graph state is isolated across sessions; reset/end destroys graph and associated state.
- Presentation reuses claims/citations; numeric refinement tests use unrelated hydraulic documents.
- Pricing is selected for the configured model rather than silently choosing another model's rate.

## Component Generalisation & Inspected Files
| Changed component | Files | Corpus/example specificity check |
|---|---|---|
| Controller | `controller/cascade.py`, `controller/suppression.py` | Only existing presentation controls and generic numeric recognition; tests include new sensor content that must retain retrieval. |
| Decomposition | `decompose/intent_set.py` | Generic regex import and canonical identity reuse; numeric constraint changes remain distinct. |
| Live session/refinement | `api/ws_server.py` | Generic per-session lifecycle, read-only pool view and existing dense delta search; hydraulic/reagent isolation and refinement tests. |
| Synthesis/output | `synth/engine.py`, `synth/renderer.py` | Existing graph/lineage/usage fields populated; unchanged rewrite prompt and output; sensor response regression. |
| Telemetry | `telemetry/cost.py` | Supports existing table and legacy flat rates; generic model-tag normalization; unknown models never use another price. |
| Harness | `core/orchestrator.py`, `api/cli.py`, `Makefile` | Correct model/string boundary and explicit file arguments; unseen polymer input; no invented benchmark data. |
| Tests/docs | new controller, websocket, CLI and `tests/synth/test_heldout.py` tests; this audit | Topic words confined to tests/documents. |

## Verification Checklist
- [x] Regression expectations written before corresponding fixes; confirmed failing baselines for dedup/suppression, CLI contracts and accounting.
- [x] Targeted held-out controller/dedup, live-session, accounting and CLI checks passed individually.
- [x] Initial sensor answer text and citations remain unchanged; frozen claims/lineage/telemetry now present.
- [x] Actual live-session seeded-graph presentation and numeric delta refinement checks passed.
- [ ] Full historical golden replay: missing fixture helpers/data; existing golden pytest cases are placeholders.
- [ ] p95 controller/LLM latency: not measured; no blanket performance-equivalence claim.
- [ ] Full closed allowlist guarantee for rendered paragraph: legacy unverified rewrite remains.
- [ ] All-component LLM accounting and <=3 calls: decomposition/budget integration still incomplete.
- [x] Final aggregate pytest: `python -m pytest -q` — 28 passed in 30.27 seconds. This includes 23 new meaningful regressions and 5 existing placeholder golden cases; it does not establish historical golden replay coverage.
- [x] `git diff --check` passed; no edits to frozen schemas or configuration files.
