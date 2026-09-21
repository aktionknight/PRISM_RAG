"""Day-1 walking-skeleton stubs (C_TEAM_COORDINATION §3).

Every stage returns canned, schema-valid output so each owner can swap in real
logic behind ``config/app.yaml`` feature flags without blocking the others.
"""

from slrag.stubs.fake_controller import fake_controller
from slrag.stubs.fake_decomposer import fake_decompose
from slrag.stubs.fake_retriever import fake_retrieve
from slrag.stubs.fake_synthesis import fake_synthesize

__all__ = ["fake_controller", "fake_decompose", "fake_retrieve", "fake_synthesize"]
