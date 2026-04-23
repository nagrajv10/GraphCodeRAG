"""
Graph Store -- Neo4j interface for storing and querying the code knowledge graph.

Responsibilities:
- Connect to Neo4j and manage sessions
- Create nodes (Function, Class, Module) with properties
- Create edges (IMPORTS, CALLS, CONTAINS, INHERITS)
- Execute Cypher queries for multi-hop traversal
- Clear/reset the graph
- Report graph statistics

Fixed issues:
- #1: Edge type allowlist prevents Cypher injection
- #2: CALLS scoped by file_path; IMPORTS/INHERITS intentionally cross-file
- #3: IMPORTS 2-phase: resolves to real nodes first, ExternalModule fallback
- #9: UNWIND batching for 10-100x faster Neo4j writes

Usage:
    from graphcoderag.storage.graph_store import GraphStore
    store = GraphStore()
    store.store_chunks(chunks)
    store.store_edges(edges)
    neighbors = store.get_neighbors("my_func", hops=2)
    store.close()
"""
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase
from graphcoderag.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Fix #1: Allowlist of valid edge types to prevent Cypher injection
ALLOWED_EDGE_TYPES = frozenset({"IMPORTS", "CALLS", "CONTAINS", "INHERITS"})
ALLOWED_NODE_LABELS = frozenset({"Function", "Class", "Module", "CodeEntity"})
NODE_LABELS_FOR_STATS = ["Function", "Class", "Module", "ExternalModule"]


