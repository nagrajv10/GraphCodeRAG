# GraphCodeRAG — End-to-End Verification and Integration Testing Instructions

## Context for the AI Reading This

You are working on a project called GraphCodeRAG located at `https://github.com/nagrajv10/GraphCodeRAG.git`. A set of metadata-enhanced retrieval changes have already been implemented and have passed initial verification: all 5 modified files pass `py_compile`, the `QueryAnalyzer` correctly extracts class names, file paths, and function names from test queries, import extraction parses statements correctly, and all modules import without circular dependency errors. However, these checks only confirm that the code is syntactically valid and that individual components work in isolation. What has not been verified yet is whether the full end-to-end pipeline — query entering the system, flowing through entity extraction, metadata-filtered FAISS search, parent-child resolution, hybrid merge with graph results, and final ranked output — actually produces better retrieval results than the original unfiltered system. The following instructions describe exactly what integration tests to create, where to create them, and how to implement them so that the metadata-enhanced retrieval is validated against real data and real queries.

---

## Test 1: End-to-End Retrieval Comparison (Filtered vs Unfiltered)

### What to do

Create a test script that ingests a real Python repository, runs a set of carefully designed queries through both the old unfiltered retrieval path and the new metadata-filtered retrieval path, and compares the ranked results side by side to measure whether metadata filtering actually surfaces better chunks.

### Where to create it

Create a new file at `tests/test_metadata_retrieval.py`.

### How to implement it

The script should first ingest a small repository like Click (clone it to `data/repos/click` or use the `--repo-url` flag via `run_ingestion.py`). After ingestion, instantiate a `HybridRetriever` with the FAISS backend. Then define a list of at least 5 test queries that deliberately mention specific code entities. Good test queries include: "How does the Command class handle argument parsing?" (mentions a class name), "What happens in core.py when a command is invoked?" (mentions a file path), "How does the Group class inherit from Command?" (mentions two class names and an inheritance relationship), "What does the make_context function do?" (mentions a specific function), and "How are options parsed in decorators.py?" (mentions a file path). For each query, run retrieval twice: once by calling `retriever.retrieve(query)` which will use the new metadata-filtered path, and once by manually calling `retriever.vector_retriever.store.search(query, top_k=10)` followed by the old parent-resolution logic without any entity extraction, which simulates the old unfiltered behavior. For each query, collect the top 10 chunk_ids and their scores from both paths. Then compute three comparison metrics: how many of the top 10 results are identical between the two paths (overlap count), how many chunks in the filtered path's top 10 contain the mentioned entity name in their `name`, `parent_class`, or `file_path` metadata (entity hit rate), and the average score of the top 5 results in each path. Print a formatted table showing query, overlap count, entity hit rate for filtered, entity hit rate for unfiltered, and average top-5 score for both paths. If the filtered path consistently has a higher entity hit rate without a lower average score, the metadata filtering is working correctly. If the overlap count is 10 out of 10 for most queries, the filtering is not having any effect and the entity extraction or the `search_filtered` method needs debugging — check that `get_ids_by_filter` is returning a non-empty candidate set and that the candidate set is actually smaller than the full index.

---

## Test 2: Filtered Search Performance and Fallback Threshold

### What to do

Verify that `search_filtered` performs acceptably when the candidate set varies in size, and add a fallback threshold so that when the filtered candidate set is too large (meaning the filter is not meaningfully narrowing results), the system falls back to a standard unfiltered FAISS search instead of doing unnecessary work.

### Where to change

Modify the `search_filtered` method in `graphcoderag/storage/faiss_store.py` and create a performance test in `tests/test_metadata_retrieval.py`.

### How to implement it

