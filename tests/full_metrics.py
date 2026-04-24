"""
Full Metrics Report - Shows ALL metrics at multiple K values with detailed analysis.
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
from graphcoderag.evaluation.metrics import (
    compute_file_recall_at_k, compute_hit_rate_at_k,
)

def run_full_metrics():
    with open("data/swebench/test_cases.json") as f:
        test_cases = json.load(f)

    retriever = HybridRetriever()
    k_values = [5, 10, 15, 20]

    print("=" * 80)
    print("  COMPREHENSIVE METRICS REPORT - GraphCodeRAG vs Baseline")
    print("=" * 80)

    for k in k_values:
        h_recalls, b_recalls = [], []
        h_hits, b_hits = [], []
        h_unique_files_total, b_unique_files_total = 0, 0
        graph_new_files_total = 0
        graph_new_files_cases = 0
        h_sources = {"vector": 0, "graph": 0, "hybrid": 0}

        for case in test_cases:
            q = case["question"]
            relevant = set(f.replace("\\", "/") for f in case.get("relevant_files", []))

            hybrid_results = retriever.retrieve(q, final_top_k=k)
            baseline_results = retriever.retrieve_vector_only(q, top_k=k)

            h_files = [r.file_path.replace("\\", "/") for r in hybrid_results]
            b_files = [r.file_path.replace("\\", "/") for r in baseline_results]

            h_unique = set(h_files)
            b_unique = set(b_files)
            h_unique_files_total += len(h_unique)
            b_unique_files_total += len(b_unique)

            new_files = h_unique - b_unique
            graph_new_files_total += len(new_files)
            if new_files:
                graph_new_files_cases += 1

            h_recalls.append(compute_file_recall_at_k(h_files, relevant, k))
            b_recalls.append(compute_file_recall_at_k(b_files, relevant, k))
            h_hits.append(compute_hit_rate_at_k(h_files, relevant, k))
            b_hits.append(compute_hit_rate_at_k(b_files, relevant, k))

            for r in hybrid_results:
                h_sources[r.source] = h_sources.get(r.source, 0) + 1

        avg_h_recall = sum(h_recalls) / len(h_recalls)
        avg_b_recall = sum(b_recalls) / len(b_recalls)
        avg_h_hit = sum(h_hits) / len(h_hits)
        avg_b_hit = sum(b_hits) / len(b_hits)
        delta_recall = avg_h_recall - avg_b_recall

        wins = sum(1 for h, b in zip(h_recalls, b_recalls) if h > b)
        ties = sum(1 for h, b in zip(h_recalls, b_recalls) if h == b)
        losses = sum(1 for h, b in zip(h_recalls, b_recalls) if h < b)

        print(f"\n{'-' * 80}")
        print(f"  K = {k}")
        print(f"{'-' * 80}")
        print(f"  {'Metric':<30} {'Hybrid':>10} {'Baseline':>10} {'Delta':>10}")
        print(f"  {'-'*30} {'-'*10} {'-'*10} {'-'*10}")
        print(f"  {'File Recall@K':<30} {avg_h_recall:>10.4f} {avg_b_recall:>10.4f} {delta_recall:>+10.4f}")
        print(f"  {'File Hit Rate@K':<30} {avg_h_hit:>10.4f} {avg_b_hit:>10.4f} {avg_h_hit-avg_b_hit:>+10.4f}")
        print(f"  {'Avg Unique Files/Query':<30} {h_unique_files_total/15:>10.1f} {b_unique_files_total/15:>10.1f}")
        print(f"  {'New Files from Graph (total)':<30} {graph_new_files_total:>10}")
        print(f"  {'Cases with New Files':<30} {graph_new_files_cases:>10} / {len(test_cases)}")
        print(f"  {'Win/Tie/Loss':<30} {f'{wins}W / {ties}T / {losses}L':>31}")
        print(f"  {'Source Mix (V/G/H)':<30} {h_sources.get('vector',0)}/{h_sources.get('graph',0)}/{h_sources.get('hybrid',0)}")

    # -- Per-case detailed breakdown at K=15 --
    print(f"\n{'=' * 80}")
    print("  PER-CASE DETAILED BREAKDOWN (K=15)")
    print(f"{'=' * 80}")
    print(f"  {'#':<3} {'Question':<45} {'H-Rec':>6} {'B-Rec':>6} {'Delta':>7} {'New':>5} {'Win?'}")
    print(f"  {'-'*3} {'-'*45} {'-'*6} {'-'*6} {'-'*7} {'-'*5} {'-'*5}")

    for i, case in enumerate(test_cases, 1):
        q = case["question"]
        relevant = set(f.replace("\\", "/") for f in case.get("relevant_files", []))

        hybrid_results = retriever.retrieve(q, final_top_k=15)
        baseline_results = retriever.retrieve_vector_only(q, top_k=15)

        h_files = [r.file_path.replace("\\", "/") for r in hybrid_results]
        b_files = [r.file_path.replace("\\", "/") for r in baseline_results]

        h_recall = compute_file_recall_at_k(h_files, relevant, 15)
        b_recall = compute_file_recall_at_k(b_files, relevant, 15)
        delta = h_recall - b_recall
        new = len(set(h_files) - set(b_files))

        marker = "  "
        if delta > 0: marker = "WIN"
        elif delta < 0: marker = "LOSS"

        print(f"  {i:<3} {q[:45]:<45} {h_recall:>6.2f} {b_recall:>6.2f} {delta:>+7.2f} {'+'+str(new) if new else '-':>5} {marker}")

    # -- Score distribution analysis --
    print(f"\n{'=' * 80}")
    print("  SCORE DISTRIBUTION - Why Graph Results Rank Lower")
    print(f"{'=' * 80}")

    q = test_cases[0]["question"]
    hybrid_results = retriever.retrieve(q, final_top_k=20)

    print(f"  Query: {q[:65]}...")
    print(f"\n  {'Rank':<5} {'Source':<8} {'Score':>8} {'Name':<30} {'File'}")
    print(f"  {'-'*5} {'-'*8} {'-'*8} {'-'*30} {'-'*40}")
    for i, r in enumerate(hybrid_results, 1):
        print(f"  {i:<5} {r.source:<8} {r.score:>8.4f} {(r.name or r.display_name)[:30]:<30} {r.file_path}")

    # -- Key insight: score gap --
    vector_scores = [r.score for r in hybrid_results if r.source == "vector"]
    graph_scores = [r.score for r in hybrid_results if r.source == "graph"]
    hybrid_scores = [r.score for r in hybrid_results if r.source == "hybrid"]

    print(f"\n  SCORE GAP ANALYSIS:")
    if vector_scores:
        print(f"    Vector scores:  min={min(vector_scores):.4f}  max={max(vector_scores):.4f}  avg={sum(vector_scores)/len(vector_scores):.4f}")
    if graph_scores:
        print(f"    Graph scores:   min={min(graph_scores):.4f}  max={max(graph_scores):.4f}  avg={sum(graph_scores)/len(graph_scores):.4f}")
    if hybrid_scores:
        print(f"    Hybrid scores:  min={min(hybrid_scores):.4f}  max={max(hybrid_scores):.4f}  avg={sum(hybrid_scores)/len(hybrid_scores):.4f}")

    if vector_scores and graph_scores:
        gap = min(vector_scores) - max(graph_scores)
        print(f"\n    >>> SCORE GAP: Lowest vector ({min(vector_scores):.4f}) - Highest graph ({max(graph_scores):.4f}) = {gap:+.4f}")
        print(f"    >>> This means ALL graph results rank BELOW all vector results")
        print(f"    >>> Graph can only help when K is large enough to include them")

    retriever.close()
    print(f"\n{'=' * 80}")
    print("  REPORT COMPLETE")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    run_full_metrics()
