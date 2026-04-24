import json

d = json.load(open('evaluation_results/swebench_v2_20260421_173828.json'))

print("=" * 100)
print("  DEEP ANALYSIS: Why Standard RAG beats GraphCodeRAG on Click & Django")
print("=" * 100)

# Check chunk counts
print("\n--- CHUNK COUNTS (why this matters) ---")
chunk_info = {
    'click': {'char_chunks': 1910, 'ast_chunks': 696, 'ratio': 1910/696},
    'pytest': {'char_chunks': 9549, 'ast_chunks': 2995, 'ratio': 9549/2995},
    'sklearn': {'char_chunks': 41184, 'ast_chunks': 5942, 'ratio': 41184/5942},
    'django': {'char_chunks': 50900, 'ast_chunks': 27724, 'ratio': 50900/27724},
}
for repo, info in chunk_info.items():
    print(f"  {repo:8s}  Char chunks: {info['char_chunks']:>6,}  AST chunks: {info['ast_chunks']:>6,}  Ratio: {info['ratio']:.1f}x")

print("\n--- PER-REPO RETRIEVAL COMPARISON ---")
for rk in ['click', 'pytest', 'sklearn', 'django']:
    r = d['repos'][rk]['retrieval']['aggregated']
    print(f"\n  {rk.upper()}")
    print(f"  {'K':>4}  {'Std RAG MRR':>12}  {'AST+Vec MRR':>12}  {'Hybrid MRR':>12}  {'Winner':>10}  {'Delta':>8}")
    print(f"  {'----':>4}  {'----------':>12}  {'----------':>12}  {'----------':>12}  {'------':>10}  {'-----':>8}")
    for K in ['K=1', 'K=3', 'K=5', 'K=10']:
        a = r[K]['A']['mrr']
        bv = r[K]['B_vec']['mrr']
        bh = r[K]['B_hybrid']['mrr']
        winner = 'Std RAG' if a > bh else ('AST' if bh > a else 'Tie')
        delta = bh - a
        print(f"  {K:>4}  {a:>12.3f}  {bv:>12.3f}  {bh:>12.3f}  {winner:>10}  {delta:>+8.3f}")

print("\n--- KEY OBSERVATION ---")
print("  B_vec == B_hybrid for ALL repos!")
print("  This means: Neo4j graph traversal adds ZERO new relevant files.")
print("  The hybrid pipeline falls back to vector-only because graph edges")
print("  don't connect to files in the SWE-bench gold patches.")
print()
print("  The REAL comparison is: Standard RAG (char chunks) vs AST chunking (AST chunks)")

# Per-case analysis for click
print("\n--- CLICK: PER-CASE BREAKDOWN (why Std RAG wins) ---")
cases = d['repos']['click']['retrieval']['per_case']
std_wins = 0
ast_wins = 0
ties = 0
for c in cases:
    a_mrr = c['metrics']['K=5']['A']['mrr']
    b_mrr = c['metrics']['K=5']['B_vec']['mrr']
    status = 'Std' if a_mrr > b_mrr else ('AST' if b_mrr > a_mrr else 'Tie')
    if status == 'Std':
        std_wins += 1
    elif status == 'AST':
        ast_wins += 1
    else:
        ties += 1
    iid = c['instance_id'][:30]
    a_files = c['files']['A'][:3]
    b_files = c['files']['B_vec'][:3]
    print(f"  {iid:30s}  Std MRR={a_mrr:.3f}  AST MRR={b_mrr:.3f}  -> {status}")

print(f"\n  Summary @ K=5: Std RAG wins {std_wins}, AST wins {ast_wins}, Ties {ties}")