In `faiss_store.py`, at the top of the `search_filtered` method, add a check: if `len(candidate_ids)` is greater than `0.7 * self.index.ntotal` (meaning the filter covers more than 70% of the index), return `self.search(query, top_k)` instead, because at that point filtering is not meaningfully narrowing the search space and reconstructing 70%+ of the vectors for manual dot products is slower than just letting FAISS search the full index natively. Also add a check: if `len(candidate_ids)` is 0, return an empty list immediately rather than proceeding with an empty candidate set. In the test script, measure the wall-clock time of three calls: `store.search(query, top_k=10)` (baseline unfiltered), `store.search_filtered(query, top_k=10, candidate_ids=small_set)` where `small_set` is a set of about 20 chunk_ids obtained from `get_ids_by_filter(parent_class="Command")`, and `store.search_filtered(query, top_k=10, candidate_ids=large_set)` where `large_set` is a set containing 80% of all chunk_ids. Use Python's `time.perf_counter()` to measure each call, run each call 5 times, and print the average time. The small filtered search should be faster than or comparable to the unfiltered search. The large filtered search should trigger the 70% fallback and produce identical results to the unfiltered search. If the small filtered search is significantly slower than unfiltered, there is a performance problem in the vector reconstruction loop and you should consider caching reconstructed vectors or using FAISS's `search_by_ids` functionality if available.

---

## Test 3: Metadata Index Persistence Across Reload

### What to do

Verify that the metadata indexes (`file_index`, `class_index`, `type_index`) are correctly rebuilt when a FAISS store is loaded from disk, without needing to re-ingest the repository.

### Where to create it

Add this test to `tests/test_metadata_retrieval.py` or create a separate file at `tests/test_faiss_persistence.py`.

### How to implement it

First, ingest a repository so that the FAISS index and metadata JSON are saved to disk at `data/faiss_index/<collection_name>/`. After ingestion, call `store.get_ids_by_filter(parent_class="Command")` and save the result as `expected_command_ids`. Also call `store.get_ids_by_filter(file_path="core.py")` and save as `expected_core_ids`. Also record `store.count()` as `expected_count`. Then delete the in-memory store object entirely (let it go out of scope or explicitly `del store`). Create a brand new `FaissVectorStore(collection_name=<same_name>)` instance, which will trigger `_load()` from disk. On the reloaded store, call `store.get_ids_by_filter(parent_class="Command")` and assert it equals `expected_command_ids`. Call `store.get_ids_by_filter(file_path="core.py")` and assert it equals `expected_core_ids`. Assert `store.count() == expected_count`. Also run a search query on the reloaded store and verify it returns results (not empty). If any assertion fails, the `_rebuild_metadata_indexes` method is not being called correctly during `_load()`, or the metadata JSON on disk is missing fields that the index builder expects. Check that `_rebuild_cache()` is called at the end of `_load()` and that `_rebuild_metadata_indexes()` is called inside `_rebuild_cache()`. Also check that the metadata dictionary loaded from JSON contains the `parent_class` and `file_path` fields for each chunk — if these fields were added after the index was originally built, the existing metadata JSON on disk will not have them, and the index builder should handle missing fields gracefully by defaulting to empty string rather than crashing.

---

## Test 4: SWE-bench Regression Test

### What to do

Run the existing SWE-bench evaluation suite against the modified codebase and compare the retrieval metrics (MRR, Recall@K, Precision@K, NDCG) against the baseline numbers reported in the project's `EVALUATION_REPORT_FINAL.md` and `README.md`. The metadata changes are designed to be additive and backward compatible, so metrics should either stay the same or improve. Any metric that drops indicates that the score boosting factors are displacing genuinely relevant results.

### Where to run it

Use the existing evaluation runner: `python -m graphcoderag.evaluation.swebench_runner_v2 --backend=faiss --retrieval-only`. The evaluation results will be saved to the `evaluation_results/` directory as a timestamped JSON file.

### How to verify

