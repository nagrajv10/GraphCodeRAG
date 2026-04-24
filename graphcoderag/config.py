"""
GraphCodeRAG — Central Configuration
=====================================
All paths, model names, API keys, and database URIs are defined here.
Every other module imports from this file to avoid hardcoded values.

Usage:
    from graphcoderag.config import PROJECT_ROOT, ANTHROPIC_API_KEY, ...
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Project Paths ===
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPOS_DIR = DATA_DIR / "repos"
SWEBENCH_DIR = DATA_DIR / "swebench"

# === API Keys (from .env file) ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# === Neo4j Configuration ===
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

# === ChromaDB Configuration ===
CHROMA_PERSIST_DIR = str(DATA_DIR / "chroma_db")
CHROMA_COLLECTION_NAME = "code_chunks"

# === FAISS Configuration ===
FAISS_INDEX_DIR = str(DATA_DIR / "faiss_index")

# === Embedding Configuration ===
# Code-specialized embedding model
# CodeRankEmbed: 137M params, 768d, 8K context, SOTA on CodeSearchNet/CoIR
# Trained on CoRNStack (21M contrastive pairs) — outperforms models 10x its size
SFR_EMBEDDING_MODEL = "nomic-ai/CodeRankEmbed"
SFR_EMBEDDING_DIMENSION = 768

# Legacy: general-purpose model (kept for backward compatibility)
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
USE_LOCAL_EMBEDDINGS = os.getenv("USE_LOCAL_EMBEDDINGS", "false").lower() == "true"

# Vector store backend: "faiss" or "chroma"
VECTOR_BACKEND = os.getenv("VECTOR_BACKEND", "faiss").lower()

# === LLM Configuration ===
LLM_MODEL = "claude-sonnet-4-20250514"
# Alternative: "llama3" (via Ollama, free)
USE_LOCAL_LLM = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5-coder:7b-instruct")

# === Retrieval Configuration ===
VECTOR_TOP_K = 10             # Number of chunks from vector search
GRAPH_HOP_DEPTH = 2           # How many hops to traverse in the graph
FINAL_TOP_K = 15              # Final number of chunks after merge+rank
GRAPH_SEED_COUNT = 5          # Top-N vector results used as graph seeds
                              # (more seeds = broader graph search, but noisier)

# === Graph Traversal Edge Filter ===
# Only follow these edge types during graph expansion
# Excluding CONTAINS reduces same-class noise and surfaces cross-file dependencies
GRAPH_EDGE_FILTER = ["CALLS", "IMPORTS", "INHERITS"]

# === File Scanner Configuration ===
EXCLUDED_DIRS = {
    "__pycache__", ".git", ".tox", "node_modules", "venv",
    ".venv", "env", ".env", "dist", "build", "egg-info",
    ".mypy_cache", ".pytest_cache"
}
EXCLUDED_FILES = {"setup.py", "conftest.py"}
INCLUDE_TEST_FILES = False     # Whether to include test_*.py files
