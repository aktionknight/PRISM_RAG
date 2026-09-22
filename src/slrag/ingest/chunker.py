"""
ingest/chunker.py — Structure-aware chunker respecting section boundaries.

Chunks documents into 250–400 token segments with ~15% overlap,
NEVER straddling section boundaries.  Each chunk carries full metadata
for the citation pipeline.

ChunkID format:  doc_id#section_id#ordinal
CitationLabel:   "Doc_ID §Section"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from slrag.ingest.loader import DocumentSection

logger = logging.getLogger(__name__)


@dataclass
class IngestChunk:
    """A single chunk produced by the structure-aware chunker."""
    chunk_id: str       # doc_id#section_id#ordinal
    doc_id: str
    section_id: str
    ordinal: int
    citation_label: str  # "Doc_12 §2"
    text: str


def _approx_token_count(text: str) -> int:
    """Approximate token count (~0.75 words per token for English)."""
    return max(1, int(len(text.split()) * 1.33))


class StructureAwareChunker:
    """Chunks sections into 250–400 token segments with overlap.

    Key invariant: a chunk NEVER straddles two sections.
    """

    def __init__(
        self,
        target_tokens: int = 300,
        min_tokens: int = 250,
        max_tokens: int = 400,
        overlap_pct: float = 0.15,
    ) -> None:
        self.target_tokens = target_tokens
        self.min_tokens = min_tokens
        self.max_tokens = max_tokens
        self.overlap_pct = overlap_pct

    def chunk_section(self, section: DocumentSection) -> list[IngestChunk]:
        """Chunk a single section into token-bounded segments with overlap."""
        words = section.text.split()
        if not words:
            return []

        # If the entire section fits in max_tokens, emit it as one chunk
        total_tokens = _approx_token_count(section.text)
        if total_tokens <= self.max_tokens:
            return [IngestChunk(
                chunk_id=f"{section.doc_id}#{section.section_id}#0",
                doc_id=section.doc_id,
                section_id=section.section_id,
                ordinal=0,
                citation_label=f"{section.doc_id} §{section.section_id}",
                text=section.text.strip(),
            )]

        overlap_tokens = int(self.target_tokens * self.overlap_pct)
        chunks: list[IngestChunk] = []
        ordinal = 0

        current_words: list[str] = []
        current_token_count = 0
        i = 0

        while i < len(words):
            word = words[i]
            word_tokens = _approx_token_count(word + " ")

            if (current_token_count + word_tokens > self.max_tokens
                    and current_token_count >= self.min_tokens):
                # Commit current chunk
                chunk_text = " ".join(current_words)
                chunks.append(IngestChunk(
                    chunk_id=f"{section.doc_id}#{section.section_id}#{ordinal}",
                    doc_id=section.doc_id,
                    section_id=section.section_id,
                    ordinal=ordinal,
                    citation_label=f"{section.doc_id} §{section.section_id}",
                    text=chunk_text,
                ))
                ordinal += 1

                # Backtrack for overlap
                overlap_words: list[str] = []
                overlap_count = 0
                for w in reversed(current_words):
                    w_tok = _approx_token_count(w + " ")
                    if overlap_count + w_tok > overlap_tokens:
                        break
                    overlap_words.insert(0, w)
                    overlap_count += w_tok

                current_words = overlap_words
                current_token_count = overlap_count

            current_words.append(word)
            current_token_count += word_tokens
            i += 1

        # Flush remaining words
        if current_words:
            chunk_text = " ".join(current_words)
            # If tiny tail, merge into last chunk
            if chunks and _approx_token_count(chunk_text) < 50:
                last = chunks[-1]
                chunks[-1] = IngestChunk(
                    chunk_id=last.chunk_id,
                    doc_id=last.doc_id,
                    section_id=last.section_id,
                    ordinal=last.ordinal,
                    citation_label=last.citation_label,
                    text=last.text + " " + chunk_text,
                )
            else:
                chunks.append(IngestChunk(
                    chunk_id=f"{section.doc_id}#{section.section_id}#{ordinal}",
                    doc_id=section.doc_id,
                    section_id=section.section_id,
                    ordinal=ordinal,
                    citation_label=f"{section.doc_id} §{section.section_id}",
                    text=chunk_text,
                ))

        logger.debug(
            f"Section {section.doc_id}§{section.section_id}: "
            f"{total_tokens} tokens → {len(chunks)} chunks"
        )
        return chunks

    def chunk_documents(self, sections: list[DocumentSection]) -> list[IngestChunk]:
        """Chunk all sections from all documents."""
        all_chunks: list[IngestChunk] = []
        for section in sections:
            all_chunks.extend(self.chunk_section(section))

        logger.info(
            f"Chunked {len(sections)} sections into {len(all_chunks)} chunks "
            f"(target: {self.min_tokens}–{self.max_tokens} tokens, "
            f"overlap: {self.overlap_pct:.0%})"
        )
        return all_chunks
