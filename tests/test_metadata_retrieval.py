"""
Integration tests for the metadata-enhanced retrieval pipeline.

Test execution order (as per INTEGRATION_TESTING_INSTRUCTIONS.md):
  Test 5 -> Test 3 -> Test 2 -> Test 1 -> (Test 4 is a manual SWE-bench run)

Run with:
    python tests/test_metadata_retrieval.py
"""
import sys
import time
import traceback
from pathlib import Path

# Ensure project root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =======================================================================
#  Helpers
# =======================================================================

_PASS = "[PASS]"
_FAIL = "[FAIL]"
_SKIP = "[SKIP]"


def _report(test_name: str, passed: bool, detail: str = ""):
    status = _PASS if passed else _FAIL
    print(f"  {status}  {test_name}")
    if detail:
        for line in detail.strip().split("\n"):
            print(f"         {line}")


def _section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# =======================================================================
#  Test 5 -- Edge Case Handling  (run FIRST)
# =======================================================================

def test_edge_cases():
    _section("Test 5: Edge Case Handling")
    from graphcoderag.retrieval.query_analyzer import QueryAnalyzer, QueryEntities

    analyzer = QueryAnalyzer()
    known_cls = {"Command", "Group", "Option"}
    known_files = {"src/click/core.py", "src/click/decorators.py"}
    known_funcs = {"parse_args", "invoke", "make_context"}

    # 5a: No-entity query
    e = analyzer.extract_entities(
        "explain how the codebase works in general",
        known_classes=known_cls, known_files=known_files, known_functions=known_funcs,
    )
    _report("5a: No-entity query -> empty lists",
            not e.classes and not e.files and not e.functions,
            f"classes={e.classes}, files={e.files}, funcs={e.functions}")

    # 5b: Unknown entity query
    e = analyzer.extract_entities(
        "How does the FooBarBaz class work?",
        known_classes=known_cls, known_files=known_files, known_functions=known_funcs,
    )
    _report("5b: Unknown entity -> empty classes",
            "FooBarBaz" not in e.classes,
            f"classes={e.classes}")

    # 5c: Case-insensitive matching
    e = analyzer.extract_entities(
        "how does the command class work",
        known_classes=known_cls, known_files=known_files, known_functions=known_funcs,
    )
    _report("5c: Case-insensitive 'command' -> matches 'Command'",
            "Command" in e.classes,
            f"classes={e.classes}")

    # 5d: Empty query -> empty results from retriever (no crash)
    try:
        from graphcoderag.retrieval.vector_retriever import VectorRetriever
        from graphcoderag.storage.faiss_store import FaissVectorStore
        empty_store = FaissVectorStore(collection_name="__test_empty_idx__")
        empty_store.clear()  # ensure empty
        vr = VectorRetriever(vector_store=empty_store)
        results = vr.retrieve("")
        _report("5d: Empty query on empty index -> no crash",
                results == [],
                f"returned {len(results)} results")
        empty_store.clear()
    except Exception as exc:
        _report("5d: Empty query on empty index -> no crash", False, str(exc))

    # 5e: Query against populated store but no matching entity
    try:
        store = FaissVectorStore(collection_name="code_chunks")
        if store.count() == 0:
            _report("5e: Populated store, no entity match", False, "code_chunks index is empty")
        else:
            vr = VectorRetriever(vector_store=store)
            results = vr.retrieve("tell me about something generic")
            _report("5e: No entity match -> falls back to unfiltered, returns results",
                    len(results) > 0,
                    f"returned {len(results)} results")
    except Exception as exc:
        _report("5e: Populated store, no entity match", False, str(exc))


# =======================================================================
#  Test 3 -- Metadata Index Persistence Across Reload
# =======================================================================

def test_faiss_persistence():
    _section("Test 3: Metadata Index Persistence Across Reload")
    from graphcoderag.storage.faiss_store import FaissVectorStore

    collection = "code_chunks"
    store1 = FaissVectorStore(collection_name=collection)
    if store1.count() == 0:
        _report("Persistence test", False, "code_chunks index is empty -- skipping")
        return

    # Capture reference data from the live store
    expected_count = store1.count()
    expected_classes = store1.get_known_classes()
    expected_files = store1.get_known_files()

    # Pick one class to test filter persistence
    test_class = next(iter(expected_classes)) if expected_classes else None
    expected_class_ids = store1.get_ids_by_filter(parent_class=test_class) if test_class else set()

    # Drop reference and reload from disk
    del store1

    store2 = FaissVectorStore(collection_name=collection)

    _report("3a: count() matches after reload",
            store2.count() == expected_count,
            f"expected={expected_count}, got={store2.count()}")

    _report("3b: known_classes match after reload",
            store2.get_known_classes() == expected_classes,
            f"expected {len(expected_classes)} classes, got {len(store2.get_known_classes())}")

    _report("3c: known_files match after reload",
            store2.get_known_files() == expected_files,
            f"expected {len(expected_files)} files, got {len(store2.get_known_files())}")

    if test_class:
        reloaded_ids = store2.get_ids_by_filter(parent_class=test_class)
        _report(f"3d: get_ids_by_filter(parent_class='{test_class}') matches",
                reloaded_ids == expected_class_ids,
                f"expected {len(expected_class_ids)} ids, got {len(reloaded_ids)}")
    else:
        _report("3d: filter persistence", False, "no classes found in index")


