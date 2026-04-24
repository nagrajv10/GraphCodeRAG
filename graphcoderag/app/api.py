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
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"], allow_methods=["*"], allow_headers=["*"])

# Singleton state
_wm: Optional[WorkspaceManager] = None
REPOS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "repos"


def _get_wm() -> WorkspaceManager:
    global _wm
    if _wm is None:
        _wm = WorkspaceManager()
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


from fastapi import BackgroundTasks
import urllib.parse

@app.post("/api/workspaces")
def create_workspace(req: IngestRequest, background_tasks: BackgroundTasks):
    wm = _get_wm()
    repo_input = req.repo_url.strip()
    branch = req.branch.strip() or "main"

    if not repo_input:
        raise HTTPException(400, "Repository URL/path is required")

    # SSRF Mitigation: only allow specific domains
    if repo_input.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(repo_input)
        allowed_domains = ["github.com", "gitlab.com", "bitbucket.org"]
        if parsed.hostname not in allowed_domains:
            raise HTTPException(400, f"SSRF Protection: Domain {parsed.hostname} is not allowed.")

    # Run ingest in background so it doesn't block the UI
    background_tasks.add_task(_ingest_and_create_workspace, wm, repo_input, branch)

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


@app.get("/api/graph")
def get_graph():
    wm = _get_wm()
    active = wm.get_active()
    ws_id = active.workspace_id if active else None
    return _load_graph_data(ws_id)


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


@app.get("/api/settings")
def get_settings():
    """Return current configuration settings from .env and config.py"""
    import graphcoderag.config as cfg
    return {
        "use_local_llm": cfg.USE_LOCAL_LLM,
        "local_llm_model": getattr(cfg, "LOCAL_LLM_MODEL", "qwen2.5-coder:7b-instruct"),
        "use_local_embeddings": cfg.USE_LOCAL_EMBEDDINGS,
        "vector_backend": cfg.VECTOR_BACKEND,
    }

class SettingsUpdate(BaseModel):
    use_local_llm: bool
    local_llm_model: str
    use_local_embeddings: bool
    vector_backend: str

from fastapi import Request

@app.put("/api/settings")
def update_settings(req: SettingsUpdate, request: Request):
    """Update settings (mocked for demo, would normally write to .env)"""
    if request.client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(403, "Forbidden: Settings can only be modified locally")
    import graphcoderag.config as cfg
    from pathlib import Path
    
    cfg.USE_LOCAL_LLM = req.use_local_llm
    cfg.LOCAL_LLM_MODEL = req.local_llm_model
    cfg.USE_LOCAL_EMBEDDINGS = req.use_local_embeddings
    cfg.VECTOR_BACKEND = req.vector_backend
    
    # Write back to .env to persist across reloads
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if line.startswith("VECTOR_BACKEND="):
                lines[i] = f'VECTOR_BACKEND="{req.vector_backend}"'
            elif line.startswith("USE_LOCAL_LLM="):
                lines[i] = f'USE_LOCAL_LLM={"true" if req.use_local_llm else "false"}'
            elif line.startswith("LOCAL_LLM_MODEL="):
                lines[i] = f'LOCAL_LLM_MODEL="{req.local_llm_model}"'
            elif line.startswith("USE_LOCAL_EMBEDDINGS="):
                lines[i] = f'USE_LOCAL_EMBEDDINGS={"true" if req.use_local_embeddings else "false"}'
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        
    return {"status": "success", "message": "Settings updated for this session."}

class SearchRequest(BaseModel):
    query: str
    top_k: int = 15

