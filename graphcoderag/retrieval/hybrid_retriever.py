"""
Hybrid Retriever -- Merges vector similarity + graph traversal results.

This is the CORE INNOVATION of GraphCodeRAG:
1. Run vector search to find semantically similar chunks
2. Take the top vector results as seeds and expand via graph traversal
3. Merge both result sets, deduplicate, and re-rank using a combined score

Combined scoring formula:
    If only in vector:  score = raw similarity (no deflation)
    If only in graph:   score = raw proximity (no deflation)
    If in both:         score = (vector_weight * similarity)
                              + (graph_weight * proximity)
                              + overlap_bonus

This ensures the final context includes both:
- Semantically relevant code (from vector search)
- Structurally connected code (from graph traversal)

Usage:
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
    retriever = HybridRetriever()
    results = retriever.retrieve("How does route matching work?", top_k=15)
"""
from typing import List, Optional, Dict
from graphcoderag.retrieval.vector_retriever import VectorRetriever, RetrievalResult
from graphcoderag.retrieval.graph_retriever import GraphRetriever
from graphcoderag.storage.vector_store import VectorStore
from graphcoderag.storage.graph_store import GraphStore
from graphcoderag.config import VECTOR_TOP_K, GRAPH_HOP_DEPTH, FINAL_TOP_K, GRAPH_SEED_COUNT, GRAPH_EDGE_FILTER

