"""
api/cli.py — CLI entry point for the Streaming Live RAG engine.

Commands:
  slrag index   --corpus ./corpus --out ./.index
  slrag replay  --stream ./bench/data/golden_example.jsonl --out ./runs/events.jsonl
  slrag chat    --corpus ./corpus
  slrag listen  --corpus ./corpus --asr faster-whisper
  slrag score   --run ./runs/answers.jsonl --corpus ./runs/chunks.jsonl
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
    """Replay controller decisions; retrieval and synthesis are not implemented here."""
    import asyncio
    import json
    from slrag.core.schemas import TranscriptChunk
    from slrag.core.session import SessionState
    from slrag.core.orchestrator import Orchestrator

    logger.info(
        f"Replay mode: stream={args.stream}, corpus={args.corpus}, out={args.out}"
    )

    async def run_replay():
        session = SessionState(session_id="sess_replay")
        orchestrator = Orchestrator(session)
        events = []
        
        stream_path = Path(args.stream)
        if not stream_path.exists():
            logger.error(f"Stream file not found: {stream_path}")
            raise SystemExit(1)
            
        with open(stream_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                chunk = TranscriptChunk(**data)
                
                decision = await orchestrator.process_chunk(chunk)
                events.append(decision.model_dump())
        
        # Call synthesis at the end (omitted for now since stubs are removed)
        
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")
                
        logger.info(f"Replay output written to {out_path}")

    asyncio.run(run_replay())


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive typed chat session."""
    logger.info("Chat mode not yet implemented (Day 2)")


def cmd_listen(args: argparse.Namespace) -> None:
    """Live mic demo mode."""
    logger.info("Listen mode not yet implemented (Day 3)")


def _get_grafana_bin(grafana_dir: Path) -> Path | None:
    import shutil
    bin_dir = grafana_dir / "bin"
    candidates = [
        bin_dir / "grafana-server.exe",
        bin_dir / "grafana.exe",
        bin_dir / "grafana-server",
        bin_dir / "grafana",
    ]
    for c in candidates:
        if c.exists():
            return c
    which_path = shutil.which("grafana-server") or shutil.which("grafana")
    if which_path:
        return Path(which_path)
    return None


def _setup_grafana_config(grafana_dir: Path, port: int, repo_root: Path) -> tuple[Path, Path]:
    grafana_bin = _get_grafana_bin(grafana_dir)
    if not grafana_bin:
        raise FileNotFoundError(f"Could not find Grafana binary in {grafana_dir / 'bin'} or PATH")

    conf_dir = grafana_dir / "conf"
    conf_dir.mkdir(parents=True, exist_ok=True)
    custom_ini = conf_dir / "custom.ini"

    custom_ini_content = f"""# Local Grafana configuration for SLRAG
[security]
admin_user = admin
admin_password = slrag
allow_embedding = true
cookie_samesite = none

[auth.anonymous]
enabled = true
org_role = Viewer
org_name = Main Org.

[server]
http_port = {port}
protocol = http

[paths]
provisioning = conf/provisioning
"""
    custom_ini.write_text(custom_ini_content, encoding="utf-8")

    dashboards_provider = conf_dir / "provisioning" / "dashboards" / "dashboard.yml"
    if dashboards_provider.exists():
        infra_dashboards = (repo_root / "infra" / "grafana" / "dashboards").resolve()
        content = f"""apiVersion: 1

providers:
  - name: 'SLRAG Dashboards'
    orgId: 1
    folder: 'SLRAG'
    type: file
    disableDeletion: false
    editable: true
    options:
      path: {str(infra_dashboards)}
      foldersFromFilesStructure: false
"""
        dashboards_provider.write_text(content, encoding="utf-8")

    return grafana_bin, custom_ini


