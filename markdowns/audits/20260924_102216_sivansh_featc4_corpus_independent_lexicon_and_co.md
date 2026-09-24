# Architecture Audit: sivansh — feat(c4): corpus-independent lexicon and constraints

## Audit Metadata
- **PR / Branch**: `sivansh`, range `648773c..cc4f47a` (`8e580d4` lexicon, `cc4f47a` constraints, plus PR-context records)
- **Previous audit**: `20260924_030412_sivansh_featc4_component_4_leftovers_g4g5_scorer.md` (CONDITIONAL)
- **Auditor**: Sivansh (Component 4 owner), agent-assisted
- **Reference**: `A_FINAL_ARCHITECTURE.md` §4, `02_SOLUTION_DESIGN.md` S-4/S-6, HC-2
- **Trigger**: the evaluation will use new documents, not the brief's three examples, so every rule fitted to those examples had to go.

---

## 1. Executive Summary & Verdict
- **Architecture Status**: **CONDITIONAL** (unchanged reason: the C-1/C-2 schema decision is still the team's).
- **This change set**: APPROVED on its own terms. Component 4's rules now come from general English resources and the grammar of each sentence, not from domain lists:

| Was (example-fitted) | Now (corpus-independent) |
|---|---|
| Hand-written stopword list | NLTK English stopwords (+ request/modal words NLTK omits) |
| Home-made plural stripper | NLTK Porter stemmer |
| Hand-written negation cues | NLTK `nltk.sentiment.util.NEGATION` (+ closed-class extras) |
| 11 hand-picked antonym pairs | WordNet antonyms + adjective satellites |
| `delta.slots`: trip_type, booking_timing, headcount, cities incl. Pune | spaCy dependency parse: noun modifiers, number + unit (WordNet `noun.person` class), verb + preposition, user role, places |
| Two queries worded after Example 2 | Generic template over the user's own phrase + facet label |
| facets.yaml `constraint_slots` / `keywords` driving C4 | Removed from C4; facets.yaml read for display labels only |
| `Venue\|Hotel\|Hall…` entity pattern | Generic "Name X" designator pattern |
| "name the venue…" in the LLM prompt | "name the place, policy or item…" |

## 2. Invariant & Hard Constraint Compliance Matrix

| Rule / Constraint | Status | Evidence |
|---|---|---|
| Rule 1 / Rule 2 | COMPLIANT (N/A to C4) | No retrieval-readiness or pooling logic changed. |
| **Rule 3: Answer as Graph** | COMPLIANT | Constraints and claim scopes are data on `Claim.preconditions`; refinements are still single revisions. |
| **HC-1: No egress** | COMPLIANT | NLTK data and the spaCy model are baked by `scripts/bake_nli_model.py --nltk --spacy` into `models/`; the loaders raise `LexiconUnavailable` rather than download. |
| **HC-2: No hardcoding** | **COMPLIANT (strengthened)** | The remaining lists are closed-class English (stopword extras, negation extras, locative prepositions, presentation verbs), not domain vocabulary. Two guard tests fail the build if held-out-domain or brief-domain words enter C4 config/prompts. |
| HC-4 | COMPLIANT | spaCy/WordNet objects are read-only and cached per path. Parse caches are per engine (per session). |
| HC-5 | COMPLIANT | No LLM calls added; parsing is deterministic. |
| Contract freeze | COMPLIANT | `core/schemas.py` untouched. `ConstraintDelta.phrases` is a C4-internal type. |

## 3. Automated Risk & Severity Scan
Script findings were keyword-density heuristics (LLM references in tests/bench); the real call count is unchanged (≤ 1 per turn from C4).

## 4. Weaknesses & Vulnerabilities
- [ ] **G-1 (MEDIUM, accuracy): parse quality bounds constraint quality.**
  - `en_core_web_sm` mislabels some places ("Bangalore" as PERSON; the locative fallback covers "in/at/near X").
  - It produces spurious modifiers on some sentences (e.g. `trip=international|reimbursed`).
  - Spurious keys are harmless unless a user constraint uses the same key.
  - `en_core_web_md/lg` would parse better at a latency cost.
- [ ] **G-2 (MEDIUM, semantics): role constraints are coarse.**
  - "I'm a staff member" conflicts with any claim whose subject is a person noun with a different role, including actors the rule is *about* (e.g. "External caterers must…").
  - If the targeted query finds nothing, a content-scoped claim is superseded.
  - An NLI-based scope check would be the principled fix.
- [ ] **G-3 (LOW, recall): the lexical fallback verifier lost two catches.**
  - WordNet has no refund/forfeit pair, and "optional" vs "must include" is not an antonym pair: false accepts rose from 7 to 9 of 24.
  - The NLI verifier (45/45) is the production path; `extra_antonym_pairs` exists for vocabulary WordNet lacks.
- [ ] **G-4 (LOW, latency): parsing every claim raises C4 p50.**
  - NEW_INTENT: ~3 ms → 29 ms. Refinement: 1.3 ms → 12 ms.
  - Still inside the 300 ms budget, and overlapped with generation on the LLM path.
- [ ] **G-5 (team): the facet taxonomy itself (`config/facets.yaml`) came from the example corpus.**
  - C4 no longer depends on it: unknown facets fall back to readable labels, and the held-out suite uses facets not in the file.
  - Component 2's decomposer still emits facets from this taxonomy; for a new corpus it must be re-derived (Aakrit).

## 5. Improvements
- [ ] Try `en_core_web_md` on the held-out suite and on the latency script; keep it if accuracy improves within budget.
- [ ] Replace the role-conflict rule with an NLI check ("does this claim apply to <role>?") when the cross-encoder backend is on.
- [ ] Grow the held-out suite with the real evaluation corpus once it's available (new domains, not new rules).

## 6. Strengths
- [x] **Generalisation is tested.**
  - The held-out library/IT suite was written before the refactor and failed on every refinement scenario (5/8 failures); it now passes 7/7 without any domain word in config.
  - Two guards keep it that way.
- [x] **The brief's examples still reproduce exactly** through generic machinery: Example 2 is 3 retained / 1 superseded / 2 added via `trip=international` and `book=after travel` read off the grammar.
- [x] **WordNet relatedness links wording variants** (trip → journey → travel) without synonym lists.

## 7. Scope
`src/slrag/synth/{lexicon (new), constraints (new), delta, text, verifier, generator, types}.py`, `config/{synth.yaml, facets.yaml, prompts/synthesize.jinja}`, `scripts/bake_nli_model.py`, `pyproject.toml`, `Makefile`, `.github/workflows/c4-ci.yml`, `bench/ablate_refinement.py`, tests (`test_heldout` + fixtures new; delta/engine/text/verifier updated).

## 8. Verification
- [x] 285 passed, 3 skipped (opt-in) with baked NLTK/spaCy data.
- [x] Opt-in NLI suite: 3 passed; calibration still 45/45 on the cross-encoder.
- [x] Golden G4/G5 gate exits 0 (0 fabricated IDs, 0 full-corpus searches on refinement).
- [x] Held-out suite 7/7 plus both vocabulary guards.
- [x] Component 4 latency, 50 iterations each:

  | Turn type | p50 | p95 |
  |---|---|---|
  | NEW_INTENT | 29.1 ms | 33.2 ms |
  | CONSTRAINT_REFINEMENT | 12.4 ms | 15.2 ms |
  | CONSTRAINT_REFINEMENT (mixed) | 10.9 ms | 12.0 ms |
  | PRESENTATION_ONLY | 2.5 ms | 2.9 ms |

- [ ] **Your local `.venv` needs `make setup`** (installs nltk/spacy and bakes their data) before the suite runs there.
