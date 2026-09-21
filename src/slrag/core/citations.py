"""Citation label resolver: ``ChunkID <-> "Doc_12 §2"`` (roadmap task 1.4).

Section identity is a primary key, not metadata (A_FINAL_ARCHITECTURE §3.1)::

    ChunkID       = f"{doc_id}#{section_id}#{ordinal}"   # internal
    CitationLabel = f"{doc_id} §{section_id}"            # emitted, e.g. "Doc_12 §2"

Kept outside ``core/schemas.py`` so the frozen contract file stays verbatim.
"""

from __future__ import annotations

import re
from typing import Iterable, NamedTuple

from slrag.core.schemas import RetrievedChunk

SECTION_SIGN = "§"

# Any bracketed span containing a section sign is treated as a citation marker,
# so malformed or fabricated markers ("[Doc 99 §1]", "[Source §2]") are caught
# by the validator too, not only well-formed ones.
CITATION_MARKER_RE = re.compile(r"\[([^\[\]]*?" + SECTION_SIGN + r"[^\[\]]*?)\]")
_LABEL_RE = re.compile(r"^\s*(?P<doc>[^\s§]+)\s*" + SECTION_SIGN + r"\s*(?P<section>[^\s§;,\]]+)\s*$")
_MARKER_SPLIT_RE = re.compile(r"\s*[;,]\s*")


class ChunkRef(NamedTuple):
    doc_id: str
    section_id: str
    ordinal: int


def make_chunk_id(doc_id: str, section_id: str, ordinal: int) -> str:
    return f"{doc_id}#{section_id}#{ordinal}"


def parse_chunk_id(chunk_id: str) -> ChunkRef:
    doc_id, section_id, ordinal = chunk_id.rsplit("#", 2)
    return ChunkRef(doc_id, section_id, int(ordinal))


def make_label(doc_id: str, section_id: str) -> str:
    return f"{doc_id} {SECTION_SIGN}{section_id}"


def parse_label(label: str) -> tuple[str, str]:
    """``"Doc_12 §2"`` -> ``("Doc_12", "2")``. Raises ValueError on malformed labels."""
    match = _LABEL_RE.match(label)
    if match is None:
        raise ValueError(f"malformed citation label: {label!r}")
    return match.group("doc"), match.group("section")


def normalize_label(label: str) -> str | None:
    """Canonical form of a label, or None if it cannot be parsed."""
    try:
        return make_label(*parse_label(label))
    except ValueError:
        return None


def label_for_chunk(chunk: RetrievedChunk) -> str:
    return make_label(chunk.doc_id, chunk.section_id)


def label_for_chunk_id(chunk_id: str) -> str:
    ref = parse_chunk_id(chunk_id)
    return make_label(ref.doc_id, ref.section_id)


def labels_for_chunks(chunks: Iterable[RetrievedChunk]) -> list[str]:
    """Ordered, de-duplicated citation labels for a set of chunks."""
    return list(dict.fromkeys(label_for_chunk(c) for c in chunks))


def format_marker(labels: Iterable[str]) -> str:
    """``["Doc_12 §2", "Doc_31 §4"]`` -> ``"[Doc_12 §2; Doc_31 §4]"``."""
    joined = "; ".join(labels)
    return f"[{joined}]" if joined else ""


def find_markers(text: str) -> list[tuple[str, list[str]]]:
    """Every citation marker in ``text`` as ``(raw_marker, [label, ...])``.

    Labels are returned as written (stripped); callers normalise/validate them.
    """
    found = []
    for match in CITATION_MARKER_RE.finditer(text):
        inner = match.group(1)
        labels = [part.strip() for part in _MARKER_SPLIT_RE.split(inner) if part.strip()]
        found.append((match.group(0), labels))
    return found
