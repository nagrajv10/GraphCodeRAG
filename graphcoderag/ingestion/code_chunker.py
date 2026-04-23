"""
Code Chunker — Converts AST nodes into structured code chunks for embedding.

Responsibilities:
- Take parsed ASTNode objects and wrap them into CodeChunk objects
- Add file-level metadata (path, repo name)
- Handle module-level code (imports, constants) as a separate chunk
- Generate unique chunk IDs for cross-referencing between vector DB and graph DB

Key design decision:
- Each function definition = one chunk
- Each class definition (including all methods) = one chunk
- Module-level code (imports, constants, global assignments) = one separate chunk
- No chunk is ever syntactically incomplete or severed from its logical context

Usage:
    from graphcoderag.ingestion.code_chunker import CodeChunker
    chunker = CodeChunker()
    chunks = chunker.chunk_file(file_path, ast_nodes, source_code)
"""
import hashlib
from dataclasses import dataclass, field
from typing import List, Optional
from graphcoderag.ingestion.ast_parser import ASTNode


@dataclass
class CodeChunk:
    """A self-contained chunk of code with full metadata."""
    chunk_id: str                # Unique ID: hash of file_path + name + line range
    file_path: str               # Relative path within the repo
    chunk_type: str              # "function", "class", or "module"
    name: str                    # Entity name (function/class name or "module_level")
    source_code: str             # Complete source code of the chunk
    start_line: int              # 1-indexed start line in the original file
    end_line: int                # 1-indexed end line in the original file
    docstring: Optional[str]     # Extracted docstring
    signature: Optional[str]     # Function signature (for functions)
    parent_class: Optional[str]  # Parent class name (for methods)
    decorators: List[str] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        """Human-readable qualified name like 'ClassName.method_name'."""
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name

    def to_embedding_text(self) -> str:
        """
        Create the text representation used for embedding.
        Includes metadata context so the embedding captures structural info,
        not just raw code.
        """
        parts = [f"# File: {self.file_path}"]
        if self.parent_class:
            parts.append(f"# Class: {self.parent_class}")
        parts.append(f"# {self.chunk_type.title()}: {self.name}")
        if self.docstring:
            parts.append(f"# Docstring: {self.docstring[:200]}")
        parts.append(self.source_code)
        return "\n".join(parts)


class CodeChunker:
    """Converts AST nodes into structured CodeChunks."""

    def chunk_file(
        self,
        rel_file_path: str,
        ast_nodes: List[ASTNode],
        source_code: str,
    ) -> List[CodeChunk]:
        """
        Create code chunks from a file's AST nodes.

        Args:
            rel_file_path: Relative path of the file within the repo.
            ast_nodes: List of ASTNode objects from the AST parser.
            source_code: Complete source code of the file.

        Returns:
            List of CodeChunk objects.
        """
        chunks: List[CodeChunk] = []

        # Extract module-level code (everything not inside a function/class)
        module_chunk = self._extract_module_level(rel_file_path, ast_nodes, source_code)
        if module_chunk:
            chunks.append(module_chunk)

        # Create a chunk for each function, method, AND class
        for node in ast_nodes:
            chunk_id = self._generate_id(rel_file_path, node.name, node.start_line, node.end_line)

            # For methods, use a display_name that includes the class
            display_name = node.name
            if node.parent_class:
                display_name = f"{node.parent_class}.{node.name}"

            chunks.append(CodeChunk(
                chunk_id=chunk_id,
                file_path=rel_file_path,
                chunk_type=node.node_type,
                name=node.name,
                source_code=node.source_code,
                start_line=node.start_line,
                end_line=node.end_line,
                docstring=node.docstring,
                signature=node.signature,
                parent_class=node.parent_class,
                decorators=node.decorators,
            ))

        return chunks

    def _extract_module_level(
        self, rel_file_path: str, ast_nodes: List[ASTNode], source_code: str
    ) -> Optional[CodeChunk]:
        """
        Extract module-level code (imports, constants, global assignments).
        This is everything outside function/class definitions.
        """
        lines = source_code.split("\n")
        # Track which lines are covered by top-level AST nodes
        covered_lines = set()
        for node in ast_nodes:
            if node.parent_class is None:  # Only top-level nodes
                for line_num in range(node.start_line, node.end_line + 1):
                    covered_lines.add(line_num)

        # Collect uncovered lines (module-level code)
        module_lines = []
        for i, line in enumerate(lines, start=1):
            if i not in covered_lines and line.strip():
                module_lines.append(line)

        if not module_lines:
            return None

        module_code = "\n".join(module_lines)
        return CodeChunk(
            chunk_id=self._generate_id(rel_file_path, "module_level", 0, 0),
            file_path=rel_file_path,
            chunk_type="module",
            name="module_level",
            source_code=module_code,
            start_line=1,
            end_line=len(lines),
            docstring=None,
            signature=None,
            parent_class=None,
        )

    @staticmethod
    def _generate_id(file_path: str, name: str, start: int, end: int) -> str:
        """Generate a deterministic unique ID for a chunk."""
        raw = f"{file_path}::{name}::{start}::{end}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
