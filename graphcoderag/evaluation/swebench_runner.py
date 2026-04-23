"""
SWE-bench Lite Evaluation Runner for GraphCodeRAG

Evaluates GraphCodeRAG (AST chunking + graph) vs Standard RAG (recursive chunking)
across 3 repos of different sizes using real SWE-bench bug reports.

Methodology:
  - Each repo is ingested ONCE into both pipelines
  - SWE-bench problem_statements serve as queries
  - Ground truth: the files modified in the actual fix (from the patch)
  - Metrics: MRR, Recall@K, Precision@K, NDCG@K, File Recall@K

Usage:
    python -m graphcoderag.evaluation.swebench_runner
"""
import json
import os
import sys
import time
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graphcoderag.config import CHROMA_PERSIST_DIR
from graphcoderag.evaluation.metrics import (
    compute_mrr, compute_recall_at_k, compute_precision_at_k,
    compute_hit_rate_at_k, compute_ndcg_at_k, compute_file_recall_at_k,
)

logger = logging.getLogger(__name__)
P = lambda *a, **kw: print(*a, **kw, flush=True)

# ─────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────
REPOS = {
    "click": {
        "path": "data/repos/click",
        "label": "Small (~20k LOC)",
        "collection": "swebench_click",
    },
    "pytest": {
        "path": "data/repos/pytest",
        "label": "Medium (~50k LOC)",
        "collection": "swebench_pytest",
    },
    "sklearn": {
        "path": "data/repos/scikit-learn",
        "label": "Medium (~80k LOC)",
        "collection": "swebench_sklearn",
    },
    "django": {
        "path": "data/repos/django",
        "label": "Large (~300k LOC)",
        "collection": "swebench_django",
    },
}

SWE_DATA_FILE = "data/swebench/swebench_lite_selected.json"
CLICK_CUSTOM_FILE = "data/swebench/test_cases.json"

K_VALUES = [1, 3, 5, 10]


def load_test_cases() -> Dict[str, List[Dict]]:
    """Load SWE-bench instances + custom Click test cases."""
    cases = {}

    # Custom Click cases (already in our format)
    if os.path.exists(CLICK_CUSTOM_FILE):
        with open(CLICK_CUSTOM_FILE) as f:
            click_data = json.load(f)
        cases["click"] = []
        for c in click_data:
            cases["click"].append({
                "question": c["question"],
                "relevant_files": [f.replace("\\", "/") for f in c.get("relevant_files", [])],
                "instance_id": "click_custom",
                "source": "custom",
            })

    # SWE-bench Lite instances
    if os.path.exists(SWE_DATA_FILE):
        with open(SWE_DATA_FILE) as f:
            swe_data = json.load(f)

        repo_map = {
            "django/django": "django",
            "pytest-dev/pytest": "pytest",
            "scikit-learn/scikit-learn": "sklearn",
        }
        for repo_full, repo_short in repo_map.items():
            instances = swe_data.get("instances", {}).get(repo_full, [])
            if not instances:
                continue
            cases[repo_short] = []
            for inst in instances:
                # Truncate problem statement for query (first ~300 chars)
                q = inst["problem_statement"][:400].strip()
                q = re.sub(r'\s+', ' ', q)  # Collapse whitespace
                cases[repo_short].append({
                    "question": q,
                    "relevant_files": [f.replace("\\", "/") for f in inst["relevant_files"]],
                    "instance_id": inst["instance_id"],
                    "source": "swebench_lite",
                })
    return cases


