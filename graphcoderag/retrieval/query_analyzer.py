"""
Query Analyzer — Lightweight entity extraction from natural language queries.

Parses a user query to identify mentioned code entities (class names, file
names, function names) by matching against the set of entities known to the
FAISS metadata index.  This is intentionally simple string matching — the
universe of possible entities is bounded by what was ingested, so NLP is
unnecessary.

Usage:
    from graphcoderag.retrieval.query_analyzer import QueryAnalyzer
    analyzer = QueryAnalyzer()
    entities = analyzer.extract_entities(
        "How does the Command class parse arguments?",
        known_classes={"Command", "Group"},
        known_files={"core.py", "cli.py"},
        known_functions={"parse_args", "invoke"},
    )
    # entities.classes == ["Command"]
"""
import re
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class QueryEntities:
    """Entities extracted from a natural language query."""
    classes: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    raw_query: str = ""

    @property
    def has_entities(self) -> bool:
        """True if any entities were extracted."""
        return bool(self.classes or self.files or self.functions)


# Matches tokens like identifiers, file names (foo.py), dotted paths (Cls.method)
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


class QueryAnalyzer:
    """Extracts code entity mentions from a user query.

    The extraction is purely string-matching against known entities
    pulled from the FAISS metadata indexes.  It never calls an LLM.
    """

    def extract_entities(
        self,
        query: str,
        known_classes: Set[str],
        known_files: Set[str],
        known_functions: Set[str],
    ) -> QueryEntities:
        """
        Identify class names, file names, and function names in *query*.

        Args:
            query: Raw natural language question.
            known_classes: Set of class names present in the FAISS index.
            known_files: Set of file paths (basenames OK) in the FAISS index.
            known_functions: Set of function/method names in the FAISS index.

        Returns:
            QueryEntities with de-duplicated lists.
        """
        entities = QueryEntities(raw_query=query)

        # Build case-insensitive lookup maps  (lower -> original)
        cls_map = {c.lower(): c for c in known_classes if c}
        file_map = {f.lower(): f for f in known_files if f}
        # Also index basenames so "core.py" matches "src/core.py"
        file_basename_map = {}
        for f in known_files:
            if f:
                basename = f.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
                file_basename_map[basename.lower()] = f
        func_map = {fn.lower(): fn for fn in known_functions if fn}

        tokens = _TOKEN_RE.findall(query)

        seen_cls: set = set()
        seen_files: set = set()
        seen_funcs: set = set()

        for token in tokens:
            low = token.lower()

            # --- Handle dotted tokens like "Command.parse_args" ---
            if "." in token:
                parts = token.split(".")
                for part in parts:
                    p_low = part.lower()
                    if p_low in cls_map and p_low not in seen_cls:
                        entities.classes.append(cls_map[p_low])
                        seen_cls.add(p_low)
                    if p_low in func_map and p_low not in seen_funcs:
                        entities.functions.append(func_map[p_low])
                        seen_funcs.add(p_low)
                # Also check the full dotted name as a file (e.g., "config.py")
                if low in file_map and low not in seen_files:
                    entities.files.append(file_map[low])
                    seen_files.add(low)
                elif low in file_basename_map and low not in seen_files:
                    entities.files.append(file_basename_map[low])
                    seen_files.add(low)
                continue

            # --- Plain token matching ---
            # Check file (with or without .py suffix)
            if low in file_map and low not in seen_files:
                entities.files.append(file_map[low])
                seen_files.add(low)
            elif low in file_basename_map and low not in seen_files:
                entities.files.append(file_basename_map[low])
                seen_files.add(low)
            elif (low + ".py") in file_basename_map and low not in seen_files:
                entities.files.append(file_basename_map[low + ".py"])
                seen_files.add(low)

            # Check class (case-insensitive, but prefer exact casing)
            if low in cls_map and low not in seen_cls:
                entities.classes.append(cls_map[low])
                seen_cls.add(low)

            # Check function
            if low in func_map and low not in seen_funcs:
                entities.functions.append(func_map[low])
                seen_funcs.add(low)

        return entities
