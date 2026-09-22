"""
retrieve/density.py — Factual density scorer.

Scores chunks by their factual information density:
  density = count(numerals, dates, currency, durations,
                  modal obligations, named entities) / token_count

Higher density → the chunk *asserts* things rather than *describes* them,
which measurably raises citation support rate.
"""

from __future__ import annotations

import re


# ── Regex patterns for factual markers ──
_RE_NUMERALS = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")
_RE_CURRENCY = re.compile(
    r"(?:[$€£₹¥])\s*\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:USD|EUR|GBP|INR|JPY)\b",
    re.IGNORECASE,
)
_RE_DATES = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
    r"|\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{2,4}\b",
    re.IGNORECASE,
)
_RE_DURATIONS = re.compile(
    r"\b\d+\s*(?:day|week|month|year|hour|minute|second)s?\b",
    re.IGNORECASE,
)
_RE_PERCENTAGES = re.compile(r"\b\d+(?:\.\d+)?%")
_RE_MODALS = re.compile(
    r"\b(?:must|shall|will|should|required|mandatory|prohibited|permitted)\b",
    re.IGNORECASE,
)
# Capitalized multi-word runs that look like named entities
# (rough heuristic — good enough for density scoring)
_RE_NAMED_ENTITIES = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")


def score_factual_density(text: str) -> float:
    """Score a chunk's factual information density.

    Args:
        text: Chunk text to score.

    Returns:
        Float in [0, 1+] — ratio of factual markers to word tokens.
        Higher means the chunk is more assertion-rich.
    """
    tokens = text.split()
    if not tokens:
        return 0.0

    word_count = len(tokens)

    # Count all factual markers
    count = 0
    count += len(_RE_NUMERALS.findall(text))
    count += len(_RE_CURRENCY.findall(text))
    count += len(_RE_DATES.findall(text))
    count += len(_RE_DURATIONS.findall(text))
    count += len(_RE_PERCENTAGES.findall(text))
    count += len(_RE_MODALS.findall(text))
    count += len(_RE_NAMED_ENTITIES.findall(text))

    return count / word_count
