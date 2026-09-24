# Streaming Live RAG — Local Setup, Demo & Testing Guide
## Document E — Run It, Use Your Own Documents, See the Telemetry

> This is the practical runbook: how to point the engine at your own documents, stand up the interface, watch it work as an end user would, and get a Grafana dashboard that actually satisfies the brief's telemetry objective (Component 5 / Gate G6) rather than just looking impressive. Read alongside **A — Final Architecture**, **B — Engineering Roadmap**, **D — Phase 0 Facet Discovery**.

---

## 1. Using Your Own Documents as the Knowledge Base

The corpus is just a folder. Nothing about the pipeline is hardcoded to the brief's example topics (workshops, cancellation policies) — that's the whole point of Phase 0's format-agnostic facet discovery (Doc D). Drop in whatever you have.

### 1.1 Supported inputs and folder layout

```
corpus/
├─ policy_handbook.pdf
├─ vendor_agreement.docx
├─ faq_notes.md
├─ product_specs.txt
└─ meeting_transcripts/
   └─ q3_review.txt
```

- **PDF** — Detector A (native bookmarks/outline) or Detector C (typographic heuristic on raw text) picks up structure automatically; no bookmarks needed.
- **DOCX** — heading *styles* (Heading 1/2/3) are read directly if present; falls through the same cascade otherwise.
- **Markdown / plain text** — `#`/`##` headings if present (Detector D); otherwise Detector E's sliding-window fallback kicks in, so even a wall of unstructured text works.
- **Mixed formats in one folder** — fine. Each file is parsed by its own loader, then all candidate units go into the same clustering pass in Phase 0, so facets can span document types (e.g. "cancellation terms" pulled from both a PDF and a DOCX).

If you don't have a real document set handy for testing, use **the Theme 4 brief PDF itself** as your corpus for a first smoke test — it's short, it's the one document you know the structure of, and it's already sitting in `/mnt/user-data/uploads/` from earlier in this session. Real generalization testing should use a *second*, unrelated document set once the pipeline works on the first.

There are **two ways to get a corpus into the running system**, and both call the exact same underlying indexing function — no logic duplication, no drift between them:

| Path | When to use it | How |
|---|---|---|
| **CLI / mounted folder** | Automated grading, replay, CI, ablations — anything that needs to be scriptable and deterministic | `slrag index --corpus ./corpus --out ./.index` (below) |
| **Browser upload** | Interactive demo/testing — a judge (or you) drags files into the running app with no terminal access at all | §1.3 below |

### 1.2 Index it (CLI path)

```bash
# one-time, explicit command — HC-2 compliant (nothing baked, nothing precomputed at import time)
slrag index --corpus ./corpus --out ./.index
```

What this actually does, in order (ties back to Doc D and Doc B Phase 1):
1. Loads and chunks every file, section-bounded, preserving `Doc_ID`/`§Section` labels.
2. Runs Phase 0 facet discovery once → writes `.index/facets.yaml`.
3. Builds the BM25 (`bm25s`) and dense (FAISS) indexes.
4. Runs the reproducibility gate automatically (`--verify-repro` flag re-runs and diffs — add this on your first run against a new corpus to catch nondeterminism early):

```bash
slrag index --corpus ./corpus --out ./.index --verify-repro
# ✓ facets.yaml identical across two runs
# ✓ 5 facets discovered via Detector C (typographic heuristic)
# ✓ 214 chunks indexed across 4 documents
```

Inspect what it found before moving on — this is the single most useful sanity check on a new corpus:

```bash
cat .index/facets.yaml
```

If `fallback_used: true` shows up and every chunk landed in `general`, your documents likely have no extractable structure at all (Detector E fired) — the pipeline still works, but facet-routed retrieval weighting (S-8) and quota fusion (S-9) will have less to work with. Worth knowing before you demo, not after.

### 1.3 Live Upload — Indexing in Real Time via the Interface

