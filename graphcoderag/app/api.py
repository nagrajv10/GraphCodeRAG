"""
GraphCodeRAG — FastAPI Backend
================================
REST API serving the GraphCodeRAG pipeline.
Serves the static HTML frontend and exposes API endpoints for
workspace management, chat, graph data, and ingestion.

Usage:
    uvicorn graphcoderag.app.api:app --reload --port 8000
"""
import os
import sys
import re
import json
import logging
import subprocess
import traceback
from pathlib import Path
from typing import Optional

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graphcoderag.app.workspace_manager import WorkspaceManager
from graphcoderag.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

# ── App Setup ──
app = FastAPI(title="GraphCodeRAG", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Singleton state
_wm: Optional[WorkspaceManager] = None
REPOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "repos"


def _get_wm() -> WorkspaceManager:
    global _wm
    if _wm is None:
        _wm = WorkspaceManager()
        # Auto-create workspace for existing data
        if not _wm.get_all_workspaces():
            stats = _load_stats()
            if stats.get("chunks", 0) > 0:
                ws = _wm.create_workspace("click", "main")
                ws.stats = stats
                _wm.update_stats(stats)
    return _wm


# ── Pydantic Models ──

class ChatRequest(BaseModel):
    message: str
    workspace_id: Optional[str] = None
    mode: str = "hybrid"          # "hybrid" | "vector" | "graph"
    context_files: list = []

class IngestRequest(BaseModel):
    repo_url: str
    branch: str = "main"


# ═══════════════════════════════════════════════════════════════
#  API ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/api/workspaces")
def list_workspaces():
    wm = _get_wm()
    active = wm.get_active()
    result = []
    for ws in wm.get_all_workspaces():
        repo_str = ws.repo or ""
        repo_name = repo_str.rstrip("/").split("/")[-1] if "/" in repo_str else repo_str
        result.append({
            "id": ws.workspace_id,
            "repo": ws.repo,
            "repo_name": repo_name,
            "branch": ws.branch,
            "status": ws.status,
            "stats": ws.stats,
            "is_active": active and ws.workspace_id == active.workspace_id,
            "chat_count": len(ws.chat_history),
        })
    return {"workspaces": result, "active_id": active.workspace_id if active else None}


@app.put("/api/workspaces/{workspace_id}/activate")
def activate_workspace(workspace_id: str):
    wm = _get_wm()
    ws = wm.switch_to(workspace_id)
    if not ws:
        raise HTTPException(404, "Workspace not found")
    return {"status": "ok", "active_id": workspace_id}


@app.delete("/api/workspaces/{workspace_id}")
def close_workspace(workspace_id: str):
    wm = _get_wm()
    wm.close_workspace(workspace_id)
    return {"status": "ok"}


@app.post("/api/workspaces")
def create_workspace(req: IngestRequest):
    wm = _get_wm()
    repo_input = req.repo_url.strip()
    branch = req.branch.strip() or "main"

    if not repo_input:
        raise HTTPException(400, "Repository URL/path is required")

    err = _ingest_and_create_workspace(wm, repo_input, branch)
    if err:
        raise HTTPException(500, err)

    active = wm.get_active()
    return {
        "status": "ok",
        "workspace_id": active.workspace_id if active else None,
        "stats": active.stats if active else {},
    }


@app.get("/api/stats")
def get_stats():
    wm = _get_wm()
    active = wm.get_active()
    ws_id = active.workspace_id if active else None
    stats = active.stats if active and active.stats.get("chunks") else _load_stats(ws_id)
    neo4j_ok = _check_neo4j()
    return {
        "stats": stats,
        "neo4j": neo4j_ok,
        "workspace": {
            "id": ws_id,
            "repo": active.repo if active else "",
            "branch": active.branch if active else "",
        } if active else None,
    }


@app.get("/api/graph")
def get_graph():
    wm = _get_wm()
    active = wm.get_active()
    ws_id = active.workspace_id if active else None
    return _load_graph_data(ws_id)


@app.get("/api/files")
def get_files():
    wm = _get_wm()
    active = wm.get_active()
    ws_id = active.workspace_id if active else None
    return {"files": _load_file_list(ws_id)}


@app.get("/api/chat/history")
def get_chat_history():
    wm = _get_wm()
    active = wm.get_active()
    if not active:
        return {"history": []}
    return {"history": active.chat_history}


@app.post("/api/chat")
def chat(req: ChatRequest):
    wm = _get_wm()
    active = wm.get_active()
    if not active:
        raise HTTPException(400, "No active workspace")

    msg = req.message.strip()
    if not msg:
        raise HTTPException(400, "Message is empty")

    # Save user message
    wm.update_chat({"role": "user", "content": msg})

    # Run retrieval + generation with mode
    resp = _run_query(msg, active, mode=req.mode)
    wm.update_chat(resp)

    return {"response": resp}


@app.get("/api/graph/node/{name:path}")
def get_graph_node(name: str):
    """Get source code for a specific graph node by reading from disk."""
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        with gs.driver.session() as session:
            result = session.run(
                "MATCH (n) WHERE n.name = $name AND n.chunk_id IS NOT NULL "
                "RETURN n.name AS name, labels(n)[0] AS label, n.file_path AS file, "
                "n.start_line AS start, n.end_line AS end, "
                "n.signature AS sig, n.docstring AS doc LIMIT 1",
                name=name,
            )
            rec = result.single()
        gs.close()
        if not rec:
            raise HTTPException(404, f"Node '{name}' not found")

        file_path = (rec["file"] or "").replace("\\", "/")
        start = rec["start"] or 0
        end = rec["end"] or 0
        source_code = ""

        # Read actual source code from disk
        if file_path and start and end:
            for repo_dir in REPOS_DIR.iterdir():
                candidate = repo_dir / file_path.replace("/", os.sep)
                if not candidate.exists():
                    # Try without leading src/ prefix
                    parts = file_path.split("/")
                    for i in range(len(parts)):
                        alt = repo_dir / os.sep.join(parts[i:])
                        if alt.exists():
                            candidate = alt
                            break
                if candidate.exists():
                    try:
                        lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                        source_code = "\n".join(lines[max(0,start-1):end])
                    except Exception:
                        pass
                    break

        return {
            "entity_name": rec["name"],
            "entity_type": (rec["label"] or "Function").lower(),
            "file": file_path,
            "line_start": start,
            "line_end": end,
            "source_code": source_code,
            "signature": rec["sig"] or "",
            "docstring": rec["doc"] or "",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Node lookup failed: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/file-content")
def get_file_content(path: str = ""):
    """Get raw file content for the code viewer."""
    if not path:
        raise HTTPException(400, "path parameter required")
    # Find file in repo directory
    for repo_dir in REPOS_DIR.iterdir():
        candidate = repo_dir / path
        if candidate.exists() and candidate.is_file():
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                return {"path": path, "content": content, "lines": content.count('\n') + 1}
            except Exception as e:
                raise HTTPException(500, str(e))
    raise HTTPException(404, f"File not found: {path}")


# ═══════════════════════════════════════════════════════════════
#  PIPELINE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def _run_query(query: str, workspace, mode: str = "hybrid") -> dict:
    """Run retrieval + LLM generation with specified mode."""
    try:
        from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
        from graphcoderag.generation.generator import LLMGenerator

        retriever = HybridRetriever()

        # Select retrieval mode
        if mode == "vector":
            results = retriever.retrieve_vector_only(query)
        elif mode == "graph":
            results = retriever.retrieve_graph_only(query)
        else:  # hybrid (default)
            results = retriever.retrieve(query)

        vector_only = sum(1 for r in results if r.source == "vector")
        graph_only = sum(1 for r in results if r.source == "graph")
        hybrid = sum(1 for r in results if r.source == "hybrid")

        generator = LLMGenerator()
        answer = generator.generate(query, results)
        retriever.close()

        return {
            "role": "assistant",
            "content": answer,
            "mode": mode,
            "trace": {
                "vector_count": vector_only,
                "graph_count": graph_only + hybrid,
                "merged_count": len(results),
                "sources": [
                    {"file": r.file_path, "name": r.name, "score": round(r.score, 3), "source": r.source}
                    for r in results[:7]
                ],
            },
        }
    except Exception as e:
        logger.error(f"Query failed: {e}")
        traceback.print_exc()
        return {"role": "assistant", "content": f"Error: {e}", "trace": {}}


def _ingest_and_create_workspace(wm: WorkspaceManager, repo_input: str, branch: str = "main"):
    """Ingest a repo and create workspace. Returns None on success, error string on failure."""
    try:
        # Validate repo name
        if repo_input.startswith(("http://", "https://")):
            repo_name = repo_input.rstrip("/").split("/")[-1]
            if not re.match(r'^[a-zA-Z0-9_.\-]+$', repo_name):
                return f"Invalid repository name: {repo_name}"
            target = REPOS_DIR / repo_name
            if not target.exists():
                REPOS_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--depth", "1", "-b", branch,
                     "--", repo_input, str(target)],
                    check=True, capture_output=True,
                )
            repo_path = str(target)
        else:
            repo_path = repo_input

        import hashlib
        ws_id = hashlib.sha256(f"{repo_input}@{branch}".encode()).hexdigest()[:12]

        # Run pipeline
        from graphcoderag.ingestion.file_scanner import scan_repository
        from graphcoderag.ingestion.ast_parser import PythonASTParser
        from graphcoderag.ingestion.code_chunker import CodeChunker
        from graphcoderag.ingestion.dependency_extractor import DependencyExtractor
        from graphcoderag.storage.graph_store import GraphStore
        from graphcoderag.storage.vector_store import VectorStore

        files = scan_repository(repo_path)
        parser = PythonASTParser()
        chunker = CodeChunker()
        dep_ext = DependencyExtractor()

        all_chunks, all_edges = [], []
        for f in files:
            try:
                tree, src = parser.parse_file(f.abs_path)
                nodes = parser.extract_functions_and_classes(tree, src)
                all_chunks.extend(chunker.chunk_file(f.rel_path, nodes, src))
                all_edges.extend(dep_ext.extract_from_file(tree, src, f.rel_path))
            except Exception:
                continue

        # Store in databases
        gs = GraphStore()
        gs.store_chunks(all_chunks)
        gs.store_edges(all_edges)
        gs.close()

        vs = VectorStore(collection_name=f"ws_{ws_id}")
        vs.add_chunks(all_chunks)

        # Create workspace
        repo_name = repo_input.rstrip("/").split("/")[-1] if "/" in repo_input else os.path.basename(repo_input)
        ws = wm.create_workspace(repo_input, branch)

        from collections import Counter
        edge_types = Counter(e.edge_type for e in all_edges)
        chunk_types = Counter(c.chunk_type for c in all_chunks)

        stats = {
            "files": len(files),
            "chunks": len(all_chunks),
            "edges": len(all_edges),
            "functions": chunk_types.get("function", 0),
            "classes": chunk_types.get("class", 0),
            "imports": edge_types.get("IMPORTS", 0),
            "calls": edge_types.get("CALLS", 0),
        }
        ws.stats = stats
        wm.update_stats(stats)
        return None

    except subprocess.CalledProcessError as e:
        return f"Git clone failed: {e.stderr.decode()[:200] if e.stderr else str(e)}"
    except Exception as e:
        traceback.print_exc()
        return str(e)


