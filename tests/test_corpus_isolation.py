"""Corpus lifecycle regressions using unrelated, temporary documents."""
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_index_output_and_calibration_are_isolated(tmp_path, monkeypatch):
    from slrag.ingest.indexer import HybridIndexer
    out = tmp_path / "evaluation"
    monkeypatch.setenv("SLRAG_INDEX_DIR", str(out))
    indexer = HybridIndexer()
    assert indexer.sparse_path == out / "bm25"
    assert indexer.dense_path == out / "faiss"
    assert indexer.chunks_path == out / "chunks.jsonl"
    indexer.calibrate_probe_thresholds([], None)
    assert (out / "probe_calibration.json").exists()


def test_facets_and_document_terms_use_selected_corpus(tmp_path, monkeypatch):
    from slrag.synth.config import load_facets
    from slrag.controller.suppression import get_indexed_doc_terms, reset_suppression_cache
    index = tmp_path / "index"
    corpus = tmp_path / "documents"
    index.mkdir()
    corpus.mkdir()
    (index / "facets.yaml").write_text("facets:\n  sensors:\n    label: Sensors\n")
    (corpus / "sensor_manual.md").write_text("# Sensors\nCalibration instructions.")
    monkeypatch.setenv("SLRAG_INDEX_DIR", str(index))
    monkeypatch.setenv("SLRAG_CORPUS_DIR", str(corpus))
    reset_suppression_cache()
    try:
        assert set(load_facets()) == {"sensors"}
        assert "sensor" in get_indexed_doc_terms()
        assert "architecture" not in get_indexed_doc_terms()
    finally:
        reset_suppression_cache()


@pytest.mark.asyncio
async def test_reset_removes_uploads_and_index_but_preserves_test_corpus(tmp_path, monkeypatch):
    from slrag.api import app, ws_server
    from slrag.ingest.indexer import HybridIndexer
    corpus = tmp_path / "corpus"
    index = tmp_path / ".index"
    test_corpus = tmp_path / "test_corpus"
    for directory in (corpus, index / "bm25", test_corpus):
        directory.mkdir(parents=True)
        (directory / "sensor.md").write_text("Sensor calibration data")
    permanent = corpus / "examples.md"
    permanent.write_text("# Sensor reference\nCalibrate annually.")
    calls = []
    monkeypatch.setattr(app, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ws_server, "reset_retriever", lambda: calls.append("retriever"))
    monkeypatch.setattr(ws_server, "get_session_manager", lambda: SimpleNamespace(reset_all=lambda: calls.append("sessions")))
    def rebuild(directory):
        assert directory == corpus
        assert [path.name for path in directory.iterdir()] == ["examples.md"]
        (index / "chunks.jsonl").write_text("Rebuilt permanent document index")
        calls.append("reindexed")
    monkeypatch.setattr(HybridIndexer, "run_pipeline", rebuild)
    application = app.create_app()
    route = next(route for route in application.routes if getattr(route, "path", None) == "/api/corpus/reset")
    response = await route.endpoint()
    assert response["status"] == "ok"
    assert permanent.read_text() == "# Sensor reference\nCalibrate annually."
    assert [doc["name"] for doc in response["documents"]] == ["examples.md"]
    assert response["documents"][0]["is_permanent"] is True
    assert (index / "chunks.jsonl").exists()
    assert not (index / "bm25").exists()
    assert (test_corpus / "sensor.md").exists()
    assert set(calls) == {"retriever", "sessions", "reindexed"}
    # The exemption and rebuilt index also survive consecutive resets.
    await route.endpoint()
    assert permanent.exists()


