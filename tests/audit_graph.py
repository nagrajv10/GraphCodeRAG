"""Deep audit of the graph structure to find why hybrid isn't beating baseline."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graphcoderag.storage.graph_store import GraphStore

store = GraphStore()

# 1. Overall stats
stats = store.get_graph_stats()
print("=== GRAPH STATS ===")
for k, v in stats.items():
    print(f"  {k}: {v}")

with store.driver.session() as s:
    # 2. What edges does Command have?
    print("\n=== EDGES FROM/TO 'Command' ===")
    r = s.run("""
        MATCH (n {name: 'Command'})-[e]-(m) 
        RETURN type(e) AS edge, n.name AS src, m.name AS tgt, 
               m.chunk_id AS cid, labels(m) AS labels, m.file_path AS fp
        LIMIT 20
    """)
    for rec in r:
        print(f"  {rec['edge']}: {rec['src']} <-> {rec['tgt']} (cid={'YES' if rec['cid'] else 'NO'}, labels={rec['labels']}, file={rec['fp']})")

    # 3. ExternalModule nodes
    print("\n=== ExternalModule NODES (sample) ===")
    r = s.run("MATCH (n:ExternalModule) RETURN n.name, n.module LIMIT 10")
    for rec in r:
        print(f"  ExternalModule: name={rec[0]}, module={rec[1]}")

    # 4. Are ExternalModules connected to real chunk nodes?
    r = s.run("MATCH (ext:ExternalModule)-[e]-(real) WHERE real.chunk_id IS NOT NULL RETURN count(e)")
    print(f"\n=== ExternalModule edges to real nodes: {r.single()[0]}")

    # 5. Cross-file edges (the key question!)
    r = s.run("""
        MATCH (a)-[e]->(b) 
        WHERE a.file_path IS NOT NULL AND b.file_path IS NOT NULL 
        AND a.file_path <> b.file_path 
        RETURN count(e)
    """)
    print(f"=== Cross-file direct edges: {r.single()[0]}")

    # 6. Same-file edges
    r = s.run("""
        MATCH (a)-[e]->(b) 
        WHERE a.file_path IS NOT NULL AND b.file_path IS NOT NULL 
        AND a.file_path = b.file_path 
        RETURN count(e)
    """)
    print(f"=== Same-file edges: {r.single()[0]}")

    # 7. Edges to ExternalModule
    r = s.run("MATCH ()-[e]->(n:ExternalModule) RETURN count(e)")
    print(f"=== Edges pointing TO ExternalModule: {r.single()[0]}")

    # 8. Node label distribution
    print("\n=== NODE LABELS ===")
    r = s.run("MATCH (n) RETURN labels(n) AS lbl, count(n) AS cnt ORDER BY cnt DESC")
    for rec in r:
        print(f"  {rec['lbl']}: {rec['cnt']}")

    # 9. Edge type distribution
    print("\n=== EDGE TYPES ===")
    r = s.run("MATCH ()-[e]->() RETURN type(e) AS t, count(e) AS cnt ORDER BY cnt DESC")
    for rec in r:
        print(f"  {rec['t']}: {rec['cnt']}")

    # 10. Graph expansion from Command chunk_id
    print("\n=== EXPANSION FROM Command (2 hops) ===")
    r = s.run("""
        MATCH (start:Class {name: 'Command', file_path: 'src\\\\click\\\\core.py'})
        MATCH path = (start)-[*1..2]-(neighbor)
        WHERE neighbor <> start AND neighbor.chunk_id IS NOT NULL
        RETURN DISTINCT neighbor.name AS name, neighbor.file_path AS fp,
               length(path) AS dist, labels(neighbor) AS labels
        ORDER BY dist, name
        LIMIT 20
    """)
    for rec in r:
        print(f"  hop={rec['dist']}: {rec['name']} ({rec['fp']}) {rec['labels']}")

    # 11. What about traversal THROUGH ExternalModule?
    print("\n=== EXPANSION THROUGH ExternalModule (3 hops) ===")
    r = s.run("""
        MATCH (start:Class {name: 'Command', file_path: 'src\\\\click\\\\core.py'})
        MATCH path = (start)-[*1..3]-(neighbor)
        WHERE neighbor <> start AND neighbor.chunk_id IS NOT NULL
        AND neighbor.file_path <> start.file_path
        RETURN DISTINCT neighbor.name AS name, neighbor.file_path AS fp,
               length(path) AS dist, labels(neighbor) AS labels
        ORDER BY dist, name
        LIMIT 20
    """)
    cross_file = list(r)
    if cross_file:
        for rec in cross_file:
            print(f"  hop={rec['dist']}: {rec['name']} ({rec['fp']}) {rec['labels']}")
    else:
        print("  NONE — graph CANNOT reach other files! This is the root cause.")

    # 12. Does INHERITS link to actual Class nodes or only ExternalModule?
    print("\n=== INHERITS TARGET INSPECTION ===")
    r = s.run("""
        MATCH (a)-[r:INHERITS]->(b) 
        RETURN labels(a) AS src_labels, a.name AS src, a.file_path AS src_file,
               labels(b) AS tgt_labels, b.name AS tgt, b.file_path AS tgt_file,
               b.chunk_id AS tgt_cid
        LIMIT 15
    """)
    for rec in r:
        print(f"  {rec['src']} ({rec['src_file']}) --INHERITS--> {rec['tgt']} (labels={rec['tgt_labels']}, has_chunk={bool(rec['tgt_cid'])})")

store.close()
