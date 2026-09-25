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
	python bench/generate.py --out ./bench/data/generated
	python -m bench.metrics --run ./runs/events.jsonl

# Run ablation experiments
ablate:
	python bench/ablate.py --stream ./bench/data/golden_example.jsonl --out ./runs/ablation.json

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
