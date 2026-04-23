"""
Dependency Extractor — Analyzes Python ASTs to extract relationships.

Extracts 4 types of directed edges:
- IMPORTS:  module A imports name B from module C
- CALLS:    function X calls function Y
- CONTAINS: class P contains method Q
- INHERITS: class R extends class S

These edges are stored in Neo4j to enable multi-hop graph traversal
during retrieval. This is what makes GraphCodeRAG aware of code structure
beyond simple text similarity.

Usage:
    from graphcoderag.ingestion.dependency_extractor import DependencyExtractor
    extractor = DependencyExtractor()
    edges = extractor.extract_from_file(tree, source_code, file_path)
"""
from dataclasses import dataclass
from typing import List


@dataclass
class DependencyEdge:
    """Represents a directed edge between two code entities."""
    source_file: str        # File containing the source entity
    source_name: str        # Name of the source entity
    target_name: str        # Name of the target entity
    target_module: str      # Module path of the target (for imports)
    edge_type: str          # "IMPORTS", "CALLS", "CONTAINS", "INHERITS"
    line_number: int        # Line where this relationship is defined


class DependencyExtractor:
    """Extracts dependency relationships from Python ASTs."""

    def __init__(self):
        # Allowlist for edge types (Fix #1: prevent Cypher injection)
        self.VALID_EDGE_TYPES = {"IMPORTS", "CALLS", "CONTAINS", "INHERITS"}

    def extract_from_file(
        self, tree, source_code: str, rel_file_path: str
    ) -> List[DependencyEdge]:
        """
        Extract all dependency edges from a parsed file.

        Args:
            tree: Tree-sitter tree object.
            source_code: Original source code.
            rel_file_path: Relative file path within the repo.

        Returns:
            List of DependencyEdge objects.
        """
        source_bytes = bytes(source_code, "utf-8")
        edges: List[DependencyEdge] = []

        edges.extend(self._extract_imports(tree.root_node, source_bytes, rel_file_path))
        edges.extend(self._extract_calls(tree.root_node, source_bytes, rel_file_path))
        edges.extend(self._extract_containment(tree.root_node, source_bytes, rel_file_path))
        edges.extend(self._extract_inheritance(tree.root_node, source_bytes, rel_file_path))

        return edges

    def _extract_imports(self, root_node, source_bytes, file_path) -> List[DependencyEdge]:
        """
        Extract import statements: 'import X' and 'from X import Y'.
        Only processes top-level import nodes (direct children of root).
        """
        edges = []
        for node in root_node.children:
            if node.type == "import_statement":
                # import module_name
                for child in node.children:
                    if child.type == "dotted_name":
                        module_name = self._node_text(child, source_bytes)
                        edges.append(DependencyEdge(
                            source_file=file_path,
                            source_name=file_path,
                            target_name=module_name,
                            target_module=module_name,
                            edge_type="IMPORTS",
                            line_number=node.start_point[0] + 1,
                        ))
                    elif child.type == "aliased_import":
                        dotted = self._find_child(child, "dotted_name")
                        if dotted:
                            module_name = self._node_text(dotted, source_bytes)
                            edges.append(DependencyEdge(
                                source_file=file_path,
                                source_name=file_path,
                                target_name=module_name,
                                target_module=module_name,
                                edge_type="IMPORTS",
                                line_number=node.start_point[0] + 1,
                            ))

            elif node.type == "import_from_statement":
                # from module import name1, name2
                module_name = self._extract_import_from_module(node, source_bytes)
                imported_names = self._extract_imported_names(node, source_bytes)

                for name in imported_names:
                    edges.append(DependencyEdge(
                        source_file=file_path,
                        source_name=file_path,
                        target_name=name,
                        target_module=module_name,
                        edge_type="IMPORTS",
                        line_number=node.start_point[0] + 1,
                    ))
        return edges

    def _extract_import_from_module(self, node, source_bytes) -> str:
        """Extract the module name from a 'from X import Y' statement."""
        # Collect relative import dots
        parts = []
        found_from = False
        for child in node.children:
            text = self._node_text(child, source_bytes)
            if text == "from":
                found_from = True
                continue
            if text == "import":
                break
            if found_from:
                if child.type == "relative_import":
                    for sub in child.children:
                        parts.append(self._node_text(sub, source_bytes))
                elif child.type in ("dotted_name", "identifier"):
                    parts.append(text)
        return "".join(parts) if parts else ""

    def _extract_imported_names(self, node, source_bytes) -> List[str]:
        """Extract the imported names from 'from X import name1, name2'."""
        names = []
        found_import = False
        for child in node.children:
            text = self._node_text(child, source_bytes)
            if text == "import":
                found_import = True
                continue
            if not found_import:
                continue
            if child.type in ("dotted_name", "identifier"):
                names.append(text)
            elif child.type == "aliased_import":
                # from X import Y as Z  -> we care about Y
                for sub in child.children:
                    if sub.type in ("dotted_name", "identifier"):
                        names.append(self._node_text(sub, source_bytes))
                        break
            elif child.type == "import_list":
                # Parenthesized import list
                for sub in child.children:
                    if sub.type in ("dotted_name", "identifier"):
                        names.append(self._node_text(sub, source_bytes))
                    elif sub.type == "aliased_import":
                        for subsub in sub.children:
                            if subsub.type in ("dotted_name", "identifier"):
                                names.append(self._node_text(subsub, source_bytes))
                                break
        return names

    def _extract_calls(self, root_node, source_bytes, file_path) -> List[DependencyEdge]:
        """
        Extract function calls within function/method bodies.
        For each function definition, find all call expressions inside it.
        """
        edges = []
        seen_calls = set()  # Avoid duplicate edges

        for func_node in self._iter_definitions(root_node, "function_definition"):
            func_name = self._get_definition_name(func_node, source_bytes)

            for call_node in self._walk_descendants(func_node):
                if call_node.type == "call":
                    called_name = self._get_call_name(call_node, source_bytes)
                    # Skip recursive calls: self-loop edges add no value for
                    # graph retrieval (the function already contains itself)
                    if called_name and called_name != func_name:
                        edge_key = (file_path, func_name, called_name)
                        if edge_key not in seen_calls:
                            seen_calls.add(edge_key)
                            edges.append(DependencyEdge(
                                source_file=file_path,
                                source_name=func_name,
                                target_name=called_name,
                                target_module="",
                                edge_type="CALLS",
                                line_number=call_node.start_point[0] + 1,
                            ))
        return edges

    def _extract_containment(self, root_node, source_bytes, file_path) -> List[DependencyEdge]:
        """Extract class-method containment: class P contains method Q."""
        edges = []
        for class_node in self._iter_definitions(root_node, "class_definition"):
            class_name = self._get_definition_name(class_node, source_bytes)
            body = self._find_child(class_node, "block")
            if not body:
                continue
            for child in body.children:
                actual = child
                if child.type == "decorated_definition":
                    for sub in child.children:
                        if sub.type == "function_definition":
                            actual = sub
                            break
                if actual.type == "function_definition":
                    method_name = self._get_definition_name(actual, source_bytes)
                    edges.append(DependencyEdge(
                        source_file=file_path,
                        source_name=class_name,
                        target_name=method_name,
                        target_module="",
                        edge_type="CONTAINS",
                        line_number=actual.start_point[0] + 1,
                    ))
        return edges

    def _extract_inheritance(self, root_node, source_bytes, file_path) -> List[DependencyEdge]:
        """Extract class inheritance: class R(S) -> R INHERITS S."""
        edges = []
        for class_node in self._iter_definitions(root_node, "class_definition"):
            class_name = self._get_definition_name(class_node, source_bytes)
            arg_list = self._find_child(class_node, "argument_list")
            if not arg_list:
                continue
            for child in arg_list.children:
                if child.type in ("identifier", "attribute", "dotted_name"):
                    parent_name = self._node_text(child, source_bytes)
                    if parent_name not in (",", "(", ")"):
                        edges.append(DependencyEdge(
                            source_file=file_path,
                            source_name=class_name,
                            target_name=parent_name,
                            target_module="",
                            edge_type="INHERITS",
                            line_number=class_node.start_point[0] + 1,
                        ))
        return edges

    # ── Helpers ──────────────────────────────────────────────────────────

    def _iter_definitions(self, root_node, def_type: str):
        """Yield all nodes of a given definition type (top-level AND inside classes)."""
        for child in root_node.children:
            if child.type == def_type:
                yield child
            elif child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type == def_type:
                        yield sub
            elif child.type == "class_definition":
                # Walk inside class bodies to find methods
                body = self._find_child(child, "block")
                if body:
                    for class_child in body.children:
                        if class_child.type == def_type:
                            yield class_child
                        elif class_child.type == "decorated_definition":
                            for sub in class_child.children:
                                if sub.type == def_type:
                                    yield sub

    @staticmethod
    def _walk_descendants(node):
        """Walk all descendant nodes (DFS)."""
        stack = list(node.children)
        while stack:
            current = stack.pop()
            yield current
            stack.extend(reversed(current.children))

    @staticmethod
    def _node_text(node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte:node.end_byte].decode("utf-8")

    @staticmethod
    def _get_definition_name(node, source_bytes: bytes) -> str:
        for child in node.children:
            if child.type == "identifier":
                return source_bytes[child.start_byte:child.end_byte].decode("utf-8")
        return "<unknown>"

    @staticmethod
    def _get_call_name(call_node, source_bytes: bytes) -> str:
        if not call_node.children:
            return ""
        func_ref = call_node.children[0]
        if func_ref.type == "identifier":
            return source_bytes[func_ref.start_byte:func_ref.end_byte].decode("utf-8")
        elif func_ref.type == "attribute":
            # e.g. self.method() or cls.method() or module.func()
            full_name = source_bytes[func_ref.start_byte:func_ref.end_byte].decode("utf-8")
            # Strip self./cls. prefix so target matches actual node names
            for prefix in ("self.", "cls."):
                if full_name.startswith(prefix):
                    return full_name[len(prefix):]
            return full_name
        return ""

    @staticmethod
    def _find_child(node, child_type: str):
        for child in node.children:
            if child.type == child_type:
                return child
        return None