After the evaluation completes, open the generated JSON file and compare the following metrics against the baseline values from the README. For Click (small repo): baseline MRR was 0.900 and baseline Recall@10 was 70.6%, so the new MRR should be greater than or equal to 0.900 and the new Recall@10 should be greater than or equal to 70.6%. For PyTest (medium repo): baseline MRR was 0.430 and baseline Recall@10 was 66.7%. For Django (large repo): baseline MRR was 0.534 and baseline Recall@10 was 73.3%. For Scikit-Learn (large repo): baseline MRR was 0.147 and baseline Recall@10 was 20.0%. If any repository's MRR drops by more than 0.02 or Recall@10 drops by more than 2 percentage points, investigate which specific test cases regressed by comparing the per-query results in the new JSON against the most recent baseline JSON in `evaluation_results/`. The most likely cause of regression is the score boost multipliers (1.1x for filtered matches in `vector_retriever.py`, 1.15x for class-matching graph chunks and 1.10x for file-matching graph chunks in `hybrid_retriever.py`) pushing structurally-matched but semantically-weak chunks above genuinely relevant results. If this happens, reduce the multipliers — try 1.05x for filtered matches and 1.08x for class-matching graph chunks — and re-run the evaluation. If reducing the multipliers to 1.0 (effectively disabling the boosts) still shows regression, the problem is in the two-phase search merge logic or the parent-resolution refactor, not in the scoring, and you should compare the unfiltered Phase B results alone against the old system's results to isolate which change caused the regression. The metadata indexes and query entity extraction themselves cannot cause regression because they are only used to generate a candidate set and boost scores — they never remove results from the pipeline. If the evaluation runner fails to import new modules or crashes with attribute errors, check that the `query_analyzer.py` file is importable from the evaluation context and that all new method signatures have default parameters for backward compatibility (especially `query_entities=None` in `_merge_and_score`).

---

## Test 5: Edge Case Handling

### What to do

Verify that the system handles edge cases gracefully: queries that mention no recognizable entities, queries that mention entities not in the ingested codebase, queries with mixed casing, empty queries, and queries against an empty FAISS index.

### Where to create it

Add these as individual test functions in `tests/test_metadata_retrieval.py`.

### How to implement it

Write the following test functions. `test_no_entity_query`: run a query like "explain how the codebase works in general" which mentions no specific class, file, or function name. Assert that the `QueryAnalyzer.extract_entities()` returns empty lists for classes, files, and functions. Assert that `retriever.retrieve(query)` returns results (it should fall back to pure unfiltered FAISS search). `test_unknown_entity_query`: run a query like "How does the FooBarBaz class work?" where FooBarBaz is not in the ingested codebase. Assert that `extract_entities()` returns an empty classes list (since FooBarBaz does not match any known class), and that the retriever falls back to unfiltered search and still returns results. `test_case_insensitive_matching`: run a query like "how does the command class work" (lowercase "command") when the ingested codebase has a class called "Command" (uppercase). Assert that the `QueryAnalyzer` still matches it. If it does not, modify the `extract_entities` method to do case-insensitive comparison by lowercasing both the token and the known entity names during matching, while preserving the original casing in the returned `QueryEntities` object. `test_empty_query`: call `retriever.retrieve("")` and assert it returns an empty list without crashing. `test_empty_index`: create a fresh `FaissVectorStore` with no chunks added, instantiate a `VectorRetriever` with it, call `retrieve("any query")`, and assert it returns an empty list without crashing. All of these edge cases should be handled by the existing guard clauses (the `if self.store.count() == 0: return []` check in `vector_retriever.py` line 67, and the empty-candidate-set check in `search_filtered`), but they should be explicitly tested to confirm.

---

## Summary of Test Files to Create or Modify

1. **Create** `tests/test_metadata_retrieval.py` — contains Test 1 (end-to-end filtered vs unfiltered comparison), Test 2 (performance and fallback threshold), Test 3 (persistence across reload), and Test 5 (edge case handling). This is the main integration test file.
2. **Modify** `graphcoderag/storage/faiss_store.py` — add the 70% fallback threshold and the empty-candidate-set guard to `search_filtered` (Test 2).
3. **Run** `python -m graphcoderag.evaluation.swebench_runner_v2 --backend=faiss --retrieval-only` and compare output JSON against baseline metrics (Test 4). No code changes needed for this, just execution and comparison.

The tests should be run in order: Test 5 (edge cases) first because it catches basic crashes, then Test 3 (persistence) because it validates infrastructure, then Test 2 (performance) because it may require a code change to `faiss_store.py`, then Test 1 (end-to-end comparison) because it requires a fully ingested repository, and finally Test 4 (SWE-bench regression) last because it is the most time-consuming and depends on all other components working correctly.
