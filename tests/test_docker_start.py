"""Container startup must index mounted documents before starting the server."""

from types import SimpleNamespace

import faiss
import numpy as np
import pytest

from scripts import docker_start
from slrag.ingest import indexer


@pytest.fixture
def startup(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sensor.md").write_text("# Maintenance\nCalibrate the sensor annually.\n")
    paths = SimpleNamespace(
        sparse_path=tmp_path / ".index" / "bm25",
        dense_path=tmp_path / ".index" / "faiss",
        metadata_path=tmp_path / ".index" / "metadata.json",
        chunks_path=tmp_path / ".index" / "chunks.jsonl",
    )
    calls = []

    def build(corpus_dir):
        calls.append(corpus_dir)
        paths.sparse_path.mkdir(parents=True, exist_ok=True)
        (paths.sparse_path / "data.csc.index.npy").write_bytes(b"sparse data")
        dense = faiss.IndexFlatIP(2)
        dense.add(np.array([[1.0, 0.0]], dtype="float32"))
        faiss.write_index(dense, str(paths.dense_path))
        paths.metadata_path.write_text('{"sensor#1#0": "sensor section 1"}')
        paths.chunks_path.write_text('{"chunk_id": "sensor#1#0"}\n')

    monkeypatch.setattr(indexer, "HybridIndexer", lambda: paths)
    monkeypatch.setattr(docker_start, "run_indexer", build)
    return corpus, paths, calls


def test_fresh_start_builds_and_validates_faiss_before_exec(startup, monkeypatch):
    corpus, paths, calls = startup
    executed = []
    monkeypatch.setattr(docker_start, "CORPUS", corpus)
    monkeypatch.setattr(docker_start.os, "execvp", lambda name, args: executed.append((name, args)))
    docker_start.main(["uvicorn", "slrag.api.app:create_app", "--factory"])
    assert calls == [corpus]
    assert faiss.read_index(str(paths.dense_path)).ntotal == 1
    assert executed == [("uvicorn", ["uvicorn", "slrag.api.app:create_app", "--factory"])]


def test_restart_rebuilds_existing_index_for_current_mounted_corpus(startup):
    corpus, _, calls = startup
    docker_start.prepare_index(corpus)
    (corpus / "new.md").write_text("# Inspection\nInspect the assembly weekly.\n")
    docker_start.prepare_index(corpus)
    assert calls == [corpus, corpus]


def test_empty_corpus_cannot_reuse_stale_index(startup):
    corpus, _, calls = startup
    docker_start.prepare_index(corpus)
    (corpus / "sensor.md").unlink()
    with pytest.raises(RuntimeError, match="No indexable"):
        docker_start.prepare_index(corpus)
    assert calls == [corpus]


def test_indexing_failure_prevents_server_exec(startup, monkeypatch):
    corpus, _, _ = startup
    monkeypatch.setattr(docker_start, "CORPUS", corpus)
    executed = []
    monkeypatch.setattr(docker_start.os, "execvp", lambda *args: executed.append(args))

    def fail(_):
        raise RuntimeError("indexing failed")

    monkeypatch.setattr(docker_start, "run_indexer", fail)
    with pytest.raises(RuntimeError, match="indexing failed"):
        docker_start.main(["uvicorn"])
    assert not executed


@pytest.mark.parametrize("failure", ["missing", "empty", "corrupt"])
def test_invalid_faiss_blocks_startup(startup, monkeypatch, failure):
    corpus, paths, _ = startup
    build = docker_start.run_indexer

    def invalid_build(corpus_dir):
        build(corpus_dir)
        if failure == "missing":
            paths.dense_path.unlink()
        elif failure == "empty":
            faiss.write_index(faiss.IndexFlatIP(2), str(paths.dense_path))
        else:
            paths.dense_path.write_bytes(b"not a FAISS index")

    monkeypatch.setattr(docker_start, "run_indexer", invalid_build)
    with pytest.raises(RuntimeError):
        docker_start.prepare_index(corpus)
