"""
AST Parser — Parses Python source code into Tree-sitter Abstract Syntax Trees.

Responsibilities:
- Initialize Tree-sitter with Python grammar
- Parse a Python file's source code into an AST
- Provide helper methods to find function/class definition nodes
- Extract node text, line ranges, docstrings, signatures, and decorators

Why Tree-sitter (not built-in ast module)?
- Handles partial/broken syntax gracefully (common in real-world repos)
- Very fast (parses large files in milliseconds)
- Language-agnostic (extensible to other languages in the future)

Usage:
    from graphcoderag.ingestion.ast_parser import PythonASTParser
    parser = PythonASTParser()
    tree, source = parser.parse_file("/path/to/file.py")
    nodes = parser.extract_functions_and_classes(tree, source)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class ASTNode:
    """Represents a parsed AST node with metadata."""
    node_type: str           # "function" or "class"
    name: str                # Function/class name
    source_code: str         # Complete source code of the node
    start_line: int          # 1-indexed start line
    end_line: int            # 1-indexed end line
    docstring: Optional[str] # Extracted docstring, if any
    signature: Optional[str] # Function signature line, if applicable
    parent_class: Optional[str] = None  # Parent class name (for methods)
    decorators: List[str] = field(default_factory=list)  # Decorator names
    children: List["ASTNode"] = field(default_factory=list)  # Nested nodes


class PythonASTParser:
    """Parser that uses Tree-sitter to produce ASTs from Python source code."""

    def __init__(self):
        """Initialize the Tree-sitter parser with the Python language."""
        self.PY_LANGUAGE = Language(tspython.language())
        self.parser = Parser(self.PY_LANGUAGE)

    def parse_source(self, source_code: str):
        """
        Parse Python source code string into a Tree-sitter tree.

        Args:
            source_code: Raw Python source code as a string.

        Returns:
            Tree-sitter Tree object.
        """
        return self.parser.parse(bytes(source_code, "utf-8"))

    def parse_file(self, file_path: str) -> Tuple:
        """
        Parse a Python file into a Tree-sitter tree.

        Args:
            file_path: Path to the .py file.

        Returns:
            Tuple of (Tree-sitter Tree object, source_code string).
        """
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source_code = f.read()
        tree = self.parse_source(source_code)
        return tree, source_code

    def extract_functions_and_classes(self, tree, source_code: str) -> List[ASTNode]:
        """
        Walk the AST and extract all top-level and nested function/class definitions.

        Args:
            tree: Tree-sitter tree object.
            source_code: Original source code string.

        Returns:
            List of ASTNode objects representing functions and classes.
        """
        source_bytes = bytes(source_code, "utf-8")
        nodes = []

        def _extract_node(ts_node, parent_class_name=None):
            """Recursively extract function and class definitions."""
            for child in ts_node.children:
                if child.type in ("function_definition", "async_function_definition"):
                    ast_node = self._build_ast_node(
                        child, source_bytes, "function", parent_class_name
                    )
                    nodes.append(ast_node)
                    # Recurse into function body to find nested functions
                    body = self._find_child_by_type(child, "block")
                    if body:
                        _extract_node(body, parent_class_name=parent_class_name)

                elif child.type == "class_definition":
                    ast_node = self._build_ast_node(
                        child, source_bytes, "class", parent_class_name
                    )
                    nodes.append(ast_node)
                    # Recurse into class body to find methods
                    body = self._find_child_by_type(child, "block")
                    if body:
                        _extract_node(body, parent_class_name=ast_node.name)

                elif child.type == "decorated_definition":
                    # Handle decorated functions/classes
                    for sub in child.children:
                        if sub.type in ("function_definition", "async_function_definition", "class_definition"):
                            node_type = "function" if "function_definition" in sub.type else "class"
                            ast_node = self._build_ast_node(
                                child, source_bytes, node_type, parent_class_name
                            )
                            # Extract decorator names
                            ast_node.decorators = self._extract_decorators(child, source_bytes)
                            nodes.append(ast_node)
                            
                            # Recurse into body
                            body = self._find_child_by_type(sub, "block")
                            if body:
                                p_name = ast_node.name if node_type == "class" else parent_class_name
                                _extract_node(body, parent_class_name=p_name)

        _extract_node(tree.root_node)
        return nodes

    def _build_ast_node(self, ts_node, source_bytes: bytes,
                         node_type: str, parent_class: Optional[str]) -> ASTNode:
        """Build an ASTNode from a tree-sitter node."""
        name = self._get_node_name(ts_node)
        source = source_bytes[ts_node.start_byte:ts_node.end_byte].decode("utf-8")
        start_line = ts_node.start_point[0] + 1  # Convert 0-indexed to 1-indexed
        end_line = ts_node.end_point[0] + 1
        docstring = self._extract_docstring(ts_node, source_bytes)
        signature = self._extract_signature(ts_node, source_bytes) if node_type == "function" else None

        return ASTNode(
            node_type=node_type,
            name=name,
            source_code=source,
            start_line=start_line,
            end_line=end_line,
            docstring=docstring,
            signature=signature,
            parent_class=parent_class,
        )

    def _get_node_name(self, ts_node) -> str:
        """Extract the name identifier from a function/class definition node."""
        for child in ts_node.children:
            if child.type == "identifier":
                return child.text.decode("utf-8")
            # Handle decorated definitions
            if child.type in ("function_definition", "class_definition"):
                return self._get_node_name(child)
        return "<anonymous>"

    def _extract_docstring(self, ts_node, source_bytes: bytes) -> Optional[str]:
        """Extract docstring from function/class body if present."""
        # For decorated definitions, find the actual func/class inside
        actual_node = ts_node
        if ts_node.type == "decorated_definition":
            for child in ts_node.children:
                if child.type in ("function_definition", "class_definition"):
                    actual_node = child
                    break

        body = self._find_child_by_type(actual_node, "block")
        if not body or not body.children:
            return None

        # Find the first expression_statement in the body (skip whitespace nodes)
        for child in body.children:
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr and expr.type == "string":
                    raw = source_bytes[expr.start_byte:expr.end_byte].decode("utf-8")
                    # Strip triple quotes properly (not char-by-char)
                    for prefix in ('"""', "'''"):
                        if raw.startswith(prefix) and raw.endswith(prefix):
                            return raw[3:-3].strip()
                    # Fallback for single-quoted strings
                    return raw.strip("\"'").strip()
                break
            elif child.type not in ("newline", "indent", "comment", "NEWLINE", "INDENT"):
                # First non-whitespace statement is not a docstring
                break
        return None

    def _extract_signature(self, ts_node, source_bytes: bytes) -> Optional[str]:
        """Extract the function signature (def line)."""
        # For decorated definitions, find the actual function inside
        actual_node = ts_node
        if ts_node.type == "decorated_definition":
            for child in ts_node.children:
                if child.type == "function_definition":
                    actual_node = child
                    break

        # Get text from start of node to the colon
        for child in actual_node.children:
            if child.type == ":":
                sig = source_bytes[actual_node.start_byte:child.start_byte].decode("utf-8").strip()
                return sig
        return None

    def _extract_decorators(self, decorated_node, source_bytes: bytes) -> List[str]:
        """Extract decorator names from a decorated definition."""
        decorators = []
        for child in decorated_node.children:
            if child.type == "decorator":
                dec_text = source_bytes[child.start_byte:child.end_byte].decode("utf-8").strip()
                decorators.append(dec_text)
        return decorators

    @staticmethod
    def _find_child_by_type(ts_node, child_type: str):
        """Find the first child of a given type."""
        for child in ts_node.children:
            if child.type == child_type:
                return child
        return None
