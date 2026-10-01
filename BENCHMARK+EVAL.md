# Deliverable 3: Benchmarking & Evaluation Report

**Project:** Streaming Live RAG (PRISM)
**Date:** October 2026

## Measurement status

No reproducible larger streaming evaluation set, baseline outputs, or per-utterance
run artifacts support the previously reported performance figures. Those figures
have been removed, including the G2 early retrieval rate, G3 sub-intent recall,
G4 citation support rate, retrieval lead time, false triggers, refinement retention,
context token savings, full-corpus-search rate, and A1/A2 ablation results.

G2, G3 and G4 are **not measured on a larger held-out streaming set** in this
report. Architecture targets and small regression tests are not empirical gate
results. The repository does not establish a baseline comparison or an overall
pass verdict for these gates.

## Available verification

Run the actual tests with:

```bash
python -m pytest -q tests/test_golden_streaming.py tests/synth/test_heldout.py
python -m pytest -q
```

The self-correction golden uses sensor-maintenance vocabulary, unrelated to the
brief's examples. It submits a 12-month calibration intent, marks it dispatched,
then submits a correction to 24 months. The test checks that the earlier intent is
superseded and linked to its replacement, while both remain in session history.
It passes the final active scope and both evidence bundles to the real synthesis
engine using its extractive backend and verifies that only the 24-month claim and
its allowed citation appear in a schema-valid answer. Additive requests, duplicate
requests and different-facet requests have separate assertions.

The embedding boundary is deterministic; decomposition candidates and evidence
are supplied by the test. These checks do not measure the controller's early
trigger timing, live LLM decomposition quality, full WebSocket routing, or the
statistical citation support rate. No runtime mechanism was tuned to this fixture.

The held-out suite separately checks paraphrase grounding, rejection of invented
numbers and polarity reversals, intent retirement, answer scope and telemetry.

`bench.metrics` can score caller-supplied answered-turn records and corpus chunks:

```bash
make score RUN=runs/answers.jsonl CORPUS=runs/chunks.jsonl
```

Controller-only replay output cannot be used as answered-turn records. Legacy
`bench.replay_c4` and `bench.ablate_refinement` currently refer to missing
`tests.helpers` and golden fixture files; their historical descriptions are not
proof of runnable evaluations in this checkout.

## Requirements for future reported results

A future G2/G3/G4 report needs a versioned held-out corpus and larger utterance
set, streaming chunk timestamps, independently defined gold intent labels and
citation judgements, a reproducible invocation, model/configuration versions,
hardware details, baseline outputs and raw run artifacts. Report denominators,
metric definitions and failure cases alongside the aggregates. Keep test fixtures
separate from threshold selection and corpus-derived runtime configuration.

Docker Compose execution and a clean-machine deployment check were not performed
for this change, as requested. Image build instructions bake the model resources,
but build success and offline container startup remain unverified.
