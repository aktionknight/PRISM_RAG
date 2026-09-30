# Stage 1: Build the React UI
FROM node:20-slim AS ui-build
WORKDIR /app/ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
COPY ui/ ./
RUN npm run build

# Stage 2: Build the Python backend and include Ollama
FROM python:3.11-slim

WORKDIR /app

# System deps and Ollama installation
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ && \
    curl -fsSL https://ollama.com/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

# Pull the LLM model during build
# We start ollama in the background, wait for it, pull the model, and then exit.
RUN nohup bash -c "ollama serve &" && \
    sleep 5 && \
    ollama pull qwen2.5:7b-instruct

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

# Initialize indexes
RUN slrag index --corpus corpus --out .index
RUN chmod -R 777 .index

# Copy built UI from Stage 1
COPY --from=ui-build /app/ui/dist /app/ui/dist

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000
EXPOSE 11434

CMD ["/start.sh"]
