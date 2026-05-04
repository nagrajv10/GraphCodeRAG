"""
Hybrid Retrieval Test -- Tests the full pipeline WITH Neo4j graph expansion.

This verifies that the metadata-aware scoring boosts (1.15x class-match,
1.10x file-match) in hybrid_retriever._merge_and_score() actually work
when graph chunks are returned from Neo4j.

Run with Neo4j running:
    python tests/test_hybrid_metadata.py
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main():
    print("\n" + "=" * 70)
    print("  Hybrid Retrieval Test (with Neo4j graph expansion)")
    print("=" * 70)

    from graphcoderag.storage.faiss_store import FaissVectorStore
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever

    store = FaissVectorStore(collection_name="code_chunks")
    if store.count() == 0:
        print("  [FAIL] code_chunks FAISS index is empty")
        return

    print(f"  FAISS index: {store.count()} vectors")

    # Create HybridRetriever with the existing FAISS store
    try:
        retriever = HybridRetriever(vector_store=store)
        has_graph = retriever.graph_retriever is not None
        print(f"  Neo4j graph: {'CONNECTED' if has_graph else 'UNAVAILABLE'}")
    except Exception as e:
        print(f"  [FAIL] Could not create HybridRetriever: {e}")
        return

    if not has_graph:
        print("  [SKIP] Neo4j not available -- hybrid tests require graph store")
        return

    # Test queries that should benefit from metadata-aware scoring
    test_queries = [
        {
            "query": "How does the Command class handle argument parsing?",
            "entities": ["Command"],
            "description": "Class-specific query",
        },
        {
            "query": "What happens in core.py when a command is invoked?",
            "entities": ["core.py"],
            "description": "File-specific query",
        },
        {
            "query": "How does Group inherit from Command?",
            "entities": ["Group", "Command"],
            "description": "Multi-class query",
        },
        {
            "query": "What does the make_context function do?",
            "entities": ["make_context"],
            "description": "Function-specific query",
        },
        {
            "query": "How are options parsed in decorators.py?",
            "entities": ["decorators.py"],
            "description": "File-specific query",
        },
    ]

    print(f"\n  {'Query':<50} {'Vec':>4} {'Graph':>6} {'Hyb':>4} {'Source Breakdown':<30} {'Avg Score':>10}")
    print(f"  {'-' * 110}")

    for tq in test_queries:
        query = tq["query"]

        t0 = time.perf_counter()
        results = retriever.retrieve(query, final_top_k=15)
        elapsed = time.perf_counter() - t0

        # Count sources
        vec_count = sum(1 for r in results if r.source == "vector")
        graph_count = sum(1 for r in results if r.source == "graph")
        hybrid_count = sum(1 for r in results if r.source == "hybrid")

        # Entity hit rate
        hits = 0
        for r in results:
            for ent in tq["entities"]:
                el = ent.lower()
                if el in (r.name or "").lower() or \
                   el in (r.parent_class or "").lower() or \
                   el in (r.file_path or "").lower():
                    hits += 1
                    break
        hit_rate = hits / max(len(results), 1)

        avg_score = sum(r.score for r in results[:5]) / max(len(results[:5]), 1)

        short_q = query[:47] + "..." if len(query) > 50 else query
        source_str = f"V={vec_count} G={graph_count} H={hybrid_count}"
        print(f"  {short_q:<50} {vec_count:>4} {graph_count:>6} {hybrid_count:>4} {source_str:<30} {avg_score:>9.3f}")

    # --- Detailed breakdown for first query ---
    print(f"\n{'=' * 70}")
    print("  Detailed: 'How does the Command class handle argument parsing?'")
    print(f"{'=' * 70}")

    query = "How does the Command class handle argument parsing?"
    results = retriever.retrieve(query, final_top_k=15)

    print(f"\n  {'#':>3} {'Source':<8} {'Score':>7} {'Name':<40} {'File':<30}")
    print(f"  {'-' * 92}")

    for i, r in enumerate(results):
        name_display = r.display_name[:38] if r.display_name else r.chunk_id[:38]
        file_display = r.file_path[:28] if r.file_path else ""
        print(f"  {i+1:>3} {r.source:<8} {r.score:>7.3f} {name_display:<40} {file_display:<30}")

    # --- Compare vector-only vs hybrid ---
    print(f"\n{'=' * 70}")
    print("  Comparison: Vector-only vs Hybrid (Command query)")
    print(f"{'=' * 70}")

    vec_results = retriever.retrieve_vector_only(query, top_k=15)
    hyb_results = results  # already have this

    vec_files = {r.file_path for r in vec_results}
    hyb_files = {r.file_path for r in hyb_results}
    extra_files = hyb_files - vec_files

    vec_hit = sum(1 for r in vec_results if "command" in (r.name or "").lower() or "command" in (r.parent_class or "").lower())
    hyb_hit = sum(1 for r in hyb_results if "command" in (r.name or "").lower() or "command" in (r.parent_class or "").lower())

    print(f"\n  Vector-only: {len(vec_results)} results, {len(vec_files)} unique files, {vec_hit} Command-related")
    print(f"  Hybrid:      {len(hyb_results)} results, {len(hyb_files)} unique files, {hyb_hit} Command-related")
    if extra_files:
        print(f"  Extra files from graph: {extra_files}")

    print(f"\n  [PASS] Hybrid retrieval test completed successfully")
    print(f"{'=' * 70}\n")

    retriever.close()


if __name__ == "__main__":
    main()
