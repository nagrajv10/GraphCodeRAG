# GraphCodeRAG — Metadata-Enhanced Retrieval: What to Change, Where, and How

## Context for the AI Reading This

You are working on a project called GraphCodeRAG, a hybrid RAG system for Python codebases. The repository lives at `https://github.com/nagrajv10/GraphCodeRAG.git`. The system currently uses a two-tier parent-child chunking strategy where large code chunks (over 1500 characters) are split into overlapping child snippets for FAISS vector search, and at retrieval time child hits are resolved back to their full parent chunks via a `parent_id` pointer stored in a flat JSON metadata dictionary. The system also has a Neo4j knowledge graph that captures IMPORTS, CALLS, CONTAINS, and INHERITS edges between code entities. The goal of this change is to make the metadata that is already being stored (file path, class name, function name, docstring, chunk type, parent-child relationships, decorators) actively participate in retrieval scoring and filtering, rather than being used only for post-hoc resolution after FAISS returns results.

---

## Problem Statement

Right now the retrieval pipeline works like this: a user query is embedded using CodeRankEmbed, FAISS does a brute-force inner-product search across all indexed vectors, results come back ranked purely by cosine similarity, and only then does the system look at metadata to resolve children to parents and deduplicate. The metadata is rich (file path, chunk type, parent class, docstring, signature, decorators, parent-child links) but it plays zero role in deciding which vectors to search or how to score them. This causes three concrete problems. First, when a user asks about a specific class like "How does the Command class parse arguments?", FAISS searches the entire index and may return chunks from unrelated files that happen to have similar embeddings, even though the metadata could immediately narrow candidates to chunks where `parent_class == "Command"` or `name` contains "Command". Second, the 3x over-fetch (`fetch_k = k * 3` on line 72 of `vector_retriever.py`) exists solely to compensate for child-to-parent deduplication collapsing multiple hits into fewer results, which is wasteful when a reverse index from parent to children could achieve the same outcome without over-fetching. Third, the hybrid merger in `hybrid_retriever.py` scores graph-discovered chunks using only their cosine similarity and hop distance, but ignores metadata signals like whether the graph chunk shares the same parent class or file as the query's target, which could provide a meaningful relevance boost.

---

## Change 1: Add a Metadata Index to FaissVectorStore

### What to change

The file `graphcoderag/storage/faiss_store.py` currently stores metadata as a flat dictionary (`self.metadata: Dict[str, Dict[str, Any]]`) keyed by chunk_id. This dictionary is only used for individual lookups via `get_chunk_metadata(chunk_id)`. You need to add inverted indexes that allow fast lookup by metadata field values, so that the retrieval layer can ask questions like "give me all chunk_ids where parent_class is Command" or "give me all chunk_ids in file core.py" without scanning the entire dictionary.

### Where to change

In `graphcoderag/storage/faiss_store.py`, inside the `FaissVectorStore` class.

### How to change

Add a new method called `_rebuild_metadata_indexes` that builds three dictionaries: `self.file_index` mapping each unique `file_path` to a set of chunk_ids, `self.class_index` mapping each unique `parent_class` value to a set of chunk_ids, and `self.type_index` mapping each `chunk_type` value to a set of chunk_ids. Call this method at the end of `_load()` (after loading metadata from disk) and at the end of `add_chunks()` (after adding new metadata entries). The implementation should iterate over `self.metadata.items()` and populate the three dictionaries. Then add a new public method called `get_ids_by_filter(file_path=None, parent_class=None, chunk_type=None)` that takes optional filter parameters and returns the intersection of matching chunk_id sets from the relevant indexes. If no filters are provided it returns all chunk_ids. This method should return a Python `set` of chunk_id strings. Also add a method called `search_filtered(query, top_k, candidate_ids)` that takes a set of candidate chunk_ids, finds their positions in `self.chunk_ids` list using the existing `self.id_to_idx` mapping, reconstructs their embeddings from the FAISS index using `self.index.reconstruct(idx)`, computes inner products with the query embedding manually using numpy dot product, and returns the top_k results sorted by score. This avoids having to build a separate FAISS index per filter combination. The `_rebuild_metadata_indexes` call should also be added inside `_rebuild_cache()` so that the indexes are always kept in sync with the chunk_ids list.

---

## Change 2: Add Query Entity Extraction

### What to change

The system currently passes the user's raw natural language query directly to FAISS embedding without analyzing what code entities the query is referring to. You need to add a lightweight entity extraction step that parses the query string to identify mentioned class names, function names, and file paths, which can then be used as metadata filters.

### Where to change

Create a new file at `graphcoderag/retrieval/query_analyzer.py`.

### How to change