You don't have to deploy anything or ship a pre-built `.index/` folder. **The Dockerfile you send is the entire deliverable** — whoever runs it gets an empty engine with a drag-and-drop upload panel, and the *full* Phase 0 pipeline (structure detection, facet clustering, embedding, BM25/FAISS build) runs live, in the browser session, the moment they drop files in. This is actually the better default for judges: they can test your system against *their own* documents without touching a terminal, which is a direct, practical answer to the "held-out corpus" problem — nobody has to hand you their private test set in advance, and you never see it either.

**What "real-time" means here, precisely.** The per-chunk controller budget (≤15 ms, Doc A §1) is about live *query* processing and is untouched by any of this. Indexing a corpus is a one-time cost paid once per upload, not once per chunk — it typically completes in single-digit seconds for a handful of documents and scales roughly linearly with total token count (the embedding step dominates; Phase 0's clustering runs on section/heading *count*, which is small, so it's cheap regardless of document length). "Real-time" means: no separate CLI step, no container restart, no rebuild — upload finishes, the pipeline runs to completion in the background while you watch a progress bar, and chat unlocks the moment it's done, all inside one running container.

**Flow:**

```
Browser: drag files onto the dropzone
   │  POST /upload  (multipart)
   ▼
FastAPI: saves files to /data/uploads/{job_id}/, kicks off a background task, returns job_id immediately
   │
   ▼
Background task calls the SAME index_corpus() function the CLI uses:
   parsing → Phase 0 facet discovery → embedding → BM25/FAISS build → ready
   │  each stage pushes a progress event
   ▼
Browser: WS /ws/index-progress/{job_id} streams stage + percent
   │
   ▼
On "ready": engine hot-swaps its active index pointer → chat unlocks automatically
```

```python
# src/slrag/api/upload_router.py
import asyncio, shutil, uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, WebSocket
from slrag.ingest.pipeline import index_corpus   # the exact function `slrag index` calls — one code path

router = APIRouter()
UPLOAD_DIR, INDEX_DIR = Path("/data/uploads"), Path("/data/index")
index_jobs: dict[str, asyncio.Queue] = {}

@router.post("/upload")
async def upload_documents(files: list[UploadFile]):
    job_id = str(uuid.uuid4())
    corpus_dir = UPLOAD_DIR / job_id
    corpus_dir.mkdir(parents=True, exist_ok=True)
    for f in files:
        with (corpus_dir / f.filename).open("wb") as out:
            shutil.copyfileobj(f.file, out)

    queue: asyncio.Queue = asyncio.Queue()
    index_jobs[job_id] = queue
    asyncio.create_task(_run_indexing(job_id, corpus_dir, queue))
    return {"job_id": job_id}

async def _run_indexing(job_id, corpus_dir, queue):
    # index_corpus is an async generator yielding (stage, pct, extra) — same stages the CLI logs to stdout
    async for stage, pct, extra in index_corpus(corpus_dir, INDEX_DIR / job_id, stream_progress=True):
        await queue.put({"type": "index_progress", "stage": stage, "pct": pct, **extra})
    await queue.put(None)  # sentinel

@router.websocket("/ws/index-progress/{job_id}")
async def index_progress_ws(ws: WebSocket, job_id: str):
    await ws.accept()
    queue = index_jobs.get(job_id)
    if queue is None:
        await ws.close(code=4404); return
    while (event := await queue.get()) is not None:
        await ws.send_json(event)
    await ws.send_json({"type": "index_progress", "stage": "ready", "pct": 100})
    engine.load_index(INDEX_DIR / job_id)   # atomic swap — in-flight queries on the old index finish safely
    await ws.close()
```

Progress events on the wire look like:
```json
{"type":"index_progress","stage":"parsing","pct":10}
{"type":"index_progress","stage":"facet_discovery","pct":35,"facets_found":6}
{"type":"index_progress","stage":"embedding","pct":65,"chunks_embedded":142}
{"type":"index_progress","stage":"building_index","pct":90}
{"type":"index_progress","stage":"ready","pct":100,"chunks_indexed":214}
```

**Frontend dropzone**, added ahead of the chat view from §3.3 — the app is in one of two states, `uploading` or `ready`:

