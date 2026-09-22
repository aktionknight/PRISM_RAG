"""Decomposition pipeline — intent set, decomposer, overlap merge, facets."""

from .decomposer import Decomposer
from .facets import FacetTagger
from .intent_set import IntentSet
from .overlap import OverlapMerger

__all__ = ["Decomposer", "FacetTagger", "IntentSet", "OverlapMerger"]
