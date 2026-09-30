"""FastAPI application factory — serves WS + REST + SSE + metrics + frontend.

Entry point: ``uvicorn slrag.api.app:create_app --factory``
or via ``slrag serve`` CLI command.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import asyncio
import yaml
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_UI_DIR = _PROJECT_ROOT / "ui"
_CONFIG_PATH = _PROJECT_ROOT / "config" / "app.yaml"
_PERMANENT_CORPUS_FILES = frozenset({"examples.md"})


def _load_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


async def _warmup_llm(app: FastAPI) -> dict:
    """Check the actual configured inference endpoint independently of NLP preload."""
    import aiohttp
    with open(_PROJECT_ROOT / "config" / "synth.yaml", encoding="utf-8") as f:
        generator = (yaml.safe_load(f) or {}).get("generator", {})
    cfg = generator.get("openai_compatible", {})
    result = {"status": "warming", "model": cfg.get("model", ""),
              "base_url": cfg.get("base_url", "")}
    app.state.llm_status = result
    if generator.get("backend") != "openai_compatible":
        result["status"] = "disabled"
        return result
    logger.info("LLM warmup starting: model=%s endpoint=%s", result["model"], result["base_url"])
    try:
        import os
        key = os.environ.get(cfg.get("api_key_env", "SLRAG_LLM_API_KEY"), "")
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        async with aiohttp.ClientSession(headers=headers) as client:
            async with client.post(result["base_url"].rstrip("/") + "/chat/completions",
                    json={"model": result["model"], "messages": [{"role": "user", "content": "Reply OK."}],
                          "max_tokens": 4, "stream": False},
                    timeout=aiohttp.ClientTimeout(total=cfg.get("timeout_s", 120))) as response:
                response.raise_for_status()
                data = await response.json()
                if not data.get("choices") or "error" in data:
                    raise RuntimeError(str(data.get("error", "No completion choices returned")))
        result["status"] = "ready"
        logger.info("LLM warmup complete: model=%s endpoint=%s", result["model"], result["base_url"])
    except Exception as exc:
        result.update(status="error", error=f"{type(exc).__name__}: {exc}")
        logger.error("LLM warmup failed: model=%s error=%s", result["model"], result["error"])
    return result


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    from slrag.telemetry.bus import get_bus
    from slrag.telemetry.jsonl_sink import JSONLSink

    application_logger = logging.getLogger("slrag")
    if not application_logger.handlers and not logging.getLogger().handlers:
        application_logger.addHandler(logging.StreamHandler())
    application_logger.setLevel(logging.INFO)

    # Always-on JSONL sink
    sink = JSONLSink()
    bus = get_bus()
    bus.subscribe(sink)
    app.state.telemetry_bus = bus
    app.state.jsonl_sink = sink
    app.state.config = _load_config()

    app.state.llm_warmup_task = asyncio.create_task(_warmup_llm(app))
    logger.info("SLRAG engine started")
    yield

    task = app.state.llm_warmup_task
    if not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    sink.close()
    logger.info("SLRAG engine stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SLRAG — Streaming Live RAG",
        description="Samsung Theme 4: Real-time streaming retrieval-augmented generation",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS for local dev
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Import and include routers --
    from slrag.api.ws_server import router as ws_router
    app.include_router(ws_router)

    # -- Prometheus metrics endpoint --
    @app.get("/metrics")
    async def prometheus_metrics():
        from slrag.telemetry.metrics import metrics_response
        body, content_type = metrics_response()
        return Response(content=body, media_type=content_type)

    # -- Health check --
    @app.get("/health")
    async def health():
        return {"status": "ok", "engine": "slrag"}

    @app.get("/api/llm/status")
    async def llm_status():
        return getattr(app.state, "llm_status", {"status": "not_started"})

    # -- Preload Models --
    @app.get("/api/preload")
    async def preload():
        errors = []
        logger.info("Starting model preload")
        # Warm up Embedding Model
        try:
            from slrag.decompose.intent_set import _get_embedding_model
            await asyncio.to_thread(_get_embedding_model, "BAAI/bge-small-en-v1.5")
        except Exception as e:
            logger.error(f"Embedding load failed: {e}")
            errors.append(f"Embedding load failed: {e}")

        # Warm up SpaCy model
        try:
            import spacy
            await asyncio.to_thread(spacy.load, "en_core_web_sm")
        except Exception as e:
            logger.error(f"SpaCy load failed: {e}")
            errors.append(f"SpaCy load failed: {e}")

        # Warm up CrossEncoder NLI Scorer (if configured)
        try:
            from slrag.synth.verifier import make_scorer
            await asyncio.to_thread(make_scorer)
        except Exception as e:
            logger.error(f"CrossEncoder NLI load failed: {e}")
            errors.append(f"CrossEncoder NLI load failed: {e}")

        # Warm up Reranker (if used)
        try:
            from slrag.retrieve.rerank import Reranker
            await asyncio.to_thread(Reranker)
        except Exception as e:
            logger.error(f"Reranker load failed: {e}")
            errors.append(f"Reranker load failed: {e}")

        # Reuse startup warmup; expose its result instead of waiting behind NLP loads.
        task = getattr(app.state, "llm_warmup_task", None)
        if task is None or (task.done() and getattr(app.state, "llm_status", {}).get("status") == "error"):
            task = asyncio.create_task(_warmup_llm(app))
            app.state.llm_warmup_task = task
        result = await task
        if result["status"] == "error":
            errors.append(result["error"])

        return {"status": "error" if errors else "ok", "message": "Preload incomplete" if errors else "Models preloaded", "errors": errors}

    # -- API: list sessions --
    @app.get("/api/sessions")
    async def list_sessions():
        from slrag.api.ws_server import get_session_manager
        mgr = get_session_manager()
        return {"sessions": list(mgr.sessions.keys()), "count": len(mgr.sessions)}

    # -- Corpus Document Management Endpoints --

    @app.get("/api/corpus/documents")
    async def list_corpus_documents():
        """List all documents currently in the corpus."""
        corpus_dir = _PROJECT_ROOT / "corpus"
        docs = []
        if corpus_dir.exists():
            for f in sorted(corpus_dir.iterdir()):
                if f.is_file():
                    docs.append({
                        "name": f.name,
                        "size": f.stat().st_size,
                        "is_sample": f.name.lower().startswith("sample_doc"),
                        "is_permanent": f.name.casefold() in _PERMANENT_CORPUS_FILES,
                    })
        return {"documents": docs, "count": len(docs)}

    @app.post("/api/corpus/upload")
    async def upload_corpus_document(file: UploadFile = File(...)):
        """Upload custom markdown or text document to corpus and re-index."""
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        allowed_exts = {".md", ".txt", ".markdown"}
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file extension '{ext}'. Only .md and .txt files are supported."
            )

        corpus_dir = _PROJECT_ROOT / "corpus"
        corpus_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(file.filename).name
        if safe_name.casefold() in _PERMANENT_CORPUS_FILES:
            raise HTTPException(status_code=409, detail="This filename belongs to a permanent document. Rename your upload.")
        target_path = corpus_dir / safe_name

        content = await file.read()
        target_path.write_bytes(content)
        logger.info(f"Saved custom document to corpus: {target_path} ({len(content)} bytes)")

        # Run ingest and index pipeline in threadpool
        try:
            from slrag.ingest.indexer import HybridIndexer
            await asyncio.to_thread(HybridIndexer.run_pipeline, corpus_dir)
        except Exception as e:
            import traceback
            logger.error(f"Error during re-indexing: {e}\n{traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

        from slrag.api.ws_server import reset_retriever
        reset_retriever()

        docs = []
        for f in sorted(corpus_dir.iterdir()):
            if f.is_file():
                docs.append({
                    "name": f.name,
                    "size": f.stat().st_size,
                    "is_sample": f.name.lower().startswith("sample_doc"),
                    "is_permanent": f.name.casefold() in _PERMANENT_CORPUS_FILES,
                })

        return {
            "status": "ok",
            "message": f"Document '{safe_name}' uploaded and corpus indexed successfully.",
            "uploaded": safe_name,
            "documents": docs,
        }

    @app.post("/api/test-suite/run")
    async def run_test_suite():
        """Runs the PRISM RAG evaluation criteria examples on a separate test corpus."""
        import subprocess
        import sys
        import os

        try:
            # We run the script that handles indexing the test corpus and running the examples
            result = await asyncio.to_thread(
                subprocess.run,
                [sys.executable, str(_PROJECT_ROOT / "scripts" / "run_test_suite.py")],
                cwd=_PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            return {
                "status": "success",
                "output": result.stdout
            }
        except subprocess.CalledProcessError as e:
            return {
                "status": "error",
                "output": e.stdout + "\n" + e.stderr
            }

    @app.post("/api/corpus/reset")
    async def reset_corpus():
        """Remove custom uploads and session state, retaining permanent documents."""
        import shutil

        corpus_dir = _PROJECT_ROOT / "corpus"
        deleted = []
        errors = []
        if corpus_dir.exists():
            for f in list(corpus_dir.iterdir()):
                if f.is_file():
                    if f.name.casefold() in _PERMANENT_CORPUS_FILES:
                        continue
                    try:
                        f.unlink()
                        deleted.append(f.name)
                        logger.info(f"Deleted corpus document: {f.name}")
                    except Exception as e:
                        logger.error(f"Failed deleting {f.name}: {e}")
                        errors.append(f"{f.name}: {e}")

        # Completely clear FAISS index, BM25 index, and all indexing artifacts
        index_dir = _PROJECT_ROOT / ".index"
        if index_dir.exists():
            for item in list(index_dir.iterdir()):
                try:
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)
                    logger.info(f"Deleted index artifact: {item.name}")
                except Exception as e:
                    logger.error(f"Failed deleting index artifact {item.name}: {e}")
                    errors.append(f"{item.name}: {e}")
        index_dir.mkdir(parents=True, exist_ok=True)

        from slrag.api.ws_server import reset_retriever, get_session_manager
        reset_retriever()
        mgr = get_session_manager()
        mgr.reset_all()

        if errors:
            raise HTTPException(status_code=500, detail="Reset incomplete: " + "; ".join(errors))

        if any(corpus_dir.glob("*")):
            from slrag.ingest.indexer import HybridIndexer
            try:
                await asyncio.to_thread(HybridIndexer.run_pipeline, corpus_dir)
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Permanent document re-indexing failed: {exc}") from exc
            reset_retriever()

        remaining = await list_corpus_documents()

        return {
            "status": "ok",
            "message": "Custom uploads and sessions reset. Permanent documents retained and indexed.",
            "deleted": deleted,
            "documents": remaining["documents"],
        }


    # -- Frontend UI --
    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        index = _UI_DIR / "dist" / "index.html"
        if index.exists():
            return FileResponse(index)
        # Fallback to the old one if dist doesn't exist
        old_index = _UI_DIR / "index.html"
        if old_index.exists():
            return FileResponse(old_index)
        return HTMLResponse("<h1>SLRAG Engine Running</h1><p>Frontend not found in ui/dist/</p>")

    # Serve static assets
    dist_assets = _UI_DIR / "dist" / "assets"
    if dist_assets.exists():
        app.mount("/assets", StaticFiles(directory=str(dist_assets)), name="assets")
    
    if _UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(_UI_DIR)), name="ui")

    return app