Create a class called `QueryAnalyzer` with a method `extract_entities(query, known_classes, known_files, known_functions)` that takes the query string and lists of known entity names (which can be derived from the metadata index). The method should do the following. First, tokenize the query by splitting on whitespace and punctuation. Second, for each token, check if it matches (case-insensitive) any known class name, file name (with or without `.py` extension), or function name. Third, also check for patterns like "ClassName.method_name" which indicate both a class and a method. Fourth, return a dataclass called `QueryEntities` with fields `classes: List[str]`, `files: List[str]`, `functions: List[str]`, and `raw_query: str`. The known entity lists should be obtained from the FAISS metadata index: `known_classes` is the set of keys in `self.class_index`, `known_files` is the set of keys in `self.file_index`, and known_functions can be extracted from the metadata values where `chunk_type == "function"`. This extraction does not need to be perfect or use NLP; simple string matching against known entities is sufficient because the universe of possible entities is bounded by what was ingested.

---

## Change 3: Modify VectorRetriever to Use Metadata Filtering

### What to change

The file `graphcoderag/retrieval/vector_retriever.py` contains the `VectorRetriever.retrieve()` method which currently does a single unfiltered FAISS search followed by parent resolution. You need to modify this method to optionally perform a metadata-filtered search when the query mentions specific entities, and to replace the 3x over-fetch with a smarter parent-aware deduplication strategy.

### Where to change

In `graphcoderag/retrieval/vector_retriever.py`, inside the `VectorRetriever` class, modifying the `retrieve()` method and adding helper methods.

### How to change

First, at the top of the `retrieve()` method, instantiate a `QueryAnalyzer` and call `extract_entities()` with the query and the known entity sets from the FAISS store's metadata indexes. If the extraction finds any classes, files, or functions, call the FAISS store's `get_ids_by_filter()` to get a candidate set. Then do a two-phase search: Phase A runs `search_filtered(query, top_k=k, candidate_ids=filtered_set)` to get results strictly matching the metadata filter, and Phase B runs the normal unfiltered `self.store.search(query, top_k=k)` to get the standard results. Merge Phase A and Phase B results, giving Phase A results a small score boost (multiply their similarity by 1.1, capped at 1.0) because they matched both semantically and structurally. Deduplicate by chunk_id, keeping the higher-scored entry. This two-phase approach ensures that metadata filtering improves results when entities are recognized, but never harms results when they are not (because Phase B always runs as a fallback).

Second, replace the 3x over-fetch strategy. Instead of fetching `k * 3` results and hoping enough survive deduplication, build a reverse index at the start of retrieval: `parent_to_children = defaultdict(list)` populated from the metadata's `parent_id` field. After FAISS returns results, for each result that is a child chunk, look up the parent_id, and check if we have already resolved that parent. If yes, just add the child's score to the existing parent's `child_scores` list. If no, resolve the parent and start tracking it. Continue fetching from FAISS in batches of `k` until you have `k` unique resolved parents, or until you have exhausted `k * 3` raw results (as a safety cap). This is more efficient because it stops early when enough unique parents are found rather than always fetching 3x.

---

## Change 4: Add Metadata-Aware Scoring to the Hybrid Merger

### What to change

The file `graphcoderag/retrieval/hybrid_retriever.py` contains the `_merge_and_score()` method which scores graph-discovered chunks using cosine similarity and graph hop distance, plus a cross-file bonus. You need to add metadata-derived scoring signals so that graph chunks which share structural properties with the query's target entities get appropriately boosted.

### Where to change

In `graphcoderag/retrieval/hybrid_retriever.py`, inside the `_merge_and_score()` method, specifically in the Step 3 loop (around line 269 onward) where graph-only chunks are scored.

### How to change

Pass the `QueryEntities` object (from Change 2) into `_merge_and_score()` as an additional parameter. The `retrieve()` method should extract entities once and pass them through. Then in the Step 3 scoring loop, after computing the base `hybrid_score` for each graph chunk, apply the following conditional boosts. If `query_entities.classes` is non-empty and the graph chunk's `parent_class` or `name` matches any of the query's mentioned classes, multiply `hybrid_score` by 1.15 (same magnitude as the existing cross-file bonus). If `query_entities.files` is non-empty and the graph chunk's `file_path` matches any mentioned file, multiply `hybrid_score` by 1.10. These boosts stack with the existing cross-file bonus. The rationale is that if the user asked about "Command" and the graph discovered a chunk that belongs to the Command class, that chunk is almost certainly relevant even if its cosine similarity to the query is moderate. Also modify the `retrieve()` method signature to accept an optional `query_entities` parameter and pass it through to `_merge_and_score()`, defaulting to None if the caller does not provide it (for backward compatibility with evaluation scripts).

---

## Change 5: Store Richer Metadata During Ingestion

### What to change

The file `graphcoderag/storage/faiss_store.py` in the `add_chunks()` method currently stores metadata fields like `file_path`, `chunk_type`, `name`, `docstring`, `parent_class`, `parent_id`, and `is_child`. You should additionally store `signature`, `decorators`, and a new field called `import_names` (the list of names imported by the module-level chunk of the same file), because these fields can improve metadata filtering and scoring in future iterations.