def ingest_repo(repo_key: str, collection_name: str) -> int:
    """Ingest a repo into ChromaDB with a specific collection name."""
    from graphcoderag.ingestion.file_scanner import scan_repository
    from graphcoderag.ingestion.ast_parser import PythonASTParser
    from graphcoderag.ingestion.code_chunker import CodeChunker
    from graphcoderag.ingestion.dependency_extractor import DependencyExtractor
    from graphcoderag.storage.vector_store import VectorStore

    repo_cfg = REPOS[repo_key]
    repo_path = repo_cfg["path"]

    P(f"\n  Scanning {repo_path}...")
    py_files = scan_repository(repo_path)
    P(f"  Found {len(py_files)} Python files")

    parser = PythonASTParser()
    chunker = CodeChunker()
    dep_extractor = DependencyExtractor()
    all_chunks = []
    all_edges = []

    for file_info in py_files:
        try:
            tree, source_code = parser.parse_file(file_info.abs_path)
            ast_nodes = parser.extract_functions_and_classes(tree, source_code)
            chunks = chunker.chunk_file(file_info.rel_path, ast_nodes, source_code)
            all_chunks.extend(chunks)
            edges = dep_extractor.extract_from_file(tree, source_code, file_info.rel_path)
            all_edges.extend(edges)
        except Exception:
            continue

    P(f"  Parsed: {len(all_chunks)} chunks, {len(all_edges)} edges")

    # Store in Neo4j (shared graph)
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        gs.store_chunks(all_chunks)
        gs.store_edges(all_edges)
        stats = gs.get_graph_stats()
        P(f"  Neo4j: {stats.get('total_nodes',0)} nodes, {stats.get('total_edges',0)} edges")
        gs.close()
    except Exception as e:
        P(f"  [WARN] Neo4j unavailable: {e}")

    # Store in ChromaDB with specific collection
    vs = VectorStore(collection_name=collection_name)
    vs.add_chunks(all_chunks)
    P(f"  ChromaDB[{collection_name}]: {len(all_chunks)} chunks stored")

    return len(all_chunks)


def run_retrieval_eval(
    repo_key: str,
    collection_name: str,
    test_cases: List[Dict],
) -> Dict[str, Any]:
    """Run retrieval evaluation for one repo."""
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(collection_name=collection_name)

    results_per_case = []
    for i, case in enumerate(test_cases):
        q = case["question"]
        relevant = set(f.replace("\\", "/") for f in case["relevant_files"])

        P(f"    [{i+1}/{len(test_cases)}] {case.get('instance_id', 'custom')[:40]}...")

        try:
            # GraphCodeRAG (hybrid)
            hybrid_results = retriever.retrieve(q, final_top_k=max(K_VALUES))
            hybrid_files = [r.file_path.replace("\\", "/") for r in hybrid_results]

            # Vector-only baseline
            vector_results = retriever.retrieve_vector_only(q, top_k=max(K_VALUES))
            vector_files = [r.file_path.replace("\\", "/") for r in vector_results]
        except Exception as e:
            P(f"      ERROR: {e}")
            hybrid_files, vector_files = [], []

        # Compute metrics at each K
        per_k = {}
        for K in K_VALUES:
            hf = hybrid_files[:K]
            vf = vector_files[:K]
            per_k[f"K={K}"] = {
                "hybrid": {
                    "mrr": compute_mrr(hf, relevant),
                    "recall": compute_recall_at_k(hf, relevant, K),
                    "precision": compute_precision_at_k(hf, relevant, K),
                    "ndcg": compute_ndcg_at_k(hf, relevant, K),
                    "file_recall": compute_file_recall_at_k(hf, relevant, K),
                    "hit_rate": compute_hit_rate_at_k(hf, relevant, K),
                },
                "vector": {
                    "mrr": compute_mrr(vf, relevant),
                    "recall": compute_recall_at_k(vf, relevant, K),
                    "precision": compute_precision_at_k(vf, relevant, K),
                    "ndcg": compute_ndcg_at_k(vf, relevant, K),
                    "file_recall": compute_file_recall_at_k(vf, relevant, K),
                    "hit_rate": compute_hit_rate_at_k(vf, relevant, K),
                },
            }

        # Source distribution
        sources = {}
        for r in hybrid_results:
            sources[r.source] = sources.get(r.source, 0) + 1

        results_per_case.append({
            "instance_id": case.get("instance_id", ""),
            "question": q[:120],
            "relevant_files": list(relevant),
            "hybrid_files": hybrid_files[:10],
            "vector_files": vector_files[:10],
            "sources": sources,
            "metrics": per_k,
        })

    retriever.close()

    # Aggregate metrics
    aggregated = {}
    for K in K_VALUES:
        kl = f"K={K}"
        agg = {"hybrid": {}, "vector": {}}
        for path in ["hybrid", "vector"]:
            for metric in ["mrr", "recall", "precision", "ndcg", "file_recall", "hit_rate"]:
                values = [r["metrics"][kl][path][metric] for r in results_per_case]
                agg[path][metric] = sum(values) / len(values) if values else 0
        agg["delta"] = {m: round(agg["hybrid"][m] - agg["vector"][m], 4)
                        for m in agg["hybrid"]}
        aggregated[kl] = agg

    return {
        "repo": repo_key,
        "num_cases": len(test_cases),
        "aggregated": aggregated,
        "per_case": results_per_case,
    }