```jsx
// ui/src/Uploader.jsx
import { useState } from "react";

export default function Uploader({ onReady }) {
  const [stage, setStage] = useState(null);
  const [pct, setPct] = useState(0);

  async function handleFiles(fileList) {
    const form = new FormData();
    [...fileList].forEach((f) => form.append("files", f));
    const { job_id } = await fetch("/upload", { method: "POST", body: form }).then((r) => r.json());

    const ws = new WebSocket(`ws://${location.host}/ws/index-progress/${job_id}`);
    ws.onmessage = (e) => {
      const evt = JSON.parse(e.data);
      setStage(evt.stage); setPct(evt.pct);
      if (evt.stage === "ready") { ws.close(); onReady(); }
    };
  }

  return (
    <div onDrop={(e) => { e.preventDefault(); handleFiles(e.dataTransfer.files); }}
         onDragOver={(e) => e.preventDefault()}
         style={{ border: "2px dashed #888", padding: 40, textAlign: "center" }}>
      {stage ? `${stage}… ${pct}%` : "Drop documents here to build the knowledge base"}
      <input type="file" multiple onChange={(e) => handleFiles(e.target.files)} />
    </div>
  );
}
```

**One active corpus at a time, by design.** For a hackathon demo, the engine holds a single loaded index in memory; uploading a new set of documents rebuilds and atomically replaces it. If you want to test against two different document sets in one sitting, just upload again — the old index is discarded, not merged. This keeps the mental model simple for whoever's testing it ("what you uploaded is what it answers from") and avoids stale-evidence bugs from mixing corpora.

**Note on the reproducibility gate (Doc D §3.6).** That gate — run indexing twice, diff the output, must match — stays a **dev-time CI check** run against your own fixed test corpus, confirming the pipeline is deterministic in principle. It does **not** re-run on every live upload; doubling every judge's wait time to re-verify something already proven deterministic in CI would be wasted latency for no additional information.

---

## 2. Running It End-to-End Locally

```bash
git clone <your-repo> && cd streaming-live-rag
cp .env.example .env                      # set model paths / API keys for local LLM serving if needed
docker compose up --build                 # core engine + FastAPI + built frontend, one port
```

Then open **`http://localhost:8000`**. That single command is also exactly what a judge runs — this is not a separate "dev mode," it's the real path, which is deliberate (fewer things that behave differently between your machine and theirs).

For fast local iteration without rebuilding the Docker image every time:
```bash
uv sync                                    # installs pinned deps from uv.lock
uvicorn slrag.api.ws_server:app --reload --port 8000
cd ui && npm install && npm run dev        # Vite dev server on :5173, proxies WS to :8000
```
Use this loop while you're actively coding; use `docker compose up` to verify it still works the way a judge will see it, at least once a day.

---

## 3. Implementing the Interface

### 3.1 Serving frontend + WebSocket from one FastAPI app

```python
# src/slrag/api/ws_server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from slrag.core.session import SessionStore
from slrag.engine import SLRAGEngine

app = FastAPI()
sessions = SessionStore()          # ephemeral, HC-4 compliant — nothing written to disk
engine = SLRAGEngine.from_config("config/app.yaml")

@app.websocket("/ws/session")
async def ws_session(ws: WebSocket):
    await ws.accept()
    session = sessions.create()
    try:
        async for msg in ws.iter_json():
            if msg["type"] == "chunk":
                async for event in engine.ingest_chunk(session, msg["t_s"], msg["text"]):
                    await ws.send_json(event.model_dump())      # controller_decision, retrieval_started, ...
            elif msg["type"] == "utterance_end":
                async for event in engine.finalize_turn(session):
                    await ws.send_json(event.model_dump())      # answer_token, citation_attached, answer_version
    except WebSocketDisconnect:
        sessions.destroy(session.id)                            # explicit ephemeral cleanup — HC-4

@app.get("/health")
async def health():
    return {"status": "ok", "facets_loaded": len(engine.facets)}

app.mount("/", StaticFiles(directory="ui/dist", html=True), name="ui")   # built React app, served last
```

