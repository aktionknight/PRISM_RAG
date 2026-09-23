"""Benchmark, scoring and ablation tools (roadmap §2 ``bench/``). Never imported by ``src/``."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT / "src", _ROOT):          # run as `python -m bench.<tool>` without an install
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
