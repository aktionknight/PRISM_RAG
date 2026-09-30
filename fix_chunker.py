import sys
content = open('D:/downloads/PRISM_RAG/src/slrag/ingest/chunker.py').read()
new_content = content.replace('    def chunk_section(self, section: DocumentSection) -> list[IngestChunk]:\n        """Chunk a single section into token-bounded segments with overlap."""', '''    def chunk_section(self, section: DocumentSection, start_ordinal: int = 0) -> tuple[list[IngestChunk], int]:
        """Chunk a single section into token-bounded segments with overlap."""''')

new_content = new_content.replace('''        if total_tokens <= self.max_tokens:
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
        ordinal = 0''', '''        if total_tokens <= self.max_tokens:
            return [IngestChunk(
                chunk_id=f"{section.doc_id}#{section.section_id}#{start_ordinal}",
                doc_id=section.doc_id,
                section_id=section.section_id,
                ordinal=start_ordinal,
                citation_label=f"{section.doc_id} §{section.section_id}",
                text=section.text.strip(),
            )], start_ordinal + 1

        overlap_tokens = int(self.target_tokens * self.overlap_pct)
        chunks: list[IngestChunk] = []
        ordinal = start_ordinal''')

new_content = new_content.replace('''            else:
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
        return chunks''', '''            else:
                chunks.append(IngestChunk(
                    chunk_id=f"{section.doc_id}#{section.section_id}#{ordinal}",
                    doc_id=section.doc_id,
                    section_id=section.section_id,
                    ordinal=ordinal,
                    citation_label=f"{section.doc_id} §{section.section_id}",
                    text=chunk_text,
                ))
                ordinal += 1

        logger.debug(
            f"Section {section.doc_id}§{section.section_id}: "
            f"{total_tokens} tokens → {len(chunks)} chunks"
        )
        return chunks, ordinal''')

new_content = new_content.replace('''    def chunk_documents(self, sections: list[DocumentSection]) -> list[IngestChunk]:
        """Chunk all sections from all documents."""
        all_chunks: list[IngestChunk] = []
        for section in sections:
            all_chunks.extend(self.chunk_section(section))''', '''    def chunk_documents(self, sections: list[DocumentSection]) -> list[IngestChunk]:
        """Chunk all sections from all documents."""
        all_chunks: list[IngestChunk] = []
        doc_ordinals: dict[str, int] = {}
        for section in sections:
            start_ord = doc_ordinals.get(section.doc_id, 0)
            chunks, next_ord = self.chunk_section(section, start_ord)
            doc_ordinals[section.doc_id] = next_ord
            all_chunks.extend(chunks)''')

open('D:/downloads/PRISM_RAG/src/slrag/ingest/chunker.py', 'w').write(new_content)
