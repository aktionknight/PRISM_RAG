# Component 4 — Edge Cases (D3 write-up)

**Owner:** Sivansh (Session Refinement + Corpus Grounding) · **Scope:** what Component 4 does when a conversation stops being tidy · **Status:** every behaviour below is pinned by a test on the `sivansh` branch.

Each case lists what the user says, what Component 4 does, the config switch that controls it (HC-2), and the test that pins it. Where a behaviour is a known limitation rather than a fix, it says so.

---

## 1. Self-correction: "Actually, make it 40 people"

**Situation.** V1 answered a workshop question for 30 people. The user corrects the headcount.

**Behaviour.**
- The turn is a `CONSTRAINT_REFINEMENT` with delta `{headcount: "40"}`. The answer is revised as V2; it is never regenerated from scratch.
- Claims scoped to the old headcount are *affected*. Each affected facet gets one targeted query, `"40 attendees Venue capacity"`; nothing else is re-retrieved (`full_corpus_searches: 0`).
- **Fixed in this update.** Previously, an affected claim whose delta query came back empty was superseded anyway. On "make it 40", the catering answer ("Venue B offers on-site catering for groups of up to 80 guests", still true for 40) disappeared.
  - Now such a claim is **kept** if its own text never stated the old value (`DeltaEngine.content_scoped`). It had only inherited `headcount=30` from the session.
  - A claim that does state it ("In classroom layout Venue A seats 30 attendees.") is still superseded, or replaced by the fresh evidence.
- Coverage no longer reports a replaced V1 intent as "could not be verified". A delta target succeeds it.

| | |
|---|---|
| Config | `delta.keep_unreplaced_session_scoped: true` |
| Telemetry | `answer_refined.affected_kept` |
| Tests | `test_unreplaced_session_scoped_claims_are_kept`, `test_content_scoped_claims_are_still_superseded`, `test_keeping_unreplaced_claims_can_be_disabled` (tests/synth/test_delta.py); golden scenario `edge_self_correction_mixed` |

## 2. Self-correction mixed with a new question

**Situation.** "Make it 40 people, and is AV equipment included?"

**Behaviour.**
- Before this update, the classifier saw only the constraint. The AV question was silently dropped, because refinement turns skip Components 2–3.
- Now the turn is a `CONSTRAINT_REFINEMENT` flagged `mixed`, so `needs_upstream_retrieval` is true:
  - The harness runs decomposition and retrieval for the new question.
  - Component 4 applies the headcount as a delta.
  - It answers the novel sub-intent in the **same single generator call** (HC-5).
- Detection before decomposition: a question clause whose content words are not in the active claims, not in a constraint phrase, and not a follow-up word.
  - "does that change anything?" is about the constraint, so it stays a pure refinement.
- Detection after decomposition: a novel sub-intent on a facet the answer lacks.

**Golden result.**
- 4 claims retained, 3 superseded, 5 added.
- 2 targeted queries plus 1 upstream query for the new question; `full_corpus_searches: 0`.
- The catering claims survive verbatim.

| | |
|---|---|
| Config | `delta.question_cues`, `delta.question_clause_splitters`, `delta.follow_up_neutral` |
| Telemetry | `answer_refined.new_intents`, `classify.reason = constraint_delta_with_new_question` |
| Tests | `test_self_correction_mixed_with_a_new_question` (test_engine_golden.py); `test_refinement_with_a_new_question_is_mixed`, `test_pure_refinement_is_not_mixed`, `test_novel_sub_intent_on_an_unanswered_facet_makes_a_refinement_mixed` (test_delta.py); harness-order routing test counts the mixed turn as an upstream pass |

## 3. Contradicting sources

**Situation.**
- Doc_31 §4 says a full refund needs more than 14 days' notice; Doc_08 §1 says more than 7 days.
- Both are retrieved with strong, close scores (0.84 / 0.82).

**Behaviour.**
- **Fixed in this update.** Each sentence was entailed by its own chunk, so both passed verification, and the answer asserted two contradictory policies with no uncertainty.
- The new `ContradictionGate` runs after verification and before the graph revision. A pair conflicts when it cites different documents, shares a frame (≥ 0.75 token overlap, numerals excluded), and differs in numerals or polarity.
  - **Close scores:** both sentences are retracted, and the user is asked *"Could you clarify whether you mean 14 days or 7 days?"*. This is the same HC-3 clarification branch the coverage matrix uses for bimodal evidence.
  - **Clear winner:** the claim from the higher-ranked chunk is kept and the other is retracted.
- The unrelated sentence from the same chunk ("... forfeit the 25% booking deposit") is unaffected.
- Retracted sentences are re-emitted as `RETRACTED` stream events with reason `contradiction`.
  - **UI note (Matangi):** a `RETRACTED` can now follow a `COMMITTED` for the same `seq`.
- This is the last line behind Component 3's S-9 contradiction gating, not a replacement for it.

