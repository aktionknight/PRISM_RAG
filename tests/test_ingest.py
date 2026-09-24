"""
tests/test_ingest.py — Tests for the ingest pipeline (loader, chunker).
"""

import pytest

from slrag.ingest.loader import DocumentSection, MarkdownLoader
from slrag.ingest.chunker import IngestChunk, StructureAwareChunker


class TestMarkdownLoader:
    def test_section_extraction(self, tmp_path):
        """Loader should split a markdown file into sections by heading."""
        doc = tmp_path / "test_doc.md"
        doc.write_text(
            "# 1. Introduction\nWelcome to the policy.\n\n"
            "# 2. Capacity\nMax 40 people.\n\n"
            "# 3. Pricing\n$5000 per day.\n",
            encoding="utf-8",
        )

        loader = MarkdownLoader(tmp_path)
        sections = loader.load_all()

        assert len(sections) == 3
        assert sections[0].section_id == "1"
        assert sections[0].doc_id == "test_doc"
        assert "Welcome" in sections[0].text
        assert sections[1].section_id == "2"
        assert sections[2].section_id == "3"

    def test_no_headers(self, tmp_path):
        """Document with no headers → single section."""
        doc = tmp_path / "plain.md"
        doc.write_text("Just plain text content.", encoding="utf-8")

        loader = MarkdownLoader(tmp_path)
        sections = loader.load_all()

        assert len(sections) == 1
        assert sections[0].section_id == "1"

    def test_empty_corpus(self, tmp_path):
        """Empty directory → no sections."""
        loader = MarkdownLoader(tmp_path)
        sections = loader.load_all()
        assert len(sections) == 0


class TestStructureAwareChunker:
    def test_small_section_single_chunk(self):
        """Section that fits within max_tokens → one chunk."""
        section = DocumentSection(
            doc_id="Doc_01",
            section_id="1",
            heading="Introduction",
            text="This is a short section. " * 10,
        )

        chunker = StructureAwareChunker(
            target_tokens=300, min_tokens=250, max_tokens=400
        )
        chunks = chunker.chunk_section(section)

        assert len(chunks) == 1
        assert chunks[0].chunk_id == "Doc_01#1#0"
        assert chunks[0].citation_label == "Doc_01 §1"

    def test_large_section_multiple_chunks(self):
        """Section exceeding max_tokens → multiple chunks."""
        section = DocumentSection(
            doc_id="Doc_02",
            section_id="3",
            heading="Pricing",
            text="This is a word. " * 500,  # ~500 words
        )

        chunker = StructureAwareChunker(
            target_tokens=300, min_tokens=250, max_tokens=400
        )
        chunks = chunker.chunk_section(section)

        assert len(chunks) > 1
        # All chunks should have the same doc_id and section_id
        for chunk in chunks:
            assert chunk.doc_id == "Doc_02"
            assert chunk.section_id == "3"
            assert chunk.citation_label == "Doc_02 §3"

    def test_chunk_id_format(self):
        """ChunkID must be doc_id#section_id#ordinal."""
        section = DocumentSection(
            doc_id="Doc_12", section_id="2", heading="Capacity",
            text="The venue holds 40 people. " * 50,
        )

        chunker = StructureAwareChunker()
        chunks = chunker.chunk_section(section)

        for chunk in chunks:
            parts = chunk.chunk_id.split("#")
            assert len(parts) == 3
            assert parts[0] == "Doc_12"
            assert parts[1] == "2"
            assert parts[2].isdigit()

    def test_citation_label_format(self):
        """CitationLabel must be 'Doc_ID §Section'."""
        section = DocumentSection(
            doc_id="Doc_31", section_id="4", heading="Cancellation",
            text="Cancel 14 days before for full refund.",
        )

        chunker = StructureAwareChunker()
        chunks = chunker.chunk_section(section)

        assert chunks[0].citation_label == "Doc_31 §4"

    def test_never_straddles_sections(self):
        """Chunks from different sections must never be merged."""
        sections = [
            DocumentSection(doc_id="D1", section_id="1", heading="A", text="Section one content."),
            DocumentSection(doc_id="D1", section_id="2", heading="B", text="Section two content."),
        ]

        chunker = StructureAwareChunker()
        all_chunks = chunker.chunk_documents(sections)

        section_ids_per_chunk = [c.section_id for c in all_chunks]
        # No chunk should contain content from two sections
        for chunk in all_chunks:
            assert "Section one" not in chunk.text or chunk.section_id == "1"
            assert "Section two" not in chunk.text or chunk.section_id == "2"
