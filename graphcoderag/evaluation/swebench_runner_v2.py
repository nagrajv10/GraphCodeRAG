"""
SWE-bench Evaluation Runner v2 — 4-Way Controlled Comparison

Pipelines:
  A:       Standard RAG  (recursive char chunking + vector-only)
  B-Vec:   AST-only      (AST chunking + vector-only, no graph)
  B-Hybrid: GraphCodeRAG (AST chunking + hybrid vector + graph)
  C:       Plain LLM     (no retrieval, control group)

Judge: Gemini 2.5 Flash (cross-model, eliminates self-bias)
Metrics: MRR, Recall@K, File Recall@K (retrieval) + accuracy/completeness/helpfulness (generation)
          + pairwise preference with position-swap debiasing

Usage:
    python -m graphcoderag.evaluation.swebench_runner_v2
"""
import json, os, sys, time, re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graphcoderag.evaluation.metrics import (
    compute_mrr, compute_recall_at_k, compute_precision_at_k,
    compute_hit_rate_at_k, compute_ndcg_at_k, compute_file_recall_at_k,
)

P = lambda *a, **kw: print(*a, **kw, flush=True)

# ─────────────────────────────────────────────────────────
REPOS = {
    "click":   {"path": "data/repos/click",         "label": "Small (~20k LOC)"},
    "pytest":  {"path": "data/repos/pytest",         "label": "Medium (~50k LOC)"},
    "sklearn": {"path": "data/repos/scikit-learn",   "label": "Medium (~80k LOC)"},
    "django":  {"path": "data/repos/django",         "label": "Large (~300k LOC)"},
}
K_VALUES = [1, 3, 5, 10]
SWE_DATA = "data/swebench/swebench_lite_selected.json"
CLICK_CUSTOM = "data/swebench/test_cases.json"


def load_test_cases() -> Dict[str, List[Dict]]:
    """Load SWE-bench + custom test cases."""
    cases = {}

    if os.path.exists(CLICK_CUSTOM):
        with open(CLICK_CUSTOM) as f:
            click_data = json.load(f)
        cases["click"] = [{
            "question": c["question"],
            "relevant_files": [f.replace("\\", "/") for f in c.get("relevant_files", [])],
            "instance_id": f"click_custom_{i}",
            "source": "custom",
        } for i, c in enumerate(click_data)]

    if os.path.exists(SWE_DATA):
        with open(SWE_DATA) as f:
            swe = json.load(f)
        repo_map = {
            "django/django": "django",
            "pytest-dev/pytest": "pytest",
            "scikit-learn/scikit-learn": "sklearn",
        }
        for full, short in repo_map.items():
            insts = swe.get("instances", {}).get(full, [])
            if insts:
                cases[short] = [{
                    "question": re.sub(r'\s+', ' ', inst["problem_statement"][:500]).strip(),
                    "relevant_files": [f.replace("\\", "/") for f in inst["relevant_files"]],
                    "instance_id": inst["instance_id"],
                    "source": "swebench_lite",
                } for inst in insts]
    return cases


# Which backend to use — set via --backend=faiss or --backend=chroma
_BACKEND = "faiss"  # Updated by CLI arg


def _get_store(collection_name: str):
    """Create the appropriate vector store based on selected backend."""
    if _BACKEND == "faiss":
        from graphcoderag.storage.faiss_store import FaissVectorStore
        return FaissVectorStore(collection_name=collection_name)
    else:
        from graphcoderag.storage.vector_store import VectorStore
        return VectorStore(collection_name=collection_name)


