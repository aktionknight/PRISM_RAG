PYTHON ?= .venv/bin/python

.PHONY: up setup setup-nli index replay bench score test test-nli lint clean bench-c4 calibrate-nli ablate ablate-a3

# Default target
up:
	docker compose up

setup:                ## core + dev deps, plus NLTK data and the spaCy pipeline baked into models/ (never at runtime)
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) scripts/bake_nli_model.py --nltk --spacy --no-nli

setup-nli: setup      ## Component 4 NLI verifier: deps + weights baked at build time (never at runtime)
	$(PYTHON) -m pip install -e ".[nli]"
	$(PYTHON) scripts/bake_nli_model.py

index:                ## build hybrid index + Phase 0 facet discovery from ./corpus (any corpus)
	$(PYTHON) -m slrag.api.cli index --corpus ./corpus

replay:               ## golden replay through the harness
	$(PYTHON) -m slrag.api.cli replay --stream ./bench/data/golden_example.jsonl --out ./runs/events.jsonl

bench:                ## full benchmark suite
	$(PYTHON) -m slrag.api.cli replay --stream ./bench/data/suite.jsonl --out ./runs/events.jsonl
	$(PYTHON) -m slrag.api.cli score --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl

score:
	$(PYTHON) -m slrag.api.cli score --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl

test:
	$(PYTHON) -m pytest -q

test-nli:             ## golden replay + calibration pairs on the real cross-encoder (needs setup-nli)
	SLRAG_NLI=1 $(PYTHON) -m pytest -q tests/synth/test_nli_backend.py

lint:
	$(PYTHON) -m ruff check src/ tests/

bench-c4:             ## Component 4 golden replay -> run records -> G4/G5 gates (non-zero exit on failure)
	$(PYTHON) -m bench.replay_c4 --out runs/c4_golden.jsonl
	$(PYTHON) -m bench.metrics --run runs/c4_golden.jsonl --corpus tests/fixtures/fixture_chunks.jsonl --gate

calibrate-nli:        ## sweep verifier.entailment_threshold on golden + adversarial pairs (needs setup-nli)
	$(PYTHON) -m bench.calibrate_nli --pairs bench/data/nli_calibration.jsonl

ablate: ablate-a3     ## ablations (A3 implemented; A1/A2/A4 owned by Components 1-3)

ablate-a3:            ## A3: delta refinement vs full restart on the golden refinement scenario
	$(PYTHON) -m bench.ablate_refinement

clean:
	rm -rf .index/ runs/ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