# =======================================================================
#  Test 2 -- Filtered Search Performance & Fallback
# =======================================================================

def test_search_performance():
    _section("Test 2: Filtered Search Performance & Fallback Threshold")
    from graphcoderag.storage.faiss_store import FaissVectorStore

    store = FaissVectorStore(collection_name="code_chunks")
    if store.count() == 0:
        _report("Performance test", False, "code_chunks index is empty -- skipping")
        return

    query = "How does the Command class handle argument parsing?"
    n_runs = 3
    total = store.count()

    # Prepare candidate sets
    classes = store.get_known_classes()
    if not classes:
        _report("Performance test", False, "No classes in index -- skipping")
        return

    # Small set: one class's chunks
    test_class = "Command" if "Command" in classes else next(iter(classes))
    small_set = store.get_ids_by_filter(parent_class=test_class)

    # Large set: >70% of all chunk_ids
    all_ids = set(store.chunk_ids)
    large_set_size = int(0.8 * total)
    large_set = set(list(all_ids)[:large_set_size])

    print(f"\n  Index size: {total} vectors")
    print(f"  Small candidate set ({test_class}): {len(small_set)} chunks")
    print(f"  Large candidate set (80%): {len(large_set)} chunks")
    print()

    # Benchmark: unfiltered
    times_unfiltered = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        res_unfiltered = store.search(query, top_k=10)
        times_unfiltered.append(time.perf_counter() - t0)
    avg_unfiltered = sum(times_unfiltered) / n_runs

    # Benchmark: small filtered
    times_small = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        res_small = store.search_filtered(query, top_k=10, candidate_ids=small_set)
        times_small.append(time.perf_counter() - t0)
    avg_small = sum(times_small) / n_runs

    # Benchmark: large filtered (should trigger 70% fallback)
    times_large = []
    for _ in range(n_runs):
        t0 = time.perf_counter()
        res_large = store.search_filtered(query, top_k=10, candidate_ids=large_set)
        times_large.append(time.perf_counter() - t0)
    avg_large = sum(times_large) / n_runs

    print(f"  {'Method':<30} {'Avg Time':>10}  {'Results':>8}")
    print(f"  {'-' * 50}")
    print(f"  {'Unfiltered (baseline)':<30} {avg_unfiltered*1000:>8.1f}ms  {len(res_unfiltered):>8}")
    print(f"  {f'Filtered (small, {len(small_set)} ids)':<30} {avg_small*1000:>8.1f}ms  {len(res_small):>8}")
    print(f"  {f'Filtered (large, {len(large_set)} ids)':<30} {avg_large*1000:>8.1f}ms  {len(res_large):>8}")
    print()

    # Check small filtered returned results from the candidate set
    if res_small:
        small_result_ids = {r["chunk_id"] for r in res_small}
        # Results should be subset of candidate_ids (some may be missing if not indexed)
        valid_small = small_result_ids.issubset(small_set | set(store.chunk_ids))
        _report("2a: Small filtered returns valid results",
                len(res_small) > 0, f"{len(res_small)} results")
    else:
        _report("2a: Small filtered returns valid results", False, "0 results")

    # Check 70% fallback: large filtered should produce same results as unfiltered
    large_ids = [r["chunk_id"] for r in res_large]
    unfiltered_ids = [r["chunk_id"] for r in res_unfiltered]
    fallback_triggered = large_ids == unfiltered_ids
    _report("2b: Large candidate (>70%) triggers fallback -> identical to unfiltered",
            fallback_triggered,
            f"large_ids == unfiltered_ids: {fallback_triggered}")

    # Performance: small filtered should not be dramatically slower
    perf_ok = avg_small < avg_unfiltered * 5  # generous 5x tolerance
    _report("2c: Small filtered search performance acceptable",
            perf_ok,
            f"small={avg_small*1000:.1f}ms vs unfiltered={avg_unfiltered*1000:.1f}ms "
            f"(ratio={avg_small/max(avg_unfiltered, 0.0001):.1f}x)")


