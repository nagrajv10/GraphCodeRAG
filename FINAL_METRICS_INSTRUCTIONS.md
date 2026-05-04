# GraphCodeRAG — Final Evaluation Metrics: What to Compute, Where, and How

## Context for the AI Reading This

You are working on a project called GraphCodeRAG located at `https://github.com/nagrajv10/GraphCodeRAG.git`. The system has already been built, tested, and validated. The evaluation infrastructure exists in `graphcoderag/evaluation/` with metrics implemented in `metrics.py` (MRR, Recall@K, Precision@K, NDCG@K, Hit Rate@K, File Recall@K) and an LLM judge in `llm_judge.py`. The SWE-bench evaluation runner at `graphcoderag/evaluation/swebench_runner_v2.py` already performs a 4-way controlled comparison (Standard RAG vs AST vector-only vs GraphCodeRAG Hybrid vs Plain LLM) across real repositories (Click, PyTest, Django, Scikit-Learn) using 15 test cases per repo. Evaluation results are saved as timestamped JSON files in `evaluation_results/`. The hybrid retriever in `graphcoderag/retrieval/hybrid_retriever.py` tags every result with a `source` field that is either `"vector"`, `"graph"`, or `"hybrid"` depending on how the chunk was discovered. The task now is to compute and present seven specific metrics plus one qualitative example in a clean, structured format suitable for a project presentation, poster, or report. The comparison axis is always Standard RAG (Pipeline A: character chunking + vector-only) versus GraphCodeRAG (Pipeline B-hybrid: AST chunking + vector + graph). All metrics should be computed at three K values: K=1, K=5, and K=15.

---

## Metric 1: MRR @ K=1, K=5, K=15

### What it measures

Mean Reciprocal Rank answers "how high is the first relevant result?" For each query, the reciprocal rank is 1/position of the first correct file in the results list. MRR is the average across all queries. An MRR of 1.0 means the correct file is always the first result. An MRR of 0.5 means the correct file is on average the second result. MRR at different K values shows the ceiling — MRR@1 can only be 0 or 1 per query (did we nail the first result or not), while MRR@15 allows credit for finding the correct file anywhere in the top 15.

### Where to compute it

The function `compute_mrr` already exists in `graphcoderag/evaluation/metrics.py`. The SWE-bench runner already computes MRR but only at a single K value per run. You need to modify the evaluation output to compute MRR at K=1, K=5, and K=15 separately.

### How to compute it

For each test case in the evaluation results JSON, take the `retrieved_files` list (ordered by score) for both Pipeline A (Standard RAG) and Pipeline B-hybrid (GraphCodeRAG). For MRR@K, truncate the retrieved list to the first K items, then call `compute_mrr(retrieved_files[:K], relevant_files)`. Do this for K=1, K=5, and K=15. Average across all test cases per repository, then also compute a global average across all repositories. Present as a table with rows for each repository (Click, PyTest, Django, Scikit-Learn) and columns for Standard RAG MRR@1, GraphCodeRAG MRR@1, Standard RAG MRR@5, GraphCodeRAG MRR@5, Standard RAG MRR@15, GraphCodeRAG MRR@15. Also add a Delta column for each K showing the improvement.

---

## Metric 2: NDCG @ K=1, K=5, K=15

### What it measures

Normalized Discounted Cumulative Gain measures ranking quality. Unlike MRR which only cares about the first relevant result, NDCG rewards having multiple relevant results ranked high. A high NDCG means the entire top-K is well-ordered — the system doesn't just find one right file, it puts the class definition and its callers and the decorators all near the top. NDCG@1 degenerates to a binary signal (is the top result relevant?), while NDCG@15 captures the full ranking quality.

### Where to compute it

The function `compute_ndcg_at_k` already exists in `graphcoderag/evaluation/metrics.py`. It takes `retrieved_ids`, `relevant_ids`, and `k` as parameters.

### How to compute it

For each test case, call `compute_ndcg_at_k(retrieved_files, relevant_files, k=K)` for K=1, K=5, and K=15, for both Pipeline A and Pipeline B-hybrid. Average across all test cases per repository and globally. Present in the same table format as MRR, or as a separate table with the same structure. The key insight to highlight in the presentation: if GraphCodeRAG's NDCG@5 is significantly higher than Standard RAG's NDCG@5, it means the hybrid system isn't just finding one right file — it's finding multiple right files and ranking them correctly, which is critical for giving the LLM clean, comprehensive context.

