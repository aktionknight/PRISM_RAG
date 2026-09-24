FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev,nli]" 2>/dev/null || pip install --no-cache-dir .

# Bake spaCy model
RUN python -m spacy download en_core_web_sm 2>/dev/null || true

# NLTK data
RUN python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('stopwords', quiet=True); nltk.download('wordnet', quiet=True)" 2>/dev/null || true

# Copy source
COPY src/ src/
COPY config/ config/
COPY ui/ ui/
COPY bench/ bench/
COPY corpus/ corpus/
COPY Makefile .

EXPOSE 8000

CMD ["uvicorn", "slrag.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
