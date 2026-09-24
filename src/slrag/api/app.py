"""FastAPI application factory — serves WS + REST + SSE + metrics + frontend.

Entry point: ``uvicorn slrag.api.app:create_app --factory``
or via ``slrag serve`` CLI command.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, Response
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

    # -- API: list sessions --
    @app.get("/api/sessions")
    async def list_sessions():
        from slrag.api.ws_server import get_session_manager
        mgr = get_session_manager()
        return {"sessions": list(mgr.sessions.keys()), "count": len(mgr.sessions)}

    # -- Frontend UI --
    @app.get("/", response_class=HTMLResponse)
    async def serve_ui():
        index = _UI_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse("<h1>SLRAG Engine Running</h1><p>Frontend not found in ui/</p>")

    # Serve static assets from ui/
    if _UI_DIR.exists():
        app.mount("/ui", StaticFiles(directory=str(_UI_DIR)), name="ui")

    return app