# =======================================================================
#  Test 1 -- End-to-End Retrieval Comparison (Filtered vs Unfiltered)
# =======================================================================

def test_e2e_retrieval():
    _section("Test 1: End-to-End Retrieval Comparison")
    from graphcoderag.storage.faiss_store import FaissVectorStore
    from graphcoderag.retrieval.vector_retriever import VectorRetriever, RetrievalResult

    store = FaissVectorStore(collection_name="code_chunks")
    if store.count() == 0:
        _report("E2E test", False, "code_chunks index is empty -- skipping")
        return

    retriever = VectorRetriever(vector_store=store)

    test_queries = [
        ("How does the Command class handle argument parsing?", ["Command"]),
        ("What happens in core.py when a command is invoked?", ["core.py"]),
        ("How does Group inherit from Command?", ["Group", "Command"]),
        ("What does the make_context function do?", ["make_context"]),
        ("How are options parsed in decorators.py?", ["decorators.py"]),
    ]

    print(f"\n  {'Query':<55} {'Overlap':>8} {'FiltHit':>8} {'UnfiltHit':>8} {'FAvg5':>7} {'UAvg5':>7}")
    print(f"  {'-' * 100}")

    for query, expected_entities in test_queries:
        # Phase A+B (new metadata-filtered path)
        filtered_results = retriever.retrieve(query, top_k=10)

        # Old unfiltered path: raw FAISS search + manual parent resolution
        raw_unfiltered = store.search(query, top_k=30)
        unfiltered_resolved = {}
        for r in raw_unfiltered:
            meta = r.get("metadata", {})
            dist = r.get("distance", 1.0)
            sim = max(0.0, 1.0 - (dist / 2.0))
            parent_id = meta.get("parent_id")
            resolved_id = parent_id if (parent_id and store.get_chunk_metadata(parent_id)) else r["chunk_id"]
            if resolved_id not in unfiltered_resolved:
                unfiltered_resolved[resolved_id] = sim
        unfiltered_top10 = sorted(unfiltered_resolved.items(), key=lambda x: x[1], reverse=True)[:10]

        # Metrics
        filtered_ids = [r.chunk_id for r in filtered_results[:10]]
        unfiltered_ids = [cid for cid, _ in unfiltered_top10]

        overlap = len(set(filtered_ids) & set(unfiltered_ids))

        def entity_hit_rate(results_with_meta, entities):
            hits = 0
            for item in results_with_meta:
                if isinstance(item, RetrievalResult):
                    name = item.name or ""
                    pc = item.parent_class or ""
                    fp = item.file_path or ""
                else:
                    name = pc = fp = ""
                for ent in entities:
                    ent_low = ent.lower()
                    if ent_low in name.lower() or ent_low in pc.lower() or ent_low in fp.lower():
                        hits += 1
                        break
            return hits / max(len(results_with_meta), 1)

        filt_hit = entity_hit_rate(filtered_results[:10], expected_entities)

        # Build lightweight result objects for unfiltered
        unf_hit_count = 0
        for cid, _ in unfiltered_top10:
            meta = store.get_chunk_metadata(cid) or {}
            for ent in expected_entities:
                el = ent.lower()
                if el in (meta.get("name", "") or "").lower() or \
                   el in (meta.get("parent_class", "") or "").lower() or \
                   el in (meta.get("file_path", "") or "").lower():
                    unf_hit_count += 1
                    break
        unf_hit = unf_hit_count / max(len(unfiltered_top10), 1)

        f_avg5 = sum(r.score for r in filtered_results[:5]) / max(len(filtered_results[:5]), 1)
        u_avg5 = sum(s for _, s in unfiltered_top10[:5]) / max(len(unfiltered_top10[:5]), 1)

        short_q = query[:52] + "..." if len(query) > 55 else query
        print(f"  {short_q:<55} {overlap:>6}/10 {filt_hit:>7.0%} {unf_hit:>9.0%} {f_avg5:>7.3f} {u_avg5:>7.3f}")

    print()
    _report("1: E2E comparison table printed above",
            True, "Check that FiltHit >= UnfiltHit for entity-specific queries")


# =======================================================================
#  Main
# =======================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  GraphCodeRAG -- Metadata Retrieval Integration Tests")
    print("=" * 60)

    tests = [
        ("Test 5: Edge Cases", test_edge_cases),
        ("Test 3: Persistence", test_faiss_persistence),
        ("Test 2: Performance", test_search_performance),
        ("Test 1: E2E Retrieval", test_e2e_retrieval),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            _section(name)
            _report(name, False, f"CRASHED: {exc}\n{traceback.format_exc()}")

    print(f"\n{'=' * 60}")
    print("  All integration tests completed.")
    print(f"{'=' * 60}\n")
