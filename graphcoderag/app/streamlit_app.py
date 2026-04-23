"""
GraphCodeRAG — Streamlit Dashboard (Exact Mockup)
===================================================
Pixel-perfect ui_mockup_v3.html layout. Chat input is embedded in the
HTML iframe. Messages sent via query-param redirect.

Usage:
    streamlit run graphcoderag/app/streamlit_app.py
"""
import sys
import os
import re
import json
import html
import urllib.parse
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import streamlit as st
import streamlit.components.v1 as components
from graphcoderag.app.workspace_manager import WorkspaceManager

st.set_page_config(page_title="GraphCodeRAG", page_icon="🔮", layout="wide", initial_sidebar_state="expanded")

# Apply dark theme styling but KEEP sidebar visible for native widgets
st.markdown("""<style>
#MainMenu,footer,div[data-testid="stToolbar"],
div[data-testid="stDecoration"],div[data-testid="stStatusWidget"] {display:none!important;}
.block-container{padding-top:1rem!important;max-width:100%!important;}
.stApp{background:#09090b;}
[data-testid="stSidebar"]{background:#111118;border-right:1px solid #2a2a3a;}
[data-testid="stMetric"]{background:#111118;border:1px solid #2a2a3a;border-radius:8px;padding:12px;}
[data-testid="stMetricLabel"]{color:#8b8b9e;}
[data-testid="stMetricValue"]{color:#e0e0ff;font-size:1.5rem;}
iframe{border:none!important;}
h1,h2,h3,h4,h5{color:#e0e0ff!important;}
</style>""", unsafe_allow_html=True)


def main():
    if "wm" not in st.session_state:
        st.session_state["wm"] = WorkspaceManager()
    if "show_add_repo" not in st.session_state:
        st.session_state["show_add_repo"] = False
    if "ingest_error" not in st.session_state:
        st.session_state["ingest_error"] = ""
    if "ingest_success" not in st.session_state:
        st.session_state["ingest_success"] = ""

    wm: WorkspaceManager = st.session_state["wm"]

    # ── Auto-create workspace for existing data if none exist ──
    if not wm.get_all_workspaces():
        stats = _load_stats()
        if stats.get("chunks", 0) > 0:
            ws = wm.create_workspace("click", "main")
            ws.stats = stats
            wm.update_stats(stats)

    active_ws = wm.get_active()
    ws_id = active_ws.workspace_id if active_ws else None
    graph_data = _load_graph_data(ws_id)
    file_list = _load_file_list(ws_id)
    stats = active_ws.stats if active_ws and active_ws.stats.get("chunks") else _load_stats(ws_id)
    neo4j_ok = _check_neo4j()

    # ═══════════════════════════════════════════════════════════════
    #  SIDEBAR — Native Streamlit widgets
    # ═══════════════════════════════════════════════════════════════
    with st.sidebar:
        st.markdown("### 🔮 WORKSPACES")

        # Add repo button
        if st.button("➕ Add Repository", use_container_width=True):
            st.session_state["show_add_repo"] = True

        st.divider()

        # Workspace list
        all_ws = wm.get_all_workspaces()
        if all_ws:
            for ws_item in all_ws:
                repo_str = ws_item.repo or ""
                ws_name = html.escape(repo_str.rstrip("/").split("/")[-1] if "/" in repo_str else repo_str)
                ws_branch = html.escape(ws_item.branch)
                chunks = ws_item.stats.get("chunks", 0)
                edges = ws_item.stats.get("edges", 0)
                is_active = active_ws and ws_item.workspace_id == active_ws.workspace_id
                icon = "🟢" if is_active else "⚪"

                col1, col2 = st.columns([5, 1])
                with col1:
                    if st.button(
                        f"{icon} **{ws_name}** `{ws_branch}`\n\n{chunks} chunks · {edges} edges",
                        key=f"ws_{ws_item.workspace_id}",
                        use_container_width=True,
                    ):
                        wm.switch_to(ws_item.workspace_id)
                        st.rerun()
                with col2:
                    if st.button("✕", key=f"close_{ws_item.workspace_id}"):
                        wm.close_workspace(ws_item.workspace_id)
                        st.rerun()
        else:
            st.info("No workspaces yet. Add a repository to get started.")

    # ═══════════════════════════════════════════════════════════════
    #  ADD REPOSITORY MODAL
    # ═══════════════════════════════════════════════════════════════
    if st.session_state["show_add_repo"]:
        _show_add_repo_dialog(wm)

    # Show ingest notifications
    if st.session_state["ingest_error"]:
        st.error(f"❌ {st.session_state['ingest_error']}")
        st.session_state["ingest_error"] = ""
    if st.session_state["ingest_success"]:
        st.success(f"✅ {st.session_state['ingest_success']}")
        st.session_state["ingest_success"] = ""

    # ═══════════════════════════════════════════════════════════════
    #  MAIN LAYOUT — Stats + Files + Graph + Chat
    # ═══════════════════════════════════════════════════════════════
    if not active_ws:
        st.markdown("## 🔮 GraphCodeRAG")
        st.markdown("Add a repository from the sidebar to get started.")
        return

    # Stats bar
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Chunks", stats.get("chunks", 0))
    c2.metric("Functions", stats.get("functions", 0))
    c3.metric("Edges", stats.get("edges", 0))
    c4.metric("Classes", stats.get("classes", 0))
    c5.metric("Neo4j", "✅ Connected" if neo4j_ok else "❌ Down")

    # Main content: Files | Graph | Chat
    col_files, col_graph, col_chat = st.columns([1, 2, 2])

    # ── Files Panel ──
    with col_files:
        st.markdown(f"##### 📁 FILES ({len(file_list)})")
        for f in file_list:
            fname = html.escape(f["name"])
            st.markdown(f"📄 `{fname}` — {f['edges']} chunks")

    # ── Graph Panel ──
    with col_graph:
        st.markdown("##### 🔗 KNOWLEDGE GRAPH")
        graph_html = _build_graph_html(graph_data)
        components.html(graph_html, height=400, scrolling=False)

    # ── Chat Panel ──
    with col_chat:
        st.markdown("##### ⭐ AI ASSISTANT")

        # Chat history
        chat_container = st.container(height=350)
        with chat_container:
            chat_history = active_ws.chat_history if active_ws else []
            if not chat_history:
                st.markdown("*Ask a question about the codebase...*")
            for msg in chat_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    st.chat_message("user").markdown(content)
                else:
                    st.chat_message("assistant").markdown(content)
                    if msg.get("trace"):
                        t = msg["trace"]
                        st.caption(
                            f"🔍 Vector: {t.get('vector_count', 0)} · "
                            f"🔗 Graph: +{t.get('graph_count', 0)} · "
                            f"📦 Merged: {t.get('merged_count', 0)}"
                        )

        # Chat input — NATIVE Streamlit widget
        chat_input = st.chat_input("Ask about the codebase...")
        if chat_input:
            wm.update_chat({"role": "user", "content": chat_input})
            with st.spinner("Querying..."):
                resp = _run_query(chat_input, active_ws)
            wm.update_chat(resp)
            st.rerun()


