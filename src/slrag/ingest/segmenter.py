"""
ingest/segmenter.py — Structure-Agnostic Segmenter (Doc D §3.1).

Implements a 5-detector cascade that produces candidate topic units from
any corpus format.  Each detector is tried in order; the first to produce
≥ MIN_CANDIDATES results wins.

Detector A — Native document outline / bookmarks (PDF TOC, DOCX headings)
Detector B — Numbered / lettered section patterns
Detector C — Typographic heading heuristic (short title-cased lines)
Detector D — Markdown headings
Detector E — FALLBACK: sliding window (~500 tokens, 50% overlap)

The segmenter is used ONLY for Phase 0 facet discovery — the existing
``MarkdownLoader`` remains the primary loader for the chunk-ingest pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional heavy dependencies — graceful fallback if missing
try:
    import pdfplumber  # type: ignore[import-untyped]

    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import docx as python_docx  # type: ignore[import-untyped]

    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False


MIN_CANDIDATES = 3  # Minimum candidates for a detector to "win"
SLIDING_WINDOW_TOKENS = 500
SLIDING_WINDOW_OVERLAP = 0.50


# ─────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CandidateUnit:
    """A single candidate topic unit produced by the segmenter."""
    text: str
    source_doc: str
    source_detector: str  # "A", "B", "C", "D", or "E"
    unit_index: int


# ─────────────────────────────────────────────────────────────────────
# Individual detectors
# ─────────────────────────────────────────────────────────────────────

def _approx_token_count(text: str) -> int:
    """Approximate token count (~1.33 tokens per whitespace-delimited word)."""
    return max(1, int(len(text.split()) * 1.33))


def _split_by_positions(
    content: str,
    positions: list[tuple[int, int, str]],
    doc_id: str,
    detector: str,
) -> list[CandidateUnit]:
    """Split *content* into CandidateUnits at the given (start, end, heading) positions."""
    units: list[CandidateUnit] = []
    for i, (start, end, heading) in enumerate(positions):
        # Body runs from end-of-heading-line to next heading (or EOF)
        body_start = end
        body_end = positions[i + 1][0] if i + 1 < len(positions) else len(content)
        body = content[body_start:body_end].strip()
        text = f"{heading}\n{body}" if heading else body
        if text.strip():
            units.append(CandidateUnit(
                text=text.strip(),
                source_doc=doc_id,
                source_detector=detector,
                unit_index=i,
            ))
    return units


# ── Detector A: native document outline / bookmarks ─────────────────

def _detect_pdf_toc(filepath: Path, doc_id: str) -> list[CandidateUnit]:
    """Extract sections from PDF bookmarks / TOC via pdfplumber."""
    if not HAS_PDFPLUMBER:
        return []
    try:
        with pdfplumber.open(str(filepath)) as pdf:
            # Collect full text per page for positional slicing
            full_text = "\n".join(
                page.extract_text() or "" for page in pdf.pages
            )
            if not full_text.strip():
                return []

            # pdfplumber doesn't expose bookmarks directly on all PDFs,
            # but we can check outline if the PDF reader supports it.
            # Fallback: look for page-level headings in metadata.
            # For robustness we rely on Detector B/C for PDFs without
            # native outline support.
            return []  # Bookmarks are unreliable; let B/C handle PDFs
    except Exception as exc:
        logger.debug(f"Detector A (PDF TOC): failed on {filepath}: {exc}")
        return []


def _detect_docx_headings(filepath: Path, doc_id: str) -> list[CandidateUnit]:
    """Extract sections from DOCX heading styles via python-docx."""
    if not HAS_PYTHON_DOCX:
        return []
    try:
        document = python_docx.Document(str(filepath))
        units: list[CandidateUnit] = []
        current_heading: Optional[str] = None
        current_body: list[str] = []
        idx = 0

        for para in document.paragraphs:
            style_name = (para.style.name or "").lower()
            if style_name.startswith("heading"):
                # Flush previous section
                if current_heading is not None and current_body:
                    text = f"{current_heading}\n" + "\n".join(current_body)
                    units.append(CandidateUnit(
                        text=text.strip(),
                        source_doc=doc_id,
                        source_detector="A",
                        unit_index=idx,
                    ))
                    idx += 1
                current_heading = para.text.strip()
                current_body = []
            else:
                if para.text.strip():
                    current_body.append(para.text.strip())

        # Flush last section
        if current_heading and current_body:
            text = f"{current_heading}\n" + "\n".join(current_body)
            units.append(CandidateUnit(
                text=text.strip(),
                source_doc=doc_id,
                source_detector="A",
                unit_index=idx,
            ))

        return units
    except Exception as exc:
        logger.debug(f"Detector A (DOCX headings): failed on {filepath}: {exc}")
        return []


def _detector_a(filepath: Path, content: str, doc_id: str) -> list[CandidateUnit]:
    """Detector A — Native document outline / bookmarks."""
    suffix = filepath.suffix.lower()
    if suffix == ".pdf":
        return _detect_pdf_toc(filepath, doc_id)
    elif suffix == ".docx":
        return _detect_docx_headings(filepath, doc_id)
    return []


# ── Detector B: numbered / lettered section patterns ─────────────────

_NUMBERED_PATTERN = re.compile(
    r"^(?:(?:\d+\.)\s|(?:[A-Z]\.)\s|(?:§\s*\d)|(?:Section\s+\d+))",
    re.MULTILINE,
)


def _detector_b(filepath: Path, content: str, doc_id: str) -> list[CandidateUnit]:
    """Detector B — Numbered / lettered section patterns."""
    matches = list(_NUMBERED_PATTERN.finditer(content))
    if len(matches) < MIN_CANDIDATES:
        return []

    positions: list[tuple[int, int, str]] = []
    lines = content.split("\n")
    # For each match, find the line it's on and its extent
    for m in matches:
        line_start = content.rfind("\n", 0, m.start()) + 1
        line_end = content.find("\n", m.start())
        if line_end == -1:
            line_end = len(content)
        heading = content[line_start:line_end].strip()
        positions.append((line_start, line_end, heading))

    return _split_by_positions(content, positions, doc_id, "B")


# ── Detector C: typographic heading heuristic ────────────────────────

_SENTENCE_ENDING = re.compile(r"[.!?;:]\s*$")


def _detector_c(filepath: Path, content: str, doc_id: str) -> list[CandidateUnit]:
    """Detector C — Typographic heading heuristic.

    A candidate heading line is short (<12 words), title-cased or
    all-uppercase, not ending in sentence punctuation, and followed
    by a longer paragraph.
    """
    lines = content.split("\n")
    heading_indices: list[int] = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        words = stripped.split()
        if len(words) >= 12:
            continue  # Too long to be a heading

        # Must not end in sentence punctuation
        if _SENTENCE_ENDING.search(stripped):
            continue

        # Must be title-cased or all-caps
        is_title = stripped.istitle() or stripped == stripped.upper()
        if not is_title:
            continue

        # Must be followed by a longer paragraph (within next 3 non-empty lines)
        has_body = False
        for j in range(i + 1, min(i + 4, len(lines))):
            next_line = lines[j].strip()
            if next_line and len(next_line.split()) > len(words):
                has_body = True
                break
        if has_body:
            heading_indices.append(i)

    if len(heading_indices) < MIN_CANDIDATES:
        return []

    # Convert line indices to character positions
    positions: list[tuple[int, int, str]] = []
    char_pos = 0
    line_starts: list[int] = []
    for line in lines:
        line_starts.append(char_pos)
        char_pos += len(line) + 1  # +1 for newline

    for li in heading_indices:
        start = line_starts[li]
        end = start + len(lines[li])
        heading = lines[li].strip()
        positions.append((start, end, heading))

    return _split_by_positions(content, positions, doc_id, "C")


# ── Detector D: Markdown headings ────────────────────────────────────

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)


def _detector_d(filepath: Path, content: str, doc_id: str) -> list[CandidateUnit]:
    """Detector D — Markdown headings (``#``, ``##``, ``###``, etc.)."""
    matches = list(_MD_HEADING.finditer(content))
    if len(matches) < MIN_CANDIDATES:
        return []

    positions: list[tuple[int, int, str]] = []
    for m in matches:
        heading = m.group(2).strip()
        positions.append((m.start(), m.end(), heading))

    return _split_by_positions(content, positions, doc_id, "D")


# ── Detector E: fallback sliding window ──────────────────────────────

def _detector_e(filepath: Path, content: str, doc_id: str) -> list[CandidateUnit]:
    """Detector E — Fallback sliding window (~500 tokens, 50% overlap).

    Guarantees the pipeline never has zero input, even on a single
    wall of unstructured text.
    """
    words = content.split()
    if not words:
        return []

    # Convert token target to approximate word count
    words_per_window = int(SLIDING_WINDOW_TOKENS / 1.33)
    overlap_words = int(words_per_window * SLIDING_WINDOW_OVERLAP)
    stride = max(1, words_per_window - overlap_words)

    units: list[CandidateUnit] = []
    idx = 0
    start = 0

    while start < len(words):
        end = min(start + words_per_window, len(words))
        window_text = " ".join(words[start:end])
        if window_text.strip():
            units.append(CandidateUnit(
                text=window_text.strip(),
                source_doc=doc_id,
                source_detector="E",
                unit_index=idx,
            ))
            idx += 1
        if end >= len(words):
            break
        start += stride

    return units


# ─────────────────────────────────────────────────────────────────────
# Main segmenter class
# ─────────────────────────────────────────────────────────────────────

# Ordered cascade of detectors
_DETECTORS: list[tuple[str, callable]] = [
    ("A", _detector_a),
    ("B", _detector_b),
    ("C", _detector_c),
    ("D", _detector_d),
    ("E", _detector_e),
]

_SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


class StructureAgnosticSegmenter:
    """Structure-agnostic corpus segmenter for Phase 0 Facet Discovery.

    Runs a deterministic 5-detector cascade across all files in a corpus
    directory.  The first detector to produce ≥ ``MIN_CANDIDATES`` results
    for a file wins.  If none of A–D fire, Detector E (sliding window)
    guarantees non-empty output.

    The segmenter is used **only** during offline facet discovery — never
    at runtime.
    """

    def segment(self, corpus_dir: Path) -> tuple[list[CandidateUnit], str]:
        """Segment all documents in *corpus_dir* into candidate topic units.

        Args:
            corpus_dir: Path to the corpus directory.

        Returns:
            A tuple of ``(candidate_units, detector_used)`` where
            *detector_used* is the letter of the first detector that
            produced enough candidates across the corpus ("A"–"E").
        """
        corpus_dir = Path(corpus_dir)
        if not corpus_dir.exists():
            logger.warning(f"Corpus directory does not exist: {corpus_dir}")
            return [], "E"

        # Collect all supported files in sorted order (deterministic)
        files = sorted(
            f for f in corpus_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in _SUPPORTED_EXTENSIONS
        )

        if not files:
            logger.warning(f"No supported files found in {corpus_dir}")
            return [], "E"

        logger.info(
            f"Segmenter: found {len(files)} file(s) in {corpus_dir}"
        )

        # Try each detector in cascade order across ALL files
        for detector_letter, detector_fn in _DETECTORS:
            all_units: list[CandidateUnit] = []
            global_idx = 0

            for filepath in files:
                doc_id = filepath.stem

                # Read content for text-based detectors
                content = ""
                if filepath.suffix.lower() in {".md", ".txt"}:
                    try:
                        content = filepath.read_text(encoding="utf-8")
                    except Exception as exc:
                        logger.warning(f"Failed to read {filepath}: {exc}")
                        continue
                elif filepath.suffix.lower() == ".pdf" and HAS_PDFPLUMBER:
                    try:
                        with pdfplumber.open(str(filepath)) as pdf:
                            content = "\n".join(
                                page.extract_text() or "" for page in pdf.pages
                            )
                    except Exception as exc:
                        logger.warning(f"Failed to read PDF {filepath}: {exc}")
                        continue
                elif filepath.suffix.lower() == ".docx" and HAS_PYTHON_DOCX:
                    # Detector A handles DOCX natively; for others pass text
                    try:
                        document = python_docx.Document(str(filepath))
                        content = "\n".join(
                            p.text for p in document.paragraphs
                        )
                    except Exception as exc:
                        logger.warning(f"Failed to read DOCX {filepath}: {exc}")
                        continue
                elif filepath.suffix.lower() in {".pdf", ".docx"}:
                    # Missing optional dependency — skip this file for this detector
                    continue

                units = detector_fn(filepath, content, doc_id)

                # Re-number unit_index globally
                for unit in units:
                    unit.unit_index = global_idx
                    global_idx += 1

                all_units.extend(units)

            if len(all_units) >= MIN_CANDIDATES:
                logger.info(
                    f"Segmenter: Detector {detector_letter} produced "
                    f"{len(all_units)} candidate unit(s)"
                )
                return all_units, detector_letter

        # Should never reach here — Detector E always produces output
        # for non-empty files.  Defensive fallback.
        logger.warning("Segmenter: no detector produced enough candidates")
        return [], "E"
