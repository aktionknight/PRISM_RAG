"""Config loading for Component 4 (``config/synth.yaml`` + ``config/facets.yaml``).

Set ``SLRAG_CONFIG_DIR`` to point at an alternative config directory (ablations, tests).
Loaders return fresh dicts on every call so callers can never mutate shared state.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    return Path(os.environ.get("SLRAG_CONFIG_DIR", REPO_ROOT / "config"))


def resolve_path(path: str | Path) -> Path:
    """Resolve a config-relative path (e.g. ``config/prompts``) against the repo root."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_synth_config(path: str | Path | None = None) -> dict[str, Any]:
    return _load_yaml(Path(path) if path else config_dir() / "synth.yaml")


def load_facets(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Facet key -> facet spec (label, uncertainty_label, keywords, constraint_slots, ...)."""
    data = _load_yaml(Path(path) if path else config_dir() / "facets.yaml")
    return dict(data.get("facets", {}))


def facet_label(facets: dict[str, dict[str, Any]], facet: str, *, key: str = "label") -> str:
    """Human label for a facet; unknown facets fall back to a readable form of the key."""
    spec = facets.get(facet, {})
    return spec.get(key) or spec.get("label") or facet.replace("_", " ").capitalize()
