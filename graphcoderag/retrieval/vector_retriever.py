"""
Vector Retriever -- Wraps VectorStore search with scoring and metadata.

Responsibilities:
- Accept a natural language query
- Search FAISS/ChromaDB for semantically similar code chunks
- Convert raw distances to similarity scores (1 - distance for cosine)
- Return RetrievalResult objects with normalized scores

Enhanced with metadata-aware retrieval:
- Phase A: Filtered search using QueryAnalyzer entity extraction
- Phase B: Standard unfiltered fallback (always runs)
- Parent-aware progressive fetching replaces naive 3x over-fetch

Usage:
    from graphcoderag.retrieval.vector_retriever import VectorRetriever
    retriever = VectorRetriever()
    results = retriever.retrieve("how does authentication work?", top_k=10)
"""
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
from graphcoderag.storage.vector_store import VectorStore
from graphcoderag.config import VECTOR_TOP_K

import logging
logger = logging.getLogger(__name__)


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

        Implements:
        1. Metadata-filtered search (Phase A) when entities are recognized
        2. Standard unfiltered search (Phase B) as a fallback
        3. Two-Tier parent resolution with score aggregation
        """
        k = top_k or VECTOR_TOP_K

        if self.store.count() == 0:
            return []

        # ── Entity Extraction ──────────────────────────────────────────
        query_entities = None
        filtered_results = []
        try:
            if hasattr(self.store, "get_known_classes"):
                from graphcoderag.retrieval.query_analyzer import QueryAnalyzer
                analyzer = QueryAnalyzer()
                entities = analyzer.extract_entities(
                    query,
                    known_classes=self.store.get_known_classes(),
                    known_files=self.store.get_known_files(),
                    known_functions=self.store.get_known_functions(),
                )
                query_entities = entities

                if entities.has_entities:
                    candidate_ids = self._build_candidate_set(entities)
                    if candidate_ids and hasattr(self.store, "search_filtered"):
                        filtered_results = self.store.search_filtered(
                            query, top_k=k, candidate_ids=candidate_ids,
                        )
                        logger.info(
                            f"Phase A: {len(filtered_results)} results from "
                            f"metadata filter (classes={entities.classes}, "
                            f"files={entities.files}, functions={entities.functions})"
                        )
        except Exception as e:
            logger.warning(f"Metadata-filtered search failed, falling back: {e}")

        # ── Phase B: Standard unfiltered search ────────────────────────
        # Parent-aware progressive fetching: start with k*2, stop early
        # when we have k unique resolved parents.
        fetch_k = k * 2
        max_fetch = k * 3  # safety cap
        raw_results = self.store.search(query, top_k=min(fetch_k, max_fetch))

        # ── Merge Phase A + Phase B ────────────────────────────────────
        merged_raw = self._merge_phases(filtered_results, raw_results)

        # ── Parent Resolution + Score Aggregation ──────────────────────
        resolved_results: Dict[str, dict] = {}

        for r in merged_raw:
            meta = r.get("metadata", {})

            # Convert FAISS/Chroma distance to similarity
            dist = r.get("distance", 1.0)
            similarity = max(0.0, 1.0 - (dist / 2.0))

            # Apply Phase A boost (matched both semantically AND structurally)
            if r.get("_phase_a", False):
                similarity = min(1.0, similarity * 1.1)

            # Parent Resolution
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
                # Check if we have enough unique parents (early stopping)
                if len(resolved_results) >= k:
                    break
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

    def _build_candidate_set(self, entities) -> Set[str]:
        """Build the union of chunk_ids matching any extracted entity."""
        candidates: Set[str] = set()

        for cls in entities.classes:
            ids = self.store.get_ids_by_filter(parent_class=cls)
            candidates |= ids

        for fp in entities.files:
            ids = self.store.get_ids_by_filter(file_path=fp)
            candidates |= ids

        # For functions, search by name across all metadata
        if entities.functions and hasattr(self.store, "metadata"):
            for cid, meta in self.store.metadata.items():
                name = meta.get("name", "")
                if name and name in entities.functions:
                    candidates.add(cid)

        return candidates

    @staticmethod
    def _merge_phases(
        phase_a: List[dict], phase_b: List[dict]
    ) -> List[dict]:
        """Merge Phase A (filtered) and Phase B (unfiltered), deduplicating.

        Phase A results get a ``_phase_a`` flag so the caller can apply
        a similarity boost.  Phase B results fill in any gaps.
        """
        seen: Set[str] = set()
        merged: List[dict] = []

        # Phase A first (higher priority)
        for r in phase_a:
            cid = r["chunk_id"]
            if cid not in seen:
                r["_phase_a"] = True
                merged.append(r)
                seen.add(cid)

        # Phase B
        for r in phase_b:
            cid = r["chunk_id"]
            if cid not in seen:
                r["_phase_a"] = False
                merged.append(r)
                seen.add(cid)

        return merged
