"""FastAPI application factory — serves WS + REST + SSE + metrics + frontend.

Entry point: ``uvicorn slrag.api.app:create_app --factory``
or via ``slrag serve`` CLI command.
"""

from __future__ import annotations

import logging
import json
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


def _load_config() -> dict[str, Any]:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _test_suite_config() -> dict[str, str]:
    with (_PROJECT_ROOT / "bench" / "ui_test_suite.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def _corpus_documents() -> list[dict[str, Any]]:
    permanent = _test_suite_config()["corpus_file"].casefold()
    corpus = _PROJECT_ROOT / "corpus"
    return [
        {"name": path.name, "size": path.stat().st_size,
         "is_sample": path.name.casefold() == permanent,
         "is_permanent": path.name.casefold() == permanent}
        for path in sorted(corpus.iterdir()) if path.is_file()
    ] if corpus.exists() else []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    from slrag.telemetry.bus import get_bus
    from slrag.telemetry.jsonl_sink import JSONLSink

    # Always-on JSONL sink
    sink = JSONLSink()
    bus = get_bus()
    bus.subscribe(sink)
    app.state.telemetry_bus = bus
    app.state.jsonl_sink = sink
    app.state.config = _load_config()

    logger.info("SLRAG engine started")
    yield

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

    # -- Preload Models --
    @app.get("/api/preload")
    async def preload():
        # Warm up Embedding Model
        try:
            from slrag.decompose.intent_set import _get_embedding_model
            _get_embedding_model("BAAI/bge-small-en-v1.5")
        except Exception as e:
            logger.error(f"Embedding load failed: {e}")

        # Warm up SpaCy model
        try:
            import spacy
            spacy.load("en_core_web_sm")
        except Exception as e:
            logger.error(f"SpaCy load failed: {e}")

        # Warm up CrossEncoder NLI Scorer (if configured)
        try:
            from slrag.synth.verifier import make_scorer
            make_scorer()
        except Exception as e:
            logger.error(f"CrossEncoder NLI load failed: {e}")

        # Warm up Reranker (if used)
        try:
            from slrag.retrieve.rerank import Reranker
            Reranker()
        except Exception as e:
            logger.error(f"Reranker load failed: {e}")

        # Warm up Ollama LLM (this usually takes ~1 min for the first query)
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": "qwen2.5:7b-instruct",
                    "messages": [{"role": "user", "content": "warmup"}],
                    "max_tokens": 1
                }
                import os
                url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1/chat/completions")
                async with session.post(url, json=payload, timeout=120) as resp:
                    await resp.json()
                logger.info("Ollama LLM warmup complete.")
        except Exception as e:
            logger.error(f"Ollama load failed: {e}")

        return {"status": "ok", "message": "Models preloaded"}

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
        docs = _corpus_documents()
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
        if safe_name.casefold() == _test_suite_config()["corpus_file"].casefold():
            raise HTTPException(status_code=409, detail="The permanent sample document cannot be overwritten. Rename your upload.")
        target_path = corpus_dir / safe_name

        content = await file.read()
        target_path.write_bytes(content)
        logger.info(f"Saved custom document to corpus: {target_path} ({len(content)} bytes)")

        # Run ingest and index pipeline in threadpool
        try:
            from slrag.ingest.indexer import HybridIndexer
            await asyncio.to_thread(HybridIndexer.run_pipeline, corpus_dir)
        except Exception as e:
            logger.error(f"Error during re-indexing: {e}")
            raise HTTPException(status_code=500, detail=f"Indexing failed: {str(e)}")

        from slrag.api.ws_server import reset_retriever
        reset_retriever()

        docs = _corpus_documents()

        return {
            "status": "ok",
            "message": f"Document '{safe_name}' uploaded and corpus indexed successfully.",
            "uploaded": safe_name,
            "documents": docs,
        }

    @app.post("/api/test-suite/prepare")
    async def prepare_test_suite():
        """Index the permanent sample with the corpus and return its test prompt."""
        suite = _test_suite_config()
        corpus_dir = _PROJECT_ROOT / "corpus"
        if not (corpus_dir / suite["corpus_file"]).is_file():
            raise HTTPException(status_code=409, detail="The permanent sample document is missing.")
        from slrag.ingest.indexer import HybridIndexer
        from slrag.api.ws_server import reset_retriever
        try:
            await asyncio.to_thread(HybridIndexer.run_pipeline, corpus_dir)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Test corpus indexing failed: {exc}") from exc
        reset_retriever()
        return {"status": "ok", **suite, "documents": _corpus_documents()}

    @app.post("/api/corpus/reset")
    async def reset_corpus():
        """Reset custom uploads and sessions, retaining and indexing the permanent sample."""
        import shutil
        corpus_dir = _PROJECT_ROOT / "corpus"
        permanent = _test_suite_config()["corpus_file"].casefold()
        deleted = []
        errors = []
        if corpus_dir.exists():
            for f in list(corpus_dir.iterdir()):
                if f.is_file():
                    if f.name.casefold() == permanent:
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
        from slrag.ingest.indexer import HybridIndexer
        try:
            await asyncio.to_thread(HybridIndexer.run_pipeline, corpus_dir)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Sample re-indexing failed: {exc}") from exc
        reset_retriever()

        return {
            "status": "ok",
            "message": "Custom uploads and sessions reset. Permanent sample retained and indexed.",
            "deleted": deleted,
            "documents": _corpus_documents(),
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
