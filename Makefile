.PHONY: up index replay bench ablate score test lint clean

# Default target
up:
	docker compose up

# Build hybrid index from corpus
index:
	python -m slrag.api.cli index --corpus ./corpus

# Run golden replay
replay:
	python -m slrag.api.cli replay --stream ./bench/data/golden_example.jsonl --out ./runs/events.jsonl

# Run full benchmark suite
bench:
	python -m slrag.api.cli replay --stream ./bench/data/suite.jsonl --out ./runs/events.jsonl
	python -m slrag.api.cli score --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl

# Run ablation experiments
ablate:
	@echo "Ablation runner not yet implemented (Day 3)"

# Score a run
score:
	python -m slrag.api.cli score --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl

# Run tests
test:
	python -m pytest tests/ -v

# Lint
lint:
	python -m ruff check src/ tests/

# Clean build artifacts
clean:
	rm -rf .index/ runs/ __pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
