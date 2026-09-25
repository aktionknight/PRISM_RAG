"""
stubs/fake_decomposer.py — Deterministic decomposer stub for Day 1 integration.

Returns all applicable sub-intents for the current prefix. Deduplication
is handled by IntentSet in the caller (ws_server), NOT by this stub.

The stub always returns all intents matching the current prefix — it is
the IntentSet that decides which are genuinely novel (S-2 monotonic
diffing). This matches the design in 02_SOLUTION_DESIGN §C2: decompose
the *full prefix*, then diff against the IntentSet.
"""

from __future__ import annotations

from slrag.core.schemas import IntentStatus, SubIntent


def fake_decompose(prefix: str, existing_intents: dict[str, SubIntent] | None = None) -> list[SubIntent]:
    """Deterministic stub returning all applicable sub-intents for the prefix.

    Design pattern (02_SOLUTION_DESIGN §C2):
    - Decompose the current full prefix (not just new chunk)
    - Return ALL candidate intents (dedup is done by IntentSet in caller)
    
    At 0.8s (short prefix) → returns [venue_capacity]
    At 1.6s (longer prefix) → returns [venue_capacity, cancellation_terms, catering_options]
    
    The IntentSet diff will detect that venue_capacity already exists and
    only dispatch retrieval for the 2 new intents.
    """
    intents = []

    # Always emit venue_capacity as a candidate (IntentSet handles dedup)
    intents.append(SubIntent(
        intent_id="stub_i1",
        facet="venue_capacity",
        query_nl="venue capacity for 30 attendees",
        search_string="workshop venue capacity 30",
        novel=True,
        first_seen_ts=0.8,
        status=IntentStatus.pending,
    ))

    # If prefix mentions cancellation or is long enough to contain it
    if "cancellation" in prefix.lower() or "cancel" in prefix.lower() or len(prefix) > 60:
        intents.append(SubIntent(
            intent_id="stub_i2",
            facet="cancellation_terms",
            query_nl="cancellation terms and refund policies for workshop venues",
            search_string="cancellation policy workshop venues",
            novel=True,
            first_seen_ts=1.6,
            status=IntentStatus.pending,
        ))

    # If prefix mentions catering or is long enough to contain it
    if "catering" in prefix.lower() or "cater" in prefix.lower() or len(prefix) > 80:
        intents.append(SubIntent(
            intent_id="stub_i3",
            facet="catering_options",
            query_nl="on-site and external catering options for workshop venues",
            search_string="catering service options workshop",
            novel=True,
            first_seen_ts=1.6,
            status=IntentStatus.pending,
        ))

    return intents


def reset_stub() -> None:
    """Reset stub state between sessions (no-op — stub is now stateless)."""
    pass