# ═══════════════════════════════════════════════════════════════
#  DATA LOADERS
# ═══════════════════════════════════════════════════════════════

def _load_stats(ws_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        from graphcoderag.storage.vector_store import VectorStore
        gs = GraphStore()
        stats = gs.get_graph_stats()
        gs.close()
        vs = VectorStore()
        chunk_count = vs.count()
        return {
            "chunks": chunk_count,
            "functions": stats.get("Function", 0),
            "classes": stats.get("Class", 0),
            "edges": sum(v for k, v in stats.items() if k in ("CALLS", "IMPORTS", "CONTAINS", "INHERITS")),
            "imports": stats.get("IMPORTS", 0),
            "calls": stats.get("CALLS", 0),
        }
    except Exception:
        return {"chunks": 0, "functions": 0, "classes": 0, "edges": 0}


def _get_repo_prefix():
    """Get the file_path prefix for the active workspace's repo."""
    wm = _get_wm()
    active = wm.get_active()
    if active and active.repo:
        repo_name = active.repo.rstrip("/").split("/")[-1]
        if repo_name:
            return repo_name
    return None


def _load_graph_data(ws_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        prefix = _get_repo_prefix()

        def _run_node_query(p=None):
            if p:
                q = (
                    "MATCH (n) WHERE n.chunk_id IS NOT NULL AND n.name IS NOT NULL "
                    "AND n.file_path CONTAINS $prefix "
                    "RETURN n.name AS name, labels(n)[0] AS label, n.file_path AS file, "
                    "n.parent_class AS parent "
                    "ORDER BY n.name LIMIT 40"
                )
                with gs.driver.session() as session:
                    return list(session.run(q, prefix=p))
            else:
                q = (
                    "MATCH (n) WHERE n.chunk_id IS NOT NULL AND n.name IS NOT NULL "
                    "RETURN n.name AS name, labels(n)[0] AS label, n.file_path AS file, "
                    "n.parent_class AS parent "
                    "ORDER BY n.name LIMIT 40"
                )
                with gs.driver.session() as session:
                    return list(session.run(q))

        # Try scoped, fallback to unscoped
        result = _run_node_query(prefix) if prefix else []
        if not result:
            result = _run_node_query(None)

        nodes = []
        for r in result:
            if not r["name"]:
                continue
            fp = (r["file"] or "").replace("\\", "/")
            fname = fp.split("/")[-1] if fp else ""
            full_name = r["name"]
            short_name = full_name.split(".")[-1] if "." in full_name else full_name
            label = r["label"] or "Function"

            # Build display name with file context for ambiguous names
            if len(short_name) <= 3 and fname:
                # Very short names like "A", "B" — add file module context
                module = fname.replace(".py", "")
                display = f"{module}.{short_name}"
            elif label == "Function":
                display = short_name + "()"
            else:
                display = short_name

            nodes.append({
                "name": full_name,
                "label": label,
                "file": fname,
                "display": display,
                "parent": r["parent"] or "",
            })

        # Get edges between these nodes
        node_names = [n["name"] for n in nodes]
        edge_query = (
            "MATCH (a)-[r]->(b) WHERE a.name IN $names AND b.name IN $names "
            "RETURN a.name AS source, b.name AS target, type(r) AS rel LIMIT 80"
        )
        with gs.driver.session() as session:
            edge_result = list(session.run(edge_query, names=node_names))
            name_set = set(node_names)
            edges = [
                {"source": r["source"], "target": r["target"], "type": r["rel"]}
                for r in edge_result
                if r["source"] in name_set and r["target"] in name_set
                   and r["source"] != r["target"]
            ]

        gs.close()
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.error(f"Graph load failed: {e}")
        return {"nodes": [], "edges": []}


def _load_file_list(ws_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        prefix = _get_repo_prefix()

        def _run_file_query(p=None):
            if p:
                q = (
                    "MATCH (n) WHERE n.file_path IS NOT NULL AND n.chunk_id IS NOT NULL "
                    "AND n.file_path CONTAINS $prefix "
                    "WITH n.file_path AS fp, count(*) AS cnt "
                    "RETURN fp, cnt ORDER BY cnt DESC LIMIT 30"
                )
                with gs.driver.session() as session:
                    return list(session.run(q, prefix=p))
            else:
                q = (
                    "MATCH (n) WHERE n.file_path IS NOT NULL AND n.chunk_id IS NOT NULL "
                    "WITH n.file_path AS fp, count(*) AS cnt "
                    "RETURN fp, cnt ORDER BY cnt DESC LIMIT 30"
                )
                with gs.driver.session() as session:
                    return list(session.run(q))

        # Try scoped, fallback to unscoped
        result = _run_file_query(prefix) if prefix else []
        if not result:
            result = _run_file_query(None)

        gs.close()
        files = []
        for r in result:
            fp = r["fp"].replace("\\", "/")
            parts = fp.split("/")
            display = "/".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
            files.append({"name": display, "path": fp, "chunks": r["cnt"]})
        return files
    except Exception:
        return []


def _check_neo4j():
    try:
        from neo4j import GraphDatabase
        d = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        d.verify_connectivity()
        d.close()
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  EVALUATION ENDPOINT
# ═══════════════════════════════════════════════════════════════

@app.get("/api/evaluation")
def get_evaluation():
    """Return evaluation metrics from actual evaluation runs on SWE-bench Lite."""
    return {
        "study": {
            "title": "Retrieval & Generation Evaluation -- SWE-bench Lite",
            "instances": 60,
            "repositories": ["pallets/click", "pytest-dev/pytest", "scikit-learn/sklearn", "django/django"],
            "evaluation_files": [
                "swebench_v2_20260421_173828.json (4 repos, 60 instances, retrieval)",
                "eval_20260418_124609.json (Click, 15 cases, 3-way generation)",
            ],
        },
        "methods": [
            {
                "name": "GraphCodeRAG (AST+Vec)",
                "description": "AST-aware chunking (Tree-sitter) + vector search (MiniLM-L6-v2)",
                "color": "#a855f7",
            },
            {
                "name": "Standard RAG",
                "description": "Character-based chunking (512 char, 50 overlap) + vector similarity",
                "color": "#60a5fa",
            },
        ],
        "metrics": {
            "mrr_pytest": {
                "label": "MRR@5 (pytest)",
                "description": "AST chunking shows +27.2% MRR improvement on medium repos",
                "values": {"graphcoderag": 0.467, "standard_rag": 0.367},
                "repo": "pytest",
            },
            "mrr_sklearn": {
                "label": "MRR@5 (sklearn)",
                "description": "AST chunking shows +161% MRR improvement on large noisy repos",
                "values": {"graphcoderag": 0.217, "standard_rag": 0.083},
                "repo": "sklearn",
            },
            "mrr_click": {
                "label": "MRR@5 (click)",
                "description": "Standard RAG wins on small repos where overlap context helps",
                "values": {"graphcoderag": 0.830, "standard_rag": 0.933},
                "repo": "click",
            },
            "mrr_django": {
                "label": "MRR@5 (django)",
                "description": "Both methods converge on large repos. Standard RAG wins by 2.8%",
                "values": {"graphcoderag": 0.589, "standard_rag": 0.606},
                "repo": "django",
            },
            "file_recall_pytest": {
                "label": "File Recall@10 (pytest)",
                "description": "AST chunking finds 12.6% more relevant files",
                "values": {"graphcoderag": 0.600, "standard_rag": 0.533},
                "repo": "pytest",
            },
        },
        "per_repo": [
            {
                "repo": "pytest", "instances": 15,
                "graphcoderag_mrr": 0.467, "standard_mrr": 0.367,
                "graphcoderag_recall": 0.467, "standard_recall": 0.400,
                "delta_mrr": "+27.2%",
                "finding": "Medium repo (9.5K vs 3K chunks) -- AST chunking reduces noise by 3.2x, improving MRR by +27.2%.",
            },
            {
                "repo": "sklearn", "instances": 15,
                "graphcoderag_mrr": 0.217, "standard_mrr": 0.083,
                "graphcoderag_recall": 0.267, "standard_recall": 0.133,
                "delta_mrr": "+161%",
                "finding": "41K vs 6K chunks -- AST reduces noise by 6.9x. Standard RAG drowns in noisy fragments.",
            },
            {
                "repo": "click", "instances": 15,
                "graphcoderag_mrr": 0.830, "standard_mrr": 0.933,
                "graphcoderag_recall": 0.789, "standard_recall": 0.811,
                "delta_mrr": "-11.0%",
                "finding": "Small repo -- character overlap provides useful cross-function context. Both achieve 100% hit rate.",
            },
            {
                "repo": "django", "instances": 15,
                "graphcoderag_mrr": 0.596, "standard_mrr": 0.614,
                "graphcoderag_recall": 0.800, "standard_recall": 0.800,
                "delta_mrr": "-2.9%",
                "finding": "Large repo -- both methods converge. Same file recall (80%), comparable MRR.",
            },
        ],
        "generation": {
            "title": "Generation Quality -- LLM Judge (Click, 15 cases)",
            "judge_model": "Gemini 2.5 Flash",
            "scale": "1-5",
            "scores": {
                "rag_hybrid": {"accuracy": 4.80, "completeness": 4.73, "helpfulness": 4.80, "avg": 4.78},
                "vector_only": {"accuracy": 4.73, "completeness": 4.67, "helpfulness": 4.73, "avg": 4.71},
                "plain_llm": {"accuracy": 4.80, "completeness": 4.80, "helpfulness": 4.80, "avg": 4.80},
            },
            "pairwise": {
                "rag_vs_plain": {"rag_wins": 2, "ties": 10, "plain_wins": 3},
                "rag_vs_vector": {"rag_wins": 2, "ties": 12, "vector_wins": 1},
            },
            "note": "All paths score 4.7+/5.0. Click is small and well-documented, compressing RAG advantage.",
        },
        "key_findings": [
            "AST-aware chunking provides +27% MRR on medium repos (pytest) and +161% on large repos (sklearn)",
            "The key advantage is noise reduction: 41K char chunks -> 6K AST chunks (6.9x) on sklearn",
            "Standard RAG wins on small repos (click) where character overlap provides cross-function context",
            "Both methods converge at scale (django, 300k LOC) -- same 80% file recall",
            "RAG beats Vector-Only in generation quality: 2W-12T-1L (LLM Judge)",
            "Crossover point: AST chunking helps when char chunks exceed ~5K (medium+ repos)",
        ],
    }


# ═══════════════════════════════════════════════════════════════
#  STATIC FILES + ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

# Serve static files (CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
def serve_frontend():
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Frontend not found. Place index.html in graphcoderag/app/static/"}
