# GraphCodeRAG

**Graph-Enhanced Code Retrieval-Augmented Generation**

A hybrid RAG system that combines AST-aware code chunking with Neo4j knowledge graph traversal to improve code retrieval quality over standard vector-only RAG.

> Built for AI for Engineers (Spring 2026) — Final Project

---

## Architecture

```
                    ┌─────────────────┐
                    │   User Query    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼                              ▼
    ┌──────────────────┐          ┌──────────────────┐
    │  ChromaDB Vector │          │   Neo4j Graph     │
    │  Similarity      │          │   Traversal       │
    │  (Cosine Search) │          │   (Multi-hop)     │
    └────────┬─────────┘          └────────┬──────────┘
              │                              │
              └──────────┬───────────────────┘
                         ▼
              ┌──────────────────┐
              │  Hybrid Merger   │
              │  Score Fusion    │
              │  + Reranking     │
              └────────┬─────────┘
                         ▼
              ┌──────────────────┐
              │  LLM Generator   │
              │  (Qwen/Claude)   │
              └────────┬─────────┘
                         ▼
              ┌──────────────────┐
              │  Grounded Answer │
              │  + Source Cites   │
              └──────────────────┘
```

## Key Innovation

Standard RAG only finds **semantically similar** code. GraphCodeRAG also finds **structurally related** code via knowledge graph edges:

| Edge Type | What It Captures |
|-----------|-----------------|
| `IMPORTS` | Cross-file dependencies |
| `CALLS` | Function call chains |
| `CONTAINS` | Class → method relationships |
| `INHERITS` | Class hierarchies |

This surfaces files that vector search misses — callers, callees, parent classes, and sibling methods.

## Quick Start

### Prerequisites

- **Python 3.10.11**
- **Neo4j Desktop** (running on `bolt://localhost:7687`)
- **Ollama** with `qwen2.5-coder:7b-instruct` model

### Setup

```bash
# 1. Create virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
# Edit .env with your settings (local mode is default — no API keys needed)

# 4. Start services
# Start Neo4j Desktop
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

# Launch the web UI
streamlit run graphcoderag/app/streamlit_app.py

# Run evaluation (15 SWE-bench-inspired test cases)
python -m graphcoderag.evaluation.run_evaluation
```

## Project Structure

```
graphcoderag/
├── ingestion/              # Code parsing pipeline
│   ├── file_scanner.py     # Walk and filter .py files
│   ├── ast_parser.py       # Tree-sitter AST extraction
│   ├── code_chunker.py     # Function/class/module chunks
│   └── dependency_extractor.py  # IMPORTS/CALLS/CONTAINS/INHERITS edges
├── storage/                # Dual database layer
│   ├── vector_store.py     # ChromaDB + embedding management
│   └── graph_store.py      # Neo4j knowledge graph + Cypher queries
├── retrieval/              # Hybrid retrieval engine
│   ├── vector_retriever.py # Cosine similarity search
│   ├── graph_retriever.py  # Multi-hop graph traversal (batched)
│   └── hybrid_retriever.py # Merge + rerank with semantic reranking
├── generation/             # LLM answer generation
│   ├── generator.py        # Claude API + Ollama dual backend
│   └── prompt_templates.py # QA / Explain / Debug templates
├── evaluation/             # Comparative evaluation pipeline
│   ├── metrics.py          # MRR, Recall@K, Precision@K, NDCG, Hit Rate
│   ├── llm_judge.py        # LLM-as-Judge (accuracy, completeness, helpfulness)
│   ├── baseline_comparison.py  # Hybrid vs Vector-only comparison
│   └── run_evaluation.py   # Full 3-path evaluation runner
└── app/                    # Interactive interface
    ├── streamlit_app.py    # Streamlit UI (chat + graph viz)
    ├── api.py              # FastAPI REST backend
    └── workspace_manager.py # Multi-repo session persistence
```

## Evaluation Results

Tested on **pallets/click** (Python CLI library) with 15 SWE-bench-inspired test cases:

### Retrieval: Hybrid vs Vector-only (File Recall)

| K  | Hybrid   | Vector-only | Delta    |
|----|----------|-------------|----------|
| 5  | 74.4%    | 74.4%       | +0.0%    |
| 10 | 86.7%    | 86.7%       | +0.0%    |
| **15** | **94.4%** | **88.9%** | **+5.6%** |

### Generation Quality (LLM Judge Score /5)

| Metric | GraphCodeRAG | Plain LLM | Delta |
|--------|-------------|-----------|-------|
| Accuracy | 4.13 | 4.40 | -0.27 |
| Completeness | 4.60 | 4.73 | -0.13 |
| Helpfulness | 4.60 | 4.67 | -0.07 |

**Key insight**: RAG excels on **implementation-specific questions** (control_flow: +2.3, error_handling: +1.0) where actual code inspection is needed. Plain LLMs score well on Click because it's a famous library — the advantage would be much larger on proprietary code.

## Configuration

All settings via `.env`:

```env
# Free local mode (default)
USE_LOCAL_EMBEDDINGS=true
USE_LOCAL_LLM=true
LOCAL_LLM_MODEL=qwen2.5-coder:7b-instruct

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=graphcoderag2026

# Optional: paid cloud APIs
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Code Parsing | Tree-sitter |
| Knowledge Graph | Neo4j 5.x |
| Vector Database | ChromaDB |
| Embeddings | all-MiniLM-L6-v2 (local) |
| LLM | Qwen 2.5 Coder 7B (local) / Claude 3.5 (cloud) |
| Frontend | Streamlit |
| Backend | FastAPI |

## License

Academic project — AI for Engineers, Spring 2026.