@pytest.mark.asyncio
async def test_reset_reports_failed_deletion(tmp_path, monkeypatch):
    from fastapi import HTTPException
    from slrag.api import app, ws_server
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    blocked = corpus / "sensor.md"
    blocked.write_text("Sensor data")
    monkeypatch.setattr(app, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ws_server, "reset_retriever", lambda: None)
    monkeypatch.setattr(ws_server, "get_session_manager", lambda: SimpleNamespace(reset_all=lambda: None))
    unlink = Path.unlink

    def remove(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("File is locked")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", remove)
    application = app.create_app()
    route = next(route for route in application.routes if getattr(route, "path", None) == "/api/corpus/reset")
    with pytest.raises(HTTPException) as exc:
        await route.endpoint()
    assert exc.value.status_code == 500
    assert "sensor.md" in exc.value.detail
    assert blocked.exists()


def test_probe_uses_selected_calibration(tmp_path, monkeypatch):
    import json
    from slrag.controller import probe
    (tmp_path / "probe_calibration.json").write_text(json.dumps({"tau_hi": 0.6}))
    monkeypatch.setenv("SLRAG_INDEX_DIR", str(tmp_path))
    probe.reset_probe_cache()
    try:
        assert probe._load_calibration() == {"tau_hi": 0.6}
    finally:
        probe.reset_probe_cache()


@pytest.mark.asyncio
async def test_upload_cannot_overwrite_permanent_document(tmp_path, monkeypatch):
    from io import BytesIO
    from fastapi import HTTPException, UploadFile
    from slrag.api import app
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    permanent = corpus / "examples.md"
    permanent.write_text("Permanent sensor reference")
    monkeypatch.setattr(app, "_PROJECT_ROOT", tmp_path)
    application = app.create_app()
    route = next(route for route in application.routes if getattr(route, "path", None) == "/api/corpus/upload")
    with pytest.raises(HTTPException) as exc:
        await route.endpoint(UploadFile(file=BytesIO(b"Replacement"), filename="EXAMPLES.md"))
    assert exc.value.status_code == 409
    assert permanent.read_text() == "Permanent sensor reference"


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["sensor_manual §calibration", "uploaded_manual §calibration"])
async def test_evaluation_worker_uses_only_test_documents(tmp_path, monkeypatch, citation):
    import importlib.util
    import json
    from slrag.ingest.indexer import HybridIndexer
    from slrag.api import ws_server
    spec = importlib.util.spec_from_file_location("evaluation_worker", Path(__file__).resolve().parents[1] / "scripts/run_test_suite.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    test_corpus = tmp_path / "test_corpus"
    test_corpus.mkdir()
    (test_corpus / "sensor_manual.md").write_text("# Calibration\nAdjust the sensor annually.")
    monkeypatch.setattr(worker, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("SLRAG_INDEX_DIR", str(tmp_path / "uploads_index"))
    monkeypatch.setenv("SLRAG_CORPUS_DIR", str(tmp_path / "uploads"))
    received = []

    def build(corpus, output_dir):
        from slrag.core.paths import index_dir, corpus_dir
        assert corpus == test_corpus == corpus_dir()
        assert index_dir() == Path(output_dir)
        assert index_dir() != tmp_path / "uploads_index"
        (Path(output_dir) / "chunks.jsonl").write_text(json.dumps({"citation_label": "sensor_manual §calibration"}), encoding="utf-8")

    async def chunk(session, data, socket):
        received.append(data["text"])

    async def end(session, socket):
        await socket.send_json({"type": "answer_version", "answer": "Adjust the sensor annually.", "citations": [citation]})

    monkeypatch.setattr(HybridIndexer, "run_pipeline", build)
    monkeypatch.setattr(ws_server, "_process_chunk", chunk)
    monkeypatch.setattr(ws_server, "_process_utterance_end", end)
    if citation.startswith("uploaded"):
        with pytest.raises(RuntimeError, match="citations outside test_corpus"):
            await worker.run_test_suite()
    else:
        results = await worker.run_test_suite()
        assert len(results) == 3
        assert all(result["citations"] == [citation] for result in results)
        assert "".join(received).startswith("I need the cancellation policy")
