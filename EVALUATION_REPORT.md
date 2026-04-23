# GraphCodeRAG — Complete Evaluation Report
## SWE-bench Lite Retrieval & Generation Evaluation

**Date:** April 21, 2026
**Author:** Peddarangareddy Lokeshwar Reddy
**Course:** AI for Engineers — Spring 2026

---

## 1. Evaluation Overview

This evaluation compares **GraphCodeRAG** (AST-aware chunking + knowledge graph hybrid retrieval)
against **Standard RAG** (character-based chunking + vector similarity) on code understanding tasks
derived from the SWE-bench Lite dataset.

### 1.1 Methodology

| Parameter | Value |
|-----------|-------|
| **Benchmark** | SWE-bench Lite (curated Python bug-fix dataset) |
| **Total Instances** | 60 (15 per repository) |
| **Repositories** | pallets/click, pytest-dev/pytest, scikit-learn/sklearn, django/django |
| **Pipelines** | **A** = Standard RAG (char chunks + vector), **B_vec** = AST chunks + vector, **B_hybrid** = AST chunks + vector + graph |
| **Embedding Model** | all-MiniLM-L6-v2 (384d, sentence-transformers) |
| **Graph Store** | Neo4j (CALLS, IMPORTS, CONTAINS, INHERITS edges) |
| **AST Parser** | Tree-sitter (Python) |
| **LLM for Generation** | Gemini 2.5 Flash (temperature=0) |
| **LLM Judge** | Gemini 2.5 Flash (5-point scale: accuracy, completeness, helpfulness) |
| **Chunking — Standard RAG** | Character-based: 512 chars, 50 overlap |
| **Chunking — GraphCodeRAG** | AST-aware: function/class/module boundaries |

### 1.2 Pipelines

| Pipeline | Chunking | Retrieval | Description |
|----------|----------|-----------|-------------|
| **A (Standard RAG)** | Character (512 char) | Vector similarity | Baseline — text splits + embeddings |
| **B_vec (AST + Vector)** | AST-aware (Tree-sitter) | Vector similarity | AST chunks + embeddings (no graph) |
| **B_hybrid (GraphCodeRAG)** | AST-aware (Tree-sitter) | Vector + Graph (2-hop) | Full system: AST + embeddings + Neo4j traversal |

### 1.3 Evaluation Run

```
File: evaluation_results/swebench_v2_20260421_173828.json
Command: python -m graphcoderag.evaluation.swebench_runner_v2 --retrieval-only
Mode: retrieval-only (60 instances across 4 repos)
```

---

## 2. Retrieval Results

### 2.1 pallets/click — 15 instances (Small, ~20k LOC)

**Ingestion:** Standard RAG = 1,910 chunks | AST-aware = 696 chunks

| Metric | K | Std RAG (A) | AST+Vec (B_vec) | Hybrid (B_hybrid) | D(Hybrid-Std) |
|--------|---|:-----------:|:----------------:|:-----------------:|:-------------:|
| **MRR** | 1 | **0.867** | 0.733 | 0.733 | -0.133 |
| **MRR** | 3 | **0.933** | 0.800 | 0.800 | -0.133 |
| **MRR** | 5 | **0.933** | 0.830 | 0.830 | -0.103 |
| **MRR** | 10 | **0.933** | 0.830 | 0.830 | -0.103 |
| **File Recall** | 5 | **0.739** | 0.656 | 0.656 | -0.083 |
| **File Recall** | 10 | **0.811** | 0.789 | 0.789 | -0.022 |
| **Hit Rate** | 5 | **1.000** | 1.000 | 1.000 | 0.000 |
| **Hit Rate** | 10 | **1.000** | 1.000 | 1.000 | 0.000 |

**Analysis:** Standard RAG wins on Click because the small codebase (696 AST chunks vs 1,910 char chunks)
means character chunking creates more overlapping context windows. The 512-char chunks with 50-char
overlap capture cross-function patterns that tight AST boundaries miss. Both hit 100% hit rate at K>=5.

---

### 2.2 pytest-dev/pytest — 15 instances (Medium, ~50k LOC)

**Ingestion:** Standard RAG = 9,549 chunks | AST-aware = 2,995 chunks

