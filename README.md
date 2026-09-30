# PRISM RAG: Streaming Live RAG System

PRISM RAG (Streaming Live RAG) is a high-performance, real-time Retrieval-Augmented Generation engine designed for sub-second responsiveness, minimal LLM cost, and strictly verifiable provenance. 

It treats incoming utterances as continuous event streams, allowing it to begin retrieval while the user is still speaking.

## Key Features

- **Speculative Retrieval Cascade:** A 5-stage early-exit controller that triggers retrieval aggressively (< 15 ms p95) using a BM25 discriminativeness probe, before the sentence even finishes. Cancelled speculative branches cost zero context window tokens.
- **Multi-Intent Decomposition:** Safely unrolls compound queries into monotonic intent sets with facet-keyed diffing, preventing over-fragmentation and redundant API calls.
- **Facet-Quota Fusion:** Dynamically allocates context budget across distinct sub-intents to prevent dense paragraphs from starving specific policy or eligibility details.
- **Claim Graph Refinement:** Answers are held as a graph of typed claims. Late constraints (e.g. "Wait, actually for 50 people") cause a surgical graph mutation rather than a full pipeline restart.
- **Constrained Citation Allowlist:** Hallucination of document IDs is structurally impossible. Provisional sentences are streamed to the UI and verified in parallel using NLI entailment before committing.

## System Architecture

The PRISM system bypasses traditional vector database infrastructure to remain strictly bounded and parsimonious (HC-5 constraint).

- **Sparse Index:** `bm25s`
- **Dense Index:** `FAISS` (Exact Search / `IndexFlatIP`) with `bge-small-en-v1.5`
- **LLM Engine:** Local Open-Source Models (e.g., Llama-3, Qwen) using `vLLM` / `Ollama`.

For more in-depth architectural details and design decisions, please review:
- [System Architecture Brief](./System_Architecture_Brief.md)
- [Benchmarking & Evaluation Report](./Benchmarking_and_Evaluation_Report.md)
- [Final Architecture Specs](./markdowns/globals/A_FINAL_ARCHITECTURE.md)

## Getting Started

### Prerequisites
- Python 3.10+
- `uv` (recommended for fast virtual environments)
- Docker (optional, for observability stack)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd PRISM_RAG

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
uv pip install -e .
```

### Configuration
System behaviors, controller thresholds, and model endpoints are centralized in the `config/` directory.
- `config/controller.yaml`: Thresholds for the early-trigger cascade.
- `config/retrieval.yaml`: Weights for facet-routed hybrid retrieval.
- `config/synth.yaml`: LLM parameters and validation thresholds.

### Running the System

**Method 1: Complete Evaluator Docker Stack (Recommended)**
The easiest way to run the entire system ?" including the FastAPI Engine, Web UI, Prometheus, Grafana, and the Ollama LLM backend ?" is to use the provided Windows startup script.

```powershell
# Open PowerShell as Administrator (if required for Docker) and run:
.\start.ps1
```
This single command will:
1. Boot up the entire architecture via `docker-compose.yml`.
2. Wait for the local Ollama LLM container to initialize.
3. Automatically pull the required **Qwen 2.5 7B** model.
4. Output the URLs for the Web UI (`localhost:8000`), Grafana (`localhost:3000`), and Prometheus (`localhost:9090`).

*(Note: Grafana's default credentials are `admin` / `slrag`. Anonymous viewing is enabled by default).*

**Method 2: Local Development Setup**
If you prefer to run the components separately for development:

**1. Build the Index**
Before serving, you must ingest and index the corpus.
```bash
python -m slrag.api.cli index
```
*Note: This will parse markdown documents in `corpus/`, extract sections, generate BM25 and FAISS indexes, and discover facets.*

**2. Start the Streaming WebSocket Server**
```bash
python -m slrag.api.cli serve --reload
```
The server will bind to `localhost:8000` by default.

**3. Run the UI**
Navigate to the UI directory to start the frontend.
```bash
cd ui
npm install
npm run dev
```

### Observability
PRISM is equipped with a 100% trace-coverage invariant suite. Every chunk decision, retrieval event, and graph mutation is logged to `events.jsonl`.
For a visual dashboard, the OpenTelemetry + Prometheus + Grafana stack is now bundled and starts automatically when using `.\start.ps1` or `docker compose up -d`.

## Documentation
- `markdowns/globals/01_OBJECTIVES_AND_REQUIREMENTS.md`: The core requirements.
- `AGENTS.md`: Guidelines for AI agents working within this repository.
- `System_Architecture_Brief.md`: Deliverable 2.
- `Benchmarking_and_Evaluation_Report.md`: Deliverable 3.