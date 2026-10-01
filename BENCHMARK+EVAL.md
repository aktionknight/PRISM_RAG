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

## Measured regression results (October 1, 2026)

The focused golden and held-out suite was rerun at revision
`01b65c42125c69834313dbed643d2509492a0a07`. Its sample size is **24 collected
pytest cases**, including parametrized cases. These are fixed regression inputs,
not 24 independent streaming utterances or a larger evaluation corpus.

| Check group | Sample size | Passed | Failed |
| :--- | ---: | ---: | ---: |
| Self-correction golden: 12-month intent replaced by 24-month intent, verified final answer | 1 scenario | 1 | 0 |
| Additive, duplicate and different-facet controls | 3 scenarios | 3 | 0 |
| Held-out paraphrase, numeric, polarity and factual grounding | 8 premise/claim cases | 8 | 0 |
| Held-out source-attribution grounding | 4 premise/claim cases | 4 | 0 |
| Other held-out scope, synthesis, pricing and telemetry checks | 8 test cases | 8 | 0 |
| **Focused suite total** | **24 test cases** | **24 (100%)** | **0** |

Within the twelve labeled grounding cases, all **6/6 supported claims were
accepted** and all **6/6 unsupported claims were rejected** by the real verifier.
Agreement with the fixture labels was **12/12 (100%)**, with zero false accepts
and zero false rejects in that small set. This is verifier regression accuracy,
not the G4 citation support rate over generated answers. The single correction
golden also verified zero fabricated citation IDs in its final output.

The full suite separately collected **48 test cases**: **47 passed, 1 skipped,
0 failed, 0 errors**. The skipped case was the opt-in NLI test, which requires
`SLRAG_NLI=1`; the focused 24 cases are included in the full suite and must not
be counted again as additional samples.

The opt-in NLI test was then explicitly enabled and run separately: **1 test
passed, 0 skipped, 0 failed, 0 errors**, in **49.27 seconds**. It exercised two
premise/claim pairs against the baked cross-encoder, accepting the supported
calibration claim and rejecting the contradiction (**2/2 expected decisions**).
This is the same test skipped by the default full-suite invocation, not a new
independent evaluation set.

The focused pytest invocation took **64.15 seconds**; the full invocation took
**67.48 seconds**. These are single test-run durations including imports, model
loading and verification, with the two runs sharing the local machine. They do
not measure per-turn pipeline latency or establish a latency distribution.

Environment: Windows build 26200, Python 3.11.9, pytest 9.0.2. Grounding used the
configured locally baked `nli-deberta-v3-small` cross-encoder with entailment
threshold 0.5; generation in the correction golden was extractive and its
embeddings were deterministic. Other tests explicitly stub some boundaries as
shown in their source. No Docker execution was performed.

Both invocations emitted a Windows native access-violation diagnostic while
importing PyArrow through the model dependencies, then completed with exit code
zero and the passing results above. This environment diagnostic remains
unresolved; these runs are not clean-machine deployment verification.

Raw per-case results:
[focused suite JUnit XML](./bench/results/20261001_focused_regressions.xml) and
[full suite JUnit XML](./bench/results/20261001_full_regressions.xml), plus
[explicit NLI test JUnit XML](./bench/results/20261001_nli_regression.xml).

### Deployment regression follow-up

After adding automatic startup indexing and restoring Ollama's NVIDIA device
reservation, the updated working tree was tested with:

```bash
python -m pytest -q --junitxml=runs/deployment_regression_benchmark.xml
python -m ruff check scripts/docker_start.py tests/test_docker_start.py
```

This run collected **55 cases: 54 passed, 1 skipped, 0 failures, 0 errors**, in
**35.34 seconds**. It includes **7/7 passing startup cases** covering a fresh
index before server execution, rebuild on restart, empty corpus rejection,
indexing failure, and missing, empty or corrupt FAISS indexes. The build boundary
is stubbed in these startup tests; the corpus loader and FAISS file operations
are real. They do not prove that a Docker image builds or that GPU inference
meets the existing request timeouts. Static checks also confirmed the image's
entrypoint wiring and NVIDIA reservation. Changed-file lint passed.

The same PyArrow import diagnostic appeared, followed by successful completion.
The opt-in NLI case remained skipped in this default invocation; its separate
successful run is documented above. These overlapping test runs must not be
summed into a larger sample size. The seven startup tests add no new G2/G3/G4
streaming samples.

[Deployment follow-up JUnit XML](./bench/results/20261001_deployment_regressions.xml)
records the per-case results. Docker Compose execution remains skipped at the
user's request.

## Available verification

Run the actual tests with:

```bash
python -m pytest -q tests/test_golden_streaming.py tests/synth/test_heldout.py --junitxml=runs/regression_benchmark.xml
python -m pytest -q --junitxml=runs/full_regression_benchmark.xml
python -c "import os, pytest; os.environ['SLRAG_NLI']='1'; raise SystemExit(pytest.main(['-q', 'tests/synth/test_nli_backend.py', '--junitxml=runs/nli_regression_benchmark.xml']))"
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