The engine emits a typed event per internal step (`ControllerDecision`, `RetrievalEvent`, `AnswerToken`, `CitationAttached`, `AnswerVersion`, `UncertaintyFlag` — the schemas frozen back in Doc C §2). The frontend just renders whatever arrives; it never re-derives anything.

### 3.2 Testing the backend alone, before touching the frontend

Don't debug both ends at once. Verify the WS contract with a raw client first:

```bash
pip install websockets
python -c "
import asyncio, websockets, json

async def main():
    async with websockets.connect('ws://localhost:8000/ws/session') as ws:
        await ws.send(json.dumps({'type':'chunk','t_s':0.0,'text':'I need to plan a workshop in'}))
        print(await ws.recv())
        await ws.send(json.dumps({'type':'chunk','t_s':0.8,'text':'Pune for 30 people, and cancellation terms'}))
        print(await ws.recv())
        await ws.send(json.dumps({'type':'utterance_end'}))
        async for _ in range(10):
            print(await ws.recv())

asyncio.run(main())
"
```

You should see `controller_decision` events flip WAIT→RETRIEVE, then `retrieval_started`, then streamed `answer_token`s with citations. If this works, the frontend is purely a rendering problem.

### 3.3 The minimal three-pane frontend

You don't need the full polished UI from Doc B to *test* the system — a bare version proves the pipeline end-to-end fastest:

