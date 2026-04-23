"""
GraphCodeRAG - Full Evaluation Pipeline
========================================
Compares: GraphCodeRAG (hybrid) vs Vector-only vs Plain LLM
Metrics: File Recall, Hit Rate, MRR, NDCG + LLM Judge (Accuracy, Completeness, Helpfulness)
"""
import os, sys, json, time, traceback
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from dotenv import load_dotenv
load_dotenv()

P = lambda *a, **kw: print(*a, **kw, flush=True)

# ── SWE-bench-inspired test cases for Click codebase ──
BENCHMARK = [
    {
        "question": "How does Click's Group class handle subcommand routing when invoke() is called?",
        "relevant_files": ["src/click/core.py"],
        "reference_answer": "Group.invoke() resolves the subcommand via resolve_command(), creates a child context, and delegates.",
        "category": "control_flow",
    },
    {
        "question": "What is the class hierarchy of BaseCommand, Command, MultiCommand, and Group?",
        "relevant_files": ["src/click/core.py"],
        "reference_answer": "BaseCommand -> Command (leaf) and MultiCommand -> Group (subcommands).",
        "category": "architecture",
    },
    {
        "question": "How does Click handle type conversion for parameters?",
        "relevant_files": ["src/click/types.py", "src/click/core.py"],
        "reference_answer": "Click uses ParamType subclasses. Built-in: STRING, INT, FLOAT, BOOL, UUID, Path, Choice, DateTime.",
        "category": "type_system",
    },
    {
        "question": "How does CliRunner work for testing CLI applications?",
        "relevant_files": ["src/click/testing.py"],
        "reference_answer": "CliRunner creates isolated env with captured IO, invokes commands, returns Result with output and exit_code.",
        "category": "testing",
    },
    {
        "question": "What decorators does Click provide and how do they work?",
        "relevant_files": ["src/click/decorators.py", "src/click/core.py"],
        "reference_answer": "@click.command(), @click.group(), @click.option(), @click.argument() wrap functions into Command objects.",
        "category": "api_surface",
    },
    {
        "question": "How does Click parse command-line arguments?",
        "relevant_files": ["src/click/parser.py", "src/click/core.py"],
        "reference_answer": "Click uses OptionParser to process argv, split options/arguments, handle short/long forms.",
        "category": "parsing",
    },
    {
        "question": "How does Click handle shell completion?",
        "relevant_files": ["src/click/shell_completion.py"],
        "reference_answer": "ShellComplete subclasses for bash/zsh/fish. Completions generated for commands, params, types.",
        "category": "completion",
    },
    {
        "question": "What exception hierarchy does Click use?",
        "relevant_files": ["src/click/exceptions.py", "src/click/core.py"],
        "reference_answer": "ClickException base -> UsageError, BadParameter, MissingParameter, Abort, FileError.",
        "category": "error_handling",
    },
    {
        "question": "How does Click's Context object work?",
        "relevant_files": ["src/click/core.py", "src/click/globals.py"],
        "reference_answer": "Context holds command, parent, params. get_current_context() from thread-local stack. Tree structure.",
        "category": "state_management",
    },
    {
        "question": "How does Click format help text?",
        "relevant_files": ["src/click/formatting.py", "src/click/utils.py", "src/click/core.py"],
        "reference_answer": "HelpFormatter wraps, indents, builds definition lists. Auto-generated from docstrings and params.",
        "category": "help_system",
    },
    {
        "question": "How does Click handle environment variables for options?",
        "relevant_files": ["src/click/core.py", "src/click/types.py"],
        "reference_answer": "Options can specify envvar. Checked before defaults. Multiple env vars in list, checked in order.",
        "category": "env_vars",
    },
    {
        "question": "What is the difference between Click options and arguments?",
        "relevant_files": ["src/click/core.py", "src/click/decorators.py"],
        "reference_answer": "Options: optional, --name, defaults, flags, prompting. Arguments: positional, required, variadic nargs.",
        "category": "parameters",
    },
    {
        "question": "How does pass_context and pass_obj work for dependency injection?",
        "relevant_files": ["src/click/decorators.py", "src/click/core.py", "src/click/globals.py"],
        "reference_answer": "pass_context injects Context as first arg. pass_obj passes ctx.obj. Both use get_current_context().",
        "category": "dependency_injection",
    },
    {
        "question": "How does Click handle prompting users for input?",
        "relevant_files": ["src/click/core.py", "src/click/termui.py", "src/click/decorators.py"],
        "reference_answer": "Option(prompt=True), confirmation_prompt, click.prompt() with type conversion, click.confirm().",
        "category": "interactive",
    },
    {
        "question": "How does Click handle file path validation and the Path type?",
        "relevant_files": ["src/click/types.py"],
        "reference_answer": "Path type validates exists, file_okay, dir_okay, writable, readable, resolve_path. Returns Path or str.",
        "category": "file_handling",
    },
]