@st.dialog("Add Repository")
def _show_add_repo_dialog(wm: WorkspaceManager):
    """Native Streamlit dialog for adding repositories."""
    tab_url, tab_local = st.tabs(["GitHub URL", "Local Path"])

    with tab_url:
        repo_url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
        branch = st.text_input("Branch (optional)", placeholder="main")

    with tab_local:
        local_path = st.text_input("Local Path", placeholder="C:/path/to/repo")

    col_cancel, col_ingest = st.columns(2)
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            st.session_state["show_add_repo"] = False
            st.rerun()
    with col_ingest:
        if st.button("🚀 Ingest Repository", type="primary", use_container_width=True):
            repo_input = repo_url.strip() if repo_url.strip() else local_path.strip()
            br = branch.strip() or "main"
            if not repo_input:
                st.error("Please enter a repository URL or local path.")
            else:
                with st.spinner(f"Ingesting {repo_input}..."):
                    err = _ingest_and_create_workspace(wm, repo_input, br)
                if err:
                    st.session_state["ingest_error"] = err
                else:
                    st.session_state["ingest_success"] = f"Successfully ingested {repo_input}"
                st.session_state["show_add_repo"] = False
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
#  GRAPH VISUALIZATION (HTML component — display only, no interaction)
# ═══════════════════════════════════════════════════════════════════════

def _build_graph_html(graph_data):
    """Build a self-contained HTML/JS force-directed graph."""
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    nodes_json = json.dumps(nodes)
    edges_json = json.dumps(edges)

    return f"""<!DOCTYPE html>
<html><head><style>
body{{margin:0;background:#0d0d15;overflow:hidden;}}
canvas{{display:block;}}
.legend{{position:absolute;bottom:8px;left:8px;display:flex;gap:14px;}}
.legend span{{color:#8b8b9e;font:11px sans-serif;display:flex;align-items:center;gap:4px;}}
.legend .dot{{width:8px;height:8px;border-radius:50%;}}
</style></head><body>
<canvas id="c"></canvas>
<div class="legend">
  <span><span class="dot" style="background:#6c63ff"></span>Func</span>
  <span><span class="dot" style="background:#e040fb"></span>Class</span>
  <span><span class="dot" style="background:#00e676"></span>Module</span>
</div>
<script>
const nodes={nodes_json}, edges={edges_json};
const canvas=document.getElementById('c'), ctx=canvas.getContext('2d');
canvas.width=canvas.parentElement.clientWidth;
canvas.height=canvas.parentElement.clientHeight||380;

const colors={{'Function':'#6c63ff','Class':'#e040fb','Module':'#00e676'}};
const W=canvas.width, H=canvas.height;

// Initialize positions
nodes.forEach((n,i)=>{{
  n.x=W/2+Math.cos(i*2.4)*120+Math.random()*60;
  n.y=H/2+Math.sin(i*2.4)*100+Math.random()*40;
  n.vx=0;n.vy=0;
  n.r=n.label==='Class'?14:n.label==='Module'?10:8;
}});

function simulate(){{
  // Repulsion
  for(let i=0;i<nodes.length;i++)
    for(let j=i+1;j<nodes.length;j++){{
      let dx=nodes[j].x-nodes[i].x, dy=nodes[j].y-nodes[i].y;
      let d=Math.sqrt(dx*dx+dy*dy)||1;
      let f=200/(d*d);
      nodes[i].vx-=f*dx/d; nodes[i].vy-=f*dy/d;
      nodes[j].vx+=f*dx/d; nodes[j].vy+=f*dy/d;
    }}
  // Attraction (edges)
  edges.forEach(e=>{{
    let a=nodes.find(n=>n.name===e.source), b=nodes.find(n=>n.name===e.target);
    if(!a||!b) return;
    let dx=b.x-a.x, dy=b.y-a.y, d=Math.sqrt(dx*dx+dy*dy)||1;
    let f=(d-80)*0.01;
    a.vx+=f*dx/d; a.vy+=f*dy/d;
    b.vx-=f*dx/d; b.vy-=f*dy/d;
  }});
  // Center gravity + update
  nodes.forEach(n=>{{
    n.vx+=(W/2-n.x)*0.002; n.vy+=(H/2-n.y)*0.002;
    n.vx*=0.9; n.vy*=0.9;
    n.x+=n.vx; n.y+=n.vy;
    n.x=Math.max(n.r,Math.min(W-n.r,n.x));
    n.y=Math.max(n.r,Math.min(H-n.r,n.y));
  }});
}}

function draw(){{
  ctx.clearRect(0,0,W,H);
  // Edges
  ctx.strokeStyle='rgba(100,100,180,0.3)'; ctx.lineWidth=1;
  edges.forEach(e=>{{
    let a=nodes.find(n=>n.name===e.source), b=nodes.find(n=>n.name===e.target);
    if(!a||!b) return;
    ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.stroke();
  }});
  // Nodes
  nodes.forEach(n=>{{
    let c=colors[n.label]||'#6c63ff';
    ctx.beginPath(); ctx.arc(n.x,n.y,n.r,0,Math.PI*2);
    ctx.fillStyle=c; ctx.globalAlpha=0.8; ctx.fill();
    ctx.globalAlpha=1;
    ctx.fillStyle='#ccc'; ctx.font='9px sans-serif'; ctx.textAlign='center';
    ctx.fillText(n.name.length>12?n.name.slice(0,12)+'..':n.name, n.x, n.y+n.r+11);
  }});
}}

let frame=0;
function loop(){{ simulate(); draw(); if(++frame<200) requestAnimationFrame(loop); }}
loop();
</script></body></html>"""


# ═══════════════════════════════════════════════════════════════════════
#  INGESTION
# ═══════════════════════════════════════════════════════════════════════

def _ingest_and_create_workspace(wm: WorkspaceManager, repo_input: str, branch: str = "main"):
    """Ingest a repo and create a new workspace for it.

    Returns None on success, or an error message string on failure.
    """
    log = logging.getLogger(__name__)
    import subprocess

    try:
        # Derive repo_name for clone target path
        is_url = repo_input.startswith("http")
        if is_url:
            from graphcoderag.config import REPOS_DIR
            repo_name = repo_input.rstrip("/").split("/")[-1].replace(".git", "")
            # Security: reject path-traversal names (#13)
            if not re.match(r'^[A-Za-z0-9._-]+$', repo_name) or repo_name in ('.', '..'):
                return f"Invalid repository name: {repo_name}"
            target = REPOS_DIR / repo_name
            if not target.exists():
                REPOS_DIR.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    ["git", "clone", "--depth", "1", "-b", branch,
                     "--", repo_input, str(target)],  # "--" prevents option injection
                    check=True, capture_output=True,
                )
            repo_path = str(target)
        else:
            repo_path = repo_input

        # Generate workspace id early (for tagging Neo4j nodes), but create
        # the persistent workspace record only AFTER successful ingestion (#3)
        import hashlib
        ws_id = hashlib.sha256(f"{repo_input}@{branch}".encode()).hexdigest()[:12]

        # Run pipeline
        from graphcoderag.ingestion.file_scanner import scan_repository
        from graphcoderag.ingestion.ast_parser import PythonASTParser
        from graphcoderag.ingestion.code_chunker import CodeChunker
        from graphcoderag.ingestion.dependency_extractor import DependencyExtractor

        files = scan_repository(repo_path)
        parser = PythonASTParser()
        chunker = CodeChunker()
        dep_extractor = DependencyExtractor()

        all_chunks, all_edges, parse_errors = [], [], 0
        for f in files:
            try:
                tree, src = parser.parse_file(f.abs_path)
                nodes = parser.extract_functions_and_classes(tree, src)
                chunks = chunker.chunk_file(f.rel_path, nodes, src)
                all_chunks.extend(chunks)
                edges = dep_extractor.extract_from_file(tree, src, f.rel_path)
                all_edges.extend(edges)
            except Exception:
                parse_errors += 1
                continue

        if not all_chunks:
            return f"No Python code found in {repo_input} (branch: {branch})"

        # Store in databases — workspace-scoped (#1/#5)
        from graphcoderag.storage.graph_store import GraphStore
        from graphcoderag.storage.vector_store import VectorStore

        gs = GraphStore()
        # Delete only THIS workspace's nodes, not everything (#1)
        _clear_workspace_graph(gs, ws_id)
        # Tag all chunks with workspace_id before storing
        for c in all_chunks:
            c.workspace_id = ws_id
        gs.store_chunks(all_chunks)
        gs.store_edges(all_edges)
        gs.close()

        # ChromaDB is already workspace-scoped via collection name
        collection_name = f"ws_{ws_id}"
        vs = VectorStore(collection_name=collection_name)
        vs.clear()
        vs.add_chunks(all_chunks)

        # NOW create workspace record (only after success) (#3)
        ws = wm.create_workspace(repo_input, branch)
        ws.stats = {
            "chunks": len(all_chunks),
            "functions": sum(1 for c in all_chunks if c.chunk_type == "function"),
            "classes": sum(1 for c in all_chunks if c.chunk_type == "class"),
            "edges": len(all_edges),
            "files": len(files),
            "parse_errors": parse_errors,
        }
        wm.update_stats(ws.stats)
        log.info("Ingested %s (%s): %d chunks, %d edges, %d parse errors",
                 repo_input, branch, len(all_chunks), len(all_edges), parse_errors)
        return None  # success

    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.decode(errors='replace')[:200] if e.stderr else str(e)
        log.error("Git clone failed: %s", err_msg)
        return f"Clone failed: {err_msg}"
    except Exception as e:
        log.error("Ingestion failed: %s", e, exc_info=True)
        return f"Ingestion error: {e}"


