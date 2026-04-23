"""
Vector Retriever -- Wraps VectorStore search with scoring and metadata.

Responsibilities:
- Accept a natural language query
- Search ChromaDB for semantically similar code chunks
- Convert raw distances to similarity scores (1 - distance for cosine)
- Return RetrievalResult objects with normalized scores

Usage:
    from graphcoderag.retrieval.vector_retriever import VectorRetriever
    retriever = VectorRetriever()
    results = retriever.retrieve("how does authentication work?", top_k=10)
"""
from dataclasses import dataclass, field
from typing import List, Optional
from graphcoderag.storage.vector_store import VectorStore
from graphcoderag.config import VECTOR_TOP_K


@dataclass
class RetrievalResult:
    """A single retrieval result with metadata and scoring."""
    chunk_id: str
    name: str
    file_path: str
    chunk_type: str
    start_line: int
    end_line: int
    source_code: str           # The actual code content
    docstring: str
    score: float               # Normalized similarity score (0-1, higher is better)
    source: str                # "vector", "graph", or "hybrid"
    distance: int = 0          # Graph hop distance (0 for vector results)
    parent_class: str = ""

    @property
    def display_name(self) -> str:
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name


class VectorRetriever:
    """Retrieves code chunks via semantic similarity search."""

    def __init__(self, vector_store: Optional[VectorStore] = None):
        self.store = vector_store or VectorStore()

    def retrieve(self, query: str, top_k: int = None) -> List[RetrievalResult]:
        """
        Search for code chunks semantically similar to the query.

        Args:
            query: Natural language question about the codebase.
            top_k: Number of results to return. Defaults to config VECTOR_TOP_K.

        Returns:
            List of RetrievalResult objects sorted by score (highest first).
        """
        k = top_k or VECTOR_TOP_K

        if self.store.count() == 0:
            return []

        raw_results = self.store.search(query, top_k=k)

        results = []
        for r in raw_results:
            meta = r["metadata"]
            # ChromaDB cosine distance: 0 = identical, 2 = opposite
            # Convert to similarity: 1 - (distance / 2) for [0, 1] range
            similarity = max(0.0, 1.0 - (r["distance"] / 2.0))

            results.append(RetrievalResult(
                chunk_id=r["chunk_id"],
                name=meta.get("name", ""),
                file_path=meta.get("file_path", ""),
                chunk_type=meta.get("chunk_type", ""),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0),
                source_code=r["document"],
                docstring=meta.get("docstring", ""),
                score=similarity,
                source="vector",
                parent_class=meta.get("parent_class", ""),
            ))

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results
