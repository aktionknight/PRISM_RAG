"""
api/cli.py — CLI entry point for the Streaming Live RAG engine.

Component 5 & Integration Lead (Matangi).
Commands:
  slrag index     --corpus ./corpus --out ./.index
  slrag replay    --stream ./bench/data/golden_example.jsonl --out ./runs/events.jsonl
  slrag coverage  --run ./runs/events.jsonl
  slrag score     --run ./runs/events.jsonl --gold ./bench/data/gold.jsonl
  slrag serve     --host 0.0.0.0 --port 8000
  slrag chat      --corpus ./corpus
  slrag listen    --corpus ./corpus --asr faster-whisper
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys

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
    """Replay a JSONL stream through the engine and produce schema-valid events.jsonl."""
    from slrag.core.orchestrator import Orchestrator
    from slrag.core.session import SessionState
    from slrag.stream.source_replay import ReplaySource
    from slrag.telemetry.bus import TelemetryBus
    from slrag.telemetry.jsonl_sink import JSONLSink

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()  # Clean run

    logger.info(
        f"Replay mode: stream={args.stream}, out={args.out}, real_time={args.real_time}"
    )

    async def run_replay():
        bus = TelemetryBus()
        sink = JSONLSink(file_path=out_path)
        bus.subscribe(sink.write)
        otel_sink = None
        if args.otel:
            from slrag.telemetry.otel_sink import OpenTelemetrySink

            otel_sink = OpenTelemetrySink(
                enabled=True,
                configure_exporter=True,
                exporter_endpoint="http://localhost:4318/v1/traces",
            )
            bus.subscribe(otel_sink.handle_event)

        session = SessionState(session_id="sess_replay")
        orchestrator = Orchestrator(session=session, bus=bus)

        source = ReplaySource(
            file_path=args.stream,
            real_time=args.real_time,
            speed_factor=args.speed,
        )

        last_ts = 0.0
        async for chunk in source.stream():
            last_ts = chunk.t_s
            await orchestrator.process_chunk(chunk)

        # Finalize turn, synthesize, and record costs
        answer_output = await orchestrator.finalize_turn(last_ts=last_ts)
        sink.close()
        if otel_sink:
            otel_sink.close()

        logger.info(f"Replay complete! Output written to {out_path}")
        logger.info(f"Generated Answer Version: {answer_output.answer_version}")
        logger.info(f"Answer: {answer_output.answer[:120]}...")
        logger.info(f"Citations: {answer_output.citations}")
        logger.info(f"Total Telemetry Events Logged: {len(bus.get_events())}")

    asyncio.run(run_replay())


def cmd_coverage(args: argparse.Namespace) -> None:
    """Evaluate an events.jsonl file against the 6 trace-coverage invariants (Gate G6)."""
    from slrag.telemetry.coverage import (
        TraceCoverageSuite,
        load_indexed_citation_labels,
    )

    try:
        labels = load_indexed_citation_labels(args.index)
    except FileNotFoundError as exc:
        logger.error(str(exc))
        sys.exit(1)
    suite = TraceCoverageSuite(indexed_citation_labels=labels)
    report = suite.evaluate_file(args.run)
    print(report.summary())
    if not report.is_clean:
        sys.exit(1)
    print("\nGate G6 Passed: 100% Trace Coverage Invariant Compliance Verified.")


def cmd_score(args: argparse.Namespace) -> None:
    """Score an events.jsonl run against gold metrics."""
    run_path = Path(args.run)
    if not run_path.exists():
        logger.error(f"Run file not found: {run_path}")
        sys.exit(1)

    events = []
    with open(run_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line))

    # Calculate key metrics
    chunks = [e for e in events if e.get("event_type") == "chunk_received"]
    decisions = [e for e in events if e.get("event_type") == "controller_decision"]
    retrieve_decisions = [
        d for d in decisions if d.get("payload", {}).get("decision") == "RETRIEVE"
    ]
    retrievals = [e for e in events if e.get("event_type") == "retrieval_started"]
    costs = [e for e in events if e.get("event_type") == "cost_record"]
    total_cost = sum(c.get("payload", {}).get("cost_usd", 0.0) for c in costs)

    print("=== Streaming Live RAG — Run Evaluation Scorecard ===")
    print(f"Total Events: {len(events)}")
    print(f"Total Chunks: {len(chunks)}")
    print(f"Controller Decisions: {len(decisions)} ({len(retrieve_decisions)} RETRIEVE)")
    print(f"Retrieval Events: {len(retrievals)}")
    print(f"Total Cost USD: ${total_cost:.6f}")
    if chunks and retrieve_decisions:
        first_ret = retrieve_decisions[0].get("ts_stream_s", 0.0)
        final_chunk = chunks[-1].get("ts_stream_s", 0.0)
        lead_time = max(0.0, final_chunk - first_ret)
        print(f"Early Retrieval Triggered at: {first_ret:.2f}s (Lead Time: {lead_time:.2f}s before utterance end)")
    print("=====================================================")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI WebSocket server."""
    try:
        import uvicorn
        logger.info(f"Starting Live RAG WebSocket Server on {args.host}:{args.port}")
        uvicorn.run("slrag.api.ws_server:app", host=args.host, port=args.port, reload=False)
    except ImportError:
        logger.error("uvicorn is not installed. Run 'pip install uvicorn fastapi' to use serve mode.")
        sys.exit(1)


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive typed chat session."""
    logger.info("Chat mode interactive session (Day 2)")


def cmd_listen(args: argparse.Namespace) -> None:
    """Live mic demo mode."""
    logger.info("Listen mode not yet implemented (Day 3)")


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
    p_replay.add_argument("--stream", default="./bench/data/golden_example.jsonl", help="JSONL stream file")
    p_replay.add_argument("--out", default="./runs/events.jsonl")
    p_replay.add_argument("--real-time", action="store_true", help="Simulate real-time pacing")
    p_replay.add_argument("--speed", type=float, default=1.0, help="Replay speed factor")
    p_replay.add_argument("--otel", action="store_true", help="Enable OpenTelemetry export")
    p_replay.set_defaults(func=cmd_replay)

    # coverage
    p_cov = subparsers.add_parser("coverage", help="Assert trace coverage invariants (Gate G6)")
    p_cov.add_argument("--run", default="./runs/events.jsonl", help="Path to events.jsonl")
    p_cov.add_argument("--index", default="./.index", help="Built index directory")
    p_cov.set_defaults(func=cmd_coverage)

    # score
    p_score = subparsers.add_parser("score", help="Score a run against gold")
    p_score.add_argument("--run", default="./runs/events.jsonl")
    p_score.add_argument("--gold", default="./bench/data/golden_example.jsonl")
    p_score.set_defaults(func=cmd_score)

    # serve
    p_serve = subparsers.add_parser("serve", help="Launch live WebSocket & REST server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.set_defaults(func=cmd_serve)

    # chat
    p_chat = subparsers.add_parser("chat", help="Interactive chat session")
    p_chat.add_argument("--corpus", default="./corpus")
    p_chat.set_defaults(func=cmd_chat)

    # listen
    p_listen = subparsers.add_parser("listen", help="Live mic demo")
    p_listen.add_argument("--corpus", default="./corpus")
    p_listen.add_argument("--asr", default="faster-whisper")
    p_listen.set_defaults(func=cmd_listen)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
