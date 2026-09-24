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
    """Facet key -> facet spec (label / display, uncertainty_label, ...), display-only for Component 4.

    Prefers the taxonomy that Phase 0 facet discovery generated from the loaded corpus
    (``.index/facets.yaml``, a list of ``{facet_id, display, description, ...}``) over the
    example-derived fallback ``config/facets.yaml`` (AGENTS.md rule 3). Unknown facets are
    always fine: ``facet_label`` falls back to a readable form of the key.
    """
    if path is None:
        generated = REPO_ROOT / ".index" / "facets.yaml"
        path = generated if generated.exists() else config_dir() / "facets.yaml"
    facets = _load_yaml(Path(path)).get("facets", {}) or {}
    if isinstance(facets, list):   # Phase 0 output
        facets = {str(row["facet_id"]): dict(row) for row in facets if isinstance(row, dict) and row.get("facet_id")}
    return dict(facets)


def facet_label(facets: dict[str, dict[str, Any]], facet: str, *, key: str = "label") -> str:
    """Human label for a facet; unknown facets fall back to a readable form of the key."""
    spec = facets.get(facet, {})
    return spec.get(key) or spec.get("label") or spec.get("display") or facet.replace("_", " ").capitalize()