---

## Metric 3: File Recall @ K=1, K=5, K=15

### What it measures

File Recall answers "what fraction of the ground-truth relevant files did we find in the top K results?" This is the most intuitive metric for a non-technical audience. If a bug fix touches 3 files and the system retrieves 2 of them in the top 10, the file recall is 66.7%. Showing it at three K values demonstrates whether GraphCodeRAG finds the right files earlier (high recall at K=1 and K=5) rather than just eventually finding them at K=15.

### Where to compute it

The function `compute_file_recall_at_k` already exists in `graphcoderag/evaluation/metrics.py`. It normalizes path separators for cross-platform matching.

### How to compute it

For each test case, extract the file paths from the ordered retrieval results for both pipelines. Call `compute_file_recall_at_k(retrieved_files, relevant_files, k=K)` for K=1, K=5, and K=15. Average across all test cases per repository and globally. Present as a table. The strongest number in the project is PyTest's file recall improvement — highlight this specifically. Also include a Hit Rate@1 column in this table, computed as `compute_hit_rate_at_k(retrieved_files, relevant_files, k=1)`, which answers the simplest possible question: "what percentage of queries got a correct file as the very first result?" Hit Rate@1 is a single percentage that even someone skimming a poster will absorb.

---

## Metric 4: Graph Contribution Rate

### What it measures

This metric justifies the entire Neo4j graph component. It answers "what did the graph actually do?" by measuring how often graph-discovered chunks appear in the final results. Without this metric, someone could argue the improvement comes entirely from AST chunking or better embeddings rather than from the graph. Two numbers should be reported: the percentage of queries where at least one graph-sourced chunk appeared in the final top-K results (Graph Hit Rate), and the average number of graph-sourced chunks per query (Graph Chunk Count).

### Where to compute it

This is not currently implemented as a standalone metric. You need to compute it from the hybrid retriever's output, which already tags each result with `source: "vector"`, `source: "graph"`, or `source: "hybrid"` in the `RetrievalResult` objects returned by `hybrid_retriever.py`.

### How to compute it

Modify the SWE-bench runner or create a separate analysis script. For each test case, after running hybrid retrieval, iterate over the final result list and count how many results have `source == "graph"` or `source == "hybrid"` (both indicate graph contribution). Compute two aggregates: `graph_hit_rate = (number of queries where graph_count > 0) / (total queries)` expressed as a percentage, and `avg_graph_chunks = sum(graph_count per query) / total_queries`. Also compute a per-repository breakdown. Present as a simple table with one row per repository showing Graph Hit Rate (%) and Average Graph Chunks per Query. If the Graph Hit Rate is above 30%, the graph is clearly contributing. If it's below 10%, the graph is rarely adding value and you should investigate why (possibly the graph is too sparse for that repository or the queries don't trigger cross-file relationships). Also break down the graph contribution by edge type if possible — count how many graph-discovered chunks were reached via CALLS edges versus IMPORTS edges versus INHERITS edges. This shows which relationship types are most valuable.

---

## Metric 5: Query Latency Breakdown

### What it measures

This preempts the practical objection "isn't the graph too slow?" by showing the wall-clock time of each retrieval stage. The breakdown should show embedding time (encoding the query into a vector), FAISS search time (vector similarity search), graph traversal time (Neo4j Cypher execution), merge time (hybrid score fusion), and total retrieval time (sum of all stages). This excludes LLM generation time because that is the same for both pipelines and would dominate the numbers.

### Where to compute it

This requires adding timing instrumentation to the retrieval pipeline. The relevant methods are `embed_query()` in `graphcoderag/storage/embedding.py`, `search()` and `search_filtered()` in `graphcoderag/storage/faiss_store.py`, `retrieve()` in `graphcoderag/retrieval/graph_retriever.py`, and `_merge_and_score()` in `graphcoderag/retrieval/hybrid_retriever.py`.

### How to compute it

