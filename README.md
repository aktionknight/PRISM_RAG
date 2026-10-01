<img width="1917" height="912" alt="image" src="https://github.com/user-attachments/assets/9195d22c-7e85-467d-a7ca-29ca39d2d108" />
# PRISM RAG: Streaming Live RAG System

PRISM RAG (Streaming Live RAG) is a Retrieval-Augmented Generation engine designed for streaming queries, bounded LLM use, and verifiable provenance. Measured performance status is documented in the evaluation report.

It treats incoming utterances as continuous event streams, allowing it to begin retrieval while the user is still speaking.

## IMPORTANT NOTE : 

DRIVE LINK FOR PPT + VIDEO (DEMO) : https://drive.google.com/drive/folders/1CRqfgGIXGbzIoco69SHwpMasvHCWhd5M?usp=sharing

follow the instructions for Starting up, Recommended Ollama + atleast 4GB VRAM for local inference, best works with the integrated Qwen 7B model, change model preference in the Synth.yaml in slrag/ and change it in decomposer for the harcoded fallback

Run the project with : .\start.ps1 (from project root) or follow steps in the README below

(THE RERANKING CODE EXISTS BUT IS NOT WIRED IN DUE TO EXTREME PERFORMANCE ISSUES ON DEV PC WHILE TESTING, FULL PRODUCTION CODE SHOULD WORK WELL WITH THE RERANKER AND HYBRID RETRIEVAL)

## Key Features

- **Speculative Retrieval Cascade:** A 5-stage early-exit controller uses a BM25 discriminativeness probe to start retrieval before the sentence finishes. Cancelled branches can populate the evidence pool for reuse.
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
- [System Architecture Brief](./SYSTEM_ARCHITECTURE.md)
- [Benchmarking & Evaluation Report](./BENCHMARK+EVAL.md)
- [Final Architecture Specs](./markdowns/globals/A_FINAL_ARCHITECTURE.md)

## Getting Started

### Prerequisites
- Python 3.11+
- `uv` (recommended for fast virtual environments)
- Docker with Compose (for the container stack)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd PRISM_RAG

# Create a virtual environment and install dependencies
uv venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
uv pip install -e ".[dev,nli]"
python scripts/bake_nli_model.py --nltk --spacy
```

### Configuration
System behaviors, controller thresholds, and model endpoints are centralized in the `config/` directory.
- `config/controller.yaml`: Thresholds for the early-trigger cascade.
- `config/retrieval.yaml`: Weights for facet-routed hybrid retrieval.
- `config/synth.yaml`: LLM parameters and validation thresholds.

### Running the System

**Method 1: Complete Evaluator Docker Stack (Recommended)**
The Windows startup script starts the FastAPI engine, built Web UI, Prometheus, Grafana, and Ollama backend. The engine image downloads and verifies its NLP, embedding, reranker and NLI resources during the build. The default Compose stack reserves NVIDIA GPUs for Ollama; the host needs compatible NVIDIA drivers and container GPU support.

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

On other platforms, run `docker compose up --build -d`, then
`docker compose exec ollama ollama pull qwen2.5:7b-instruct`.
The Ollama model pull is a separate setup step; it is not baked into the engine image.
The engine entrypoint builds BM25, FAISS and corpus facets from the mounted
`corpus/` before starting the HTTP server. It rebuilds on each container start
so the persisted `.index/` matches the current corpus. An empty corpus, failed
build, or missing/empty/corrupt FAISS index prevents the server from starting.
No corpus index is baked into the image. Initial startup includes indexing time;
use `docker compose logs -f engine` to monitor progress.

Ollama uses the reserved NVIDIA GPU when its model fits the available GPU memory.
After pulling the model, check `docker compose exec ollama ollama ps` while a
request is running to inspect actual CPU/GPU placement. CPU-only hosts require
explicitly removing the device reservation in a local Compose configuration;
CPU execution of the default 7B model may exceed the existing request timeouts.

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
PRISM emits structured telemetry for controller decisions, retrieval and graph changes to `events.jsonl`. Full trace coverage has not been established by a larger streaming evaluation.
For a visual dashboard, the OpenTelemetry + Prometheus + Grafana stack is now bundled and starts automatically when using `.\start.ps1` or `docker compose up -d`.

## Documentation
- `markdowns/globals/01_OBJECTIVES_AND_REQUIREMENTS.md`: The core requirements.
- `AGENTS.md`: Guidelines for AI agents working within this repository.
- [System Architecture Brief](./SYSTEM_ARCHITECTURE.md): Deliverable 2.
- [Benchmarking & Evaluation Report](./BENCHMARK+EVAL.md): Deliverable 3.

## Verification commands

`make test-golden` runs the self-correction golden and held-out sensor tests.
`make test` runs all available tests. `make serve` starts the local backend;
`make down` stops the container stack. Use `make help` for supported targets.
On Windows without Make, use `python -m pytest -q` or
`python -m pytest -q tests/test_golden_streaming.py tests/synth/test_heldout.py`.
Override `PYTHON` when your installed dependencies are outside `.venv`, for example
`make test PYTHON=python`.

`make bench-c4` is an alias for the available golden and held-out checks.
The stale ablation targets have been removed because their helper and scenario
fixtures are missing from this checkout. `make score RUN=... CORPUS=...` remains
available for scoring real answered-turn records.

The golden regression uses deterministic embeddings and extractive synthesis.
It checks supersession, exclusion of withdrawn evidence, verified citations and
schema validity; it does not establish streaming gate rates or live model latency.
