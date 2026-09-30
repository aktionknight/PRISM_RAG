"""Controller replay contracts and scoring argument forwarding, on unseen inputs."""
import argparse
import asyncio
from unittest.mock import AsyncMock

import pytest

from slrag.api.cli import cmd_score
from slrag.core.orchestrator import Orchestrator
from slrag.core.schemas import ControllerDecision, TranscriptChunk
from slrag.core.session import SessionState


@pytest.mark.parametrize("value", ["WAIT", "RETRIEVE", "NO_RETRIEVAL"])
def test_orchestrator_returns_serializable_decision(monkeypatch, value):
    expected = ControllerDecision(t_s=1, decision=value, reason="test", confidence=1)
    monkeypatch.setattr("slrag.core.orchestrator.RetrievalController.process_chunk", lambda *a: expected)
    orchestrator = Orchestrator(SessionState(session_id="unseen"))
    orchestrator.decomposer.decompose = AsyncMock(return_value=[])
    orchestrator.intent_set.add_intents = AsyncMock(return_value=[])
    actual = asyncio.run(orchestrator.process_chunk(TranscriptChunk(t_s=1, text="Explain polymer durability")))
    assert actual.model_dump() == expected.model_dump()
    assert orchestrator.decomposer.decompose.await_count == (value == "RETRIEVE")


def test_score_forwards_corpus(monkeypatch, tmp_path):
    paths = {key: tmp_path / f"{key}.jsonl" for key in ("run", "gold", "corpus")}
    for path in paths.values():
        path.write_text("", encoding="utf-8")
    received = []
    monkeypatch.setattr("bench.metrics.main", lambda argv: received.extend(argv) or 0)
    with pytest.raises(SystemExit) as result:
        cmd_score(argparse.Namespace(**{key: str(path) for key, path in paths.items()}))
    assert result.value.code == 0
    assert received == ["--run", str(paths["run"]), "--corpus", str(paths["corpus"]), "--gold", str(paths["gold"])]
