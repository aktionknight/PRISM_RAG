"""Shared, deterministic lexical utilities for Component 4.

One tokeniser for the generator (relevance), the verifier (lexical entailment,
copy check) and the delta engine (pool-first resolution), so the three can
never disagree about what "the same word" means. Lexicons come from
``config/synth.yaml`` ``text:`` (HC-2).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?|[a-z]+(?:-[a-z]+)*")
_NUMERAL_RE = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
# Capitalised word, optionally followed by capitalised words or a single
# capital/digit designator ("Venue A", "Doc 12", "New Delhi").
_PROPER_RE = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+(?:[A-Z][a-zA-Z]+|[A-Z0-9]\b))*")


def stopwords_from(config: dict[str, Any] | None) -> frozenset[str]:
    return frozenset((config or {}).get("text", {}).get("stopwords", ()))


def _stem(token: str) -> str:
    if token[0].isdigit():
        return token.replace(",", "")
    if token.endswith("'s"):
        token = token[:-2]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    """Lower-cased, lightly stemmed tokens; numerals lose thousands separators."""
    return [_stem(tok) for tok in _TOKEN_RE.findall(text.lower())]


def content_tokens(text: str, stopwords: Iterable[str] = ()) -> list[str]:
    """Tokens minus stopwords and single letters (numerals always kept)."""
    stop = {_stem(s) for s in stopwords} | set(stopwords)
    return [t for t in tokenize(text) if (t[0].isdigit() or len(t) > 1) and t not in stop]


def overlap(a: Iterable[str], b: Iterable[str]) -> float:
    """|A ∩ B| / |A| over token sets — "how much of A is covered by B"."""
    set_a, set_b = set(a), set(b)
    return len(set_a & set_b) / len(set_a) if set_a else 0.0


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.split(text.strip()) if s.strip()]


def extract_numerals(text: str) -> list[str]:
    """Normalised numerals ("45,000" -> "45000", "25%" kept) in order of appearance."""
    return [m.replace(",", "") for m in _NUMERAL_RE.findall(text)]


def extract_proper_nouns(text: str) -> list[str]:
    """Capitalised spans, excluding a lone sentence-initial word (heuristic, no NER model)."""
    found: list[str] = []
    for sentence in split_sentences(text) or [text]:
        for match in _PROPER_RE.finditer(sentence):
            span = match.group(0)
            if match.start() == 0 and " " not in span:
                continue
            if span not in found:
                found.append(span)
    return found