def run_generation_eval(
    repo_key: str,
    collection_name: str,
    test_cases: List[Dict],
) -> Dict[str, Any]:
    """Run generation quality eval using LLM-as-Judge (Qwen local)."""
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
    from graphcoderag.generation.generator import LLMGenerator
    from graphcoderag.evaluation.llm_judge import LLMJudge

    retriever = HybridRetriever(collection_name=collection_name)
    generator = LLMGenerator()
    judge = LLMJudge(generator)

    gen_results = []
    for i, case in enumerate(test_cases):
        q = case["question"]
        P(f"    [{i+1}/{len(test_cases)}] Generating for {case.get('instance_id', '')[:35]}...")

        try:
            # Retrieve context
            hybrid_results = retriever.retrieve(q, final_top_k=10)
            vector_results = retriever.retrieve_vector_only(q, top_k=10)

            # Generate answers
            rag_answer = generator.generate(q, hybrid_results[:10])
            vec_answer = generator.generate(q, vector_results[:10])
            plain_answer = generator.generate_raw(
                f"You are a Python expert. Answer this question:\n\n{q}",
                max_tokens=1500
            )

            # Judge all three
            ref = case.get("reference_answer", "")
            rag_scores = judge.rate_answer(q, rag_answer, "", ref)
            vec_scores = judge.rate_answer(q, vec_answer, "", ref)
            plain_scores = judge.rate_answer(q, plain_answer, "", ref)
        except Exception as e:
            P(f"      ERROR: {e}")
            rag_scores = vec_scores = plain_scores = {
                "accuracy": 0, "completeness": 0, "helpfulness": 0,
                "avg_score": 0, "reasoning": str(e)
            }
            rag_answer = vec_answer = plain_answer = f"[Error: {e}]"

        gen_results.append({
            "instance_id": case.get("instance_id", ""),
            "question": q[:120],
            "rag_scores": rag_scores,
            "vec_scores": vec_scores,
            "plain_scores": plain_scores,
        })

        ra = rag_scores.get("avg_score", 0)
        va = vec_scores.get("avg_score", 0)
        pa = plain_scores.get("avg_score", 0)
        P(f"      RAG: {ra:.1f}  Vec: {va:.1f}  Plain: {pa:.1f}")

    retriever.close()

    # Aggregate generation scores
    n = len(gen_results) or 1
    paths = {"rag": "rag_scores", "vec": "vec_scores", "plain": "plain_scores"}
    avgs = {}
    for label, skey in paths.items():
        avgs[label] = {}
        for metric in ["accuracy", "completeness", "helpfulness", "avg_score"]:
            avgs[label][metric] = round(
                sum(r[skey].get(metric, 0) for r in gen_results) / n, 2
            )

    return {
        "repo": repo_key,
        "num_cases": len(gen_results),
        "averages": avgs,
        "per_case": gen_results,
    }