def cmd_grafana(args: argparse.Namespace) -> None:
    """Start local Grafana server with iframe embedding enabled."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[3]
    grafana_dir = Path(args.homepath).resolve() if args.homepath else (repo_root / "grafana-bin").resolve()

    if not grafana_dir.exists():
        logger.error(f"Grafana directory not found at: {grafana_dir}")
        sys.exit(1)

    try:
        grafana_bin, custom_ini = _setup_grafana_config(grafana_dir, args.port, repo_root)
    except FileNotFoundError as err:
        logger.error(str(err))
        sys.exit(1)

    cmd = [str(grafana_bin)]
    if grafana_bin.name in ("grafana.exe", "grafana"):
        cmd.append("server")
    cmd.extend([
        f"--homepath={grafana_dir}",
        f"--config={custom_ini}",
    ])

    logger.info(f"Starting local Grafana: {grafana_bin}")
    logger.info(f"Grafana UI: http://localhost:{args.port}/ (iframe embedding enabled)")
    logger.info(f"Dashboard:  http://localhost:{args.port}/d/slrag-main/slrag-streaming-live-rag?orgId=1&refresh=5s")

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        logger.info("Grafana server stopped.")


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the FastAPI server with WebSocket + UI."""
    import subprocess
    import uvicorn
    from slrag.api.app import create_app

    host = args.host
    port = args.port
    reload = args.reload
    with_grafana = getattr(args, "with_grafana", False)

    grafana_proc = None
    if with_grafana:
        repo_root = Path(__file__).resolve().parents[3]
        grafana_dir = (repo_root / "grafana-bin").resolve()
        if grafana_dir.exists():
            try:
                grafana_bin, custom_ini = _setup_grafana_config(grafana_dir, 3000, repo_root)
                cmd = [str(grafana_bin)]
                if grafana_bin.name in ("grafana.exe", "grafana"):
                    cmd.append("server")
                cmd.extend([f"--homepath={grafana_dir}", f"--config={custom_ini}"])
                logger.info("Starting local Grafana in background on http://localhost:3000")
                grafana_proc = subprocess.Popen(cmd)
            except Exception as e:
                logger.warning(f"Failed to launch background Grafana: {e}")

    logger.info(f"Starting SLRAG server on {host}:{port}")
    logger.info(f"Frontend UI: http://{host}:{port}/")
    logger.info(f"WebSocket:   ws://{host}:{port}/ws/session")
    logger.info(f"Metrics:     http://{host}:{port}/metrics")

    try:
        uvicorn.run(
            "slrag.api.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
            log_level="info",
        )
    finally:
        if grafana_proc:
            logger.info("Stopping background Grafana...")
            grafana_proc.terminate()
            try:
                grafana_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                grafana_proc.kill()


def cmd_score(args: argparse.Namespace) -> None:
    """Score a run against gold standard."""
    run_path = Path(args.run)
    corpus_path = Path(args.corpus)
    gold_path = Path(args.gold) if args.gold else None

    if not run_path.exists():
        logger.error(f"Run file not found: {run_path}")
        sys.exit(1)

    if not corpus_path.is_file():
        logger.error(f"Corpus chunks file not found: {corpus_path}")
        sys.exit(1)

    if gold_path is not None and not gold_path.exists():
        logger.error(f"Gold file not found: {gold_path}")
        sys.exit(1)

    logger.info(f"Scoring run={run_path} against gold={gold_path}")

    # Import bench.metrics dynamically since it's not in src/
    try:
        import sys as _sys
        bench_dir = Path(__file__).resolve().parents[3] / "bench"
        if str(bench_dir) not in _sys.path:
            _sys.path.insert(0, str(bench_dir.parent))

        from bench.metrics import main as bench_main  # type: ignore

        # Call the bench.metrics main function with appropriate args
        score_args = [
            "--run", str(run_path),
            "--corpus", str(corpus_path),
        ]
        if gold_path is not None:
            score_args.extend(["--gold", str(gold_path)])
        exit_code = bench_main(score_args)
        sys.exit(exit_code)
    except ImportError as e:
        logger.error(f"Could not import bench.metrics: {e}")
        sys.exit(1)


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
    p_replay = subparsers.add_parser("replay", help="Replay controller decisions (no answer synthesis)")
    p_replay.add_argument("--corpus", default="./corpus")
    p_replay.add_argument("--stream", required=True, help="JSONL stream file")
    p_replay.add_argument("--out", default="./runs/events.jsonl")
    p_replay.set_defaults(func=cmd_replay)

    # serve (NEW)
    p_serve = subparsers.add_parser("serve", help="Start the SLRAG server with UI")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind host")
    p_serve.add_argument("--port", type=int, default=8000, help="Bind port")
    p_serve.add_argument("--reload", action="store_true", help="Enable auto-reload")
    p_serve.add_argument("--with-grafana", action="store_true", help="Also start local Grafana in the background")
    p_serve.set_defaults(func=cmd_serve)

    # grafana (local standalone runner)
    p_grafana = subparsers.add_parser("grafana", help="Start local Grafana server with iframe embedding")
    p_grafana.add_argument("--port", type=int, default=3000, help="Grafana port (default: 3000)")
    p_grafana.add_argument("--homepath", default=None, help="Path to grafana-bin directory")
    p_grafana.set_defaults(func=cmd_grafana)

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
    p_score.add_argument("--corpus", required=True, help="Corpus chunks JSONL (RetrievedChunk rows)")
    p_score.add_argument("--gold", help="Optional gold JSONL")
    p_score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