import logging
logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Merges vector similarity search with graph structural traversal.

    This is what makes GraphCodeRAG better than standard RAG:
    standard RAG only finds semantically similar text, while this
    also finds structurally related code (callers, callees, parent
    classes, sibling methods, etc.).
    """

    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        graph_store: Optional[GraphStore] = None,
        vector_weight: float = 0.6,
        graph_weight: float = 0.3,
        overlap_bonus: float = 0.1,
        collection_name: Optional[str] = None,
    ):
        """
        Args:
            vector_store: Shared VectorStore instance (created if None).
            graph_store: Shared GraphStore instance (created if None).
            vector_weight: Weight for vector similarity score (default 0.6).
            graph_weight: Weight for graph proximity score (default 0.3).
            overlap_bonus: Bonus for chunks found by both sources (default 0.1).
            collection_name: Optional ChromaDB collection name (for multi-repo eval).
        """
        if vector_store is None and collection_name:
            from graphcoderag.config import VECTOR_BACKEND
            if VECTOR_BACKEND == "faiss":
                from graphcoderag.storage.faiss_store import FaissVectorStore
                vector_store = FaissVectorStore(collection_name=collection_name)
            else:
                from graphcoderag.storage.vector_store import VectorStore
                vector_store = VectorStore(collection_name=collection_name)
        self.vector_retriever = VectorRetriever(vector_store)
        try:
            self.graph_retriever = GraphRetriever(graph_store)
        except Exception as e:
            logger.warning(f"Graph store unavailable ({e}), using vector-only mode")
            self.graph_retriever = None
        self.vector_weight = vector_weight
        self.graph_weight = graph_weight
        self.overlap_bonus = overlap_bonus

    def retrieve(
        self,
        query: str,
        vector_top_k: int = None,
        graph_hops: int = None,
        final_top_k: int = None,
    ) -> List[RetrievalResult]:
        """
        Run the full hybrid retrieval pipeline.

        Steps:
        1. Vector search for semantically similar chunks
        2. File-diversified seeding: pick top-1 per unique file
        3. Expand via graph traversal (multi-hop, edge-type filtered)
        4. Merge, deduplicate, re-rank by combined score
        5. Return top-K final results

        Args:
            query: Natural language question about the codebase.
            vector_top_k: How many vector results to fetch (seeds).
            graph_hops: How many hops to traverse in the graph.
            final_top_k: How many final results to return.

        Returns:
            List of RetrievalResult objects with combined scores.
        """
        v_k = vector_top_k or VECTOR_TOP_K
        g_hops = graph_hops or GRAPH_HOP_DEPTH
        f_k = final_top_k or FINAL_TOP_K

        # Step 1: Vector search
        vector_results = self.vector_retriever.retrieve(query, top_k=v_k)

        if not vector_results:
            return []

        # Step 2: File-diversified seeding — top-1 per unique file
        # Instead of naively taking top-5, pick the best result from each file
        # This ensures graph seeds span multiple files → broader graph expansion
        seed_chunk_ids = self._diversified_seeds(vector_results, max_seeds=GRAPH_SEED_COUNT)

        if self.graph_retriever is not None:
            graph_results = self.graph_retriever.expand_from_chunk_ids(
                seed_chunk_ids, hops=g_hops, edge_types=GRAPH_EDGE_FILTER,
            )
        else:
            graph_results = []

        # Step 3: Merge and score
        merged = self._merge_and_score(vector_results, graph_results, query=query)

        # Step 4: Return top-K (vector results in original order, graph appended)
        return merged[:f_k]

    @staticmethod
    def _diversified_seeds(results: List[RetrievalResult], max_seeds: int) -> List[str]:
        """Pick top-1 result per unique file, up to max_seeds.

        This ensures graph expansion covers multiple files instead of
        clustering all seeds in the same file (which gives identical
        graph neighbors and explains why B_hybrid == B_vec before).
        """
        seen_files = set()
        seeds = []
        for r in results:
            if r.file_path not in seen_files:
                seen_files.add(r.file_path)
                seeds.append(r.chunk_id)
                if len(seeds) >= max_seeds:
                    break
        # If we still have room, fill with remaining top results
        if len(seeds) < max_seeds:
            for r in results:
                if r.chunk_id not in seeds:
                    seeds.append(r.chunk_id)
                    if len(seeds) >= max_seeds:
                        break
        return seeds

    def retrieve_vector_only(
        self, query: str, top_k: int = None
    ) -> List[RetrievalResult]:
        """Vector-only retrieval (for baseline comparison in evaluation)."""
        return self.vector_retriever.retrieve(query, top_k=top_k or FINAL_TOP_K)

    def retrieve_graph_only(
        self, query: str, top_k: int = None, graph_hops: int = None,
    ) -> List[RetrievalResult]:
        """Graph-only retrieval: vector seeds → graph expansion, return only graph results."""
        g_hops = graph_hops or GRAPH_HOP_DEPTH
        f_k = top_k or FINAL_TOP_K

        if self.graph_retriever is None:
            return []

        # Still need vector search to find seed entities
        vector_results = self.vector_retriever.retrieve(query, top_k=GRAPH_SEED_COUNT)
        if not vector_results:
            return []

        seed_ids = [r.chunk_id for r in vector_results[:GRAPH_SEED_COUNT]]
        graph_results = self.graph_retriever.expand_from_chunk_ids(seed_ids, hops=g_hops)

        # Convert to RetrievalResult format
        results = []
        seen = set()
        for gr in graph_results:
            if gr.chunk_id in seen:
                continue
            seen.add(gr.chunk_id)
            results.append(RetrievalResult(
                chunk_id=gr.chunk_id, name=gr.name, file_path=gr.file_path,
                chunk_type=gr.chunk_type, start_line=0, end_line=0,
                source_code="", docstring=gr.docstring or "",
                score=gr.proximity_score, source="graph", distance=gr.distance,
            ))
        self._enrich_graph_results({r.chunk_id: r for r in results})
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:f_k]

    def _merge_and_score(
        self,
        vector_results: List[RetrievalResult],
        graph_results: list,
        query: str = "",
    ) -> List[RetrievalResult]:
        """
        Merge vector and graph results — graph can REPLACE bottom vector results.

        Strategy:
        1. Lock the top half of vector results (never displaced)
        2. Graph chunks compete for the bottom half if their hybrid_score
           (alpha * cosine_sim + (1-alpha) * graph_proximity) exceeds
           the vector result they would replace
        3. Final list is sorted by score: locked top + best of (bottom vec, graph)

        This ensures graph genuinely improves results without hurting top rankings.
        """
        ALPHA = 0.75          # Semantic similarity dominates but graph gets 25% weight
        MIN_SIM_THRESHOLD = 0.20  # Graph chunk must be reasonably relevant (increased for Two-Tier)
        LOCK_RATIO = 0.5      # Protect top 50% of vector results from displacement

        if not vector_results:
            return []

        # ---- Step 1: Split vector results into locked (top) and contestable (bottom) ----
        lock_count = max(1, int(len(vector_results) * LOCK_RATIO))
        locked_results = vector_results[:lock_count]   # Never displaced
        contestable_results = vector_results[lock_count:]  # Can be replaced by better graph chunks

        for r in locked_results:
            r.source = "vector"
        for r in contestable_results:
            r.source = "vector"

        # Track all vector chunk IDs and files
        seen_ids = {r.chunk_id for r in vector_results}
        vector_files = {r.file_path for r in vector_results}

        # ---- Step 2: Identify graph-only chunks ----
        graph_only_chunks = []
        graph_seen = set()
        for gr in graph_results:
            if gr.chunk_id not in seen_ids and gr.chunk_id not in graph_seen:
                graph_only_chunks.append(gr)
                graph_seen.add(gr.chunk_id)

        if not graph_only_chunks or not query:
            # No new graph chunks — return vector as-is with overlap tagging
            graph_chunk_ids = {gr.chunk_id for gr in graph_results}
            for r in locked_results + contestable_results:
                if r.chunk_id in graph_chunk_ids:
                    r.source = "hybrid"
            return locked_results + contestable_results

        # ---- Step 3: Score graph chunks using stored embeddings ----
        graph_candidates = []
        try:
            from graphcoderag.storage.embedding import embed_texts, embed_query
            import numpy as np

            q_emb = embed_query(query)[0]  # (768,), L2-normalized, with query prefix

            # Try to get embeddings from the AST vector store directly
            # This is faster and more accurate than re-embedding chunk names
            ast_store = self.vector_retriever.store

            for gr in graph_only_chunks:
                cos_sim = None

                # Method 1: Look up stored embedding vector by chunk_id
                if hasattr(ast_store, 'get_embedding_by_id'):
                    stored_emb = ast_store.get_embedding_by_id(gr.chunk_id)
                    if stored_emb is not None:
                        cos_sim = float(np.dot(q_emb, stored_emb))

                # Method 2: Fall back to embedding the chunk name
                if cos_sim is None:
                    text = gr.name or gr.chunk_id
                    chunk_emb = embed_texts([text])[0]
                    cos_sim = float(np.dot(q_emb, chunk_emb))

                # SCALE MISMATCH FIX: VectorRetriever returns scores mapped via
                # similarity = 1.0 - (distance / 2.0) where distance = 1.0 - cos_sim
                # This maps raw cos_sim of 0.0 -> 0.5, and 1.0 -> 1.0
                # We MUST apply the exact same mapping to graph chunks!
                distance = 1.0 - cos_sim
                scaled_cos_sim = max(0.0, 1.0 - (distance / 2.0))

                # Skip if not semantically relevant (scaled threshold)
                if scaled_cos_sim < 0.55:
                    continue

                # Hybrid score: semantic + structural
                graph_proximity = 1.0 / (1.0 + gr.distance)
                hybrid_score = ALPHA * scaled_cos_sim + (1 - ALPHA) * graph_proximity

                # Cross-file bonus: graph's core strength
                # Cross-file bonus: graph's core strength
                is_cross_file = gr.file_path not in vector_files
                if is_cross_file:
                    hybrid_score *= 1.15
                    
                # Two-Tier Visualization: How many vector chunks led to this graph node?
                children_count = sum(1 for vr in vector_results if vr.file_path == gr.file_path and vr.chunk_id != gr.chunk_id)
                if children_count == 0 and not is_cross_file:
                    # If it's in the same file but not exact match, count it as related
                    children_count = 1

                result = RetrievalResult(
                    chunk_id=gr.chunk_id,
                    name=gr.name,
                    file_path=gr.file_path,
                    chunk_type=gr.chunk_type,
                    start_line=0, end_line=0,
                    source_code="",
                    docstring=gr.docstring or "",
                    score=hybrid_score,
                    source="graph",
                    distance=gr.distance,
                    children_count=children_count,
                )
                graph_candidates.append(result)

        except Exception as e:
            logger.warning(f"Graph semantic scoring failed: {e}")

        # ---- Step 4: Merge — graph competes with bottom vector results ----
        # Pool = contestable vector results + graph candidates
        # Sort by score, take the best to fill remaining slots
        competition_pool = list(contestable_results) + graph_candidates
        competition_pool.sort(key=lambda r: r.score, reverse=True)

        # How many slots for the competition pool
        remaining_slots = len(vector_results) - lock_count
        # Allow graph to add extra slots (up to 3 bonus chunks beyond original count)
        max_extra = 3
        total_slots = remaining_slots + max_extra
        winners = competition_pool[:total_slots]

        # ---- Step 5: Tag overlap ----
        graph_chunk_ids = {gr.chunk_id for gr in graph_results}
        for r in locked_results:
            if r.chunk_id in graph_chunk_ids:
                r.source = "hybrid"

        # ---- Step 6: Combine locked + winners ----
        final = locked_results + winners
        return final

    def _enrich_graph_results(self, merged: Dict[str, RetrievalResult]):
        """Fetch source code for graph-only results from ChromaDB."""
        graph_only_ids = [
            cid for cid, r in merged.items()
            if not r.source_code and r.source == "graph"
        ]
        if not graph_only_ids:
            return

        # Batch fetch chunk data from vector store by ID
        try:
            store = self.vector_retriever.store
            # Use store.search or get by ID — both FAISS and ChromaDB support this
            if hasattr(store, 'collection'):
                # ChromaDB path
                fetched = store.collection.get(
                    ids=graph_only_ids,
                    include=["documents", "metadatas"],
                )
                if fetched and fetched["ids"]:
                    for i, cid in enumerate(fetched["ids"]):
                        if cid in merged:
                            merged[cid].source_code = fetched["documents"][i]
                            meta = fetched["metadatas"][i]
                            merged[cid].start_line = meta.get("start_line", 0)
                            merged[cid].end_line = meta.get("end_line", 0)
                            if not merged[cid].name:
                                merged[cid].name = meta.get("name", "")
            elif hasattr(store, 'metadata') and isinstance(store.metadata, dict):
                # FAISS path — use stored metadata
                for cid in graph_only_ids:
                    if cid in merged and cid in store.metadata:
                        meta = store.metadata[cid]
                        # In Two-Tier FAISS, raw code is in "source_code", not "document"
                        merged[cid].source_code = meta.get("source_code", "")
                        merged[cid].start_line = meta.get("start_line", 0)
                        merged[cid].end_line = meta.get("end_line", 0)
                        if not merged[cid].name:
                            merged[cid].name = meta.get("name", "")
        except Exception as e:
            logger.warning(f"Failed to enrich graph-only results: {e}")

    def close(self):
        """Close underlying stores."""
        if hasattr(self, 'graph_retriever') and self.graph_retriever:
            try:
                self.graph_retriever.close()
            except Exception:
                pass

    def get_retrieval_stats(
        self, query: str, vector_top_k: int = None, graph_hops: int = None
    ) -> dict:
        """
        Run retrieval and return detailed stats for debugging/evaluation.
        Useful for comparing vector-only vs hybrid performance.
        """
        v_k = vector_top_k or VECTOR_TOP_K
        g_hops = graph_hops or GRAPH_HOP_DEPTH

        # Vector only
        vector_results = self.vector_retriever.retrieve(query, top_k=v_k)

        # Graph expansion
        seed_ids = [r.chunk_id for r in vector_results[:GRAPH_SEED_COUNT]]
        graph_results = self.graph_retriever.expand_from_chunk_ids(seed_ids, hops=g_hops)

        # Hybrid merge
        hybrid_results = self._merge_and_score(vector_results, graph_results, query=query)
        hybrid_results.sort(key=lambda r: r.score, reverse=True)

        # Count sources
        vector_only = sum(1 for r in hybrid_results if r.source == "vector")
        graph_only = sum(1 for r in hybrid_results if r.source == "graph")
        both = sum(1 for r in hybrid_results if r.source == "hybrid")

        return {
            "query": query,
            "vector_results_count": len(vector_results),
            "graph_results_count": len(graph_results),
            "hybrid_merged_count": len(hybrid_results),
            "vector_only": vector_only,
            "graph_only": graph_only,
            "overlap": both,
            "top_5_hybrid": [
                {
                    "name": r.name or r.display_name,
                    "file": r.file_path,
                    "score": round(r.score, 4),
                    "source": r.source,
                }
                for r in hybrid_results[:5]
            ],
        }
