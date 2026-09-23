PYTHON ?= .venv/bin/python

.PHONY: setup setup-nli test test-nli bench-c4 calibrate-nli ablate-a3

setup:                ## core + dev deps; CI and golden replay stay offline (lexical verifier)
	$(PYTHON) -m pip install -e ".[dev]"

setup-nli: setup      ## Component 4 NLI verifier: deps + weights baked at build time (never at runtime)
	$(PYTHON) -m pip install -e ".[nli,ner]"
	$(PYTHON) scripts/bake_nli_model.py --spacy

test:
	$(PYTHON) -m pytest -q

test-nli:             ## golden replay + calibration pairs on the real cross-encoder (needs setup-nli)
	SLRAG_NLI=1 $(PYTHON) -m pytest -q tests/synth/test_nli_backend.py

bench-c4:             ## Component 4 golden replay -> run records -> G4/G5 gates (non-zero exit on failure)
	$(PYTHON) -m bench.replay_c4 --out runs/c4_golden.jsonl
	$(PYTHON) -m bench.metrics --run runs/c4_golden.jsonl --corpus tests/fixtures/fixture_chunks.jsonl --gate

calibrate-nli:        ## sweep verifier.entailment_threshold on golden + adversarial pairs (needs setup-nli)
	$(PYTHON) -m bench.calibrate_nli --pairs bench/data/nli_calibration.jsonl

ablate-a3:            ## A3: delta refinement vs full restart on the golden refinement scenario
	$(PYTHON) -m bench.ablate_refinement
