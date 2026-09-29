# Stage 1: Build the React UI
FROM node:20-slim AS ui-build
WORKDIR /app/ui
# We copy package files first for caching
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
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
RUN pip install --no-cache-dir -e ".[dev,nli]" 2>/dev/null || pip install --no-cache-dir .

# Bake spaCy model
RUN python -m spacy download en_core_web_sm 2>/dev/null || true

# NLTK data
RUN python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('wordnet', quiet=True)" 2>/dev/null || true

# Copy other resources
COPY config/ config/
COPY bench/ bench/
COPY corpus/ corpus/
COPY Makefile .

# Copy built UI from Stage 1
COPY --from=ui-build /app/ui/dist /app/ui/dist

EXPOSE 8000

CMD ["uvicorn", "slrag.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