### Where to change

In `graphcoderag/storage/faiss_store.py`, inside the `add_chunks()` method, in the dictionary comprehension that builds metadata entries (around line 110).

### How to change

Add two new fields to the metadata dictionary: `"signature": getattr(c, "signature", "") or ""` and `"decorators": getattr(c, "decorators", [])`. The signature field is useful because queries that mention function parameter names (like "the function that takes ctx and args") can be matched against signatures via the query analyzer. The decorators field is useful because queries about specific patterns ("all the click.command decorated functions") can filter by decorator content. Also, during ingestion (in `run_ingestion.py` or in `code_chunker.py`), collect the import names from each file's module-level chunk and attach them as a field called `import_names` to every chunk from that same file. This allows the metadata filter to answer questions like "which chunks are in files that import the requests library" without hitting Neo4j. To implement this, after the chunker produces all chunks for a file, find the module-level chunk (where `chunk_type == "module"`), parse its `source_code` for import statements (simple regex like `from\s+(\S+)\s+import` and `import\s+(\S+)` is sufficient), collect the module names into a list, and set `import_names` on every chunk from that file.

---

## Change 6: Update the Embedding Text to Separate Metadata from Code

### What to change

The `to_embedding_text()` method in `graphcoderag/ingestion/code_chunker.py` (line 51) currently prepends metadata as Python comment lines (`# File: ...`, `# Class: ...`) directly into the text that gets embedded. This means the metadata is baked into the embedding vector, which is generally good, but it makes it impossible to use the metadata independently for filtering versus embedding. This change is minor and optional but improves clarity.

### Where to change

In `graphcoderag/ingestion/code_chunker.py`, in the `CodeChunk` class.

### How to change

Add a new method called `to_metadata_dict()` that returns a clean dictionary of all metadata fields (file_path, parent_class, chunk_type, name, docstring, signature, decorators). Keep `to_embedding_text()` as-is because embedding the metadata context into the vector is beneficial for semantic search quality. The new method is used by the FAISS store's metadata index builders so they have a canonical source of metadata rather than reconstructing it from the stored dictionary. This is a refactoring change that does not alter behavior but makes the code easier to maintain because metadata field names are defined in one place (the CodeChunk dataclass) rather than being duplicated between `code_chunker.py` and `faiss_store.py`.

---

## Summary of File Changes

Here is the complete list of files that need to be created or modified, in the order they should be implemented:

1. **Create** `graphcoderag/retrieval/query_analyzer.py` — new file containing the `QueryAnalyzer` class and `QueryEntities` dataclass (Change 2).
2. **Modify** `graphcoderag/storage/faiss_store.py` — add `_rebuild_metadata_indexes()`, `get_ids_by_filter()`, and `search_filtered()` methods to the `FaissVectorStore` class, and call `_rebuild_metadata_indexes()` from `_rebuild_cache()` (Change 1). Also add `signature` and `decorators` fields to the metadata dictionary in `add_chunks()` (Change 5).
3. **Modify** `graphcoderag/retrieval/vector_retriever.py` — modify `retrieve()` to instantiate `QueryAnalyzer`, run two-phase filtered+unfiltered search, and replace the 3x over-fetch with parent-aware progressive fetching (Change 3).
4. **Modify** `graphcoderag/retrieval/hybrid_retriever.py` — modify `retrieve()` to extract query entities and pass them to `_merge_and_score()`, and modify `_merge_and_score()` to apply metadata-aware scoring boosts for graph chunks that match query entities (Change 4).
5. **Modify** `graphcoderag/ingestion/code_chunker.py` — add `to_metadata_dict()` method to `CodeChunk` class (Change 6, optional refactor).
6. **Modify** `graphcoderag/ingestion/code_chunker.py` or `run_ingestion.py` — attach `import_names` field to chunks during ingestion (Change 5).

No changes are needed to `graph_store.py`, `graph_retriever.py`, `embedding.py`, `ast_parser.py`, `dependency_extractor.py`, `file_scanner.py`, `generator.py`, `prompt_templates.py`, or the evaluation modules. The API layer (`app/api.py`) does not need changes because it calls `HybridRetriever.retrieve()` which will internally use the new metadata-aware logic transparently.

---

## Backward Compatibility

All changes are additive. The `QueryAnalyzer` returns empty entity lists when no entities are recognized, in which case the retriever falls back to the existing unfiltered FAISS search. The metadata indexes are built from already-stored metadata fields, so existing FAISS indexes on disk do not need to be rebuilt (the indexes are constructed in memory from the loaded metadata JSON). The `_merge_and_score()` method accepts `query_entities=None` as default, preserving compatibility with evaluation scripts that call it directly. The two-phase search (filtered + unfiltered) always includes the unfiltered phase, so results can never be worse than the current system — they can only be equal or better.