def ensure_baseline_ingested(repo_key: str) -> str:
    """Ingest repo with character chunking (Pipeline A) if not done."""
    col = f"baseline_{repo_key}_{_BACKEND}"
    vs = _get_store(col)
    if vs.count() > 0:
        P(f"  [A] Baseline already ingested ({vs.count()} chunks)")
        return col

    from graphcoderag.evaluation.baseline_rag import BaselineRAG
    baseline = BaselineRAG(chunk_size=512, chunk_overlap=50)
    repo_path = REPOS[repo_key]["path"]

    if _BACKEND == "faiss":
        # FAISS backend: scan, chunk, then ingest via FAISS store
        chunks = baseline.scan_and_chunk(repo_path)
        P(f"  [A] {len(chunks)} character chunks")
        vs.add_chunks(chunks)
        P(f"  [A] FAISS[{col}]: {vs.count()} vectors (SFR 1024d)")
    else:
        # ChromaDB backend: use existing ingest method
        baseline.ingest(repo_path, col)
    return col


def ensure_ast_ingested(repo_key: str) -> str:
    """Ingest repo with AST chunking (Pipeline B) if not done."""
    col = f"swebench_{repo_key}_{_BACKEND}"
    vs = _get_store(col)
    if vs.count() > 0:
        P(f"  [B] AST already ingested ({vs.count()} chunks)")
        return col

    # Use the existing ingestion function
    from graphcoderag.ingestion.file_scanner import scan_repository
    from graphcoderag.ingestion.ast_parser import PythonASTParser
    from graphcoderag.ingestion.code_chunker import CodeChunker
    from graphcoderag.ingestion.dependency_extractor import DependencyExtractor

    repo_path = REPOS[repo_key]["path"]
    P(f"  [B] Scanning {repo_path}...")
    py_files = scan_repository(repo_path)
    P(f"  [B] {len(py_files)} Python files")

    parser = PythonASTParser()
    chunker = CodeChunker()
    dep_extractor = DependencyExtractor()
    all_chunks, all_edges = [], []

    for fi in py_files:
        try:
            tree, src = parser.parse_file(fi.abs_path)
            ast_nodes = parser.extract_functions_and_classes(tree, src)
            chunks = chunker.chunk_file(fi.rel_path, ast_nodes, src)
            all_chunks.extend(chunks)
            edges = dep_extractor.extract_from_file(tree, src, fi.rel_path)
            all_edges.extend(edges)
        except:
            continue

    P(f"  [B] {len(all_chunks)} AST chunks, {len(all_edges)} edges")

    # Graph store (skip for django due to 96k edge timeout)
    if repo_key != "django":
        try:
            from graphcoderag.storage.graph_store import GraphStore
            gs = GraphStore()
            gs.store_chunks(all_chunks)
            gs.store_edges(all_edges)
            stats = gs.get_graph_stats()
            P(f"  [B] Neo4j: {stats.get('total_nodes',0)} nodes, {stats.get('total_edges',0)} edges")
            gs.close()
        except Exception as e:
            P(f"  [B] Neo4j unavailable: {e}")
    else:
        P(f"  [B] Skipping Neo4j for django (96k edges too slow)")

    vs = _get_store(col)
    vs.add_chunks(all_chunks)
    P(f"  [B] {_BACKEND.upper()}[{col}]: {vs.count()} chunks (SFR 1024d)")
    return col


