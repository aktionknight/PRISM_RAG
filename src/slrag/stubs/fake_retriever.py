"""
stubs/fake_retriever.py — Deterministic retriever stub for Day 1 integration.

Returns fixture chunks matching the golden example's expected citations.
Swapped out when Aakrit's real retriever is ready.
"""

from __future__ import annotations

from slrag.core.schemas import RetrievedChunk, SubIntent


# Canned chunks matching golden example expectations
_FIXTURE_CHUNKS: dict[str, list[RetrievedChunk]] = {
    "venue_capacity": [
        RetrievedChunk(
            chunk_id="Doc_12#2#0",
            doc_id="Doc_12",
            section_id="2",
            text="Venue A holds up to 40 people with flexible seating arrangements. "
                 "The main conference room supports theatre-style (40), classroom (30), "
                 "and boardroom (20) configurations.",
            score=0.92,
            citation_label="Doc_12 §2",
        ),
        RetrievedChunk(
            chunk_id="Doc_12#2#1",
            doc_id="Doc_12",
            section_id="2",
            text="Venue B accommodates up to 60 attendees across two connected halls. "
                 "A partition wall can divide the space for parallel sessions.",
            score=0.85,
            citation_label="Doc_12 §2",
        ),
    ],
    "cancellation_terms": [
        RetrievedChunk(
            chunk_id="Doc_31#4#0",
            doc_id="Doc_31",
            section_id="4",
            text="Cancellations made more than 14 days before the event receive a full refund. "
                 "Cancellations between 7-14 days incur a 25% fee. "
                 "Cancellations within 7 days are non-refundable.",
            score=0.91,
            citation_label="Doc_31 §4",
        ),
    ],
    "catering_options": [
        RetrievedChunk(
            chunk_id="Doc_09#1#0",
            doc_id="Doc_09",
            section_id="1",
            text="On-site catering packages are available starting at ₹500 per head. "
                 "External caterers are permitted with prior approval and a ₹5,000 "
                 "kitchen usage fee.",
            score=0.78,
            citation_label="Doc_09 §1",
        ),
    ],
}


def fake_retrieve(sub_intent: SubIntent) -> list[RetrievedChunk]:
    """Return canned chunks for the given sub-intent's facet."""
    return _FIXTURE_CHUNKS.get(sub_intent.facet, [])