def run_full_evaluation():
    P("=" * 70)
    P("  GraphCodeRAG -- Full Evaluation Pipeline")
    P("=" * 70)
    P(f"  Time: {datetime.now().isoformat()}")
    P(f"  Test cases: {len(BENCHMARK)}")
    P("=" * 70)

    results = {
        "timestamp": datetime.now().isoformat(),
        "num_cases": len(BENCHMARK),
        "config": {
            "generator_temperature": 0.0,
            "system_prompt_version": "relaxed_v2",
            "judge_context_symmetric": True,
            "paths_evaluated": ["rag_hybrid", "vector_only", "plain_claude"],
        },
    }

    # ── Load models ONCE ──
    P("\n[1/5] Loading retriever...", end=" ")
    t0 = time.time()
    from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
    retriever = HybridRetriever()
    P(f"OK ({time.time()-t0:.1f}s)")

    # Neo4j health check — abort early if the graph is unreachable,
    # otherwise HybridRetriever silently falls back to vector-only and
    # hybrid == vector in the saved JSON (methodology trap).
    try:
        gs = getattr(retriever, "graph_store", None) or getattr(retriever, "graph", None)
        if gs is not None and hasattr(gs, "driver"):
            with gs.driver.session() as s:
                s.run("RETURN 1").single()
            P("      Neo4j reachable: OK")
        else:
            P("      Neo4j pre-check skipped (no driver attr found)")
    except Exception as e:
        P(f"\n[ABORT] Neo4j is not reachable: {e}")
        P("        Start Neo4j (bolt://localhost:7687) before running the eval,")
        P("        otherwise hybrid retrieval silently falls back to vector-only.")
        sys.exit(1)

    P("[2/5] Loading generator...", end=" ")
    from graphcoderag.generation.generator import LLMGenerator
    from graphcoderag.evaluation.llm_judge import LLMJudge
    generator = LLMGenerator()
    judge = LLMJudge(generator)
    P("OK")

    # ══════════════════════════════════════════════════════════════
    #  PHASE 1: RETRIEVAL (retrieve once at K=15, evaluate at K=5,10,15)
    # ══════════════════════════════════════════════════════════════
    P("\n--- PHASE 1: Retrieval Metrics ---")

    from graphcoderag.evaluation.metrics import (
        compute_mrr, compute_recall_at_k, compute_precision_at_k,
        compute_hit_rate_at_k, compute_ndcg_at_k, compute_file_recall_at_k,
    )

    all_retrievals = []
    for i, case in enumerate(BENCHMARK):
        q = case["question"]
        P(f"  [{i+1}/{len(BENCHMARK)}] Retrieving: {q[:55]}...")
        t0 = time.time()

        try:
            hybrid_results = retriever.retrieve(q, final_top_k=15)
            vector_results = retriever.retrieve_vector_only(q, top_k=15)
        except Exception as e:
            P(f"    ERROR: {e}")
            hybrid_results, vector_results = [], []

        hybrid_files = [r.file_path.replace("\\", "/") for r in hybrid_results]
        vector_files = [r.file_path.replace("\\", "/") for r in vector_results]
        relevant = set(f.replace("\\", "/") for f in case.get("relevant_files", []))

        # Count sources
        sources = {}
        for r in hybrid_results:
            sources[r.source] = sources.get(r.source, 0) + 1

        all_retrievals.append({
            "question": q,
            "category": case.get("category", ""),
            "hybrid_files": hybrid_files,
            "vector_files": vector_files,
            "relevant_files": list(relevant),
            "hybrid_sources": sources,
            "new_from_graph": list(set(hybrid_files) - set(vector_files)),
            "_hybrid_results": hybrid_results,
            "_vector_results": vector_results,
        })
        P(f"    H:{len(hybrid_results)} V:{len(vector_results)} sources:{sources} ({time.time()-t0:.1f}s)")

    # Compute ALL metrics at K=5,10,15
    retrieval_metrics = {}
    for K in [5, 10, 15]:
        h_file_recalls, b_file_recalls = [], []
        h_hit_rates, b_hit_rates = [], []
        h_recalls, b_recalls = [], []
        h_precisions, b_precisions = [], []
        h_ndcgs, b_ndcgs = [], []
        h_mrrs, b_mrrs = [], []

        for ret in all_retrievals:
            rel = set(ret["relevant_files"])
            hf = ret["hybrid_files"][:K]
            vf = ret["vector_files"][:K]

            # File-level metrics
            h_file_recalls.append(compute_file_recall_at_k(hf, rel, K))
            b_file_recalls.append(compute_file_recall_at_k(vf, rel, K))
            h_hit_rates.append(compute_hit_rate_at_k(hf, rel, K))
            b_hit_rates.append(compute_hit_rate_at_k(vf, rel, K))

            # Chunk-level IR metrics (using file paths as relevance proxy)
            h_recalls.append(compute_recall_at_k(hf, rel, K))
            b_recalls.append(compute_recall_at_k(vf, rel, K))
            h_precisions.append(compute_precision_at_k(hf, rel, K))
            b_precisions.append(compute_precision_at_k(vf, rel, K))
            h_ndcgs.append(compute_ndcg_at_k(hf, rel, K))
            b_ndcgs.append(compute_ndcg_at_k(vf, rel, K))

            # MRR (position of first relevant file)
            h_mrrs.append(compute_mrr(hf, rel))
            b_mrrs.append(compute_mrr(vf, rel))

        n = len(all_retrievals) or 1
        avg = lambda lst: sum(lst) / n

        ha = {
            "file_recall": avg(h_file_recalls), "hit_rate": avg(h_hit_rates),
            "recall": avg(h_recalls), "precision": avg(h_precisions),
            "ndcg": avg(h_ndcgs), "mrr": avg(h_mrrs),
        }
        ba = {
            "file_recall": avg(b_file_recalls), "hit_rate": avg(b_hit_rates),
            "recall": avg(b_recalls), "precision": avg(b_precisions),
            "ndcg": avg(b_ndcgs), "mrr": avg(b_mrrs),
        }
        da = {k: round(ha[k] - ba[k], 4) for k in ha}

        retrieval_metrics[f"K={K}"] = {"hybrid": ha, "vector_only": ba, "delta": da}
        P(f"  K={K:>2} | Hybrid FR: {ha['file_recall']:.1%} | Vector FR: {ba['file_recall']:.1%} | Delta: {da['file_recall']:+.1%} | MRR: {ha['mrr']:.3f} vs {ba['mrr']:.3f}")

    results["retrieval"] = retrieval_metrics

    # ══════════════════════════════════════════════════════════════
    #  PHASE 2: GENERATION QUALITY (GraphCodeRAG vs Plain LLM)
    # ══════════════════════════════════════════════════════════════
    P("\n--- PHASE 2: Generation Quality (LLM Judge) ---")

    gen_results = []
    for i, (case, ret) in enumerate(zip(BENCHMARK, all_retrievals)):
        q = case["question"]
        ref = case.get("reference_answer", "")
        P(f"  [{i+1}/{len(BENCHMARK)}] Generating: {q[:55]}...")

        # 1. GraphCodeRAG answer (with hybrid retrieval)
        try:
            rag_answer = generator.generate(q, ret["_hybrid_results"][:10])
        except Exception as e:
            rag_answer = f"[Error: {e}]"

        # 2. Vector-only RAG answer (vector retrieval, no graph)
        try:
            vec_answer = generator.generate(q, ret["_vector_results"][:10])
        except Exception as e:
            vec_answer = f"[Error: {e}]"

        # 3. Plain LLM answer (no retrieval context)
        try:
            plain_prompt = (
                "You are a Python expert. Answer this question about the Click CLI library. "
                "Provide a detailed technical answer.\n\n" + q
            )
            plain_answer = generator.generate_raw(plain_prompt, max_tokens=1500)
        except Exception as e:
            plain_answer = f"[Error: {e}]"

        # 4. Judge all three answers (symmetric empty context for all paths)
        # Skip [LLM Error]/[Error:] answers — otherwise the judge scores them
        # as 1/5 and contaminates the averages with API-failure noise.
        def _safe_judge(ans):
            if not ans or ans.startswith("[LLM Error]") or ans.startswith("[Error:"):
                return {"accuracy": None, "completeness": None, "helpfulness": None,
                        "avg_score": None, "reasoning": "skipped: generation failed"}
            try:
                return judge.rate_answer(q, ans, "", ref)
            except Exception as e:
                return {"accuracy": None, "completeness": None, "helpfulness": None,
                        "avg_score": None, "reasoning": f"judge error: {e}"}

        rag_scores = _safe_judge(rag_answer)
        vec_scores = _safe_judge(vec_answer)
        plain_scores = _safe_judge(plain_answer)

        gen_results.append({
            "question": q,
            "category": case.get("category", ""),
            "rag_answer": rag_answer[:800],
            "vec_answer": vec_answer[:800],
            "plain_answer": plain_answer[:800],
            "rag_scores": rag_scores,
            "vec_scores": vec_scores,
            "plain_scores": plain_scores,
        })

        ra = rag_scores.get("avg_score") or 0
        va = vec_scores.get("avg_score") or 0
        pa = plain_scores.get("avg_score") or 0
        best = max(ra, va, pa)
        w = "RAG+" if ra == best and ra > max(va, pa) else \
            "Vec+" if va == best and va > max(ra, pa) else \
            "Plain+" if pa == best and pa > max(ra, va) else "Tie"
        P(f"    RAG: {ra:.1f}  Vec: {va:.1f}  Plain: {pa:.1f}  -> {w}")

    # Aggregate
    # Per-path totals + counts (skip None — those are generation/judge failures)
    keys = ["accuracy", "completeness", "helpfulness", "avg_score"]
    rag_totals = {k: 0.0 for k in keys}; rag_counts = {k: 0 for k in keys}
    vec_totals = {k: 0.0 for k in keys}; vec_counts = {k: 0 for k in keys}
    plain_totals = {k: 0.0 for k in keys}; plain_counts = {k: 0 for k in keys}
    wins_rag_plain = {"rag": 0, "plain": 0, "tie": 0}
    wins_rag_vec = {"rag": 0, "vec": 0, "tie": 0}

    def _acc(totals, counts, scores):
        for k in keys:
            v = scores.get(k)
            if v is None: continue
            totals[k] += v; counts[k] += 1

    for r in gen_results:
        _acc(rag_totals, rag_counts, r["rag_scores"])
        _acc(vec_totals, vec_counts, r["vec_scores"])
        _acc(plain_totals, plain_counts, r["plain_scores"])
        ra = r["rag_scores"].get("avg_score")
        va = r["vec_scores"].get("avg_score")
        pa = r["plain_scores"].get("avg_score")
        # pairwise comparisons only if both sides have a score
        if ra is not None and pa is not None:
            if ra > pa: wins_rag_plain["rag"] += 1
            elif pa > ra: wins_rag_plain["plain"] += 1
            else: wins_rag_plain["tie"] += 1
        if ra is not None and va is not None:
            if ra > va: wins_rag_vec["rag"] += 1
            elif va > ra: wins_rag_vec["vec"] += 1
            else: wins_rag_vec["tie"] += 1

    def _avg(totals, counts):
        return {k: (round(totals[k]/counts[k], 2) if counts[k] else None) for k in keys}

    rag_avg = _avg(rag_totals, rag_counts)
    vec_avg = _avg(vec_totals, vec_counts)
    plain_avg = _avg(plain_totals, plain_counts)

    results["generation"] = {
        "rag_avg": rag_avg, "vec_avg": vec_avg, "plain_avg": plain_avg,
        "wins_rag_vs_plain": wins_rag_plain,
        "wins_rag_vs_vec": wins_rag_vec,
        "per_case": gen_results,
    }
    wins = wins_rag_plain

    # ══════════════════════════════════════════════════════════════
    #  PHASE 3: ABLATION (Category breakdown)
    # ══════════════════════════════════════════════════════════════
    P("\n--- PHASE 3: Category Ablation ---")

    cats = {}
    for r in gen_results:
        c = r.get("category", "other")
        if c not in cats:
            cats[c] = {"rag": [], "vec": [], "plain": []}
        for path, key in [("rag", "rag_scores"), ("vec", "vec_scores"), ("plain", "plain_scores")]:
            v = r[key].get("avg_score")
            if v is not None:
                cats[c][path].append(v)

    ablation = {}
    for c, d in sorted(cats.items()):
        ra = sum(d["rag"]) / max(len(d["rag"]), 1)
        va = sum(d["vec"]) / max(len(d["vec"]), 1)
        pa = sum(d["plain"]) / max(len(d["plain"]), 1)
        ablation[c] = {
            "rag": round(ra, 2),
            "vec": round(va, 2),
            "plain": round(pa, 2),
            "delta_rag_vs_plain": round(ra - pa, 2),
            "delta_rag_vs_vec": round(ra - va, 2),
        }
        P(f"  {c:25s} RAG: {ra:.1f}  Vec: {va:.1f}  Plain: {pa:.1f}  | d(R-P): {ra-pa:+.1f}  d(R-V): {ra-va:+.1f}")

    results["ablation"] = ablation

    # Clean up retrieval objects before saving
    for ret in all_retrievals:
        ret.pop("_hybrid_results", None)
        ret.pop("_vector_results", None)
    results["retrieval"]["per_case"] = all_retrievals

    # ── Save ──
    out_dir = Path(__file__).parent.parent.parent / "evaluation_results"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"eval_{ts}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    P(f"\nResults saved: {out_file}")

    # ══════════════════════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════════════════════
    P("\n" + "=" * 70)
    P("  EVALUATION SUMMARY")
    P("=" * 70)

    P("\n  RETRIEVAL: Hybrid vs Vector-only (All Metrics)")
    P(f"  {'K':>4} | {'Metric':>12} | {'Hybrid':>8} | {'Vector':>8} | {'Delta':>8}")
    P(f"  {'----':>4} | {'------------':>12} | {'--------':>8} | {'--------':>8} | {'--------':>8}")
    for kl in ["K=5", "K=10", "K=15"]:
        d = retrieval_metrics.get(kl, {})
        h = d.get("hybrid", {})
        b = d.get("vector_only", {})
        dl = d.get("delta", {})
        for metric in ["mrr", "recall", "precision", "ndcg", "file_recall", "hit_rate"]:
            hv = h.get(metric, 0)
            bv = b.get(metric, 0)
            dv = dl.get(metric, 0)
            label = metric.replace('_', ' ').title()
            P(f"  {kl:>4} | {label:>12} | {hv:>7.3f} | {bv:>7.3f} | {dv:>+7.3f}")
        P(f"  {'':>4} | {'':>12} | {'':>8} | {'':>8} | {'':>8}")

    P(f"\n  GENERATION: GraphCodeRAG (RAG) vs Vector-only vs Plain LLM")
    P(f"  {'Metric':>15} | {'RAG':>8} | {'Vec':>8} | {'Plain':>8} | {'R-P':>7} | {'R-V':>7}")
    P(f"  {'---------------':>15} | {'--------':>8} | {'--------':>8} | {'--------':>8} | {'-------':>7} | {'-------':>7}")
    for key in ["accuracy", "completeness", "helpfulness", "avg_score"]:
        r = rag_avg.get(key) or 0
        v = vec_avg.get(key) or 0
        p = plain_avg.get(key) or 0
        P(f"  {key:>15} | {r:>7.2f} | {v:>7.2f} | {p:>7.2f} | {r-p:>+7.2f} | {r-v:>+7.2f}")

    P(f"\n  Win/Tie/Loss (RAG vs Plain): RAG {wins_rag_plain['rag']}W / {wins_rag_plain['tie']}T / {wins_rag_plain['plain']}L")
    P(f"  Win/Tie/Loss (RAG vs Vec):   RAG {wins_rag_vec['rag']}W / {wins_rag_vec['tie']}T / {wins_rag_vec['vec']}L")
    P(f"\n{'=' * 70}")

    retriever.close()
    return results


if __name__ == "__main__":
    run_full_evaluation()
