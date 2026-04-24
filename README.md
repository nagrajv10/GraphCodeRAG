# GraphCodeRAG

**Graph-Enhanced Code Retrieval-Augmented Generation**

A hybrid RAG system that combines **AST-aware code chunking** with **Neo4j knowledge graph traversal** to improve code retrieval quality over standard vector-only RAG approaches.

> Built for AI for Engineers (Spring 2026) — Final Project

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        User Query                                │
└───────────────────────────┬──────────────────────────────────────┘
                            │
            ┌───────────────┴──────────────────┐
            ▼                                  ▼
  ┌───────────────────┐             ┌────────────────────┐
  │  FAISS / ChromaDB │             │  Neo4j Knowledge   │
  │  Vector Search    │             │  Graph Traversal   │
  │  (Cosine / IP)    │             │  (Multi-hop)       │
  └────────┬──────────┘             └─────────┬──────────┘
           │                                  │
           └───────────────┬──────────────────┘
                           ▼
                ┌─────────────────────┐
                │  Hybrid Merger      │
                │  Score Fusion       │
                │  + Reranking        │
                └──────────┬──────────┘
                           ▼
                ┌─────────────────────┐
                │  LLM Generator      │
                │  (Qwen / Claude)    │
                └──────────┬──────────┘
                           ▼
                ┌─────────────────────┐
                │  Grounded Answer    │
                │  + Source Citations  │
                └─────────────────────┘
```

## Key Innovation

Standard RAG only finds **semantically similar** code via vector cosine similarity. GraphCodeRAG also finds **structurally related** code by traversing knowledge graph edges:

| Edge Type    | What It Captures              |
|-------------|-------------------------------|
| `IMPORTS`    | Cross-file dependencies       |
| `CALLS`      | Function call chains          |
| `CONTAINS`   | Class → method relationships  |
| `INHERITS`   | Class hierarchies             |

This surfaces files that vector search alone misses — callers, callees, parent classes, and sibling methods.

---

## Tech Stack

| Component        | Technology                                    |
|-----------------|-----------------------------------------------|
| Code Parsing     | Tree-sitter (AST extraction)                 |
| Knowledge Graph  | Neo4j 5.x (Cypher queries)                   |
| Vector Database  | **FAISS** (default) / ChromaDB (persistent)  |
| Embeddings       | **nomic-ai/CodeRankEmbed** (768d, 137M params) |
| LLM              | Qwen 2.5 Coder 7B (local via Ollama)         |
| LLM Judge        | Gemini 2.0 Flash Lite (cross-model evaluator)|
| Frontend         | Vanilla JS + FastAPI (single-page app)        |
| Backend          | FastAPI (REST API)                            |

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Neo4j Desktop** or Community Edition (running on `bolt://localhost:7687`)
- **Ollama** with `qwen2.5-coder:7b-instruct` model pulled

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/nagrajv10/GraphCodeRAG.git
cd GraphCodeRAG

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt
pip install faiss-cpu           # For FAISS vector backend

# 4. Configure environment
# Copy .env.example to .env and fill in your settings
# Local mode is the default — no paid API keys needed

# 5. Start required services
# Start Neo4j Desktop (or neo4j console)
ollama serve
ollama pull qwen2.5-coder:7b-instruct
```

### Usage

```bash
# Ingest a Python repository
python run_ingestion.py --repo-path data/repos/click
python run_ingestion.py --repo-url https://github.com/pallets/click

# Query the codebase (CLI)
python run_query.py --query "How does Click parse arguments?" --show-context
python run_query.py --interactive

# Launch the Web UI (FastAPI)
uvicorn graphcoderag.app.api:app --reload --port 8000
# Then open http://localhost:8000

