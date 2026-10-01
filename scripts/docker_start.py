"""Build the mounted corpus index before replacing this process with the server.

Indexes are runtime corpus artifacts, never baked into the image (HC-2).
Rebuild on every container start so a persisted index cannot silently describe
different mounted documents. Startup errors prevent serving empty retrievals.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[1] / "corpus"
logger = logging.getLogger(__name__)


def run_indexer(corpus: Path) -> None:
    from slrag.ingest.indexer import HybridIndexer

    HybridIndexer.run_pipeline(corpus)


def prepare_index(corpus: Path) -> None:
    import faiss

    from slrag.ingest.indexer import HybridIndexer
    from slrag.ingest.loader import MarkdownLoader

    # The existing indexer returns without raising on an empty corpus. Detect
    # that first so stale artifacts cannot make an empty startup look successful.
    if not MarkdownLoader(corpus).load_all():
        raise RuntimeError(f"No indexable Markdown sections in mounted corpus: {corpus}")

    run_indexer(corpus)
    indexer = HybridIndexer()
    for path in (indexer.dense_path, indexer.metadata_path, indexer.chunks_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Index build did not produce required artifact: {path}")
    if not indexer.sparse_path.is_dir() or not any(indexer.sparse_path.iterdir()):
        raise RuntimeError(f"Index build did not produce BM25 artifacts: {indexer.sparse_path}")
    try:
        dense = faiss.read_index(str(indexer.dense_path))
    except Exception as exc:
        raise RuntimeError(f"Cannot load built FAISS index: {indexer.dense_path}") from exc
    if dense.ntotal == 0:
        raise RuntimeError(f"Built FAISS index contains no vectors: {indexer.dense_path}")


def main(command: list[str] | None = None) -> None:
    command = sys.argv[1:] if command is None else command
    if not command:
        raise RuntimeError("Container startup requires a server command")
    logging.basicConfig(level=logging.INFO)
    logger.info("Building retrieval indexes from mounted corpus: %s", CORPUS)
    prepare_index(CORPUS)
    logger.info("Retrieval indexes ready; starting %s", command[0])
    # The server becomes PID 1 and receives container shutdown signals directly.
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