def _clear_workspace_graph(gs, workspace_id: str):
    """Delete only nodes belonging to a specific workspace (#1)."""
    with gs.driver.session() as session:
        session.run(
            "MATCH (n {workspace_id: $wid}) DETACH DELETE n",
            wid=workspace_id,
        )


# ═══════════════════════════════════════════════════════════════════════
#  FULL HTML
# ═══════════════════════════════════════════════════════════════════════

def _build_html(graph_data, file_list, stats, chat_history, neo4j_ok, ws_summary, active_ws, ingest_error=""):
    nodes_html = _graph_nodes(graph_data.get("nodes", []))
    edges_svg = _graph_edges(graph_data.get("nodes", []), graph_data.get("edges", []))
    files_html = _file_list_html(file_list)
    chat_html = _chat_html(chat_history)
    sidebar_html = _sidebar_html(ws_summary, active_ws)
    tabs_html = _tabs_html(ws_summary, active_ws)

    c = stats.get("chunks", 0)
    fn = stats.get("functions", 0)
    e = stats.get("edges", 0)
    cl = stats.get("classes", 0)
    nf = len(file_list)
    branch = active_ws.branch if active_ws else "main"
    sc = "status-connected" if neo4j_ok else "status-disconnected"
    sd = "#4ade80" if neo4j_ok else "#ef4444"
    st_txt = "Connected" if neo4j_ok else "Disconnected"

    return f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{height:100%;overflow:hidden;}}
