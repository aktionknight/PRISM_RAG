"""Permanent UI sample survives reset and remains available to the test prompt."""
import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, UploadFile

from slrag.api import app, ws_server
from slrag.ingest.indexer import HybridIndexer


@pytest.fixture
def api(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sample_reference.md").write_text("# Sensor manual\nInspect every 7 days.")
    (corpus / "uploaded.md").write_text("Private custom document")
    fixtures = tmp_path / "bench"
    fixtures.mkdir(parents=True)
    (fixtures / "ui_test_suite.json").write_text(json.dumps({
        "corpus_file": "sample_reference.md", "prompt": "What is the inspection interval?"}))
    monkeypatch.setattr(app, "_PROJECT_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(ws_server, "reset_retriever", lambda: calls.append("cache"))
    monkeypatch.setattr(ws_server, "get_session_manager", lambda: SimpleNamespace(reset_all=lambda: calls.append("sessions")))
    monkeypatch.setattr(HybridIndexer, "run_pipeline", lambda path: calls.append(sorted(p.name for p in path.iterdir())))
    application = app.create_app()
    routes = {r.path: r.endpoint for r in application.routes if hasattr(r, "path") and hasattr(r, "endpoint")}
    return routes, corpus, calls


@pytest.mark.asyncio
async def test_reset_keeps_sample_and_reindexes_remaining_documents(api):
    routes, corpus, calls = api
    for _ in range(2):
        response = await routes["/api/corpus/reset"]()
        assert [p.name for p in corpus.iterdir()] == ["sample_reference.md"]
        assert response["documents"][0]["is_permanent"] is True
        assert calls[-1] == "cache"
        assert ["sample_reference.md"] in calls
    assert "sessions" in calls


@pytest.mark.asyncio
async def test_prepare_returns_fixture_prompt_and_indexes_without_deleting_uploads(api):
    routes, corpus, calls = api
    response = await routes["/api/test-suite/prepare"]()
    assert response["prompt"] == "What is the inspection interval?"
    assert response["corpus_file"] == "sample_reference.md"
    assert (corpus / "uploaded.md").exists()
    assert ["sample_reference.md", "uploaded.md"] in calls


@pytest.mark.asyncio
async def test_upload_cannot_replace_permanent_sample(api):
    routes, corpus, calls = api
    with pytest.raises(HTTPException) as error:
        await routes["/api/corpus/upload"](UploadFile(filename="SAMPLE_REFERENCE.md", file=BytesIO(b"replacement")))
    assert error.value.status_code == 409
    assert "Inspect" in (corpus / "sample_reference.md").read_text()


@pytest.mark.asyncio
async def test_failed_reindex_does_not_report_success(api, monkeypatch):
    routes, corpus, calls = api
    def fail(path):
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(HybridIndexer, "run_pipeline", fail)
    with pytest.raises(HTTPException) as error:
        await routes["/api/corpus/reset"]()
    assert error.value.status_code == 500
    assert (corpus / "sample_reference.md").exists()
