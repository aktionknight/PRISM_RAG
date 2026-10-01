# Stage 1: Build the React UI
FROM node:20-slim AS ui-build
WORKDIR /app/ui
# We copy package files first for caching
COPY ui/package.json ui/package-lock.json* ./
RUN npm ci
COPY ui/ ./
RUN npm run build

# Stage 2: Build the Python backend
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir -e ".[dev,nli]"

# Bake language resources and NLI to the configured disk paths. Fail the build
# if any required download or label-order check fails.
COPY config/ config/
COPY scripts/bake_nli_model.py scripts/bake_nli_model.py
RUN python scripts/bake_nli_model.py --nltk --spacy
RUN python scripts/bake_nli_model.py --nltk --spacy --check

# Retrieval loads model IDs from config; preserve their HF cache in the image.
ENV HF_HOME=/app/models/huggingface
RUN python -c "import yaml; from sentence_transformers import SentenceTransformer; from transformers import AutoTokenizer, AutoModelForSequenceClassification; c=yaml.safe_load(open('config/retrieval.yaml')); SentenceTransformer(c['embedding']['model_name']); r=c['reranker']['model_name']; AutoTokenizer.from_pretrained(r); AutoModelForSequenceClassification.from_pretrained(r)"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 NLTK_DATA=/app/models/nltk_data

# Copy other resources
COPY bench/ bench/
COPY tests/ tests/
COPY corpus/ corpus/
COPY Makefile .

# Copy built UI from Stage 1
COPY --from=ui-build /app/ui/dist /app/ui/dist

EXPOSE 8000

CMD ["uvicorn", "slrag.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
