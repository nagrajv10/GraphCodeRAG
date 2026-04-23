"""
Graph Retriever -- Expands retrieval via multi-hop graph traversal in Neo4j.

Responsibilities:
- Given seed entity names or chunk_ids from vector search results,
  traverse the knowledge graph to find structurally related code
- Compute proximity scores based on hop distance (closer = higher score)
- Return RetrievalResult objects compatible with the hybrid merger

Key insight: Vector search finds semantically similar code, but may miss
structurally related code (e.g., a function that calls the matched function,
or the class that contains it). Graph traversal fills this gap.

Usage:
    from graphcoderag.retrieval.graph_retriever import GraphRetriever
    retriever = GraphRetriever()
    results = retriever.expand(seed_names=["Command"], hops=2)
    results = retriever.expand_from_chunk_ids(["abc123"], hops=2)
"""
from dataclasses import dataclass
from typing import List, Optional, Set
from graphcoderag.storage.graph_store import GraphStore
from graphcoderag.config import GRAPH_HOP_DEPTH


class GraphRetriever:
    """Retrieves structurally related code via Neo4j graph traversal."""

    def __init__(self, graph_store: Optional[GraphStore] = None):
        self.store = graph_store or GraphStore()
        self._owns_store = graph_store is None  # Track if we created it

    def expand(
        self,
        seed_names: List[str],
        hops: int = None,
        edge_types: Optional[List[str]] = None,
    ) -> List["GraphRetrievalResult"]:
        """
        Expand from seed entity names via graph traversal.

        Args:
            seed_names: List of entity names to start traversal from.
            hops: Maximum traversal depth. Defaults to config GRAPH_HOP_DEPTH.
            edge_types: Optional filter for edge types to follow.

        Returns:
            List of GraphRetrievalResult with proximity scores.
        """
        depth = hops or GRAPH_HOP_DEPTH
        seen_ids: Set[str] = set()
        results = []

        for name in seed_names:
            neighbors = self.store.get_neighbors(
                entity_name=name,
                hops=depth,
                edge_types=edge_types,
            )
            for neighbor in neighbors:
                chunk_id = neighbor.get("chunk_id")
                # Skip nodes without chunk_ids (e.g., ExternalModule nodes)
                if not chunk_id or chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)

                # Proximity score: inverse of distance (closer = higher)
                distance = neighbor.get("distance", depth)
                proximity = 1.0 / (1.0 + distance)

                results.append(GraphRetrievalResult(
                    chunk_id=chunk_id,
                    name=neighbor.get("name", ""),
                    file_path=neighbor.get("file_path", ""),
                    chunk_type=neighbor.get("chunk_type", ""),
                    docstring=neighbor.get("docstring", ""),
                    distance=distance,
                    proximity_score=proximity,
                ))

        # Sort by proximity (closest first)
        results.sort(key=lambda r: r.proximity_score, reverse=True)
        return results

    def expand_from_chunk_ids(
        self,
        chunk_ids: List[str],
        hops: int = None,
        edge_types: Optional[List[str]] = None,
    ) -> List["GraphRetrievalResult"]:
        """
        Expand from chunk_ids (typically from vector search results).

        Uses a single batched Cypher query (UNWIND) instead of
        one query per seed for better performance.

        Args:
            chunk_ids: List of chunk IDs to start traversal from.
            hops: Maximum traversal depth.
            edge_types: Optional edge type filter (e.g., ["CALLS", "IMPORTS", "INHERITS"]).

        Returns:
            List of GraphRetrievalResult with proximity scores.
        """
        depth = hops or GRAPH_HOP_DEPTH
        seed_set = set(chunk_ids)
        results = []

        # Single batched query with edge-type filtering
        neighbors = self.store.get_neighbors_by_chunk_ids_batch(
            chunk_ids=chunk_ids, hops=depth, edge_types=edge_types,
        )

        seen_ids: Set[str] = set(chunk_ids)  # Don't return seeds
        for neighbor in neighbors:
            neighbor_id = neighbor.get("chunk_id")
            if not neighbor_id or neighbor_id in seen_ids:
                continue
            seen_ids.add(neighbor_id)

            distance = neighbor.get("distance", depth)
            proximity = 1.0 / (1.0 + distance)

            results.append(GraphRetrievalResult(
                chunk_id=neighbor_id,
                name=neighbor.get("name", ""),
                file_path=neighbor.get("file_path", ""),
                chunk_type=neighbor.get("chunk_type", ""),
                docstring=neighbor.get("docstring", ""),
                distance=distance,
                proximity_score=proximity,
            ))

        results.sort(key=lambda r: r.proximity_score, reverse=True)
        return results

    def close(self):
        """Close the graph store if we own it."""
        if self._owns_store:
            self.store.close()


@dataclass
class GraphRetrievalResult:
    """A graph traversal result with proximity metadata."""
    chunk_id: str
    name: str
    file_path: str
    chunk_type: str
    docstring: str
    distance: int              # Hop count from seed
    proximity_score: float     # 1/(1+distance), higher = closer