@app.post("/api/search")
def global_search(req: SearchRequest):
    wm = _get_wm()
    active = wm.get_active()
    if not active:
        raise HTTPException(400, "No active workspace")

    try:
        # Load vector store using the configured backend
        from graphcoderag.config import VECTOR_BACKEND
        if VECTOR_BACKEND == "faiss":
            from graphcoderag.storage.faiss_store import FaissVectorStore
            vs = FaissVectorStore(collection_name=f"ws_{active.workspace_id}")
        else:
            from graphcoderag.storage.vector_store import VectorStore
            vs = VectorStore(collection_name=f"ws_{active.workspace_id}")

        results = vs.search(req.query, top_k=req.top_k)
        
        # Format results for frontend
        formatted = []
        for r in results:
            meta = r.get("metadata", {})
            formatted.append({
                "chunk_id": r["chunk_id"],
                "file": meta.get("file_path", ""),
                "name": meta.get("name", ""),
                "type": meta.get("chunk_type", "function"),
                "line_start": meta.get("start_line", 0),
                "line_end": meta.get("end_line", 0),
                "docstring": meta.get("docstring", ""),
                "similarity": 1.0 - r.get("distance", 0.0)
            })
            
        return {"results": formatted}
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(500, "Internal Server Error")


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
            try:
                candidate = Path(file_path)
                if candidate.is_absolute() and candidate.exists():
                    lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                    source_code = "\n".join(lines[max(0,start-1):end])
                else:
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
                                # Also try adding src/ if missing
                                alt_src = repo_dir / "src" / os.sep.join(parts[i:])
                                if alt_src.exists():
                                    candidate = alt_src
                                    break
                        if candidate.exists():
                            lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
                            source_code = "\n".join(lines[max(0,start-1):end])
                            break
            except Exception as e:
                logger.error(f"Failed reading code from disk for node {name}: {e}")

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
        raise HTTPException(500, "Internal Server Error")


