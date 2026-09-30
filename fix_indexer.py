import sys
content = open('D:/downloads/PRISM_RAG/src/slrag/ingest/indexer.py').read()
new_content = content.replace('    def build_and_save(self, chunks: list[IngestChunk]) -> None:\n        """Build both indexes and persist all artifacts."""\n        if not chunks:\n            logger.warning("No chunks provided to indexer — skipping.")\n            return\n\n        self._ensure_dirs()\n        corpus_texts = [chunk.text for chunk in chunks]\n        logger.info(f"Building indexes for {len(chunks)} chunks")', '''    def build_and_save(self, chunks: list[IngestChunk]) -> None:
        """Build both indexes and persist all artifacts."""
        if not chunks:
            logger.warning("No chunks provided to indexer — skipping.")
            return

        unique_chunks = []
        seen = set()
        for c in chunks:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                unique_chunks.append(c)
            else:
                logger.warning(f"Duplicate chunk_id rejected: {c.chunk_id}")
        chunks = unique_chunks

        if not chunks:
            logger.warning("No unique chunks provided to indexer — skipping.")
            return

        self._ensure_dirs()
        corpus_texts = [chunk.text for chunk in chunks]
        logger.info(f"Building indexes for {len(chunks)} chunks")''')

open('D:/downloads/PRISM_RAG/src/slrag/ingest/indexer.py', 'w').write(new_content)