def run_swebench_evaluation():
    """Main entry point for the SWE-bench evaluation."""
    P("=" * 70)
    P("  GraphCodeRAG — SWE-bench Lite Evaluation")
    P("  3-Repo Comparison: GraphRAG vs Standard Vector RAG")
    P("=" * 70)

    test_cases = load_test_cases()
    P(f"\nLoaded test cases:")
    for repo, cases in test_cases.items():
        P(f"  {repo}: {len(cases)} instances")

    results = {
        "timestamp": datetime.now().isoformat(),
        "repos": {},
    }

    # Phase 1: Ingest repos that need it
    for repo_key in ["click", "pytest", "sklearn", "django"]:
        if repo_key not in test_cases:
            continue
        cfg = REPOS.get(repo_key)
        if not cfg:
            continue

        P(f"\n{'='*60}")
        P(f"  REPO: {repo_key} ({cfg['label']})")
        P(f"{'='*60}")

        collection = cfg["collection"]

        # Check if already ingested
        from graphcoderag.storage.vector_store import VectorStore
        vs = VectorStore(collection_name=collection)
        existing = vs.collection.count()
        if existing > 0:
            P(f"  [SKIP] Already ingested ({existing} chunks in {collection})")
        else:
            P(f"  Ingesting {repo_key}...")
            t0 = time.time()
            ingest_repo(repo_key, collection)
            P(f"  Ingestion took {time.time()-t0:.1f}s")

        # Phase 2: Retrieval evaluation
        P(f"\n  --- Retrieval Metrics ---")
        ret_results = run_retrieval_eval(repo_key, collection, test_cases[repo_key])

        # Print retrieval summary
        P(f"\n  Retrieval Summary for {repo_key}:")
        P(f"  {'K':>4} | {'Metric':>12} | {'Hybrid':>8} | {'Vector':>8} | {'Delta':>8}")
        P(f"  {'----':>4} | {'--------':>12} | {'------':>8} | {'------':>8} | {'-----':>8}")
        for kl in [f"K={k}" for k in K_VALUES]:
            agg = ret_results["aggregated"].get(kl, {})
            h = agg.get("hybrid", {})
            v = agg.get("vector", {})
            d = agg.get("delta", {})
            for metric in ["mrr", "recall", "precision", "ndcg", "file_recall", "hit_rate"]:
                label = metric.replace('_', ' ').title()
                hv = h.get(metric, 0)
                vv = v.get(metric, 0)
                dv = d.get(metric, 0)
                P(f"  {kl:>4} | {label:>12} | {hv:>7.3f} | {vv:>7.3f} | {dv:>+7.3f}")
            P()

        # Phase 3: Generation quality (sample 5 per repo to save time)
        gen_cases = test_cases[repo_key][:5]  # First 5 for generation
        P(f"\n  --- Generation Quality (first {len(gen_cases)} cases) ---")
        gen_results = run_generation_eval(repo_key, collection, gen_cases)

        # Print generation summary
        P(f"\n  Generation Summary for {repo_key}:")
        P(f"  {'Metric':>15} | {'RAG':>8} | {'Vec':>8} | {'Plain':>8}")
        for metric in ["accuracy", "completeness", "helpfulness", "avg_score"]:
            r = gen_results["averages"]["rag"].get(metric, 0)
            v = gen_results["averages"]["vec"].get(metric, 0)
            p = gen_results["averages"]["plain"].get(metric, 0)
            P(f"  {metric:>15} | {r:>7.2f} | {v:>7.2f} | {p:>7.2f}")

        results["repos"][repo_key] = {
            "retrieval": ret_results,
            "generation": gen_results,
        }

    # Save results
    os.makedirs("evaluation_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"evaluation_results/swebench_eval_{ts}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    P(f"\nResults saved: {out_file}")

    # ═══════════════════════════════════════════════════════
    #  CROSS-REPO SUMMARY
    # ═══════════════════════════════════════════════════════
    P(f"\n{'='*70}")
    P("  CROSS-REPO EVALUATION SUMMARY")
    P(f"{'='*70}")

    P(f"\n  {'Repo':>12} | {'Size':>15} | {'MRR(H)':>8} | {'MRR(V)':>8} | {'Delta':>8} | {'FR@10(H)':>9} | {'FR@10(V)':>9}")
    P(f"  {'----':>12} | {'----':>15} | {'------':>8} | {'------':>8} | {'-----':>8} | {'-------':>9} | {'-------':>9}")
    for repo_key in ["click", "pytest", "sklearn", "django"]:
        if repo_key not in results.get("repos", {}):
            continue
        cfg = REPOS[repo_key]
        ret = results["repos"][repo_key]["retrieval"]
        k10 = ret["aggregated"].get("K=10", {})
        h = k10.get("hybrid", {})
        v = k10.get("vector", {})
        d = k10.get("delta", {})
        P(f"  {repo_key:>12} | {cfg['label']:>15} | {h.get('mrr',0):>7.3f} | {v.get('mrr',0):>7.3f} | {d.get('mrr',0):>+7.3f} | {h.get('file_recall',0):>8.1%} | {v.get('file_recall',0):>8.1%}")

    P(f"\n{'='*70}")
    return results


if __name__ == "__main__":
    run_swebench_evaluation()