```jsx
// ui/src/App.jsx — minimal version, enough to see all six demo beats
import { useState, useRef } from "react";

const PRESETS = [
  { label: "Multi-intent", text: "workshop for 30 in Pune, cancellation policy, catering" },
  { label: "Refinement follow-up", text: "actually it was international travel" },
  { label: "Suppression", text: "repeat that in two bullets" },
];

export default function App() {
  const [decisions, setDecisions] = useState([]);
  const [answer, setAnswer] = useState("");
  const [citations, setCitations] = useState([]);
  const wsRef = useRef(null);

  function connect() {
    const ws = new WebSocket(`ws://${location.host}/ws/session`);
    ws.onmessage = (e) => {
      const evt = JSON.parse(e.data);
      if (evt.type === "controller_decision") setDecisions((d) => [...d, evt]);
      if (evt.type === "answer_token") setAnswer((a) => a + evt.text);
      if (evt.type === "citation_attached") setCitations((c) => [...c, evt.label]);
    };
    wsRef.current = ws;
  }

  function sendText(text) {
    // naive client-side chunking: split into two "chunks" to simulate streaming
    const words = text.split(" ");
    const mid = Math.floor(words.length / 2);
    wsRef.current.send(JSON.stringify({ type: "chunk", t_s: 0.0, text: words.slice(0, mid).join(" ") }));
    setTimeout(() => {
      wsRef.current.send(JSON.stringify({ type: "chunk", t_s: 0.8, text: words.slice(mid).join(" ") }));
      wsRef.current.send(JSON.stringify({ type: "utterance_end" }));
    }, 400);
  }

  return (
    <div style={{ display: "flex", gap: 16, padding: 16 }}>
      <div style={{ flex: 1 }}>
        <h3>Stream</h3>
        {PRESETS.map((p) => (
          <button key={p.label} onClick={() => sendText(p.text)}>{p.label}</button>
        ))}
        <ul>{decisions.map((d, i) => <li key={i}>{d.decision} — {d.reason}</li>)}</ul>
      </div>
      <div style={{ flex: 1 }}>
        <h3>Answer</h3>
        <p>{answer}</p>
        <div>{citations.map((c, i) => <span key={i} style={{ marginRight: 6, border: "1px solid" }}>{c}</span>)}</div>
      </div>
    </div>
  );
}
```

Get this ugly version working first. Polish (dimmed→solid streaming, the version slider, the Gantt chart) is a Phase 5 concern (Doc B §4, Phase 5.10) — don't build it before the pipeline underneath it is real.

---

## 4. Testing It Yourself as an End User

Run through this sequence once per corpus you index — it exercises every gate in one pass:

| Step | What to type | What you should see | Gate it checks |
|---|---|---|---|
| 1 | A vague partial sentence, then stop typing for a beat | `WAIT` badges, no retrieval yet | G2 (no false trigger) |
| 2 | Continue with a specific entity from your corpus (a real term, name, or number that appears in your docs) | Badge flips to `RETRIEVE` *before* you finish the sentence | G2 (early retrieval) |
| 3 | Add "and also tell me about X and Y" (two more real topics from your corpus) | `sub_queries` grows to 3; only 2 *new* retrieval events fire, not 3 | G3 (decomposition, no re-dispatch) |
| 4 | Wait for the answer, check citation chips | Every claim has a `[Doc_ID §Section]` tag; click one, see the actual source text | G4 (grounding) |
| 5 | Type a constraint that changes one fact ("actually it happened after the deadline") | Answer version increments; most of the previous answer is unchanged; `full_corpus_searches: 0` in telemetry | G5 (refinement, not restart) |
| 6 | Type "repeat that in two bullets" | No new retrieval fires at all; citations are a subset of before | P4 / suppression |
| 7 | Ask about something genuinely absent from your corpus | An explicit `uncertainty` sentence appears — not a confident guess | O4 / G4 |

If any of these doesn't behave as described, that's your bug list — this sequence **is** effectively your own private acceptance test before a judge ever sees it.

### 4.1 Replay mode — testing without typing every time

```bash
slrag replay --corpus ./corpus --stream bench/data/suite.jsonl --out runs/events.jsonl
slrag score  --run runs/events.jsonl --gold bench/data/gold.jsonl
```
This runs the same six-step story programmatically and prints G2–G6 numbers directly — use it after every code change instead of manually re-typing the sequence above.

---

## 5. The Grafana Dashboard — Built for the Telemetry Objective, Not Just for Looks

The brief's Component 5 names five specific data classes the dashboard/logs must cover: **timestamps, retrieval triggers, source mappings, version transitions, token cost.** Gate G6 requires **100% trace coverage** of these, measured, not eyeballed. The dashboard below is built to make each of those five visible as its own panel — not a generic "AI app metrics" board.

### 5.1 Bring it up

```bash
docker compose --profile obs up
```
Opens Prometheus at `:9090` and Grafana at `:3000` (default login `admin`/`admin` on first run — change it or leave it, doesn't matter for a local demo). The dashboard is **provisioned as code**, so it appears fully built — no manual panel creation.

```
obs/
├─ prometheus.yml
└─ grafana/
   ├─ provisioning/
   │  ├─ datasources/prometheus.yaml
   │  └─ dashboards/default.yaml
   └─ dashboards/slrag.json
```

```yaml
# obs/prometheus.yml
scrape_configs:
  - job_name: slrag
    static_configs:
      - targets: ["engine:8000"]      # FastAPI /metrics endpoint
    scrape_interval: 2s
```

```yaml
# obs/grafana/provisioning/datasources/prometheus.yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    access: proxy
    isDefault: true
```

```yaml
# obs/grafana/provisioning/dashboards/default.yaml
apiVersion: 1
providers:
  - name: slrag
    folder: ""
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

### 5.2 Panel list — one panel per required telemetry field, plus the gate readouts