@app.get("/api/file-content")
def get_file_content(path: str = ""):
    """Get raw file content for the code viewer."""
    if not path:
        raise HTTPException(400, "path parameter required")
    # Find file in repo directory
    for repo_dir in REPOS_DIR.iterdir():
        candidate = (repo_dir / path).resolve()
        if not str(candidate).startswith(str(repo_dir.resolve())):
            continue
        if candidate.exists() and candidate.is_file():
            try:
                content = candidate.read_text(encoding="utf-8", errors="replace")
                return {"path": path, "content": content, "lines": content.count('\n') + 1}
            except Exception as e:
                logger.error(f"File read error: {e}")
                raise HTTPException(500, "Internal Server Error")
    raise HTTPException(404, "File not found")


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

        from graphcoderag.config import VECTOR_BACKEND
        if VECTOR_BACKEND == "faiss":
            from graphcoderag.storage.faiss_store import FaissVectorStore
            vs = FaissVectorStore(collection_name=f"ws_{ws_id}")
        else:
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

        def _run_connected_query(p=None):
            q = (
                "MATCH (a)-[r]->(b) "
                f"WHERE a.chunk_id IS NOT NULL AND b.chunk_id IS NOT NULL {('AND a.file_path CONTAINS $prefix' if p else '')} "
                "RETURN a.name AS a_name, labels(a)[0] AS a_label, a.file_path AS a_file, a.parent_class AS a_parent, "
                "b.name AS b_name, labels(b)[0] AS b_label, b.file_path AS b_file, b.parent_class AS b_parent, "
                "type(r) AS rel "
                "LIMIT 80"
            )
            with gs.driver.session() as session:
                return list(session.run(q, prefix=p))

        # Try connected scoped, fallback to unconnected scoped
        result = _run_connected_query(prefix) if prefix else []
        if not result and not prefix:
            result = _run_connected_query(None)

        nodes_map = {}
        edges = []

        if result:
            for r in result:
                # Add source node
                if r["a_name"] not in nodes_map:
                    fp = (r["a_file"] or "").replace("\\", "/")
                    nodes_map[r["a_name"]] = {
                        "name": r["a_name"],
                        "label": r["a_label"] or "Function",
                        "file": fp.split("/")[-1] if fp else "",
                        "display": r["a_name"].split(".")[-1] if "." in r["a_name"] else r["a_name"],
                        "parent": r["a_parent"] or "",
                    }
                # Add target node
                if r["b_name"] not in nodes_map:
                    fp = (r["b_file"] or "").replace("\\", "/")
                    nodes_map[r["b_name"]] = {
                        "name": r["b_name"],
                        "label": r["b_label"] or "Function",
                        "file": fp.split("/")[-1] if fp else "",
                        "display": r["b_name"].split(".")[-1] if "." in r["b_name"] else r["b_name"],
                        "parent": r["b_parent"] or "",
                    }
                # Add edge
                edges.append({"source": r["a_name"], "target": r["b_name"], "type": r["rel"]})

        # Fallback to standalone nodes if no edges exist at all
        if not nodes_map:
            def _run_node_query(p=None):
                q = (
                    "MATCH (n) WHERE n.chunk_id IS NOT NULL AND n.name IS NOT NULL "
                    f"{'AND n.file_path CONTAINS $prefix ' if p else ''}"
                    "RETURN n.name AS name, labels(n)[0] AS label, n.file_path AS file, "
                    "n.parent_class AS parent "
                    "LIMIT 40"
                )
                with gs.driver.session() as session:
                    return list(session.run(q, prefix=p))
                    
            fallback = _run_node_query(prefix) if prefix else _run_node_query(None)
            for r in fallback:
                fp = (r["file"] or "").replace("\\", "/")
                nodes_map[r["name"]] = {
                    "name": r["name"],
                    "label": r["label"] or "Function",
                    "file": fp.split("/")[-1] if fp else "",
                    "display": r["name"].split(".")[-1] if "." in r["name"] else r["name"],
                    "parent": r["parent"] or "",
                }

        nodes = list(nodes_map.values())
        
        # Post-process display names to add context for short names
        for n in nodes:
            if len(n["display"]) <= 3 and n["file"]:
                module = n["file"].replace(".py", "")
                n["display"] = f"{module}.{n['display']}"
            elif n["label"] == "Function":
                n["display"] += "()"

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
    eval_dir = Path(__file__).resolve().parent.parent.parent / "evaluation_results"
    latest_file = None
    
    if eval_dir.exists():
        json_files = list(eval_dir.glob("swebench_v2_*.json"))
        if json_files:
            latest_file = sorted(json_files)[-1]
            
    if not latest_file:
        # Fallback empty state
        return {
            "study": {"title": "No Evaluation Data Found", "instances": 0, "repositories": []},
            "methods": [],
            "metrics": {},
            "per_repo": [],
            "key_findings": ["Run swebench_runner_v2.py to generate evaluation metrics."]
        }

    try:
        data = json.loads(latest_file.read_text(encoding="utf-8"))
        repos = data.get("repos", {})
        
        metrics_dict = {}
        per_repo_list = []
        
        for repo_name, repo_data in repos.items():
            agg = repo_data.get("retrieval", {}).get("aggregated", {}).get("K=5", {})
            if not agg:
                continue
                
            standard = agg.get("A", {})
            hybrid = agg.get("B_hybrid", {})
            
            mrr_g = hybrid.get("mrr", 0)
            mrr_s = standard.get("mrr", 0)
            
            delta = mrr_g - mrr_s
            pct_delta = f"+{(delta / mrr_s * 100):.1f}%" if mrr_s > 0 and delta > 0 else f"{(delta / (mrr_s or 1) * 100):.1f}%"
            
            metrics_dict[f"mrr_{repo_name}"] = {
                "label": f"MRR@5 ({repo_name})",
                "description": f"Dynamic evaluation result from {latest_file.name}",
                "values": {"graphcoderag": mrr_g, "standard_rag": mrr_s},
                "repo": repo_name
            }
            
            per_repo_list.append({
                "repo": repo_name,
                "instances": len(repo_data.get("per_case", [])),
                "graphcoderag_mrr": mrr_g,
                "standard_mrr": mrr_s,
                "delta_mrr": pct_delta,
                "finding": f"GraphCodeRAG achieved an MRR of {mrr_g:.3f} compared to Standard RAG's {mrr_s:.3f}."
            })
            
        return {
            "study": {
                "title": f"Retrieval Evaluation -- {latest_file.name}",
                "instances": sum(r["instances"] for r in per_repo_list),
                "repositories": list(repos.keys()),
            },
            "methods": [
                {
                    "name": "GraphCodeRAG (AST+Vec)",
                    "description": "AST-aware chunking + hybrid retrieval",
                    "color": "#a855f7",
                },
                {
                    "name": "Standard RAG",
                    "description": "Character-based chunking + vector similarity",
                    "color": "#60a5fa",
                },
            ],
            "metrics": metrics_dict,
            "per_repo": per_repo_list,
            "key_findings": [
                f"Parsed from local execution: {latest_file.name}",
                "Metrics represent K=5 retrieval evaluation.",
                "Generation quality evaluation requires running the LLM-as-a-judge pipeline."
            ]
        }
    except Exception as e:
        logger.error(f"Failed to parse eval file: {e}")
        raise HTTPException(500, "Internal Server Error")


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