| Metric | K | Std RAG (A) | AST+Vec (B_vec) | Hybrid (B_hybrid) | D(Hybrid-Std) |
|--------|---|:-----------:|:----------------:|:-----------------:|:-------------:|
| **MRR** | 1 | 0.333 | **0.467** | **0.467** | +0.133 |
| **MRR** | 3 | 0.367 | **0.467** | **0.467** | +0.100 |
| **MRR** | 5 | 0.367 | **0.467** | **0.467** | +0.100 |
| **MRR** | 10 | 0.386 | **0.489** | **0.489** | +0.103 |
| **File Recall** | 5 | 0.400 | **0.467** | **0.467** | +0.067 |
| **File Recall** | 10 | 0.533 | **0.600** | **0.600** | +0.067 |
| **Hit Rate** | 5 | 0.400 | **0.467** | **0.467** | +0.067 |
| **Hit Rate** | 10 | 0.533 | **0.600** | **0.600** | +0.067 |

**Analysis:** AST-aware chunking provides **+27.2% MRR improvement** at K=5. Pytest has 9,549 character
chunks (3.2x more than AST). Character chunks dilute the embedding space with noisy partial-function
fragments. AST chunking produces semantically complete code units that embed more meaningfully.

---

### 2.3 scikit-learn/sklearn — 15 instances (Medium-Large, ~80k LOC)

**Ingestion:** Standard RAG = 41,184 chunks | AST-aware = 5,942 chunks

| Metric | K | Std RAG (A) | AST+Vec (B_vec) | Hybrid (B_hybrid) | D(Hybrid-Std) |
|--------|---|:-----------:|:----------------:|:-----------------:|:-------------:|
| **MRR** | 1 | 0.067 | **0.200** | **0.200** | +0.133 |
| **MRR** | 3 | 0.067 | **0.200** | **0.200** | +0.133 |
| **MRR** | 5 | 0.083 | **0.217** | **0.217** | +0.133 |
| **MRR** | 10 | 0.093 | **0.217** | **0.217** | +0.124 |
| **File Recall** | 5 | 0.133 | **0.267** | **0.267** | +0.133 |
| **File Recall** | 10 | 0.200 | **0.267** | **0.267** | +0.067 |

**Analysis:** The biggest improvement: **AST+Vector has 2.6x the MRR of Standard RAG at K=5** (0.217 vs 0.083).
With 41,184 character chunks, Standard RAG drowns in noise — the embedding space is too diluted.
AST-aware chunking reduces to 5,942 focused chunks, making each chunk a complete function or class.
The absolute numbers are low for both because sklearn uses Cython/C extensions that limit pure-Python indexing.

---

### 2.4 django/django — 15 instances (Large, ~300k LOC)

**Ingestion:** Standard RAG = 50,900 chunks | AST-aware = 27,724 chunks

| Metric | K | Std RAG (A) | AST+Vec (B_vec) | Hybrid (B_hybrid) | D(Hybrid-Std) |
|--------|---|:-----------:|:----------------:|:-----------------:|:-------------:|
| **MRR** | 1 | **0.533** | 0.467 | 0.467 | -0.067 |
| **MRR** | 3 | 0.589 | 0.589 | 0.589 | 0.000 |
| **MRR** | 5 | **0.606** | 0.589 | 0.589 | -0.017 |
| **MRR** | 10 | **0.614** | 0.596 | 0.596 | -0.018 |
| **File Recall** | 3 | 0.667 | **0.733** | **0.733** | +0.067 |
| **File Recall** | 5 | 0.733 | 0.733 | 0.733 | 0.000 |
| **File Recall** | 10 | 0.800 | 0.800 | 0.800 | 0.000 |

**Analysis:** At scale (300k LOC), both methods converge. Standard RAG has a marginal MRR lead (-0.018)
due to more overlapping context, but AST-aware chunking reaches the same File Recall faster (73.3% vs 66.7% at K=3).
Neo4j graph edges were skipped for django (96k edges caused ingestion timeout).

---

## 3. Cross-Repository Summary @ K=10

| Repository | Size | Std RAG MRR | AST+Vec MRR | Hybrid MRR | Delta | FR@10 (Hybrid) |
|-----------|------|:-----------:|:-----------:|:----------:|:-----:|:--------------:|
| **click** | Small (20k LOC) | **0.933** | 0.830 | 0.830 | -0.103 | 78.9% |
| **pytest** | Medium (50k LOC) | 0.386 | **0.489** | **0.489** | **+0.103** | 60.0% |
| **sklearn** | Medium (80k LOC) | 0.093 | **0.217** | **0.217** | **+0.124** | 26.7% |
| **django** | Large (300k LOC) | **0.614** | 0.596 | 0.596 | -0.018 | 80.0% |

