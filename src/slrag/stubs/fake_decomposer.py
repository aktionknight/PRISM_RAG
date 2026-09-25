"""
stubs/fake_decomposer.py — Deterministic decomposer stub for Day 1 integration.

Returns the golden example's three sub-intents.
Swapped out when Aakrit's real decomposer is ready.
"""

from __future__ import annotations

from slrag.core.schemas import IntentStatus, SubIntent


_SEEN_INTENTS: dict[str, SubIntent] = {}


def fake_decompose(prefix: str, existing_intents: dict[str, SubIntent] | None = None) -> list[SubIntent]:
    """Deterministic stub returning golden example sub-intents.

    Simulates monotonic intent set behavior:
    - Short prefix → 1 intent (venue_capacity)
    - Medium prefix → 2 new intents (cancellation_terms, catering_options)
    """
    global _SEEN_INTENTS

    seen = existing_intents if existing_intents is not None else _SEEN_INTENTS
    seen_facets = {intent.facet for intent in seen.values()}

    intents = []

    # Always emit venue_capacity if not already present
    if "i1" not in seen and "venue_capacity" not in seen_facets:
        i1 = SubIntent(
            intent_id="i1",
            facet="venue_capacity",
            query_nl="venue capacity for 30 attendees in Pune",
            search_string="Pune workshop venue capacity 30",
            novel=True,
            first_seen_ts=0.8,
            status=IntentStatus.dispatched,
        )
        if existing_intents is None:
            _SEEN_INTENTS["i1"] = i1
        intents.append(i1)

    # If prefix mentions cancellation or catering, add those
    if "cancellation" in prefix.lower() or len(prefix) > 60:
        if "i2" not in seen and "cancellation_terms" not in seen_facets:
            i2 = SubIntent(
                intent_id="i2",
                facet="cancellation_terms",
                query_nl="cancellation terms and refund policies for workshop venues in Pune",
                search_string="cancellation policy workshop venues Pune",
                novel=True,
                first_seen_ts=1.6,
                status=IntentStatus.dispatched,
            )
            if existing_intents is None:
                _SEEN_INTENTS["i2"] = i2
            intents.append(i2)

    if "catering" in prefix.lower() or len(prefix) > 80:
        if "i3" not in seen and "catering_options" not in seen_facets:
            i3 = SubIntent(
                intent_id="i3",
                facet="catering_options",
                query_nl="on-site and external catering options for workshop venues in Pune",
                search_string="catering service options workshop Pune",
                novel=True,
                first_seen_ts=1.6,
                status=IntentStatus.dispatched,
            )
            if existing_intents is None:
                _SEEN_INTENTS["i3"] = i3
            intents.append(i3)

    return intents


def reset_stub() -> None:
    """Reset stub state between sessions."""
    global _SEEN_INTENTS
    _SEEN_INTENTS = {}
