"""
api/cli.py — CLI entry point for the Streaming Live RAG engine.

Commands:
  slrag index   --corpus ./corpus --out ./.index
  slrag replay  --corpus ./corpus --stream ./bench/data/suite.jsonl --out ./runs/events.jsonl
  slrag chat    --corpus ./corpus
  slrag listen  --corpus ./corpus --asr faster-whisper
  slrag score   --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_index(args: argparse.Namespace) -> None:
    """Build the hybrid index from the corpus."""
    from slrag.ingest.indexer import HybridIndexer

    corpus_dir = Path(args.corpus)
    if not corpus_dir.exists():
        logger.error(f"Corpus directory not found: {corpus_dir}")
        sys.exit(1)

    HybridIndexer.run_pipeline(corpus_dir)
    logger.info("Index build complete.")


def cmd_replay(args: argparse.Namespace) -> None:
    """Replay a JSONL stream against the engine and produce events.jsonl."""
    # TODO: Wire up full pipeline replay (Day 2)
    logger.info(
        f"Replay mode: stream={args.stream}, corpus={args.corpus}, out={args.out}"
    )
    logger.warning("Full replay not yet implemented — run golden stub replay instead")

    # For now, run the stub pipeline to produce schema-valid output
    from slrag.stubs.fake_synthesis import fake_synthesize

    output = fake_synthesize(session_id="sess_replay", turn_id=1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output.model_dump_json(indent=2))

    logger.info(f"Stub replay output written to {out_path}")


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive typed chat session."""
    logger.info("Chat mode not yet implemented (Day 2)")


def cmd_listen(args: argparse.Namespace) -> None:
    """Live mic demo mode."""
    logger.info("Listen mode not yet implemented (Day 3)")


def cmd_score(args: argparse.Namespace) -> None:
    """Score a run against gold labels."""
    logger.info("Scoring not yet implemented (Day 2)")


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="slrag",
        description="Streaming Live RAG — Samsung Theme 4",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # index
    p_index = subparsers.add_parser("index", help="Build hybrid index from corpus")
    p_index.add_argument("--corpus", default="./corpus", help="Path to corpus directory")
    p_index.add_argument("--out", default="./.index", help="Output index directory")
    p_index.set_defaults(func=cmd_index)

    # replay
    p_replay = subparsers.add_parser("replay", help="Replay a JSONL stream")
    p_replay.add_argument("--corpus", default="./corpus")
    p_replay.add_argument("--stream", required=True, help="JSONL stream file")
    p_replay.add_argument("--out", default="./runs/events.jsonl")
    p_replay.set_defaults(func=cmd_replay)

    # chat
    p_chat = subparsers.add_parser("chat", help="Interactive chat session")
    p_chat.add_argument("--corpus", default="./corpus")
    p_chat.set_defaults(func=cmd_chat)

    # listen
    p_listen = subparsers.add_parser("listen", help="Live mic demo")
    p_listen.add_argument("--corpus", default="./corpus")
    p_listen.add_argument("--asr", default="faster-whisper")
    p_listen.set_defaults(func=cmd_listen)

    # score
    p_score = subparsers.add_parser("score", help="Score a run against gold")
    p_score.add_argument("--run", required=True)
    p_score.add_argument("--gold", required=True)
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