def retrieve_all_pipelines(query: str, baseline_col: str, ast_col: str, top_k: int = 10):
    """Retrieve from all 3 retrieval pipelines."""
    from graphcoderag.retrieval.vector_retriever import VectorRetriever, RetrievalResult

    # Pipeline A: Standard RAG (char chunking + vector)
    a_store = _get_store(baseline_col)
    a_retriever = VectorRetriever(a_store)
    a_results = a_retriever.retrieve(query, top_k=top_k)
    a_files = [r.file_path.replace("\\", "/") for r in a_results]

    # Pipeline B: AST chunking
    if _BACKEND == "faiss":
        # For FAISS, use VectorRetriever with FaissVectorStore
        b_store = _get_store(ast_col)
        b_retriever = VectorRetriever(b_store)

        # B-Vec: AST + vector-only
        bv_results = b_retriever.retrieve(query, top_k=top_k)
        bv_files = [r.file_path.replace("\\", "/") for r in bv_results]

        # B-Hybrid: For FAISS, use graph expansion on top of vector results
        try:
            from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
            h_retriever = HybridRetriever(vector_store=b_store)
            bh_results = h_retriever.retrieve(query, final_top_k=top_k)
            bh_files = [r.file_path.replace("\\", "/") for r in bh_results]
            h_retriever.close()
        except Exception as e:
            P(f"    [Hybrid fallback to vector-only: {e}]")
            bh_results = bv_results
            bh_files = bv_files
    else:
        from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
        retriever = HybridRetriever(collection_name=ast_col)
        bv_results = retriever.retrieve_vector_only(query, top_k=top_k)
        bv_files = [r.file_path.replace("\\", "/") for r in bv_results]
        bh_results = retriever.retrieve(query, final_top_k=top_k)
        bh_files = [r.file_path.replace("\\", "/") for r in bh_results]
        retriever.close()

    return {
        "A": {"results": a_results, "files": a_files, "num_chunks": len(a_results)},
        "B_vec": {"results": bv_results, "files": bv_files, "num_chunks": len(bv_results)},
        "B_hybrid": {"results": bh_results, "files": bh_files, "num_chunks": len(bh_results)},
    }


def compute_retrieval_metrics(files: List[str], relevant: set, K: int) -> Dict:
    return {
        "mrr": compute_mrr(files, relevant),
        "recall": compute_recall_at_k(files, relevant, K),
        "precision": compute_precision_at_k(files, relevant, K),
        "ndcg": compute_ndcg_at_k(files, relevant, K),
        "file_recall": compute_file_recall_at_k(files, relevant, K),
        "hit_rate": compute_hit_rate_at_k(files, relevant, K),
    }