| Panel | Metric source | Telemetry class it satisfies |
|---|---|---|
| **Retrieval Gantt** | `retrieval_event{trigger, t_s, sub_query}` rendered as a table/state-timeline panel, one row per sub-query, x-axis = stream time | Retrieval trigger events |
| **Controller decision timeline** | `controller_decision{decision, reason}` as a state-timeline: grey WAIT / green RETRIEVE / amber SUPPRESS blocks over stream time | Execution timestamps |
| **Citation coverage gauge** | `citation_support_rate` (sampled claims with a valid `[Doc_ID §Section]` / total claims) | Source mappings |
| **Fabricated ID counter** | `fabricated_citation_count_total` — a Prometheus counter that must stay at **0** the entire demo | Source mappings (the zero-tolerance half of G4) |
| **Answer version lineage** | `answer_version{session_id, from, to}` as a table: from → to, claims retained/superseded/added, `full_corpus_searches` | Version transitions |
| **Token cost over time** | `llm_tokens_total{component="decompose|synthesize|tiebreak"}` and `cost_usd_total` as a time series, stacked by component | Token cost |
| **Latency breakdown** | Histogram: `stage_latency_ms{stage}` — controller / decompose / retrieve / rerank / synthesize | Execution timestamps (the performance-budget numbers from Doc B §7) |
| **Gate readout board** | Six stat panels: `early_retrieval_rate`, `sub_intent_recall`, `citation_support_rate`, `claims_retained_pct`, `trace_coverage_pct`, and a `reproducible: pass/fail` boolean | Direct G1–G6 scorecard, on screen |

The **gate readout board** is the panel that actually answers "does this satisfy the telemetry objective" at a glance — it's not decoration, it's the six numbers the brief grades you on, computed live from the same `events.jsonl`/metrics stream a judge is watching.

### 5.3 Wiring metrics out of the engine

```python
# src/slrag/telemetry/otel_sink.py
from prometheus_client import Counter, Histogram, Gauge, make_asgi_app

retrieval_events_total   = Counter("retrieval_events_total", "retrieval dispatches", ["trigger"])
controller_decisions     = Counter("controller_decisions_total", "controller outcomes", ["decision", "reason"])
fabricated_citations     = Counter("fabricated_citation_count_total", "citations rejected by allowlist")
stage_latency_ms         = Histogram("stage_latency_ms", "per-stage latency", ["stage"])
llm_tokens_total         = Counter("llm_tokens_total", "tokens used", ["component"])
cost_usd_total           = Counter("cost_usd_total", "running cost")
trace_coverage_pct       = Gauge("trace_coverage_pct", "invariant-suite coverage")

# mounted alongside the WS app:
app.mount("/metrics", make_asgi_app())
```

Every place the engine already emits a `TelemetryEvent` to `events.jsonl` (Doc A §5), add one line incrementing/observing the matching Prometheus metric — same event, two sinks, exactly the "dual sink" design from Doc A §5.1. Nothing new needs to be computed; you're just exporting what's already being logged.

### 5.4 Verifying the dashboard actually reflects reality

Don't trust that the panels are wired correctly by eyeballing them once — run the replay suite while watching Grafana:

```bash
slrag replay --stream bench/data/suite.jsonl --out runs/events.jsonl &
# watch localhost:3000/d/slrag update live as the replay plays through
```

If a panel stays flat while `events.jsonl` is clearly filling up, that's a metric-naming mismatch between the sink and the Prometheus scrape config — check this before demo day, not during it.

---

## 6. Quick Troubleshooting

| Symptom | Likely cause |
|---|---|
| `facets.yaml` shows `fallback_used: true`, one giant `general` facet | Your corpus has no detectable structure (Detector E fired) — retrieval still works, but facet-routing/quota benefits are reduced. Consider adding headings to source docs, or accept it and note it in your evaluation report. |
| WS connects but no `controller_decision` events ever arrive | Chunking on the client isn't sending enough distinct `chunk` messages — the controller needs multiple timestamped fragments, not one giant blob. |
| Citations always empty / `uncertainty` fires on everything | Index wasn't rebuilt after changing the corpus — rerun `slrag index`; stale `.index/` is the most common cause. |
| Grafana panels blank | Check `docker compose --profile obs logs prometheus` for scrape errors — usually a port mismatch between `/metrics` and `prometheus.yml`'s target. |
| `docker compose up` works but `--profile obs` fails to start | Obs stack should be isolated — if it breaks the core profile too, check for a shared network/volume conflict; core and obs must be able to start fully independently (this is a G1 risk if not). |

---

*Next natural addition, if useful: a short `bench/generate.py` walkthrough for turning your own corpus into a synthetic streaming test suite (Doc B §5.5/§4 Phase 2.2), so step 4's manual test sequence above can be run automatically across dozens of variations instead of by hand.*
