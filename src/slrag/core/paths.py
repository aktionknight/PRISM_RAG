"""Process-local corpus selection; evaluation workers never use upload artifacts."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def index_dir() -> Path:
    return Path(os.environ.get("SLRAG_INDEX_DIR", PROJECT_ROOT / ".index"))


def corpus_dir() -> Path:
    return Path(os.environ.get("SLRAG_CORPUS_DIR", PROJECT_ROOT / "corpus"))
