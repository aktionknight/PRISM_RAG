"""Decomposition exports; load model-dependent modules only when requested."""
from importlib import import_module

_EXPORTS = {"Decomposer": "decomposer", "FacetTagger": "facets",
            "IntentSet": "intent_set", "OverlapMerger": "overlap"}
__all__ = list(_EXPORTS)

def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    return getattr(import_module(f"slrag.decompose.{_EXPORTS[name]}"), name)
