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
    children_count: int = 0    # Added for Two-Tier UI visualization

    @property
    def display_name(self) -> str:
        if self.parent_class:
            return f"{self.parent_class}.{self.name}"
        return self.name


class VectorRetriever:
    """Retrieves code chunks via semantic similarity search."""

    def __init__(self, vector_store: Optional[VectorStore] = None):
        if vector_store:
            self.store = vector_store
        else:
            from graphcoderag.config import VECTOR_BACKEND
            if VECTOR_BACKEND == "faiss":
                from graphcoderag.storage.faiss_store import FaissVectorStore
                self.store = FaissVectorStore()
            else:
                self.store = VectorStore()

    def retrieve(self, query: str, top_k: int = None) -> List[RetrievalResult]:
        """
        Search for code chunks semantically similar to the query.
        Implements Two-Tier Retrieval: fetches child chunks, resolves them
        to their full AST parent, and aggregates scores for deduplication.
        """
        k = top_k or VECTOR_TOP_K

        if self.store.count() == 0:
            return []

        # Over-fetch for deduplication (Gap 4)
        fetch_k = k * 3
        raw_results = self.store.search(query, top_k=fetch_k)

        # Dictionary to store resolved parent results and aggregate scores
        # Key: chunk_id, Value: dict containing 'result': RetrievalResult, 'child_scores': list of floats
        resolved_results = {}

        for r in raw_results:
            meta = r.get("metadata", {})
            
            # Convert FAISS/Chroma distance to similarity
            dist = r.get("distance", 1.0)
            similarity = max(0.0, 1.0 - (dist / 2.0))

            # Parent Resolution (Gap 3)
            parent_id = meta.get("parent_id")
            if parent_id and hasattr(self.store, "get_chunk_metadata"):
                parent_meta = self.store.get_chunk_metadata(parent_id)
                if parent_meta:
                    resolved_id = parent_id
                    resolved_meta = parent_meta
                else:
                    resolved_id = r["chunk_id"]
                    resolved_meta = meta
            else:
                resolved_id = r["chunk_id"]
                resolved_meta = meta

            if resolved_id not in resolved_results:
                # FAISS uses metadata to store source_code; Chroma uses 'document'
                source_code = resolved_meta.get("source_code", r.get("document", ""))
                res = RetrievalResult(
                    chunk_id=resolved_id,
                    name=resolved_meta.get("name", ""),
                    file_path=resolved_meta.get("file_path", ""),
                    chunk_type=resolved_meta.get("chunk_type", ""),
                    start_line=resolved_meta.get("start_line", 0),
                    end_line=resolved_meta.get("end_line", 0),
                    source_code=source_code,
                    docstring=resolved_meta.get("docstring", ""),
                    score=similarity,
                    source="vector",
                    parent_class=resolved_meta.get("parent_class", ""),
                )
                resolved_results[resolved_id] = {
                    "result": res,
                    "child_scores": [similarity]
                }
            else:
                # Add score for later aggregation
                resolved_results[resolved_id]["child_scores"].append(similarity)

        # Apply bounded score aggregation
        final_results = []
        for v in resolved_results.values():
            res = v["result"]
            child_scores = v["child_scores"]
            n = len(child_scores)
            
            # Score Aggregation with Hard Cap
            max_score = max(child_scores)
            bonus = min(0.15, 0.05 * (n - 1))
            res.score = min(1.0, max_score + bonus)
            
            final_results.append(res)

        # Sort by aggregated score descending
        final_results.sort(key=lambda x: x.score, reverse=True)
        
        # Truncate back to original requested top_K
        return final_results[:k]
