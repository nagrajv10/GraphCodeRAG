"""Quick Django-only evaluation - skips Neo4j graph store (too slow for 96k edges)"""
import json, os, sys, time, re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from graphcoderag.evaluation.swebench_runner import (
    load_test_cases, ingest_repo, run_retrieval_eval, run_generation_eval,
    REPOS, K_VALUES,
)

P = lambda *a, **kw: print(*a, **kw, flush=True)

P("="*60)
P("  Django-only evaluation (vector-only, skip graph store)")
P("="*60)

# Check if already ingested
from graphcoderag.storage.vector_store import VectorStore
vs = VectorStore(collection_name="swebench_django")
existing = vs.collection.count()

if existing > 0:
    P(f"  Already ingested ({existing} chunks)")
else:
    # Ingest django - but skip graph store for speed
    from graphcoderag.ingestion.file_scanner import scan_repository
    from graphcoderag.ingestion.ast_parser import PythonASTParser
    from graphcoderag.ingestion.code_chunker import CodeChunker
    from graphcoderag.ingestion.dependency_extractor import DependencyExtractor

    P("  Scanning...")
    py_files = scan_repository("data/repos/django")
    P(f"  Found {len(py_files)} files")

    parser = PythonASTParser()
    chunker = CodeChunker()
    all_chunks = []
    for fi in py_files:
        try:
            tree, src = parser.parse_file(fi.abs_path)
            ast_nodes = parser.extract_functions_and_classes(tree, src)
            chunks = chunker.chunk_file(fi.rel_path, ast_nodes, src)
            all_chunks.extend(chunks)
        except:
            continue

    P(f"  Parsed {len(all_chunks)} chunks")
    P(f"  [SKIP] Neo4j graph store (96k edges too slow)")

    vs_new = VectorStore(collection_name="swebench_django")
    vs_new.add_chunks(all_chunks)
    P(f"  ChromaDB[swebench_django]: {len(all_chunks)} chunks stored")

# Run evaluation
test_cases = load_test_cases()
django_cases = test_cases.get("django", [])
P(f"  {len(django_cases)} test cases")

P("\n  --- Retrieval Metrics ---")
ret_results = run_retrieval_eval("django", "swebench_django", django_cases)

P(f"\n  Retrieval Summary for django:")
P(f"  {'K':>4} | {'Metric':>12} | {'Hybrid':>8} | {'Vector':>8} | {'Delta':>8}")
P(f"  {'----':>4} | {'--------':>12} | {'------':>8} | {'------':>8} | {'-----':>8}")
for kl in [f"K={k}" for k in K_VALUES]:
    agg = ret_results["aggregated"].get(kl, {})
    h = agg.get("hybrid", {})
    v = agg.get("vector", {})
    d = agg.get("delta", {})
    for metric in ["mrr", "recall", "precision", "ndcg", "file_recall", "hit_rate"]:
        label = metric.replace('_', ' ').title()
        P(f"  {kl:>4} | {label:>12} | {h.get(metric,0):>7.3f} | {v.get(metric,0):>7.3f} | {d.get(metric,0):>+7.3f}")
    P()

gen_cases = django_cases[:5]
P(f"\n  --- Generation Quality (first {len(gen_cases)} cases) ---")
gen_results = run_generation_eval("django", "swebench_django", gen_cases)

P(f"\n  Generation Summary for django:")
P(f"  {'Metric':>15} | {'RAG':>8} | {'Vec':>8} | {'Plain':>8}")
for metric in ["accuracy", "completeness", "helpfulness", "avg_score"]:
    r = gen_results["averages"]["rag"].get(metric, 0)
    v = gen_results["averages"]["vec"].get(metric, 0)
    p = gen_results["averages"]["plain"].get(metric, 0)
    P(f"  {metric:>15} | {r:>7.2f} | {v:>7.2f} | {p:>7.2f}")

# Save
result = {"django_retrieval": ret_results, "django_generation": gen_results}
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out = f"evaluation_results/swebench_django_{ts}.json"
os.makedirs("evaluation_results", exist_ok=True)
with open(out, "w") as f:
    json.dump(result, f, indent=2, default=str)
P(f"\nSaved: {out}")