body{{font-family:'Inter',sans-serif;background:#09090b;color:#fafafa;display:flex;height:100vh;}}

.activity-bar{{width:48px;background:#09090b;border-right:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;align-items:center;padding:12px 0;gap:4px;flex-shrink:0;}}
.activity-icon{{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;color:#52525b;cursor:pointer;transition:all 0.15s;position:relative;}}
.activity-icon:hover{{color:#a1a1aa;background:rgba(255,255,255,0.04);}}
.activity-icon.active{{color:#c084fc;background:rgba(124,58,237,0.1);}}
.activity-icon .notif{{position:absolute;top:4px;right:4px;width:8px;height:8px;border-radius:50%;background:#ef4444;border:2px solid #09090b;}}
.activity-spacer{{flex:1;}}
.activity-divider{{width:24px;height:1px;background:rgba(255,255,255,0.06);margin:4px 0;}}

.workspace-sidebar{{width:260px;background:rgba(255,255,255,0.01);border-right:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;}}
.ws-header{{padding:14px 16px;font-size:11px;font-weight:600;color:#52525b;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;justify-content:space-between;align-items:center;}}
.ws-add-btn{{width:22px;height:22px;border-radius:6px;border:1px dashed rgba(255,255,255,0.12);background:none;color:#52525b;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:14px;}}
.ws-add-btn:hover{{border-color:#c084fc;color:#c084fc;}}
.ws-section-label{{padding:12px 16px 6px;font-size:10px;font-weight:600;color:#3f3f46;text-transform:uppercase;letter-spacing:0.8px;}}
.ws-card{{margin:2px 8px;padding:10px 12px;border-radius:8px;cursor:pointer;border:1px solid transparent;transition:all 0.15s;}}
.ws-card:hover{{background:rgba(255,255,255,0.03);}}
.ws-card.active{{background:rgba(124,58,237,0.08);border-color:rgba(124,58,237,0.2);}}
.ws-card-top{{display:flex;align-items:center;gap:8px;margin-bottom:4px;}}
.ws-card-icon{{width:20px;height:20px;border-radius:5px;display:flex;align-items:center;justify-content:center;font-size:10px;flex-shrink:0;}}
.ws-card-icon.purple{{background:rgba(124,58,237,0.15);color:#c084fc;}}
.ws-card-icon.blue{{background:rgba(59,130,246,0.15);color:#60a5fa;}}
.ws-card-icon.green{{background:rgba(34,197,94,0.15);color:#4ade80;}}
.ws-card-icon.amber{{background:rgba(245,158,11,0.15);color:#fbbf24;}}
.ws-card-name{{font-size:13px;font-weight:500;color:#e4e4e7;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.ws-card-time{{font-size:10px;color:#3f3f46;}}
.ws-card-meta{{display:flex;align-items:center;gap:6px;padding-left:28px;}}
.ws-card-branch{{font-size:10px;color:#71717a;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.04);padding:1px 6px;border-radius:4px;}}
.ws-card-stats{{font-size:10px;color:#3f3f46;}}
.ws-card-preview{{font-size:11px;color:#52525b;padding-left:28px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}

.main-area{{flex:1;display:flex;flex-direction:column;min-width:0;}}
.topbar{{height:44px;display:flex;align-items:center;border-bottom:1px solid rgba(255,255,255,0.06);background:rgba(9,9,11,0.9);backdrop-filter:blur(12px);padding:0 4px;flex-shrink:0;}}
.repo-tabs{{display:flex;align-items:stretch;height:100%;flex:1;overflow-x:auto;}}
.repo-tab{{display:flex;align-items:center;gap:8px;padding:0 16px;font-size:12px;color:#71717a;cursor:pointer;border-right:1px solid rgba(255,255,255,0.04);white-space:nowrap;transition:all 0.1s;}}
.repo-tab:hover{{color:#a1a1aa;background:rgba(255,255,255,0.02);}}
.repo-tab.active{{color:#fafafa;background:rgba(255,255,255,0.04);border-bottom:2px solid #7c3aed;}}
.repo-tab .tab-dot{{width:8px;height:8px;border-radius:50%;flex-shrink:0;}}
.repo-tab .tab-name{{font-weight:500;}}
.repo-tab .tab-branch{{font-size:10px;color:#52525b;font-family:'JetBrains Mono',monospace;background:rgba(255,255,255,0.04);padding:1px 5px;border-radius:3px;}}
.repo-tab .tab-close{{width:16px;height:16px;border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#3f3f46;opacity:0;transition:all 0.1s;}}
.repo-tab:hover .tab-close{{opacity:1;}}
.tab-add{{width:32px;display:flex;align-items:center;justify-content:center;color:#3f3f46;cursor:pointer;font-size:16px;flex-shrink:0;}}
.topbar-controls{{display:flex;align-items:center;gap:8px;padding:0 12px;flex-shrink:0;}}
.branch-selector{{display:flex;align-items:center;gap:6px;padding:5px 10px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:6px;cursor:pointer;font-size:12px;}}
.branch-selector .branch-name{{color:#e4e4e7;font-family:'JetBrains Mono',monospace;font-weight:500;}}
.compare-btn{{display:flex;align-items:center;gap:5px;padding:5px 10px;background:rgba(59,130,246,0.08);border:1px solid rgba(59,130,246,0.15);border-radius:6px;font-size:11px;color:#60a5fa;font-weight:500;cursor:pointer;}}
.status-connected{{display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:10px;font-weight:500;background:rgba(34,197,94,0.08);color:#4ade80;border:1px solid rgba(34,197,94,0.15);}}
.status-disconnected{{display:flex;align-items:center;gap:5px;padding:4px 10px;border-radius:20px;font-size:10px;font-weight:500;background:rgba(239,68,68,0.08);color:#ef4444;border:1px solid rgba(239,68,68,0.15);}}

.workspace{{display:flex;flex:1;overflow:hidden;}}
.panel-left{{width:220px;border-right:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;flex-shrink:0;}}
.stats-row{{display:flex;border-bottom:1px solid rgba(255,255,255,0.04);}}
.stat-mini{{flex:1;padding:10px 8px;text-align:center;border-right:1px solid rgba(255,255,255,0.04);}}
.stat-mini:last-child{{border-right:none;}}
.stat-mini-val{{font-size:16px;font-weight:700;}}
.stat-mini-label{{font-size:9px;color:#52525b;text-transform:uppercase;letter-spacing:0.3px;}}
.stat-purple{{color:#c084fc;}}.stat-blue{{color:#60a5fa;}}.stat-green{{color:#4ade80;}}.stat-amber{{color:#fbbf24;}}
.panel-section-header{{padding:10px 14px;font-size:10px;font-weight:600;color:#3f3f46;text-transform:uppercase;letter-spacing:0.6px;display:flex;justify-content:space-between;}}
.file-list{{flex:1;overflow-y:auto;}}
.file-item{{display:flex;align-items:center;gap:7px;padding:4px 14px;font-size:12px;color:#71717a;cursor:pointer;transition:all 0.1s;}}
.file-item:hover{{background:rgba(255,255,255,0.02);color:#a1a1aa;}}
.file-item.active{{background:rgba(124,58,237,0.08);color:#c084fc;}}
.file-item .fi-name{{flex:1;}}.file-item .fi-badge{{font-size:9px;background:rgba(255,255,255,0.04);padding:1px 5px;border-radius:6px;color:#52525b;}}

.panel-center{{flex:1;display:flex;flex-direction:column;min-width:0;}}
.graph-area{{flex:1;position:relative;overflow:hidden;background:radial-gradient(ellipse at 25% 35%,rgba(124,58,237,0.06) 0%,transparent 55%),radial-gradient(ellipse at 75% 65%,rgba(59,130,246,0.04) 0%,transparent 45%),#09090b;}}
.graph-area::before{{content:'';position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,0.04) 1px,transparent 1px);background-size:20px 20px;}}
.graph-label{{position:absolute;top:12px;left:16px;font-size:10px;color:#3f3f46;text-transform:uppercase;letter-spacing:0.6px;z-index:5;}}
.graph-toolbar{{position:absolute;top:10px;right:14px;display:flex;gap:3px;z-index:5;}}
.g-btn{{width:28px;height:28px;border-radius:6px;border:1px solid rgba(255,255,255,0.06);background:rgba(9,9,11,0.7);backdrop-filter:blur(6px);color:#52525b;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:12px;}}

.node{{position:absolute;border-radius:50%;cursor:pointer;z-index:2;display:flex;align-items:center;justify-content:center;transition:all 0.2s;box-shadow:0 0 16px rgba(0,0,0,0.4);}}
.node:hover{{transform:scale(1.15);z-index:10;}}
.node.sel{{transform:scale(1.2);z-index:10;}}
.node-f{{background:radial-gradient(circle at 35% 35%,#60a5fa,#2563eb);border:2px solid rgba(96,165,250,0.3);}}
.node-f.sel{{border-color:#60a5fa;box-shadow:0 0 20px rgba(59,130,246,0.4);}}
.node-c{{background:radial-gradient(circle at 35% 35%,#c084fc,#7c3aed);border:2px solid rgba(192,132,252,0.3);}}
.node-c.sel{{border-color:#c084fc;box-shadow:0 0 20px rgba(124,58,237,0.4);}}
.node-m{{background:radial-gradient(circle at 35% 35%,#4ade80,#16a34a);border:2px solid rgba(74,222,128,0.3);}}
.node-lbl{{position:absolute;bottom:-16px;left:50%;transform:translateX(-50%);font-size:9px;color:#71717a;white-space:nowrap;font-weight:500;text-shadow:0 1px 3px rgba(0,0,0,0.8);font-family:'JetBrains Mono',monospace;}}
.node.glow{{animation:pulse-glow 2s ease-in-out infinite;}}
@keyframes pulse-glow{{0%,100%{{filter:brightness(1);}}50%{{filter:brightness(1.25);}}}}
.graph-svg{{position:absolute;inset:0;pointer-events:none;z-index:1;}}
.edge{{stroke-width:1;}}.edge-call{{stroke:rgba(96,165,250,0.2);}}.edge-import{{stroke:rgba(74,222,128,0.15);stroke-dasharray:4 3;}}.edge-contain{{stroke:rgba(192,132,252,0.15);}}.edge-hl{{stroke:rgba(250,204,21,0.4);stroke-width:1.5;}}
.graph-legend{{position:absolute;bottom:12px;left:14px;display:flex;gap:14px;font-size:10px;color:#3f3f46;background:rgba(9,9,11,0.7);backdrop-filter:blur(6px);padding:6px 12px;border-radius:6px;border:1px solid rgba(255,255,255,0.04);z-index:5;}}
.leg-item{{display:flex;align-items:center;gap:5px;}}.leg-dot{{width:6px;height:6px;border-radius:50%;}}.leg-line{{width:12px;height:2px;border-radius:1px;}}

.code-pane{{height:180px;border-top:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;}}
.code-pane-header{{display:flex;align-items:center;justify-content:space-between;padding:6px 14px;background:rgba(255,255,255,0.015);border-bottom:1px solid rgba(255,255,255,0.03);font-size:11px;}}
.code-pane-left{{display:flex;align-items:center;gap:8px;}}
.cp-badge{{padding:2px 7px;border-radius:4px;font-size:9px;font-weight:600;}}.cp-cls{{background:rgba(124,58,237,0.12);color:#c084fc;}}.cp-func{{background:rgba(59,130,246,0.12);color:#60a5fa;}}
.cp-path{{color:#71717a;font-family:'JetBrains Mono',monospace;}}.cp-lines{{color:#3f3f46;font-family:'JetBrains Mono',monospace;font-size:10px;background:rgba(255,255,255,0.03);padding:1px 5px;border-radius:3px;}}
.code-body{{flex:1;overflow:auto;padding:8px 0;font-family:'JetBrains Mono',monospace;font-size:11.5px;line-height:1.65;}}
.cl{{display:flex;padding:0 14px;}}.cl:hover{{background:rgba(255,255,255,0.015);}}.cl.hl{{background:rgba(124,58,237,0.06);border-left:2px solid #7c3aed;}}
.ln{{width:36px;text-align:right;padding-right:14px;color:#27272a;user-select:none;flex-shrink:0;}}.lc{{color:#d4d4d8;white-space:pre;}}
.kw{{color:#c084fc;}}.fn{{color:#60a5fa;}}.st{{color:#fbbf24;}}.cm{{color:#3f3f46;font-style:italic;}}.pr{{color:#f472b6;}}.op{{color:#52525b;}}

.panel-right{{width:360px;border-left:1px solid rgba(255,255,255,0.06);display:flex;flex-direction:column;flex-shrink:0;}}
.chat-head{{padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.04);display:flex;align-items:center;justify-content:space-between;}}
.chat-head-left{{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:600;color:#d4d4d8;}}
.mode-toggle{{display:flex;background:rgba(255,255,255,0.03);border-radius:5px;border:1px solid rgba(255,255,255,0.06);overflow:hidden;}}
.mode-opt{{padding:3px 9px;font-size:10px;font-weight:500;color:#52525b;cursor:pointer;}}.mode-opt.on{{background:rgba(124,58,237,0.12);color:#c084fc;}}
.chat-messages{{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:14px;}}
.msg-u{{align-self:flex-end;max-width:85%;}}.msg-u-bubble{{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px 10px 3px 10px;padding:9px 13px;font-size:12.5px;line-height:1.5;color:#d4d4d8;}}
.msg-u-bubble code{{background:rgba(124,58,237,0.1);color:#c084fc;padding:0 4px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:11px;}}
.msg-a{{display:flex;gap:9px;}}.msg-a-av{{width:24px;height:24px;border-radius:6px;flex-shrink:0;background:linear-gradient(135deg,#7c3aed,#a855f7);display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:white;margin-top:2px;}}
.msg-a-body{{flex:1;min-width:0;}}.msg-a-body p{{font-size:12.5px;line-height:1.55;color:#a1a1aa;margin-bottom:6px;}}.msg-a-body strong{{color:#e4e4e7;}}
.msg-a-body code{{background:rgba(124,58,237,0.1);color:#c084fc;padding:0 4px;border-radius:3px;font-family:'JetBrains Mono',monospace;font-size:11px;}}
.msg-code{{background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.05);border-radius:6px;margin:6px 0;overflow:hidden;}}
.msg-code-top{{display:flex;justify-content:space-between;padding:4px 10px;background:rgba(255,255,255,0.02);border-bottom:1px solid rgba(255,255,255,0.03);font-size:10px;color:#3f3f46;font-family:'JetBrains Mono',monospace;}}
.msg-code-content{{padding:8px 12px;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.55;color:#a1a1aa;white-space:pre;}}
.chips{{display:flex;flex-wrap:wrap;gap:3px;margin-top:6px;}}
.chip{{display:flex;align-items:center;gap:3px;padding:2px 7px;border-radius:4px;font-size:9px;font-family:'JetBrains Mono',monospace;cursor:pointer;}}
.chip-v{{background:rgba(59,130,246,0.08);color:#60a5fa;border:1px solid rgba(59,130,246,0.12);}}.chip-g{{background:rgba(74,222,128,0.08);color:#4ade80;border:1px solid rgba(74,222,128,0.12);}}.chip-h{{background:rgba(124,58,237,0.08);color:#c084fc;border:1px solid rgba(124,58,237,0.12);}}
.trace{{background:rgba(255,255,255,0.015);border:1px solid rgba(255,255,255,0.03);border-radius:6px;margin:6px 0;padding:8px 10px;}}
.trace-title{{font-size:10px;color:#3f3f46;margin-bottom:6px;}}.trace-step{{display:flex;align-items:flex-start;gap:8px;padding:3px 0;font-size:10px;color:#52525b;}}
.trace-num{{width:16px;height:16px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:600;flex-shrink:0;}}
.tn-v{{background:rgba(59,130,246,0.12);color:#60a5fa;}}.tn-g{{background:rgba(74,222,128,0.12);color:#4ade80;}}.tn-m{{background:rgba(250,204,21,0.12);color:#fbbf24;}}

.chat-input-wrap{{padding:10px 14px;border-top:1px solid rgba(255,255,255,0.04);}}
.chat-box{{display:flex;align-items:flex-end;gap:7px;background:rgba(255,255,255,0.025);border:1px solid rgba(255,255,255,0.07);border-radius:8px;padding:8px 10px;}}
.chat-box:focus-within{{border-color:rgba(124,58,237,0.35);}}
.chat-box textarea{{flex:1;background:none;border:none;color:#fafafa;font-size:12px;font-family:'Inter',sans-serif;resize:none;outline:none;height:18px;line-height:18px;}}
.chat-box textarea::placeholder{{color:#27272a;}}
.send{{width:26px;height:26px;border-radius:6px;border:none;background:linear-gradient(135deg,#7c3aed,#a855f7);color:white;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0;}}
.send:hover{{filter:brightness(1.1);}}
.chat-hint{{font-size:9px;color:#27272a;text-align:center;margin-top:4px;}}

/* ===== ADD REPO MODAL ===== */
.modal-overlay{{position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);z-index:300;display:flex;align-items:center;justify-content:center;}}
.modal{{background:#18181b;border:1px solid rgba(255,255,255,0.08);border-radius:14px;width:480px;box-shadow:0 24px 64px rgba(0,0,0,0.5);overflow:hidden;}}
.modal-header{{padding:18px 22px;border-bottom:1px solid rgba(255,255,255,0.06);display:flex;align-items:center;justify-content:space-between;}}
.modal-header h3{{font-size:15px;font-weight:600;}}
.modal-close{{color:#52525b;cursor:pointer;font-size:16px;padding:4px;}}
.modal-close:hover{{color:#a1a1aa;}}
.modal-body{{padding:20px 22px;}}
.modal-field{{margin-bottom:16px;}}
.modal-label{{font-size:12px;color:#71717a;font-weight:500;margin-bottom:6px;}}
.modal-input{{width:100%;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);color:#fafafa;padding:10px 14px;border-radius:8px;font-size:13px;font-family:'Inter',sans-serif;outline:none;}}
.modal-input:focus{{border-color:rgba(124,58,237,0.4);}}
.modal-input::placeholder{{color:#3f3f46;}}
.modal-hint{{font-size:11px;color:#3f3f46;margin-top:4px;}}
.modal-tabs{{display:flex;gap:2px;margin-bottom:14px;}}
.modal-tab{{padding:6px 14px;border-radius:6px;font-size:12px;color:#52525b;cursor:pointer;font-weight:500;}}
.modal-tab.active{{background:rgba(124,58,237,0.1);color:#c084fc;}}
.modal-footer{{padding:14px 22px;border-top:1px solid rgba(255,255,255,0.06);display:flex;justify-content:flex-end;gap:8px;}}
.btn-cancel{{padding:8px 16px;border-radius:8px;font-size:13px;color:#71717a;background:none;border:1px solid rgba(255,255,255,0.08);cursor:pointer;font-family:inherit;}}
.btn-cancel:hover{{border-color:rgba(255,255,255,0.15);color:#a1a1aa;}}
.btn-primary{{padding:8px 20px;border-radius:8px;font-size:13px;color:white;background:linear-gradient(135deg,#7c3aed,#a855f7);border:none;cursor:pointer;font-weight:600;font-family:inherit;}}
.btn-primary:hover{{filter:brightness(1.1);}}

/* ===== BRANCH DROPDOWN ===== */
.branch-dropdown{{position:absolute;top:46px;right:160px;z-index:200;background:#18181b;border:1px solid rgba(255,255,255,0.1);border-radius:10px;width:280px;box-shadow:0 16px 48px rgba(0,0,0,0.5);overflow:hidden;display:none;}}
.bd-search{{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.06);}}
.bd-search input{{flex:1;background:none;border:none;color:#fafafa;font-size:12px;font-family:'Inter',sans-serif;outline:none;}}
.bd-search input::placeholder{{color:#3f3f46;}}
.bd-section{{padding:6px 0;}}
.bd-label{{padding:6px 14px;font-size:9px;color:#3f3f46;text-transform:uppercase;letter-spacing:0.6px;}}
.bd-item{{display:flex;align-items:center;gap:8px;padding:7px 14px;font-size:12px;color:#a1a1aa;cursor:pointer;transition:all 0.1s;}}
.bd-item:hover{{background:rgba(255,255,255,0.04);}}
.bd-item.current{{color:#c084fc;}}
.bd-item .bd-icon{{font-size:13px;color:#52525b;width:16px;text-align:center;}}
.bd-item .bd-name{{flex:1;font-family:'JetBrains Mono',monospace;font-weight:500;}}
.bd-item .bd-check{{color:#c084fc;font-size:12px;}}
.bd-item .bd-ago{{font-size:10px;color:#3f3f46;}}

::-webkit-scrollbar{{width:4px;}}::-webkit-scrollbar-track{{background:transparent;}}::-webkit-scrollbar-thumb{{background:rgba(255,255,255,0.06);border-radius:2px;}}
</style></head>
<body>

<div class="activity-bar">
  <div class="activity-icon active" title="Explorer">&#9638;</div>
  <div class="activity-icon" title="Search">&#128269;</div>
  <div class="activity-icon" title="Graph">&#9672;</div>
  <div class="activity-divider"></div>
  <div class="activity-icon" title="Evaluation">&#128202;</div>
  <div class="activity-icon" title="Ingest">&#9881;</div>
  <div class="activity-spacer"></div>
  <div class="activity-icon" title="History">&#128337;<div class="notif"></div></div>
  <div class="activity-icon" title="Settings">&#9881;</div>
</div>

<div class="workspace-sidebar">{sidebar_html}</div>

<!-- ADD REPO MODAL -->
<div class="modal-overlay" id="modal-new" style="display:none;">
  <div class="modal">
    <div class="modal-header">
      <h3>Add Repository</h3>
      <span class="modal-close" onclick="closeModal()">&times;</span>
    </div>
    <div class="modal-body">
      <div class="modal-tabs">
        <div class="modal-tab active" id="tab-url" onclick="switchTab('url')">GitHub URL</div>
        <div class="modal-tab" id="tab-local" onclick="switchTab('local')">Local Path</div>
      </div>
      <div class="modal-field" id="field-url">
        <div class="modal-label">Repository URL</div>
        <input class="modal-input" id="input-repo" placeholder="https://github.com/owner/repo" />
        <div class="modal-hint">Supports any public GitHub repository</div>
      </div>
      <div class="modal-field" id="field-local" style="display:none;">
        <div class="modal-label">Local Path</div>
        <input class="modal-input" id="input-path" placeholder="C:\\path\\to\\repository" />
        <div class="modal-hint">Absolute path to a local Python repository</div>
      </div>
      <div class="modal-field">
        <div class="modal-label">Branch (optional)</div>
        <input class="modal-input" id="input-branch" placeholder="main (default)" />
        <div class="modal-hint">Leave empty to use the default branch</div>
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn-cancel" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="ingestRepo()">Ingest Repository</button>
    </div>
  </div>
</div>

<div class="main-area">
  <div class="topbar">
    <div class="repo-tabs">{tabs_html}<div class="tab-add" onclick="openModal()">+</div></div>
    <div class="topbar-controls">
      <div class="branch-selector" id="btn-branch" onclick="toggleBranch()"><span style="font-size:13px;color:#71717a;">&#9095;</span><span class="branch-name">{branch}</span><span style="color:#52525b;font-size:8px;">&#9660;</span></div>
      <div class="compare-btn">&#8644; Compare</div>
      <div class="{sc}"><div style="width:5px;height:5px;border-radius:50%;background:{sd};"></div>{st_txt}</div>
    </div>
    <!-- Branch Dropdown -->
    <div class="branch-dropdown" id="branch-dropdown">
      <div class="bd-search"><span style="color:#3f3f46;font-size:13px;">&#128269;</span><input placeholder="Search branches..." /></div>
      <div class="bd-section">
        <div class="bd-label">Current</div>
        <div class="bd-item current"><span class="bd-icon">&#9095;</span><span class="bd-name">{branch}</span><span class="bd-check">&#10003;</span></div>
      </div>
      <div class="bd-section">
        <div class="bd-label">Other Branches</div>
        <div class="bd-item"><span class="bd-icon">&#9095;</span><span class="bd-name">dev</span><span class="bd-ago">2 weeks ago</span></div>
      </div>
      <div class="bd-section" style="border-top:1px solid rgba(255,255,255,0.04);padding-top:8px;">
        <div class="bd-item" style="color:#60a5fa;" onclick="openModal()"><span class="bd-icon" style="color:#60a5fa;">+</span><span class="bd-name" style="color:#60a5fa;">Ingest new branch...</span></div>
      </div>
    </div>
  </div>
  <div class="workspace">
    <div class="panel-left">
      <div class="stats-row">
        <div class="stat-mini"><div class="stat-mini-val stat-purple">{c}</div><div class="stat-mini-label">Chunks</div></div>
        <div class="stat-mini"><div class="stat-mini-val stat-blue">{fn}</div><div class="stat-mini-label">Funcs</div></div>
        <div class="stat-mini"><div class="stat-mini-val stat-green">{e}</div><div class="stat-mini-label">Edges</div></div>
        <div class="stat-mini"><div class="stat-mini-val stat-amber">{cl}</div><div class="stat-mini-label">Classes</div></div>
      </div>
      <div class="panel-section-header">Files <span style="color:#3f3f46;">{nf}</span></div>
      <div class="file-list">{files_html}</div>
    </div>
    <div class="panel-center">
      <div class="graph-area">
        <div class="graph-label">Knowledge Graph</div>
        <div class="graph-toolbar"><div class="g-btn">+</div><div class="g-btn">&minus;</div><div class="g-btn">&#8634;</div><div class="g-btn">&#9776;</div></div>
        <svg class="graph-svg" width="100%" height="100%">{edges_svg}</svg>
        {nodes_html}
        <div class="graph-legend">
          <div class="leg-item"><div class="leg-dot" style="background:#3b82f6;"></div> Func</div>
          <div class="leg-item"><div class="leg-dot" style="background:#7c3aed;"></div> Class</div>
          <div class="leg-item"><div class="leg-dot" style="background:#22c55e;"></div> Module</div>
          <div class="leg-item"><div class="leg-line" style="background:#60a5fa;"></div> Calls</div>
          <div class="leg-item"><div class="leg-line" style="background:#4ade80;height:0;border-top:2px dashed #4ade80;"></div> Imports</div>
          <div class="leg-item"><div class="leg-line" style="background:#c084fc;"></div> Contains</div>
        </div>
      </div>
      <div class="code-pane">
        <div class="code-pane-header"><div class="code-pane-left"><span class="cp-badge cp-cls">CLASS</span><span class="cp-path">click/core.py</span><span class="cp-lines">L1247-1312</span></div><span style="font-size:10px;color:#3f3f46;">Selected: Group</span></div>
        <div class="code-body">
          <div class="cl"><span class="ln">1247</span><span class="lc"><span class="kw">class</span> <span class="fn">Group</span>(MultiCommand):</span></div>
          <div class="cl"><span class="ln">1248</span><span class="lc">    <span class="st">&quot;&quot;&quot;A command that has subcommands.&quot;&quot;&quot;</span></span></div>
          <div class="cl"><span class="ln">1249</span><span class="lc"></span></div>
          <div class="cl hl"><span class="ln">1284</span><span class="lc">    <span class="kw">def</span> <span class="fn">invoke</span>(<span class="pr">self</span>, <span class="pr">ctx</span>):</span></div>
          <div class="cl hl"><span class="ln">1285</span><span class="lc">        <span class="kw">def</span> <span class="fn">_process_result</span>(<span class="pr">value</span>):</span></div>
          <div class="cl hl"><span class="ln">1286</span><span class="lc">            <span class="kw">if</span> self.result_callback <span class="kw">is not</span> <span class="kw">None</span>:</span></div>
          <div class="cl hl"><span class="ln">1287</span><span class="lc">                value <span class="op">=</span> ctx.invoke(</span></div>
          <div class="cl hl"><span class="ln">1288</span><span class="lc">                    self.result_callback, value, <span class="op">**</span>ctx.params)</span></div>
        </div>
      </div>
    </div>
    <div class="panel-right">
      <div class="chat-head"><div class="chat-head-left">&#9733; AI Assistant</div><div class="mode-toggle"><div class="mode-opt on">Hybrid</div><div class="mode-opt">Vector</div></div></div>
      <div class="chat-messages" id="chat-scroll">{chat_html}</div>
      <div class="chat-input-wrap">
        <div class="chat-box">
          <textarea id="chat-input" placeholder="Ask about the codebase..." rows="1"
                    onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendMsg();}}"></textarea>
          <button class="send" onclick="sendMsg()">&#10148;</button>
        </div>
        <div class="chat-hint">Enter to send &middot; Shift+Enter for newline</div>
      </div>
    </div>
  </div>
</div>

<script>
function sendMsg(){{
  var t=document.getElementById('chat-input');
  var msg=t.value.trim();
  if(!msg)return;
  t.value='';
  window.top.location.href='?chat_msg='+encodeURIComponent(msg);
}}
function openModal(){{ document.getElementById('modal-new').style.display='flex'; closeBranch(); }}
function closeModal(){{ document.getElementById('modal-new').style.display='none'; }}
function toggleBranch(){{
  var dd=document.getElementById('branch-dropdown');
  dd.style.display=dd.style.display==='none'||!dd.style.display?'block':'none';
}}
function closeBranch(){{ document.getElementById('branch-dropdown').style.display='none'; }}
function switchTab(tab){{
  if(tab==='url'){{
    document.getElementById('tab-url').classList.add('active');
    document.getElementById('tab-local').classList.remove('active');
    document.getElementById('field-url').style.display='block';
    document.getElementById('field-local').style.display='none';
  }} else {{
    document.getElementById('tab-local').classList.add('active');
    document.getElementById('tab-url').classList.remove('active');
    document.getElementById('field-local').style.display='block';
    document.getElementById('field-url').style.display='none';
  }}
}}
function ingestRepo(){{
  var isUrl=document.getElementById('tab-url').classList.contains('active');
  var repo=isUrl?document.getElementById('input-repo').value.trim():document.getElementById('input-path').value.trim();
  var branch=document.getElementById('input-branch').value.trim()||'main';
  if(!repo){{ alert('Please enter a repository URL or path'); return; }}
  closeModal();
  window.top.location.href='?ingest_repo='+encodeURIComponent(repo)+'&ingest_branch='+encodeURIComponent(branch);
}}
// Auto-scroll chat to bottom
var cs=document.getElementById('chat-scroll');
if(cs)cs.scrollTop=cs.scrollHeight;
// Close dropdown on outside click
document.addEventListener('click',function(e){{
  if(!e.target.closest('#btn-branch')&&!e.target.closest('#branch-dropdown'))closeBranch();
  if(e.target.classList.contains('modal-overlay'))closeModal();
}});
</script>
</body></html>'''


# ═══════════════════════════════════════════════════════════════════════
#  HTML BUILDERS
# ═══════════════════════════════════════════════════════════════════════

def _sidebar_html(ws_summary, active_ws):
    active_list = ws_summary.get("active_workspaces", [])
    history_list = ws_summary.get("history_workspaces", [])
    colors = ["purple", "blue", "green", "amber"]
    parts = ['<div class="ws-header">Workspaces <button class="ws-add-btn" onclick="openModal()">+</button></div>']
    if active_list:
        parts.append('<div class="ws-section-label">Active Sessions</div>')
        for i, w in enumerate(active_list):
            ac = " active" if active_ws and w["id"] == active_ws.workspace_id else ""
            col = colors[i % 4]
            ck = w["stats"].get("chunks", 0)
            eg = w["stats"].get("edges", 0)
            # XSS fix (#11): escape all user-controlled strings
            repo = html.escape(w["repo_name"])
            br = html.escape(w["branch"])
            lq = html.escape(w["last_query"])
            parts.append(f'<div class="ws-card{ac}" onclick="window.top.location.href=\'?switch_ws={w["id"]}\'">'
                         f'<div class="ws-card-top"><div class="ws-card-icon {col}">&#9672;</div><div class="ws-card-name">{repo}</div><div class="ws-card-time">{w["time"]}</div></div>'
                         f'<div class="ws-card-meta"><div class="ws-card-branch">{br}</div><div class="ws-card-stats">{ck} chunks &middot; {eg} edges</div></div>'
                         f'<div class="ws-card-preview">Last: &quot;{lq}&quot;</div></div>')
    if history_list:
        parts.append('<div class="ws-section-label">Recent History</div>')
        for i, w in enumerate(history_list):
            col = colors[(i + len(active_list)) % 4]
            ck = w["stats"].get("chunks", 0)
            eg = w["stats"].get("edges", 0)
            repo = html.escape(w["repo_name"])
            br = html.escape(w["branch"])
            parts.append(f'<div class="ws-card" onclick="window.top.location.href=\'?switch_ws={w["id"]}\'">'
                         f'<div class="ws-card-top"><div class="ws-card-icon {col}">&#9672;</div><div class="ws-card-name">{repo}</div><div class="ws-card-time">{w["time"]}</div></div>'
                         f'<div class="ws-card-meta"><div class="ws-card-branch">{br}</div><div class="ws-card-stats">{ck} chunks &middot; {eg} edges</div></div></div>')
    if not active_list and not history_list:
        parts.append('<div style="text-align:center;padding:30px 16px;color:#3f3f46;font-size:12px;">No workspaces yet</div>')
    return "\n".join(parts)


def _tabs_html(ws_summary, active_ws):
    colors = ["#7c3aed", "#3b82f6", "#22c55e", "#f59e0b"]
    parts = []
    for i, w in enumerate(ws_summary.get("active_workspaces", [])):
        is_active = ' active' if active_ws and w['id'] == active_ws.workspace_id else ''
        repo = html.escape(str(w.get('repo_name', '')))
        br = html.escape(str(w.get('branch', '')))
        parts.append(
            f'<div class="repo-tab{is_active}" onclick="window.top.location.href=\'?switch_ws={w["id"]}\'">'
            f'<div class="tab-dot" style="background:{colors[i%4]};"></div><span class="tab-name">{repo}</span>'
            f'<span class="tab-branch">{br}</span>'
            f'<span class="tab-close" onclick="event.stopPropagation();window.top.location.href=\'?close_ws={w["id"]}\';">&times;</span></div>'
        )
    return "\n".join(parts)


def _graph_nodes(nodes):
    import math
    if not nodes: return ""
    parts, n = [], len(nodes[:18])
    cx_c, cy_c = 290, 170  # Center of graph area
    for i, nd in enumerate(nodes[:18]):
        name, label = nd["name"], nd["label"]
        # Circular layout with slight randomness
        angle = (2 * math.pi * i) / n
        r = 80 + (i % 3) * 40
        cx = int(cx_c + r * math.cos(angle))
        cy = int(cy_c + r * math.sin(angle) * 0.7)
        nd["x"], nd["y"] = cx, cy
        css = "node-c" if label == "Class" else "node-m" if label == "Module" else "node-f"
        sz = 48 if label == "Class" else 36 if label == "Module" else 28 + (i % 3) * 4
        sel = " sel" if i == 0 else ""
        glow = " glow" if i == 3 else ""
        dn = name if len(name) <= 14 else name[:12] + ".."
        parts.append(f'<div class="node {css}{sel}{glow}" style="width:{sz}px;height:{sz}px;left:{cx-sz//2}px;top:{cy-sz//2}px;"><div class="node-lbl">{dn}</div></div>')
    return "\n".join(parts)


def _graph_edges(nodes, edges):
    if not nodes or not edges: return ""
    pos = {n["name"]: (n.get("x", 0), n.get("y", 0)) for n in nodes if "x" in n}
    return "\n".join(
        f'<line class="edge {"edge-call" if e["type"]=="CALLS" else "edge-import" if e["type"]=="IMPORTS" else "edge-contain"}" '
        f'x1="{pos[e["source"]][0]}" y1="{pos[e["source"]][1]}" x2="{pos[e["target"]][0]}" y2="{pos[e["target"]][1]}"/>'
        for e in edges[:25] if e["source"] in pos and e["target"] in pos
    )


def _file_list_html(files):
    return "\n".join(
        f'<div class="file-item{" active" if i==0 else ""}"><span style="font-size:12px;opacity:0.5;">&#128196;</span><span class="fi-name">{f["name"]}</span><span class="fi-badge">{f["edges"]}</span></div>'
        for i, f in enumerate(files[:15])
    )


def _chat_html(history):
    if not history:
        return ('<div style="text-align:center;padding:40px 16px;color:#3f3f46;font-size:12px;">'
                '<div style="font-size:24px;margin-bottom:8px;">&#128172;</div>'
                'Ask a question about the codebase</div>')
    parts = []
    for m in history:
        if m["role"] == "user":
            c = m["content"].replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f'<div class="msg-u"><div class="msg-u-bubble">{c}</div></div>')
        else:
            c = m["content"].replace("<", "&lt;").replace(">", "&gt;")
            chips = ""
            if m.get("sources"):
                chip_parts = []
                for s in m["sources"][:6]:
                    src_type = s.get("source", "")
                    chip_cls = "chip-v" if src_type == "vector" else "chip-g" if src_type == "graph" else "chip-h"
                    dot_color = "#3b82f6" if src_type == "vector" else "#22c55e" if src_type == "graph" else "#7c3aed"
                    name = s.get("name", "?")[:20]
                    score_display = f'{s.get("score", 0):.2f}' if src_type != "graph" else "graph"
                    chip_parts.append(
                        f'<div class="chip {chip_cls}">'
                        f'<div style="width:4px;height:4px;border-radius:50%;background:{dot_color};"></div>'
                        f'{name} <span style="opacity:0.5;">{score_display}</span></div>'
                    )
                chips = '<div class="chips">' + "".join(chip_parts) + '</div>'
            trace = ""
            if m.get("trace"):
                t = m["trace"]
                trace = (f'<div class="trace"><div class="trace-title">&#9660; Retrieval trace &mdash; {t.get("merged_count",0)} chunks</div>'
                         f'<div class="trace-step"><div class="trace-num tn-v">1</div><div>Vector: <strong>{t.get("vector_count",0)} chunks</strong> found</div></div>'
                         f'<div class="trace-step"><div class="trace-num tn-g">2</div><div>Graph: <strong>+{t.get("graph_count",0)} chunks</strong> via edges</div></div>'
                         f'<div class="trace-step"><div class="trace-num tn-m">3</div><div>Merged: <strong>{t.get("merged_count",0)} unique</strong> re-ranked</div></div></div>')
            paras = "".join(f"<p>{l}</p>" for l in c.split("\n") if l.strip())
            parts.append(f'<div class="msg-a"><div class="msg-a-av">G</div><div class="msg-a-body">{paras}{chips}{trace}</div></div>')
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════
#  DATA LOADING
# ═══════════════════════════════════════════════════════════════════════

def _load_graph_data(workspace_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        with gs.driver.session() as s:
            # Try workspace-scoped first, fall back to unscoped for pre-existing data
            nodes = []
            if workspace_id:
                nodes = [{"name": r["name"], "label": r["label"]} for r in s.run(
                    "MATCH (n) WHERE n.chunk_id IS NOT NULL AND n.workspace_id = $wid "
                    "RETURN n.name AS name, labels(n)[0] AS label LIMIT 20", wid=workspace_id)]
            if not nodes:
                nodes = [{"name": r["name"], "label": r["label"]} for r in s.run(
                    "MATCH (n) WHERE n.chunk_id IS NOT NULL "
                    "RETURN n.name AS name, labels(n)[0] AS label LIMIT 20")]
            nn = {n["name"] for n in nodes}
            edges = [{"source": r["src"], "target": r["tgt"], "type": r["etype"]} for r in s.run(
                "MATCH (a)-[r]->(b) WHERE a.chunk_id IS NOT NULL AND b.chunk_id IS NOT NULL "
                "RETURN a.name AS src, b.name AS tgt, type(r) AS etype LIMIT 30"
            ) if r["src"] in nn and r["tgt"] in nn]
        gs.close()
        return {"nodes": nodes, "edges": edges}
    except Exception:
        return {"nodes": [], "edges": []}


def _load_file_list(workspace_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        with gs.driver.session() as s:
            files = []
            if workspace_id:
                files = [{"name": os.path.basename(r["fp"]), "path": r["fp"], "edges": r["cnt"]}
                         for r in s.run(
                    "MATCH (n) WHERE n.file_path IS NOT NULL AND n.chunk_id IS NOT NULL "
                    "AND n.workspace_id = $wid "
                    "WITH n.file_path AS fp, count(*) AS cnt RETURN fp, cnt ORDER BY cnt DESC LIMIT 15",
                    wid=workspace_id)]
            if not files:
                files = [{"name": os.path.basename(r["fp"]), "path": r["fp"], "edges": r["cnt"]}
                         for r in s.run(
                    "MATCH (n) WHERE n.file_path IS NOT NULL AND n.chunk_id IS NOT NULL "
                    "WITH n.file_path AS fp, count(*) AS cnt RETURN fp, cnt ORDER BY cnt DESC LIMIT 15")]
        gs.close()
        return files
    except Exception:
        return []


def _load_stats(workspace_id=None):
    try:
        from graphcoderag.storage.graph_store import GraphStore
        from graphcoderag.storage.vector_store import VectorStore
        gs = GraphStore(); s = gs.get_graph_stats(); gs.close()
        vs = VectorStore()
        return {"chunks": vs.count(), "functions": s.get("nodes_Function", 0),
                "classes": s.get("nodes_Class", 0), "edges": s.get("total_edges", 0)}
    except Exception:
        return {"chunks": 0, "functions": 0, "classes": 0, "edges": 0}


def _check_neo4j():
    try:
        from graphcoderag.storage.graph_store import GraphStore
        gs = GraphStore()
        with gs.driver.session() as s: s.run("RETURN 1")
        gs.close()
        return True
    except Exception:
        return False


def _run_query(prompt, active_ws):
    try:
        from graphcoderag.retrieval.hybrid_retriever import HybridRetriever
        from graphcoderag.generation.generator import LLMGenerator
        retriever = HybridRetriever(); generator = LLMGenerator()
        results = retriever.retrieve(prompt, final_top_k=10)
        sources = [{"name": r.name or r.display_name, "file": r.file_path, "score": round(r.score, 3), "source": r.source} for r in results[:6]]
        nv = sum(1 for r in results if r.source in ("vector", "hybrid"))
        ng = sum(1 for r in results if r.source in ("graph", "hybrid"))
        answer = generator.generate(query=prompt, context_chunks=results)
        retriever.close()
        return {"role": "assistant", "content": answer, "sources": sources, "trace": {"vector_count": nv, "graph_count": ng, "merged_count": len(set(r.chunk_id for r in results))}}
    except Exception as ex:
        return {"role": "assistant", "content": f"Error: {ex}", "sources": [], "trace": None}


if __name__ == "__main__":
    main()
