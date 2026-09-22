"""
ingest/loader.py — Document loader with section-structure extraction.

Loads markdown and text files from the corpus directory, extracting
heading-delimited sections that preserve document structure for the
section-bounded chunker.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DocumentSection:
    """A single section extracted from a corpus document."""
    doc_id: str
    section_id: str
    heading: str
    text: str


class MarkdownLoader:
    """Loads corpus documents and extracts section structure.

    Handles .md and .txt files. For markdown, sections are split on
    heading lines (# through ######). For plain text, numbered section
    patterns (e.g. "1. Introduction") are detected.
    """

    def __init__(self, corpus_dir: str | Path) -> None:
        self.corpus_dir = Path(corpus_dir)

    def load_all(self) -> list[DocumentSection]:
        """Load all documents from the corpus directory."""
        sections: list[DocumentSection] = []
        if not self.corpus_dir.exists():
            logger.warning(f"Corpus directory does not exist: {self.corpus_dir}")
            return sections

        for filepath in sorted(self.corpus_dir.glob("**/*.md")):
            logger.info(f"Loading {filepath.name}")
            sections.extend(self.load_file(filepath))

        for filepath in sorted(self.corpus_dir.glob("**/*.txt")):
            logger.info(f"Loading {filepath.name}")
            sections.extend(self.load_file(filepath))

        logger.info(f"Loaded {len(sections)} sections from {self.corpus_dir}")
        return sections

    def load_file(self, filepath: Path) -> list[DocumentSection]:
        """Load a single file and extract its sections."""
        doc_id = filepath.stem
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {filepath}: {e}")
            return []

        # Split by markdown headers (# through ######)
        pattern = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
        matches = list(pattern.finditer(content))

        sections: list[DocumentSection] = []

        if not matches:
            # Document has no headers — treat as one section
            text = content.strip()
            if text:
                sections.append(DocumentSection(
                    doc_id=doc_id,
                    section_id="1",
                    heading="",
                    text=text,
                ))
            return sections

        for i, match in enumerate(matches):
            heading = match.group(2).strip()

            # Extract section number from heading if present (e.g. "1. Introduction")
            num_match = re.match(r"^(\d+)", heading)
            if num_match:
                section_id = num_match.group(1)
            else:
                section_id = str(i + 1)

            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            text = content[start_pos:end_pos].strip()
            if text:
                sections.append(DocumentSection(
                    doc_id=doc_id,
                    section_id=section_id,
                    heading=heading,
                    text=text,
                ))

        return sections
