"""Run evaluation through the live pipeline in an isolated worker process."""
import asyncio
import json
import logging
import math
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


async def run_test_suite():
    corpus = PROJECT_ROOT / "test_corpus"
    if not corpus.is_dir() or not any(corpus.iterdir()):
        raise RuntimeError("test_corpus is missing or empty; no upload corpus fallback is allowed")

    # A fresh index per worker prevents stale evidence and leaves uploads untouched.
    with TemporaryDirectory(prefix="prism-test-index-") as output:
        os.environ["SLRAG_INDEX_DIR"] = output
        os.environ["SLRAG_CORPUS_DIR"] = str(corpus)
        from slrag.ingest.indexer import HybridIndexer
        from slrag.api.ws_server import SessionManager, _process_chunk, _process_utterance_end

        print("Indexing test_corpus only...", flush=True)
        await asyncio.to_thread(HybridIndexer.run_pipeline, corpus, output_dir=output)
        chunks_path = Path(output) / "chunks.jsonl"
        if not chunks_path.exists():
            raise RuntimeError("test_corpus produced no indexed chunks")
        allowed_labels = {
            json.loads(line)["citation_label"]
            for line in chunks_path.read_text(encoding="utf-8").splitlines() if line.strip()
        }

        class CaptureSocket:
            def __init__(self):
                self.messages = []

            async def send_json(self, data):
                self.messages.append(data)

        manager = SessionManager()
        session = manager.create()
        socket = CaptureSocket()
        examples = [
            ("I need the cancellation policy for workshop venues in Pune, and also the catering options.", "Multi-intent streaming"),
            ("Actually, make that for 50 people.", "Late-constraint refinement"),
            ("Can you shorten that and put it in bullet points?", "Presentation-only/no-retrieval"),
        ]
        results = []
        try:
            for text, name in examples:
                socket.messages.clear()
                print(f"\n--- Running Test: {name} ---\nUser: {text}", flush=True)
                words = text.split()
                chunk_size = max(3, math.ceil(len(words) / 4))
                for i, start in enumerate(range(0, len(words), chunk_size)):
                    await _process_chunk(session, {
                        "text": " ".join(words[start:start + chunk_size]) + " ", "t_s": i * 0.8,
                        "is_final": start + chunk_size >= len(words),
                    }, socket)
                await _process_utterance_end(session, socket)
                answers = [msg for msg in socket.messages if msg.get("type") == "answer_version"]
                if not answers:
                    raise RuntimeError(f"{name}: no final answer returned")
                answer = answers[-1]
                if not set(answer.get("citations", [])).issubset(allowed_labels):
                    raise RuntimeError(f"{name}: citations outside test_corpus")
                diagnostics = answer.get("llm_diagnostics", {})
                if diagnostics.get("error") or diagnostics.get("parse_errors"):
                    raise RuntimeError(f"{name}: generation failed: {diagnostics}")
                response = answer["answer"] or session.uncertainty
                if not response.strip():
                    raise RuntimeError(f"{name}: empty response; diagnostics={diagnostics}")
                print(f"System: {response}", flush=True)
                if session.uncertainty and answer["answer"]:
                    print(f"Uncertainty: {session.uncertainty}", flush=True)
                print(f"Citations: {answer.get('citations', [])}", flush=True)
                results.append({"name": name, "input": text, "output": response,
                                "uncertainty": session.uncertainty,
                                "citations": answer.get("citations", [])})
        finally:
            manager.reset_all()
        print("\n--- Test Suite Complete (test_corpus only) ---", flush=True)
        return results


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_test_suite())