| | |
|---|---|
| Config | `conflicts.enabled`, `conflicts.frame_overlap`, `uncertainty.ambiguity_margin` |
| Telemetry | `synthesis.conflicts` |
| Tests | tests/synth/test_conflicts.py (7 tests incl. end-to-end through `SynthesisEngine`) |

## 4. The model inverts meaning while reusing the chunk's words

**Situation.** The generator writes one of these:
- "Card statements alone are accepted." against a chunk saying they are *not* accepted;
- "... get the 25% booking deposit refunded" against "... forfeit the 25% booking deposit".

**Behaviour.**
- The lexical scorer ignores "not" and gives such sentences ≈1.0.
- The polarity check aligns each clause to its best premise clause and compares polarity. Polarity is negation parity XOR antonym swaps (refund/forfeit, accept/reject, include/exclude, require/optional, ...).
  - "Card statements alone are rejected" still agrees with "not accepted".
  - "not only" and "no more than" are not counted as negations.
- The calibrated NLI backend catches every such case in the calibration set:
  - 45/45 calibration pairs are decided correctly at threshold 0.5.
  - The lexical default still accepts 7/24 unsupported pairs (value/role swaps, extra detail). **Production should run `entailment_backend: cross_encoder`.**

| | |
|---|---|
| Config | `verifier.antonym_pairs`, `verifier.negation_exempt`, `verifier.clause_splitters`, `verifier.cross_encoder.*` |
| Evidence | `python -m bench.calibrate_nli`; `make test-nli` |
| Tests | antonym / exempt / clause tests in test_verifier.py; `test_calibration_pairs_are_all_decided_correctly` (opt-in NLI) |

## 5. A fabricated or foreign citation

**Situation.** The model cites `Doc_77 §9`, which was never retrieved.

**Behaviour.**
- The label is stripped. The sentence is **demoted** to uncertainty (A §4.4), not rescued by re-attribution.
- `fabricated_id_count` over every emitted label stays 0. CI fails the build otherwise (`bench.metrics --gate`, `.github/workflows/c4-ci.yml`).

| | |
|---|---|
| Tests | `test_llm_backend_respects_budget_and_allowlist`, `test_every_golden_scenario_has_zero_fabricated_ids`, `test_cli_gate_exit_code` |

## 6. A new name the corpus never mentions

**Situation.** "Marriott holds up to 40 people." cited to a chunk about Venue A.

**Behaviour.**
- The regex copy check skips a lone sentence-initial word, so this passed.
- With `verifier.entity_backend: spacy`, NER adds the name and the sentence is retracted.
- **Limitation:** en_core_web_sm misses some names ("Pune offers ..."). NER adds coverage; it is not a guarantee.

| | |
|---|---|
| Tests | `test_spacy_entities_extend_the_copy_check`; opt-in `test_spacy_entities_keep_calibration_and_catch_new_names` |

## 7. Translation / tone request that cannot be honoured

**Situation.**
- "Translate that into Hindi" on the extractive backend, or
- an LLM restyle that fails verification (new number, foreign citation, dropped content).

**Behaviour.**
- The deterministic English render is shown and `suppression_reason` stays `translation`.
- `extensions.restyle_fallback` now says why (`no_llm_backend`, `copy_check_failed`, `citation_outside_prior`, `content_dropped`, `no_output`), so the UI can show "translation unavailable, showing original".

| | |
|---|---|
| Tests | `test_translation_without_an_llm_backend_reports_the_fallback`, `test_ungrounded_restyle_falls_back_to_the_deterministic_render` |

## 8. Concurrency around a turn

These cases are about the session lifecycle rather than what the user says.

- **Stale route.** Another turn ran between `classify()` and `handle_turn()`, which should not happen if both run inside one `SessionStore.turn()`. The engine sees the stale `session_epoch` and re-classifies. Test: `test_a_stale_precomputed_classification_is_redone`.
- **Turn queued behind `end()`.** It now runs on a fresh session, not on the retired one. Test: `test_a_turn_queued_behind_end_runs_on_a_fresh_session`.
- **Idle sessions with no traffic.** `SessionStore.sweep_forever()` reclaims them. Test: `test_sweep_forever_reclaims_idle_sessions_without_traffic`.

## 9. Known limitations (not fixed)

- **Additive phrasing.** "also for Mumbai" replaces the `city` slot instead of extending it. Slots are single-valued in the session model.
- **Example-shaped slot lexicon.** Two explicit delta queries in `config/synth.yaml` are worded like the brief's examples (audit W-5 / I-5). Re-deriving them needs the real corpus audit (`docs/corpus_audit.md`), which does not exist in this repo yet.
- **Lexical backend limits.** Value and role swaps where every number and name appears somewhere in the cited chunk ("Venue A charges INR 60,000") pass the lexical verifier. The cross-encoder rejects them.
