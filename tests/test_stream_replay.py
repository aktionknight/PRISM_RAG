"""
tests/test_stream_replay.py — Unit tests for ReplaySource.

Component 5 & Stream Layer (Matangi).
"""

from pathlib import Path
import pytest

from slrag.core.schemas import TranscriptChunk
from slrag.stream.source_replay import ReplaySource


def test_replay_source_virtual_clock():
    golden_path = Path("bench/data/golden_example.jsonl")
    assert golden_path.exists(), "golden_example.jsonl fixture must exist"

    async def _run():
        source = ReplaySource(file_path=golden_path, real_time=False)
        chunks: list[TranscriptChunk] = []

        async for chunk in source.stream():
            assert isinstance(chunk, TranscriptChunk)
            assert isinstance(chunk.t_s, float)
            assert isinstance(chunk.text, str)
            chunks.append(chunk)

        assert len(chunks) == 4
        assert chunks[0].t_s == 0.0
        assert chunks[1].t_s == 0.8
        assert chunks[2].t_s == 1.6
        assert chunks[3].t_s == 2.1
        assert chunks[3].is_final is True

    import asyncio
    asyncio.run(_run())