class GraphStore:
    """Neo4j graph database interface for the code knowledge graph."""

    def __init__(self, uri=None, user=None, password=None):
        self.driver = GraphDatabase.driver(
            uri or NEO4J_URI,
            auth=(user or NEO4J_USER, password or NEO4J_PASSWORD),
        )
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create indexes for fast lookups on name, chunk_id, and file_path."""
        with self.driver.session() as session:
            # Composite indexes for name + file_path (Fix #2: scoped matching)
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Function) ON (n.name)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Function) ON (n.chunk_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Function) ON (n.file_path)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Class) ON (n.name)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Class) ON (n.chunk_id)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Class) ON (n.file_path)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Module) ON (n.name)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:Module) ON (n.file_path)")
            session.run("CREATE INDEX IF NOT EXISTS FOR (n:ExternalModule) ON (n.name)")

    def clear(self):
        """Delete all nodes and edges from the graph."""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")

    def store_chunks(self, chunks: list):
        """
        Store code chunks as nodes in the graph using UNWIND batching.
        Fix #9: Batched operations instead of one-query-per-chunk.

        Args:
            chunks: List of CodeChunk objects.
        """
        with self.driver.session() as session:
            # Batch by node label for type-safe MERGE
            for chunk_type, label in [("function", "Function"), ("class", "Class"), ("module", "Module")]:
                # Fix #1: label comes from hardcoded allowlist, never from user input
                batch = [
                    {
                        "chunk_id": c.chunk_id,
                        "name": c.display_name,
                        "file_path": c.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                        "docstring": c.docstring or "",
                        "signature": c.signature or "",
                        "parent_class": c.parent_class or "",
                        "chunk_type": c.chunk_type,
                    }
                    for c in chunks if c.chunk_type == chunk_type
                ]
                if not batch:
                    continue

                session.run(
                    f"""
                    UNWIND $batch AS chunk
                    MERGE (n:{label} {{chunk_id: chunk.chunk_id}})
                    SET n.name = chunk.name,
                        n.file_path = chunk.file_path,
                        n.start_line = chunk.start_line,
                        n.end_line = chunk.end_line,
                        n.docstring = chunk.docstring,
                        n.signature = chunk.signature,
                        n.parent_class = chunk.parent_class,
                        n.chunk_type = chunk.chunk_type
                    """,
                    batch=batch,
                )

    def store_edges(self, edges: list):
        """
        Store dependency edges in the graph using batched operations.

        Key design decisions:
        - IMPORTS: Resolves to actual graph nodes first (cross-file bridges!),
          falls back to ExternalModule only for truly external deps (stdlib etc.)
        - INHERITS: Links to real Class/Function nodes first (any file),
          falls back to ExternalModule for unresolved base classes.
        - CALLS: Still same-file scoped to prevent false positives on common names.
        - CONTAINS: Method nodes get derived chunk_ids so they're traversable.
        - All edge types validated against allowlist to prevent Cypher injection.

        Args:
            edges: List of DependencyEdge objects.
        """
        # Separate edges by type for batched, type-specific queries
        imports_batch = []
        calls_batch = []
        contains_batch = []
        inherits_batch = []

        for edge in edges:
            if edge.edge_type not in ALLOWED_EDGE_TYPES:
                continue

            entry = {
                "source_file": edge.source_file,
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "target_module": edge.target_module,
                "line_number": edge.line_number,
            }

            if edge.edge_type == "IMPORTS":
                imports_batch.append(entry)
            elif edge.edge_type == "CALLS":
                calls_batch.append(entry)
            elif edge.edge_type == "CONTAINS":
                contains_batch.append(entry)
            elif edge.edge_type == "INHERITS":
                inherits_batch.append(entry)

        with self.driver.session() as session:
            # ── IMPORTS ──────────────────────────────────────────────────
            # Phase 1: Try to resolve to ACTUAL nodes in the graph (cross-file bridges!)
            # e.g., decorators.py imports "Command" → links to Class{Command, core.py}
            if imports_batch:
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a:Module {file_path: edge.source_file})
                    MATCH (b {name: edge.target_name})
                    WHERE b.chunk_id IS NOT NULL AND b <> a
                    MERGE (a)-[r:IMPORTS]->(b)
                    SET r.line_number = edge.line_number
                    """,
                    batch=imports_batch,
                )
                # Phase 2: For truly external deps (stdlib, third-party), create ExternalModule
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a:Module {file_path: edge.source_file})
                    WHERE NOT EXISTS {
                        MATCH (a)-[:IMPORTS]->(x {name: edge.target_name})
                        WHERE x.chunk_id IS NOT NULL
                    }
                    MERGE (b:ExternalModule {name: edge.target_name, module: edge.target_module})
                    MERGE (a)-[r:IMPORTS]->(b)
                    SET r.line_number = edge.line_number
                    """,
                    batch=imports_batch,
                )

            # ── CALLS ────────────────────────────────────────────────────
            # Same-file scoped to prevent false positives with common names
            if calls_batch:
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a {name: edge.source_name, file_path: edge.source_file})
                    MATCH (b {name: edge.target_name, file_path: edge.source_file})
                    WHERE a <> b
                    MERGE (a)-[r:CALLS]->(b)
                    SET r.source_file = edge.source_file,
                        r.line_number = edge.line_number
                    """,
                    batch=calls_batch,
                )

            # ── CONTAINS ─────────────────────────────────────────────────
            # Methods get derived chunk_ids so they're traversable by graph retrieval
            if contains_batch:
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a {name: edge.source_name, file_path: edge.source_file})
                    WHERE a.chunk_id IS NOT NULL
                    MERGE (b:Function {name: edge.target_name, file_path: edge.source_file})
                    ON CREATE SET b.chunk_type = 'method',
                                  b.parent_class = edge.source_name,
                                  b.chunk_id = a.chunk_id + '_' + edge.target_name
                    MERGE (a)-[r:CONTAINS]->(b)
                    SET r.line_number = edge.line_number
                    """,
                    batch=contains_batch,
                )

            # ── INHERITS ─────────────────────────────────────────────────
            # Phase 1: Try to find the actual Class/Function node (any file)
            # e.g., Group inherits Command → links to Class{Command, core.py}
            if inherits_batch:
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a {name: edge.source_name, file_path: edge.source_file})
                    MATCH (b {name: edge.target_name})
                    WHERE b <> a AND b.chunk_id IS NOT NULL
                    MERGE (a)-[r:INHERITS]->(b)
                    SET r.source_file = edge.source_file,
                        r.line_number = edge.line_number
                    """,
                    batch=inherits_batch,
                )
                # Phase 2: For unresolved (stdlib base classes), create ExternalModule
                session.run(
                    """
                    UNWIND $batch AS edge
                    MATCH (a {name: edge.source_name, file_path: edge.source_file})
                    WHERE NOT EXISTS { MATCH (a)-[:INHERITS]->() }
                    MERGE (b:ExternalModule {name: edge.target_name, module: edge.target_module})
                    MERGE (a)-[r:INHERITS]->(b)
                    SET r.source_file = edge.source_file,
                        r.line_number = edge.line_number
                    """,
                    batch=inherits_batch,
                )

    def get_neighbors(
        self, entity_name: str, hops: int = 2, edge_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Traverse the graph from a starting entity and return neighbors up to N hops.

        Args:
            entity_name: Name of the starting node.
            hops: Maximum number of hops (default 2).
            edge_types: Optional list of edge types to follow.
                        Default: all types.

        Returns:
            List of dicts with neighbor info: name, file_path, chunk_id,
            docstring, distance (hop count).
        """
        edge_filter = ""
        if edge_types:
            # Fix #1: Validate edge types before interpolation
            validated = [et for et in edge_types if et in ALLOWED_EDGE_TYPES]
            if validated:
                edge_filter = ":" + "|".join(validated)

        query = f"""
        MATCH (start {{name: $entity_name}})
        MATCH path = (start)-[{edge_filter}*1..{hops}]-(neighbor)
        WHERE neighbor <> start
        RETURN DISTINCT neighbor.name AS name,
               neighbor.file_path AS file_path,
               neighbor.chunk_id AS chunk_id,
               neighbor.docstring AS docstring,
               neighbor.chunk_type AS chunk_type,
               length(path) AS distance
        ORDER BY distance ASC
        """

        with self.driver.session() as session:
            result = session.run(query, entity_name=entity_name)
            return [dict(record) for record in result]

    def get_neighbors_by_chunk_id(
        self, chunk_id: str, hops: int = 2
    ) -> List[Dict[str, Any]]:
        """Traverse graph starting from a specific chunk_id."""
        query = f"""
        MATCH (start {{chunk_id: $chunk_id}})
        MATCH path = (start)-[*1..{hops}]-(neighbor)
        WHERE neighbor <> start AND neighbor.chunk_id IS NOT NULL
        RETURN DISTINCT neighbor.name AS name,
               neighbor.file_path AS file_path,
               neighbor.chunk_id AS chunk_id,
               neighbor.docstring AS docstring,
               neighbor.chunk_type AS chunk_type,
               length(path) AS distance
        ORDER BY distance ASC
        """
        with self.driver.session() as session:
            result = session.run(query, chunk_id=chunk_id)
            return [dict(record) for record in result]

    def get_neighbors_by_chunk_ids_batch(
        self, chunk_ids: List[str], hops: int = 2,
        edge_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Batch version: traverse graph from MULTIPLE chunk_ids in one query.

        Uses UNWIND to process all seeds in a single Cypher call,
        replacing the N+1 pattern of calling get_neighbors_by_chunk_id per seed.

        Args:
            chunk_ids: List of chunk IDs to start traversal from.
            hops: Maximum traversal depth.
            edge_types: Optional list of edge types to follow (e.g., ["CALLS", "IMPORTS"]).
                        Filters out CONTAINS by default to reduce same-class noise.
        """
        if not chunk_ids:
            return []

        # Build edge type filter for Cypher
        edge_filter = ""
        if edge_types:
            validated = [et for et in edge_types if et in ALLOWED_EDGE_TYPES]
            if validated:
                edge_filter = ":" + "|".join(validated)

        query = f"""
        UNWIND $chunk_ids AS seed_id
        MATCH (start {{chunk_id: seed_id}})
        MATCH path = (start)-[{edge_filter}*1..{hops}]-(neighbor)
        WHERE neighbor <> start
          AND neighbor.chunk_id IS NOT NULL
          AND NOT neighbor.chunk_id IN $chunk_ids
        RETURN DISTINCT neighbor.name AS name,
               neighbor.file_path AS file_path,
               neighbor.chunk_id AS chunk_id,
               neighbor.docstring AS docstring,
               neighbor.chunk_type AS chunk_type,
               min(length(path)) AS distance
        ORDER BY distance ASC
        """
        with self.driver.session() as session:
            result = session.run(query, chunk_ids=chunk_ids)
            return [dict(record) for record in result]

    def get_graph_stats(self) -> Dict[str, int]:
        """Return node and edge counts by type."""
        stats = {}
        with self.driver.session() as session:
            # Node counts
            for label in NODE_LABELS_FOR_STATS:
                result = session.run(f"MATCH (n:{label}) RETURN count(n) AS cnt")
                record = result.single()
                stats[f"nodes_{label}"] = record["cnt"] if record else 0

            # Edge counts
            for edge_type in ALLOWED_EDGE_TYPES:
                result = session.run(
                    f"MATCH ()-[r:{edge_type}]->() RETURN count(r) AS cnt"
                )
                record = result.single()
                stats[f"edges_{edge_type}"] = record["cnt"] if record else 0

            # Totals
            result = session.run("MATCH (n) RETURN count(n) AS cnt")
            record = result.single()
            stats["total_nodes"] = record["cnt"] if record else 0

            result = session.run("MATCH ()-[r]->() RETURN count(r) AS cnt")
            record = result.single()
            stats["total_edges"] = record["cnt"] if record else 0

        return stats

    def close(self):
        """Close the Neo4j driver connection."""
        self.driver.close()