# Run SWE-bench evaluation
python -m graphcoderag.evaluation.swebench_runner_v2 --backend=faiss --retrieval-only
```

---

## Project Structure

```
GraphCodeRAG/
├── graphcoderag/                    # Core package
│   ├── config.py                    # Central configuration (paths, models, keys)
│   ├── ingestion/                   # Code parsing pipeline
│   │   ├── file_scanner.py          # Walk and filter .py files
│   │   ├── ast_parser.py            # Tree-sitter AST extraction
│   │   ├── code_chunker.py          # Function/class/module chunking
│   │   └── dependency_extractor.py  # IMPORTS/CALLS/CONTAINS/INHERITS edges
│   ├── storage/                     # Dual database layer
│   │   ├── embedding.py             # CodeRankEmbed embedding (singleton)
│   │   ├── faiss_store.py           # FAISS vector store backend
│   │   ├── vector_store.py          # ChromaDB vector store backend
│   │   └── graph_store.py           # Neo4j knowledge graph + Cypher
│   ├── retrieval/                   # Hybrid retrieval engine
│   │   ├── vector_retriever.py      # Vector similarity search
│   │   ├── graph_retriever.py       # Multi-hop graph traversal (batched)
│   │   └── hybrid_retriever.py      # Merge + rerank with score fusion
│   ├── generation/                  # LLM answer generation
│   │   ├── generator.py             # Ollama (local) + Claude (cloud) backends
│   │   └── prompt_templates.py      # QA / Explain / Debug templates
│   ├── evaluation/                  # Comparative evaluation suite
│   │   ├── metrics.py               # MRR, Recall@K, Precision@K, NDCG
│   │   ├── llm_judge.py             # Gemini cross-model judge (5-level rubric)
│   │   ├── baseline_rag.py          # Standard RAG baseline (char chunking)
│   │   ├── baseline_comparison.py   # A/B comparison framework
│   │   ├── swebench_runner.py       # SWE-bench evaluation runner v1
│   │   └── swebench_runner_v2.py    # SWE-bench evaluation runner v2 (4-way)
│   └── app/                         # Web interface
│       ├── api.py                   # FastAPI REST backend (security hardened)
│       └── static/                  # Frontend SPA
│           ├── index.html           # Main HTML shell
│           ├── styles/              # CSS stylesheets
│           └── scripts/             # Modular JS (chat, graph, search, etc.)
├── evaluation_results/              # Generated JSON evaluation outputs
├── run_ingestion.py                 # CLI: ingest a repository
├── run_query.py                     # CLI: query the system
├── run_evaluation.py                # CLI: run full evaluation suite
├── requirements.txt                 # Python dependencies
└── EVALUATION_REPORT_FINAL.md       # Production performance report
```

---

## Evaluation Results

Evaluated on **4 real-world Python repositories** from SWE-bench Lite using **60 test cases** (15 per repo).

### Retrieval: Standard RAG vs GraphCodeRAG Hybrid (MRR @ K=10)

| Repository     | Size             | Standard RAG | GraphCodeRAG Hybrid | Δ MRR   |
|---------------|------------------|-------------|-------------------|---------|
| **Click**      | Small (~20k LOC) | 0.817       | **0.900**          | +0.083  |
| **PyTest**     | Medium (~50k LOC)| 0.262       | **0.430**          | +0.168  |
| **Django**     | Large (~300k LOC)| 0.486       | **0.534**          | +0.048  |
| **Scikit-Learn**| Large (~200k LOC)| 0.096       | **0.147**          | +0.051  |

### File Recall @ K=10

| Repository     | Standard RAG | GraphCodeRAG Hybrid | Δ Recall |
|---------------|-------------|-------------------|----------|
| **Click**      | 67.8%       | **70.6%**          | +2.8%    |
| **PyTest**     | 46.7%       | **66.7%**          | +20.0%   |
| **Django**     | 66.7%       | **73.3%**          | +6.6%    |
| **Scikit-Learn**| 20.0%      | **20.0%**          | +0.0%    |

### FAISS vs ChromaDB Backend Benchmark (500 code chunks)

| Metric                      | FAISS (In-Memory) | ChromaDB (Persistent) |
|----------------------------|-------------------|----------------------|
| **Ingestion Time**          | **0.01 seconds**  | 60.63 seconds        |
| **Retrieval Speed (per query)** | 446.16 ms    | **36.45 ms**         |
| **Storage Size**            | **1.46 MB**       | 4.29 MB              |

**Key Insight:** GraphCodeRAG's hybrid retrieval consistently outperforms standard vector-only RAG, with the largest improvement on medium-sized repositories (+64% MRR on PyTest) where structural code relationships are most critical.

---

## Configuration

All settings are controlled via a `.env` file:

```env
# Free local mode (default — no API keys needed)
USE_LOCAL_EMBEDDINGS=true
USE_LOCAL_LLM=true
LOCAL_LLM_MODEL=qwen2.5-coder:7b-instruct

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphcoderag2026

# Vector backend: "faiss" or "chroma"
VECTOR_BACKEND=faiss

# Gemini (for LLM-as-Judge evaluation)
GEMINI_API_KEY=your-key-here
JUDGE_MODEL=gemini-2.0-flash-lite

# Optional: paid cloud APIs
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

---

## Security Hardening

The production deployment includes the following security measures:
- **CORS**: Restricted to `localhost:8000` origins only
- **SSRF Prevention**: Repository URL ingestion validates against an allowlist
- **Path Traversal**: File content API resolves paths against the repo root
- **XSS Mitigation**: DOMPurify sanitizes all LLM output; HTML-escaping on search results
- **Exception Safety**: Raw error strings are never leaked in HTTP 500 responses

---

## License

Academic project — AI for Engineers, Spring 2026.
