ifeq ($(OS),Windows_NT)
PYTHON ?= .venv/Scripts/python.exe
else
PYTHON ?= .venv/bin/python
endif
RUN ?=
CORPUS ?=
GOLD ?=

.PHONY: up down serve help grafana setup setup-nli models-check index replay bench score test test-golden test-nli lint clean bench-c4 calibrate-nli

# Default target
up:
	docker compose up

down:                 ## stop the Docker stack, preserving model and dashboard volumes
	docker compose down

serve:                ## start the backend for local development
	$(PYTHON) -m slrag.api.cli serve --reload

help:                 ## list supported workflows
	@echo "up down serve grafana setup setup-nli models-check index replay bench score test test-golden test-nli lint clean bench-c4 calibrate-nli"

models-check:         ## verify baked NLI, spaCy and NLTK resources without downloading
	$(PYTHON) scripts/bake_nli_model.py --nltk --spacy --check

grafana:              ## start local Grafana with iframe embedding enabled
	$(PYTHON) -m slrag.api.cli grafana

setup:                ## core + dev deps, plus NLTK data and the spaCy pipeline baked into models/ (never at runtime)
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) scripts/bake_nli_model.py --nltk --spacy --no-nli

setup-nli: setup      ## Component 4 NLI verifier: deps + weights baked at build time (never at runtime)
	$(PYTHON) -m pip install -e ".[nli]"
	$(PYTHON) scripts/bake_nli_model.py

index:                ## build hybrid index + Phase 0 facet discovery from ./corpus (any corpus)
	$(PYTHON) -m slrag.api.cli index --corpus ./corpus

replay:               ## controller-only replay of the example stream
	$(PYTHON) -m slrag.api.cli replay --stream ./bench/data/golden_example.jsonl --out ./runs/events.jsonl

bench: score          ## score caller-supplied answered-turn records; controller replay is not a synthesis benchmark

score:
	$(if $(strip $(RUN)),,$(error Supply RUN=<answered-turn JSONL>; controller replay events cannot be scored))
	$(if $(strip $(CORPUS)),,$(error Supply CORPUS=<RetrievedChunk JSONL>))
	$(PYTHON) -m slrag.api.cli score --run "$(RUN)" --corpus "$(CORPUS)" $(if $(strip $(GOLD)),--gold "$(GOLD)")

test:
	$(PYTHON) -m pytest -q

test-golden:          ## self-correction regression and unrelated held-out corpus
	$(PYTHON) -m pytest -q tests/test_golden_streaming.py tests/synth/test_heldout.py

test-nli:             ## held-out support/contradiction check on the real cross-encoder (needs setup-nli)
	$(PYTHON) -c "import os, pytest; os.environ['SLRAG_NLI']='1'; raise SystemExit(pytest.main(['-q', 'tests/synth/test_nli_backend.py']))"

lint:
	$(PYTHON) -m ruff check src/ tests/

bench-c4: test-golden ## available Component 4 regressions; no statistical gate-rate claim

calibrate-nli:        ## sweep verifier.entailment_threshold on golden + adversarial pairs (needs setup-nli)
	$(PYTHON) -m bench.calibrate_nli --pairs bench/data/nli_calibration.jsonl

clean:
	$(PYTHON) -c "from pathlib import Path; import shutil; [shutil.rmtree(p) for p in (Path('.index'), Path('runs'), Path('.pytest_cache')) if p.exists()]; [shutil.rmtree(p) for root in ('src', 'tests', 'bench', 'scripts') for p in Path(root).rglob('__pycache__')]"