def run_repo_evaluation(repo_key: str, test_cases: List[Dict], retrieval_only: bool = False) -> Dict:
    """Complete evaluation for one repo across all pipelines."""
    cfg = REPOS[repo_key]
    P(f"\n{'='*65}")
    P(f"  REPO: {repo_key} ({cfg['label']})")
    P(f"{'='*65}")

    # Phase 1: Ingest
    P(f"\n  Phase 1: Ingestion")
    t0 = time.time()
    baseline_col = ensure_baseline_ingested(repo_key)
    ast_col = ensure_ast_ingested(repo_key)
    P(f"  Ingestion completed in {time.time()-t0:.0f}s")

    # Phase 2: Retrieval evaluation
    P(f"\n  Phase 2: Retrieval ({len(test_cases)} queries)")
    retrieval_results = []

    for i, case in enumerate(test_cases):
        q = case["question"]
        relevant = set(case["relevant_files"])
        P(f"    [{i+1}/{len(test_cases)}] {case['instance_id'][:40]}...")

        try:
            pipelines = retrieve_all_pipelines(q, baseline_col, ast_col, max(K_VALUES))
        except Exception as e:
            P(f"      ERROR: {e}")
            pipelines = {
                "A": {"files": []}, "B_vec": {"files": []}, "B_hybrid": {"files": []}
            }

        per_k = {}
        for K in K_VALUES:
            per_k[f"K={K}"] = {}
            for pname in ["A", "B_vec", "B_hybrid"]:
                f = pipelines[pname]["files"][:K]
                per_k[f"K={K}"][pname] = compute_retrieval_metrics(f, relevant, K)

        retrieval_results.append({
            "instance_id": case["instance_id"],
            "relevant_files": list(relevant),
            "files": {p: pipelines[p]["files"][:10] for p in pipelines},
            "num_chunks": {p: pipelines[p].get("num_chunks", 0) for p in pipelines},
            "metrics": per_k,
        })

    # Aggregate retrieval
    agg_ret = {}
    for K in K_VALUES:
        kl = f"K={K}"
        agg_ret[kl] = {}
        for pname in ["A", "B_vec", "B_hybrid"]:
            agg = {}
            for m in ["mrr", "recall", "precision", "ndcg", "file_recall", "hit_rate"]:
                vals = [r["metrics"][kl][pname][m] for r in retrieval_results]
                agg[m] = round(sum(vals) / len(vals), 4) if vals else 0
            agg_ret[kl][pname] = agg

    # Aggregate avg chunks retrieved
    avg_chunks = {}
    for pname in ["A", "B_vec", "B_hybrid"]:
        chunks = [r["num_chunks"].get(pname, 0) for r in retrieval_results]
        avg_chunks[pname] = round(sum(chunks) / len(chunks), 1) if chunks else 0

    # Print retrieval summary — full metrics table
    P(f"\n  +------+--------------+--------+--------+--------+-----------+")
    P(f"  |  Retrieval Summary -- {repo_key:10s}                          |")
    P(f"  +------+--------------+--------+--------+--------+-----------+")
    P(f"  |  K   |    Metric    | Std RAG|AST+Vec | Hybrid | D(H-A)    |")
    P(f"  +------+--------------+--------+--------+--------+-----------+")
    for kl in [f"K={k}" for k in K_VALUES]:
        a = agg_ret[kl]["A"]
        bv = agg_ret[kl]["B_vec"]
        bh = agg_ret[kl]["B_hybrid"]
        for m in ["mrr", "recall", "file_recall", "hit_rate", "ndcg"]:
            label = m.replace('_', ' ').title()
            delta = bh[m] - a[m]
            P(f"  | {kl:>4} | {label:>12} | {a[m]:>5.3f} | {bv[m]:>5.3f} | {bh[m]:>5.3f} | {delta:>+8.3f} |")
        P(f"  +------+--------------+--------+--------+--------+-----------+")
    # Avg chunks
    P(f"  | Avg Chunks Retrieved  | {avg_chunks['A']:>5.1f} | {avg_chunks['B_vec']:>5.1f} | {avg_chunks['B_hybrid']:>5.1f} |           |")
    P(f"  +------+--------------+--------+--------+--------+-----------+")

    # Phase 3: Generation + Judge (skip if retrieval-only mode)
    if retrieval_only:
        P(f"\n  Phase 3: SKIPPED (--retrieval-only mode)")
        gen_agg = {p: {"accuracy": 0, "completeness": 0, "helpfulness": 0, "avg_score": 0}
                   for p in ["A", "B_vec", "B_hybrid", "C"]}
        gen_results = []
        pairwise_wins = {"A_vs_Bh": {"A": 0, "B": 0, "tie": 0}}
        return {
            "repo": repo_key, "label": cfg["label"],
            "retrieval": {"aggregated": agg_ret, "avg_chunks": avg_chunks, "per_case": retrieval_results},
            "generation": {"aggregated": gen_agg, "per_case": gen_results},
            "pairwise": pairwise_wins,
        }

    gen_cases = test_cases[:3]
    P(f"\n  Phase 3: Generation + OpenAI Judge ({len(gen_cases)} cases)")

    from graphcoderag.generation.generator import LLMGenerator
    from graphcoderag.evaluation.llm_judge import OpenAIJudge
    from graphcoderag.evaluation.baseline_rag import BaselineRAG
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever

    generator = LLMGenerator()
    judge = OpenAIJudge()
    baseline_rag = BaselineRAG()

    gen_results = []
    pairwise_wins = {"A_vs_Bh": {"A": 0, "B": 0, "tie": 0}}

    for i, case in enumerate(gen_cases):
        q = case["question"]
        gt_files = case["relevant_files"]
        P(f"    [{i+1}/{len(gen_cases)}] {case['instance_id'][:35]}...")

        try:
            # Retrieve for each pipeline
            from graphcoderag.retrieval.vector_retriever import VectorRetriever
            a_store = _get_store(baseline_col)
            a_retriever = VectorRetriever(a_store)
            a_ctx = a_retriever.retrieve(q, top_k=10)

            b_store = _get_store(ast_col)
            if _BACKEND == "faiss":
                bv_retriever = VectorRetriever(b_store)
                bv_ctx = bv_retriever.retrieve(q, top_k=10)
                try:
                    retriever = HybridRetriever(vector_store=b_store)
                    bh_ctx = retriever.retrieve(q, final_top_k=10)
                    retriever.close()
                except Exception:
                    bh_ctx = bv_ctx
            else:
                retriever = HybridRetriever(collection_name=ast_col)
                bv_ctx = retriever.retrieve_vector_only(q, top_k=10)
                bh_ctx = retriever.retrieve(q, final_top_k=10)
                retriever.close()

            # Generate answers
            a_answer = generator.generate(q, a_ctx[:10])
            bv_answer = generator.generate(q, bv_ctx[:10])
            bh_answer = generator.generate(q, bh_ctx[:10])
            c_answer = generator.generate_raw(
                f"You are a Python expert. Answer this question:\n\n{q}",
                max_tokens=1500
            )

            # Judge all 4 with OpenAI
            a_scores = judge.rate_answer(q, a_answer, gt_files)
            bv_scores = judge.rate_answer(q, bv_answer, gt_files)
            bh_scores = judge.rate_answer(q, bh_answer, gt_files)
            c_scores = judge.rate_answer(q, c_answer, gt_files)

            # Pairwise: Standard RAG (A) vs Hybrid (B-Hybrid)
            pw1 = judge.pairwise_compare(q, a_answer, bh_answer, gt_files, debias=True)
            w = pw1["winner"]
            if w == "A":
                pairwise_wins["A_vs_Bh"]["A"] += 1
            elif w == "B":
                pairwise_wins["A_vs_Bh"]["B"] += 1
            else:
                pairwise_wins["A_vs_Bh"]["tie"] += 1

            pw2 = {"winner": "n/a", "reasoning": "skipped to conserve API calls"}

        except Exception as e:
            P(f"      ERROR: {e}")
            zeroes = {"accuracy": 0, "completeness": 0, "helpfulness": 0, "avg_score": 0, "reasoning": str(e)}
            a_scores = bv_scores = bh_scores = c_scores = zeroes
            pw1 = pw2 = {"winner": "tie", "reasoning": str(e)}

        gen_results.append({
            "instance_id": case["instance_id"],
            "scores": {"A": a_scores, "B_vec": bv_scores, "B_hybrid": bh_scores, "C": c_scores},
            "pairwise_A_vs_Bh": pw1,
            "pairwise_Bv_vs_Bh": pw2,
        })

        P(f"      A:{a_scores.get('avg_score',0):.1f}  B-Vec:{bv_scores.get('avg_score',0):.1f}  "
          f"B-Hyb:{bh_scores.get('avg_score',0):.1f}  Plain:{c_scores.get('avg_score',0):.1f}  "
          f"PW: {pw1.get('winner','?')}")

    # Aggregate generation
    n = len(gen_results) or 1
    gen_agg = {}
    for pname in ["A", "B_vec", "B_hybrid", "C"]:
        gen_agg[pname] = {}
        for m in ["accuracy", "completeness", "helpfulness", "avg_score"]:
            gen_agg[pname][m] = round(
                sum(r["scores"][pname].get(m, 0) for r in gen_results) / n, 2)

    # Print generation summary
    P(f"\n  +-----------------+--------+--------+--------+--------+----------+")
    P(f"  |  Generation Quality (OpenAI Judge) -- {repo_key:10s}             |")
    P(f"  +-----------------+--------+--------+--------+--------+----------+")
    P(f"  |      Metric     | Std RAG|AST+Vec | Hybrid | Plain  | D(H-A)   |")
    P(f"  +-----------------+--------+--------+--------+--------+----------+")
    for m in ["accuracy", "completeness", "helpfulness", "avg_score"]:
        a = gen_agg["A"][m]
        bv = gen_agg["B_vec"][m]
        bh = gen_agg["B_hybrid"][m]
        c = gen_agg["C"][m]
        d = bh - a
        P(f"  | {m:>15} | {a:>5.2f} | {bv:>5.2f} | {bh:>5.2f} | {c:>5.2f} | {d:>+7.2f} |")
    P(f"  +-----------------+--------+--------+--------+--------+----------+")

    # Print pairwise
    P(f"\n  Pairwise Preference (position-swap debiased):")
    pw = pairwise_wins["A_vs_Bh"]
    P(f"    Std RAG vs Hybrid:  StdRAG wins={pw['A']}, Hybrid wins={pw['B']}, Ties={pw['tie']}")

    return {
        "repo": repo_key,
        "label": cfg["label"],
        "retrieval": {"aggregated": agg_ret, "per_case": retrieval_results},
        "generation": {"aggregated": gen_agg, "per_case": gen_results},
        "pairwise": pairwise_wins,
    }


