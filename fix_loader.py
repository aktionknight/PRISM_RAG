import sys
content = open('D:/downloads/PRISM_RAG/src/slrag/ingest/loader.py').read()
import re
new_content = content.replace('    def load_all(self) -> list[DocumentSection]:\n        """Load all documents from the corpus directory."""\n        sections: list[DocumentSection] = []\n        if not self.corpus_dir.exists():\n            logger.warning(f"Corpus directory does not exist: {self.corpus_dir}")\n            return sections\n\n        for filepath in sorted(self.corpus_dir.glob("**/*.md")):\n            logger.info(f"Loading {filepath.name}")\n            sections.extend(self.load_file(filepath))\n\n        for filepath in sorted(self.corpus_dir.glob("**/*.txt")):\n            logger.info(f"Loading {filepath.name}")\n            sections.extend(self.load_file(filepath))\n\n        logger.info(f"Loaded {len(sections)} sections from {self.corpus_dir}")\n        return sections', '''    def load_all(self) -> list[DocumentSection]:
        """Load all documents from the corpus directory."""
        sections: list[DocumentSection] = []
        if not self.corpus_dir.exists():
            logger.warning(f"Corpus directory does not exist: {self.corpus_dir}")
            return sections

        seen_docs = set()
        seen_content_hashes = set()

        for filepath in sorted(self.corpus_dir.glob("**/*.md")):
            logger.info(f"Loading {filepath.name}")
            sections.extend(self.load_file(filepath, seen_docs, seen_content_hashes))

        for filepath in sorted(self.corpus_dir.glob("**/*.txt")):
            logger.info(f"Loading {filepath.name}")
            sections.extend(self.load_file(filepath, seen_docs, seen_content_hashes))

        logger.info(f"Loaded {len(sections)} sections from {self.corpus_dir}")
        return sections''')

new_content = new_content.replace('    def load_file(self, filepath: Path) -> list[DocumentSection]:\n        """Load a single file and extract its sections."""\n        doc_id = filepath.stem\n        try:\n            content = filepath.read_text(encoding="utf-8")\n        except Exception as e:\n            logger.error(f"Failed to read {filepath}: {e}")\n            return []\n\n        # Split by markdown headers (# through ######)\n        pattern = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)\n        matches = list(pattern.finditer(content))\n\n        sections: list[DocumentSection] = []\n\n        if not matches:\n            # Document has no headers — treat as one section\n            text = content.strip()\n            if text:\n                sections.append(DocumentSection(\n                    doc_id=doc_id,\n                    section_id="1",\n                    heading="",\n                    text=text,\n                ))\n            return sections\n\n        for i, match in enumerate(matches):\n            heading = match.group(2).strip()\n\n            # Extract section number from heading if present (e.g. "1. Introduction")\n            num_match = re.match(r"^(\d+)", heading)\n            if num_match:\n                section_id = num_match.group(1)\n            else:\n                section_id = str(i + 1)\n\n            start_pos = match.end()\n            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)\n\n            text = content[start_pos:end_pos].strip()\n            if text:\n                sections.append(DocumentSection(\n                    doc_id=doc_id,\n                    section_id=section_id,\n                    heading=heading,\n                    text=text,\n                ))\n\n        return sections', '''    def load_file(self, filepath: Path, seen_docs: set[str] | None = None, seen_content_hashes: set[str] | None = None) -> list[DocumentSection]:
        """Load a single file and extract its sections."""
        try:
            rel_path = filepath.relative_to(self.corpus_dir)
            doc_id = str(rel_path.with_suffix("")).replace("\\\\", "/")
        except ValueError:
            doc_id = filepath.stem

        if seen_docs is not None:
            if doc_id in seen_docs:
                logger.warning(f"Duplicate doc_id rejected: {doc_id}")
                return []
            seen_docs.add(doc_id)

        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to read {filepath}: {e}")
            return []

        if seen_content_hashes is not None:
            import hashlib
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            if content_hash in seen_content_hashes:
                logger.warning(f"Duplicate content rejected for {filepath}")
                return []
            seen_content_hashes.add(content_hash)

        # Split by markdown headers (# through ######)
        pattern = re.compile(r"^(#{1,6})\\s+(.*)$", re.MULTILINE)
        matches = list(pattern.finditer(content))

        sections: list[DocumentSection] = []
        seen_section_ids = set()

        def _get_unique_section_id(base: str) -> str:
            sec = base
            suffix = 1
            while sec in seen_section_ids:
                sec = f"{base}_{suffix}"
                suffix += 1
            seen_section_ids.add(sec)
            return sec

        if not matches:
            # Document has no headers — treat as one section
            text = content.strip()
            if text:
                sections.append(DocumentSection(
                    doc_id=doc_id,
                    section_id=_get_unique_section_id("1"),
                    heading="",
                    text=text,
                ))
            return sections

        preamble = content[:matches[0].start()].strip()
        if preamble:
            sections.append(DocumentSection(
                doc_id=doc_id,
                section_id=_get_unique_section_id("0"),
                heading="",
                text=preamble,
            ))

        for i, match in enumerate(matches):
            heading = match.group(2).strip()

            # Extract hierarchical section number if present (e.g. "1.2")
            num_match = re.match(r"^([\\d\\.]+)", heading)
            if num_match:
                base_sec = num_match.group(1).rstrip('.')
            else:
                base_sec = str(i + 1)

            section_id = _get_unique_section_id(base_sec)

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

        return sections''')

open('D:/downloads/PRISM_RAG/src/slrag/ingest/loader.py', 'w').write(new_content)
