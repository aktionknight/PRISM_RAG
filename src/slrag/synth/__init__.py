"""Component 4 — Session Refinement & Corpus Grounding (owner: Sivansh).

Entry point for the walking skeleton is ``SynthesisEngine`` (replaces
``stubs.fake_synthesize`` behind ``config/app.yaml: use_stub_synthesis``).
Imports are lazy so ``slrag.synth.<module>`` stays importable on its own.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "SynthesisEngine": "slrag.synth.engine",
    "SynthesisResult": "slrag.synth.engine",
    "TurnInput": "slrag.synth.engine",
    "ClaimGraph": "slrag.synth.claims",
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(f"module 'slrag.synth' has no attribute {name!r}")
    return getattr(import_module(_EXPORTS[name]), name)