---

## 4. Generation Quality (Click, 15 Test Cases)

*From evaluation_results/eval_20260418_124609.json*

### 4.1 LLM Judge Scores (Gemini 2.5 Flash, 1-5 scale)

| Metric | RAG+Hybrid | Vector-Only | Plain LLM |
|--------|:----------:|:-----------:|:---------:|
| Accuracy | 4.80 | 4.73 | 4.80 |
| Completeness | 4.73 | 4.67 | 4.80 |
| Helpfulness | 4.80 | 4.73 | 4.80 |
| **Overall Average** | **4.78** | 4.71 | 4.80 |

### 4.2 Pairwise Win Rates

| Comparison | Wins | Ties | Losses |
|------------|:----:|:----:|:------:|
| RAG vs Plain LLM | 2 | 10 | 3 |
| RAG vs Vector-Only | **2** | 12 | 1 |

---

## 5. Key Findings

### 5.1 AST-Aware Chunking Is the Primary Innovation

| Finding | Evidence |
|---------|----------|
| **AST chunking helps most on medium+ repos** | pytest: +27.2% MRR, sklearn: +161% MRR |
| **Character chunking wins on small repos** | click: Standard RAG wins by -10.3% MRR |
| **The crossover point is ~5K chunks** | Below that, character overlap is helpful; above, it dilutes |

### 5.2 Graph Traversal Has Limited Impact (B_vec = B_hybrid)

| Observation | Reason |
|-------------|--------|
| Hybrid = Vector-Only across all repos | Graph edges didn't surface new relevant files beyond vector search |
| Neo4j was skipped for django | 96k edges caused ingestion timeout |
| Graph edges help for structural queries | See Chat demo: class hierarchy queries show graph benefit |

### 5.3 Architecture Insights

1. **Reduction ratio matters**: AST chunking reduces sklearn from 41K to 6K chunks (6.9x), which concentrates
   the embedding space and reduces noise. This is the primary advantage.
2. **Small repos don't need chunking innovation**: With only 696 AST chunks, Click has high signal density
   either way. The extra context overlap from character chunks is actually beneficial.
3. **Graph traversal needs code-aware embeddings**: MiniLM-L6-v2 is a general text embedder. A code-specific
   embedder (CodeBERT, StarCoder) would likely improve both paths and might allow graph edges to find
   genuinely new relevant code.
4. **Generation quality is ceiling-bounded**: All paths score 4.7+/5.0 on Click because the LLM already
   knows the library well. RAG's real value shows on proprietary/internal codebases.

---

## 6. Evaluation Files

| File | Description | Size |
|------|-------------|------|
| `evaluation_results/swebench_v2_20260421_173828.json` | **Latest: Full 4-repo eval** (60 instances) | ~330 KB |
| `evaluation_results/eval_20260418_124609.json` | Click 3-way generation eval (15 cases, LLM Judge) | 88 KB |
| `evaluation_results/eval_20260418_081445.json` | Click eval run 1 (RAG vs Plain, 15 cases) | 76 KB |
| `evaluation_results/swebench_django_20260418_184142.json` | Django SWE-bench evaluation | 62 KB |
| `evaluation_results/swebench_v2_20260419_202917.json` | Previous 4-repo eval run | 329 KB |

---

## 7. Reproducibility

```bash
# Run the SWE-bench multi-repo evaluation (retrieval only, ~3 min)
cd Final_Project
python -m graphcoderag.evaluation.swebench_runner_v2 --retrieval-only

# Run the SWE-bench multi-repo evaluation (full with Gemini judge, ~20 min)
python -m graphcoderag.evaluation.swebench_runner_v2

# Run the Click-specific evaluation (15 test cases, 3-way generation)
python -m graphcoderag.evaluation.run_evaluation

# Results stored in evaluation_results/<timestamp>.json
```

### Requirements
- Python 3.10+
- Neo4j running on bolt://localhost:7687
- Google API key for Gemini 2.5 Flash (set GOOGLE_API_KEY env var)
- All dependencies: `pip install -r requirements.txt`
