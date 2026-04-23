"""
Standard RAG Baseline (Pipeline A) — Recursive Character Chunking

This is the conventional RAG approach that GraphCodeRAG aims to beat:
  - Recursive character splitting (512 tokens, 50-token overlap)
  - Same embedding model (all-MiniLM-L6-v2)
  - Same ChromaDB vector store
  - Vector-only cosine similarity retrieval
  - NO AST parsing, NO graph traversal, NO Neo4j

Used as the controlled baseline in our A/B evaluation.
"""
import os
import hashlib
from pathlib import Path
from typing import List
from dataclasses import dataclass

from graphcoderag.storage.vector_store import VectorStore


@dataclass
class CharChunk:
    """A chunk produced by recursive character splitting."""
    chunk_id: str
    name: str
    file_path: str
    chunk_type: str
    start_line: int
    end_line: int
    content: str
    docstring: str = ""
    source_code: str = ""
    parent_class: str = ""

    @property
    def display_name(self) -> str:
        return self.name

    def to_embedding_text(self) -> str:
        """Return text for embedding — same format as CodeChunk."""
        return f"# {self.file_path}\n{self.content}"


class BaselineRAG:
    """Standard RAG pipeline using recursive character chunking."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def scan_and_chunk(self, repo_path: str) -> List[CharChunk]:
        """Scan all Python files and chunk with recursive character splitting."""
        repo = Path(repo_path)
        all_chunks = []

        for py_file in sorted(repo.rglob("*.py")):
            # Skip hidden/venv/test directories
            parts = py_file.parts
            if any(p.startswith('.') or p in ('venv', 'node_modules', '__pycache__',
                   '.git', 'build', 'dist', '.eggs', '*.egg-info')
                   for p in parts):
                continue

            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
            except Exception:
                continue

            if not content.strip():
                continue

            rel_path = str(py_file.relative_to(repo)).replace("\\", "/")
            chunks = self._recursive_split(content, rel_path)
            all_chunks.extend(chunks)

        return all_chunks

    def _recursive_split(self, text: str, file_path: str) -> List[CharChunk]:
        """
        Recursive character splitting at 512 chars with 50-char overlap.
        Splits on: double newline → single newline → space → hard cut.
        """
        separators = ["\n\n", "\n", " ", ""]
        chunks = []
        raw_chunks = self._split_recursive(text, separators)

        lines = text.split('\n')
        char_pos = 0
        line_map = []  # char_offset -> line_number
        for i, line in enumerate(lines):
            line_map.append((char_pos, i + 1))
            char_pos += len(line) + 1  # +1 for \n

        for i, chunk_text in enumerate(raw_chunks):
            # Estimate line numbers
            start_char = text.find(chunk_text) if i == 0 else text.find(chunk_text, max(0, text.find(raw_chunks[i-1])))
            start_line = 1
            end_line = 1
            for offset, lnum in line_map:
                if offset <= max(start_char, 0):
                    start_line = lnum
                if offset <= max(start_char, 0) + len(chunk_text):
                    end_line = lnum

            chunk_id = hashlib.md5(f"{file_path}:{i}:{chunk_text[:50]}".encode()).hexdigest()

            chunks.append(CharChunk(
                chunk_id=chunk_id,
                name=f"chunk_{i}",
                file_path=file_path,
                chunk_type="text_chunk",
                start_line=start_line,
                end_line=end_line,
                content=chunk_text,
                source_code=chunk_text,
            ))

        return chunks

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        """Split text recursively using progressively finer separators."""
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        sep = separators[0] if separators else ""
        remaining_seps = separators[1:] if len(separators) > 1 else [""]

        if not sep:
            # Hard split at chunk_size
            chunks = []
            for i in range(0, len(text), self.chunk_size - self.chunk_overlap):
                chunk = text[i:i + self.chunk_size]
                if chunk.strip():
                    chunks.append(chunk)
            return chunks

        parts = text.split(sep)
        chunks = []
        current = ""

        for part in parts:
            candidate = current + sep + part if current else part
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current)
                # If this part alone is too large, recurse with finer separator
                if len(part) > self.chunk_size:
                    sub_chunks = self._split_recursive(part, remaining_seps)
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current.strip():
            chunks.append(current)

        # Add overlap
        if self.chunk_overlap > 0 and len(chunks) > 1:
            overlapped = [chunks[0]]
            for i in range(1, len(chunks)):
                prev = chunks[i - 1]
                overlap_text = prev[-self.chunk_overlap:] if len(prev) > self.chunk_overlap else prev
                overlapped.append(overlap_text + chunks[i])
            chunks = overlapped

        return chunks

    def ingest(self, repo_path: str, collection_name: str) -> int:
        """Ingest a repo with character chunking into ChromaDB."""
        print(f"  [Baseline] Scanning {repo_path}...", flush=True)
        chunks = self.scan_and_chunk(repo_path)
        print(f"  [Baseline] {len(chunks)} character chunks", flush=True)

        vs = VectorStore(collection_name=collection_name)
        vs.add_chunks(chunks)
        print(f"  [Baseline] Stored in ChromaDB[{collection_name}]", flush=True)
        return len(chunks)

    def retrieve(self, query: str, collection_name: str, top_k: int = 10):
        """Retrieve using vector-only search from baseline collection."""
        from graphcoderag.retrieval.vector_retriever import VectorRetriever, RetrievalResult
        vs = VectorStore(collection_name=collection_name)
        retriever = VectorRetriever(vs)
        return retriever.retrieve(query, top_k=top_k)
