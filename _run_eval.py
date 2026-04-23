"""Run evaluation with semantic reranking fix."""
import json, sys
sys.path.insert(0, '.')

from graphcoderag.evaluation.baseline_comparison import BaselineComparison

with open('data/swebench/test_cases.json') as f:
    test_cases = json.load(f)

comp = BaselineComparison()

print("=== EVALUATION WITH SEMANTIC RERANKING ===\n")

for k in [5, 10, 15, 20]:
    results = comp.run_comparison(test_cases, top_k=k)
    h = results['hybrid_aggregate']
    b = results['baseline_aggregate']
    d = results['deltas']

    h_recall = h.get('file_recall', 0)
    b_recall = b.get('file_recall', 0)
    d_recall = d.get('file_recall', 0)

    print(f"K={k}: Hybrid={h_recall:.4f}  Baseline={b_recall:.4f}  Delta={d_recall:+.4f}")

    wins = ties = losses = 0
    for case in results['per_case']:
        hm = case['hybrid_metrics'].get('file_recall', 0)
        bm = case['baseline_metrics'].get('file_recall', 0)
        if hm > bm: wins += 1
        elif hm < bm: losses += 1
        else: ties += 1
    print(f"       W/T/L: {wins}W / {ties}T / {losses}L")

    if k == 15:
        print("\n  Per-case at K=15:")
        for i, case in enumerate(results['per_case']):
            hm = case['hybrid_metrics'].get('file_recall', 0)
            bm = case['baseline_metrics'].get('file_recall', 0)
            delta = hm - bm
            sources = case.get('hybrid_sources', {})
            marker = "  " if delta == 0 else ("+ " if delta > 0 else "- ")
            print(f"  {marker}#{i+1} H={hm:.2f} B={bm:.2f} d={delta:+.2f} src={sources}")
        print()

comp.close()
print("\nDone!")
