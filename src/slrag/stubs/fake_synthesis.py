"""
stubs/fake_synthesis.py — Deterministic synthesis stub for Day 1 integration.

Returns a schema-valid AnswerOutput from fixture claims.
Swapped out when Sivansh's real synthesis engine is ready.
"""

from __future__ import annotations

from slrag.core.schemas import (
    AnswerOutput,
    Claim,
    ClaimStatus,
    RetrievalEvent,
    RetrievalTrigger,
    TelemetrySummary,
)


def fake_synthesize(
    session_id: str = "sess_stub",
    turn_id: int = 1,
) -> AnswerOutput:
    """Return a schema-valid stub answer matching golden example output."""
    claims = [
        Claim(
            claim_id="c1",
            facet="venue_capacity",
            text="Venue A holds up to 40 people with flexible seating, "
                 "supporting theatre-style (40), classroom (30), and boardroom (20) "
                 "configurations.",
            citations=["Doc_12 §2"],
            preconditions={},
            confidence=0.92,
            introduced_in_version=1,
            status=ClaimStatus.active,
        ),
        Claim(
            claim_id="c2",
            facet="cancellation_terms",
            text="Cancellations made more than 14 days before the event receive a full refund. "
                 "Cancellations between 7-14 days incur a 25% fee. "
                 "Cancellations within 7 days are non-refundable.",
            citations=["Doc_31 §4"],
            preconditions={},
            confidence=0.91,
            introduced_in_version=1,
            status=ClaimStatus.active,
        ),
        Claim(
            claim_id="c3",
            facet="catering_options",
            text="On-site catering packages start at ₹500 per head. "
                 "External caterers are permitted with prior approval and a ₹5,000 kitchen usage fee.",
            citations=["Doc_09 §1"],
            preconditions={},
            confidence=0.78,
            introduced_in_version=1,
            status=ClaimStatus.active,
        ),
    ]

    return AnswerOutput(
        retrieval_events=[
            RetrievalEvent(
                event_id="re1",
                timestamp_s=0.8,
                query="Pune workshop venue capacity 30",
                trigger=RetrievalTrigger.provisional,
                sub_intent_id="i1",
            ),
            RetrievalEvent(
                event_id="re2",
                timestamp_s=1.6,
                query="cancellation policy workshop venues Pune",
                trigger=RetrievalTrigger.multi_intent,
                sub_intent_id="i2",
            ),
            RetrievalEvent(
                event_id="re3",
                timestamp_s=1.6,
                query="catering service options workshop Pune",
                trigger=RetrievalTrigger.multi_intent,
                sub_intent_id="i3",
            ),
        ],
        sub_queries=[
            "venue capacity for 30 attendees in Pune",
            "cancellation terms and refund policies",
            "on-site and external catering options",
        ],
        answer=(
            "For a 30-person workshop in Pune, Venue A holds up to 40 people with flexible "
            "seating configurations including theatre-style (40), classroom (30), and boardroom (20) "
            "[Doc_12 §2]. "
            "Regarding cancellation terms, cancellations made more than 14 days before the event "
            "receive a full refund, 7-14 days incur a 25% fee, and within 7 days are non-refundable "
            "[Doc_31 §4]. "
            "On-site catering packages are available starting at ₹500 per head, and external "
            "caterers are permitted with prior approval and a ₹5,000 kitchen usage fee [Doc_09 §1]."
        ),
        citations=["Doc_12 §2", "Doc_31 §4", "Doc_09 §1"],
        uncertainty="Catering accommodation policies for Venue A could not be verified from the retrieved corpus.",
        session_id=session_id,
        turn_id=turn_id,
        answer_version=1,
        retrieval_required=True,
        claims=claims,
        telemetry=TelemetrySummary(
            latency_ms={"first_retrieval": 812.0, "first_token_after_end": 287.0},
            tokens={"prompt": 2914, "completion": 318},
            cost_usd=0.0041,
        ),
    )