def main():
    global _BACKEND

    # Parse --backend flag
    for arg in sys.argv:
        if arg.startswith("--backend="):
            _BACKEND = arg.split("=")[1].lower()

    P("=" * 70)
    P("  GraphCodeRAG -- SWE-bench Evaluation v2")
    P(f"  Backend: {_BACKEND.upper()} | Embeddings: nomic-ai/CodeRankEmbed (768d)")
    P("  4-Way Comparison: Std RAG | AST+Vec | Hybrid | Plain LLM")
    P("  Judge: OpenAI GPT-4o-Mini (cross-model, position-swap debiased)")
    P("=" * 70)

    # Check for --retrieval-only flag
    retrieval_only = "--retrieval-only" in sys.argv

    test_cases = load_test_cases()
    P(f"\nLoaded: {', '.join(f'{k}: {len(v)}' for k,v in test_cases.items())}")
    if retrieval_only:
        P("  MODE: retrieval-only (skipping OpenAI judge)")

    results = {"timestamp": datetime.now().isoformat(), "backend": _BACKEND, "embedding_model": "nomic-ai/CodeRankEmbed", "mode": "retrieval_only" if retrieval_only else "full", "repos": {}}

    for repo_key in ["click", "pytest"]:
        if repo_key not in test_cases:
            continue
        results["repos"][repo_key] = run_repo_evaluation(repo_key, test_cases[repo_key], retrieval_only)

    # Save
    os.makedirs("evaluation_results", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"evaluation_results/swebench_v2_{ts}.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    P(f"\nResults saved: {out}")

    # Cross-repo summary
    P(f"\n{'='*85}")
    P("  CROSS-REPO SUMMARY @ K=10")
    P(f"{'='*85}")
    P(f"  {'Repo':>10} | {'Size':>15} | MRR(A) | MRR(Bh) | NDCG@10(Bh) | Rec@10(Bh) | FR@10(Bh)")
    P(f"  {'----':>10} | {'----':>15} | {'---':>6} | {'---':>7} | {'---':>11} | {'---':>10} | {'---':>9}")
    for rk in ["click", "pytest"]:
        if rk not in results["repos"]:
            continue
        r = results["repos"][rk]["retrieval"]["aggregated"].get("K=10", {})
        a = r.get("A", {})
        bh = r.get("B_hybrid", {})
        P(f"  {rk:>10} | {REPOS[rk]['label']:>15} | {a.get('mrr',0):>5.3f} | "
          f"{bh.get('mrr',0):>6.3f} | {bh.get('ndcg',0):>11.3f} | {bh.get('recall',0):>10.3f} | "
          f"{bh.get('file_recall',0):>8.1%}")

    P(f"\n{'='*70}")
    P(f"  OpenAI Judge API calls: {results.get('judge_calls', 'N/A')}")
    P(f"{'='*70}")


if __name__ == "__main__":
    main()
