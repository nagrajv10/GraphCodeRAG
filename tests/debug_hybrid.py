"""Debug: trace hybrid retrieval to see graph contribution."""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from graphcoderag.retrieval.hybrid_retriever import HybridRetriever

r = HybridRetriever()
query = "How does Click handle command groups and subcommands?"
results = r.retrieve(query, final_top_k=15)

print(f"Total: {len(results)}")
for i, res in enumerate(results, 1):
    src = res.source
    print(f"  {i}. [{src:6s}] score={res.score:.4f} {res.name or res.display_name} ({res.file_path})")

stats = r.get_retrieval_stats(query)
print(f"\nVector: {stats['vector_results_count']}, Graph: {stats['graph_results_count']}, Overlap: {stats['overlap']}")

# Show graph-only results separately
from graphcoderag.retrieval.graph_retriever import GraphRetriever
from graphcoderag.retrieval.vector_retriever import VectorRetriever

vr = VectorRetriever()
vector_results = vr.retrieve(query, top_k=10)
seed_ids = [x.chunk_id for x in vector_results[:5]]

gr = GraphRetriever()
graph_results = gr.expand_from_chunk_ids(seed_ids, hops=2)

print(f"\nDirect graph expansion: {len(graph_results)} results")
for g in graph_results[:20]:
    print(f"  -> {g.name} ({g.file_path}) dist={g.distance} prox={g.proximity_score:.3f}")

# Show unique files from graph that vector doesn't have
vector_files = set(x.file_path for x in vector_results)
graph_files = set(g.file_path for g in graph_results)
new_files = graph_files - vector_files
print(f"\nNew files discovered by graph: {new_files or 'NONE'}")

gr.close()
r.close()
