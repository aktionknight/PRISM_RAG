# Streaming Live RAG — Dockerfile (Samsung Theme 4)
# Delivers G1 (Reproducibility) and HC-1 (Offline / No external network egress)

FROM python:3.11-slim

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy configuration and project definitions
COPY pyproject.toml .
COPY config/ config/

# Install python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
    "pydantic>=2.5,<3" \
    "pyyaml>=6.0" \
    "jinja2>=3.1" \
    "bm25s>=0.2" \
    "faiss-cpu>=1.7" \
    "sentence-transformers>=2.2" \
    "numpy>=1.24" \
    "spacy>=3.7" \
    "fastapi>=0.110" \
    "uvicorn[standard]>=0.27" \
    "websockets>=12.0" \
    "ulid-py>=1.1" \
    "opentelemetry-api>=1.20" \
    "opentelemetry-sdk>=1.20" \
    "prometheus-client>=0.20" \
    "pytest>=8.0"

# Pre-download spaCy model for offline execution (HC-1)
RUN python -m spacy download en_core_web_sm

# Copy codebase and benchmarks
COPY src/ src/
COPY bench/ bench/
COPY corpus/ corpus/
COPY Makefile .

# Install package in editable mode
RUN pip install --no-cache-dir -e .

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Default command runs the golden replay suite
CMD ["python", "-m", "slrag.api.cli", "replay", "--stream", "./bench/data/golden_example.jsonl", "--out", "./runs/events.jsonl"]