Create a benchmarking script or modify the SWE-bench runner to wrap each stage with `time.perf_counter()`. For each test case query, record the time spent in each stage. Run all 60 test cases (or at least 15 per repo) and compute the average time per stage. Present as a table with rows for each stage (Embedding, FAISS Search, Graph Traversal, Merge, Total) and columns for average time in milliseconds. Also show the overhead of hybrid versus vector-only, computed as `(total_hybrid - total_vector_only) / total_vector_only * 100` as a percentage. If the total hybrid retrieval is under 1 second and the graph overhead is under 200ms, present this as evidence that the structural quality gains come at minimal latency cost. Also present a comparison row showing Standard RAG total time versus GraphCodeRAG total time so the audience can see the absolute overhead. If you want a visual, present this as a stacked bar chart with one bar for vector-only and one bar for hybrid, each bar segmented by stage.

---

## Metric 6: Qualitative Example

### What it measures

Numbers convince the mind, examples convince the gut. A side-by-side comparison of actual system outputs makes the improvement tangible for anyone who doesn't read tables. The Click command groups example already exists in `EVALUATION_REPORT_FINAL.md` and is ideal because it shows a clear three-way contrast.

### How to present it

Present the three outputs side by side for the query "How does Click implement command groups and subcommands?" with ground truth files being `src/click/core.py` and `src/click/decorators.py`. The Plain LLM output (Pipeline C) hallucinated a generic usage tutorial with `@click.group()` examples that any beginner guide would produce — no internal implementation knowledge. The Standard RAG output (Pipeline A) pulled in documentation strings and test code, producing an answer focused on `repr()` formatting and `runner.invoke()` rather than the actual class implementation. The GraphCodeRAG output (Pipeline B-hybrid) correctly identified the `Command` and `Group` class definitions in `core.py`, explained the inheritance relationship, listed the key methods (`add_command`, `get_command`, `list_commands`), and referenced the decorator wrappers in `decorators.py`. Highlight why GraphCodeRAG found the right code: the graph traversal followed the `INHERITS` edge from `Group` to `Command` and the `IMPORTS` edge from `decorators.py` to `core.py`, pulling in structurally connected code that vector search alone ranked lower. Do not reproduce the full output text — summarize each pipeline's answer in 2-3 sentences and show one representative code snippet from the GraphCodeRAG answer to make it concrete.

---

## Metric 7: Standard RAG vs GraphCodeRAG Summary Table

### What it is

This is not a separate metric but the master presentation format that combines all the above metrics into a single comprehensive view. It should be the centerpiece of the presentation or poster.

### How to present it

Create one main comparison table structured as follows. The rows are the four repositories (Click, PyTest, Django, Scikit-Learn) plus a weighted average row at the bottom. The columns are grouped into sections: MRR (with sub-columns @1, @5, @15 for each pipeline), File Recall (with sub-columns @1, @5, @15 for each pipeline), NDCG (with sub-columns @1, @5, @15 for each pipeline), and Graph Contribution (with sub-columns Hit Rate % and Avg Chunks). Each cell shows the GraphCodeRAG number in bold with the delta from Standard RAG in parentheses. Below this main table, add a smaller "Latency" table showing the stage breakdown and total time for each pipeline. Below that, place the qualitative example as a three-column visual comparison. This three-part layout (metrics table, latency table, qualitative example) tells a complete story: the system retrieves better code (metrics), without meaningful overhead (latency), and produces genuinely better answers as a result (qualitative).

---

## Implementation Summary

To generate all these metrics from the existing codebase, you need to do the following in order:

1. Run the SWE-bench evaluation: `python -m graphcoderag.evaluation.swebench_runner_v2 --backend=faiss --retrieval-only`. This produces the raw per-case results JSON with retrieved files and scores for all pipelines.

2. Create a script at `scripts/compute_final_metrics.py` that loads the evaluation results JSON and computes MRR, NDCG, File Recall, and Hit Rate at K=1, K=5, K=15 for both pipelines across all repositories using the functions in `graphcoderag/evaluation/metrics.py`.

3. Add graph contribution counting to the same script by re-running retrieval on the test queries and inspecting the `source` tag on each result, or by modifying `swebench_runner_v2.py` to log the source tags in the output JSON.

4. Add timing instrumentation to the retrieval pipeline by wrapping the key methods with `time.perf_counter()` calls and recording the per-stage durations.

5. Format all results into the presentation tables described above.

No changes to the core retrieval or ingestion code are needed. The metrics computation is purely a post-processing step on the existing evaluation outputs, plus timing instrumentation that only affects measurement, not behavior.
