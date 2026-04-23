"""
Workspace Manager — Multi-repo/branch session persistence.

Handles creating, saving, loading, and switching workspaces.
Each workspace stores: repo, branch, chat_history, stats, timestamps.

Data is persisted to:
    ~/.graphcoderag/workspaces/{workspace_id}/
        metadata.json     - repo, branch, timestamps, stats
        chat_history.json - full conversation with sources + traces

Neo4j/ChromaDB use workspace-scoped collections/labels so multiple
repos can coexist in the same database.
"""
import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict


# ── Storage directory ──
WORKSPACES_DIR = Path.home() / ".graphcoderag" / "workspaces"
WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Workspace:
    """A single workspace representing one repo + branch."""
    workspace_id: str
    repo: str                  # e.g., "pallets/click" or "S:/path/to/repo"
    branch: str = "main"
    status: str = "active"     # "active", "history"
    created_at: str = ""
    last_accessed: str = ""
    stats: Dict = field(default_factory=dict)
    chat_history: List[Dict] = field(default_factory=list)
    chromadb_collection: str = ""  # Scoped collection name
    neo4j_label_prefix: str = ""   # Scoped label prefix for Neo4j

    def __post_init__(self):
        if not self.created_at:
            self.created_at = _now()
        if not self.last_accessed:
            self.last_accessed = _now()
        if not self.chromadb_collection:
            self.chromadb_collection = f"ws_{self.workspace_id}"
        if not self.neo4j_label_prefix:
            self.neo4j_label_prefix = self.workspace_id


class WorkspaceManager:
    """Manages multiple workspaces with disk persistence."""

    def __init__(self):
        self._workspaces: Dict[str, Workspace] = {}
        self._active_id: Optional[str] = None
        self._load_all_from_disk()

    # ── Public API ──

    def create_workspace(self, repo: str, branch: str = "main") -> Workspace:
        """Create a new workspace for a repo + branch."""
        ws_id = _make_id(repo, branch)

        # If workspace already exists, just activate it
        if ws_id in self._workspaces:
            return self.switch_to(ws_id)

        ws = Workspace(
            workspace_id=ws_id,
            repo=repo,
            branch=branch,
            status="active",
        )
        self._workspaces[ws_id] = ws
        self._active_id = ws_id
        self._save_workspace(ws)
        return ws

    def switch_to(self, workspace_id: str) -> Optional[Workspace]:
        """Switch to a different workspace."""
        if workspace_id not in self._workspaces:
            return None

        # Save current workspace state before switching
        if self._active_id and self._active_id in self._workspaces:
            self._save_workspace(self._workspaces[self._active_id])

        # Activate the target workspace
        ws = self._workspaces[workspace_id]
        ws.status = "active"
        ws.last_accessed = _now()
        self._active_id = workspace_id
        self._save_workspace(ws)
        return ws

    def get_active(self) -> Optional[Workspace]:
        """Get the currently active workspace."""
        if self._active_id and self._active_id in self._workspaces:
            return self._workspaces[self._active_id]
        return None

    def get_all_workspaces(self) -> List[Workspace]:
        """Get all workspaces, sorted by last_accessed (most recent first)."""
        return sorted(
            self._workspaces.values(),
            key=lambda w: w.last_accessed,
            reverse=True,
        )

    def get_active_workspaces(self) -> List[Workspace]:
        """Get workspaces with status 'active'."""
        return [w for w in self.get_all_workspaces() if w.status == "active"]

    def get_history_workspaces(self) -> List[Workspace]:
        """Get workspaces with status 'history'."""
        return [w for w in self.get_all_workspaces() if w.status == "history"]

    def close_workspace(self, workspace_id: str):
        """Move a workspace to history (preserves data)."""
        if workspace_id in self._workspaces:
            ws = self._workspaces[workspace_id]
            ws.status = "history"
            self._save_workspace(ws)

            # If this was the active one, switch to another
            if self._active_id == workspace_id:
                active = self.get_active_workspaces()
                self._active_id = active[0].workspace_id if active else None

    def delete_workspace(self, workspace_id: str):
        """Permanently delete a workspace and its data."""
        if workspace_id in self._workspaces:
            del self._workspaces[workspace_id]
            ws_dir = WORKSPACES_DIR / workspace_id
            if ws_dir.exists():
                import shutil
                shutil.rmtree(ws_dir)

    def update_chat(self, message: dict):
        """Add a message to the active workspace's chat history."""
        ws = self.get_active()
        if ws:
            ws.chat_history.append(message)
            ws.last_accessed = _now()
            self._save_workspace(ws)

    def update_stats(self, stats: dict):
        """Update the active workspace's stats."""
        ws = self.get_active()
        if ws:
            ws.stats = stats
            self._save_workspace(ws)

    def get_collection_name(self) -> str:
        """Get the ChromaDB collection name for the active workspace."""
        ws = self.get_active()
        return ws.chromadb_collection if ws else "graphcoderag_default"

    # ── Persistence ──

    def _save_workspace(self, ws: Workspace):
        """Save a workspace to disk."""
        ws_dir = WORKSPACES_DIR / ws.workspace_id
        ws_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata (without chat to keep it small)
        meta = {
            "workspace_id": ws.workspace_id,
            "repo": ws.repo,
            "branch": ws.branch,
            "status": ws.status,
            "created_at": ws.created_at,
            "last_accessed": ws.last_accessed,
            "stats": ws.stats,
            "chromadb_collection": ws.chromadb_collection,
            "neo4j_label_prefix": ws.neo4j_label_prefix,
        }
        with open(ws_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # Save chat history separately (can be large)
        with open(ws_dir / "chat_history.json", "w", encoding="utf-8") as f:
            json.dump(ws.chat_history, f, indent=2, default=str)

    def _load_all_from_disk(self):
        """Load all workspaces from disk."""
        if not WORKSPACES_DIR.exists():
            return

        for ws_dir in WORKSPACES_DIR.iterdir():
            if not ws_dir.is_dir():
                continue
            meta_path = ws_dir / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                chat = []
                chat_path = ws_dir / "chat_history.json"
                if chat_path.exists():
                    with open(chat_path, "r", encoding="utf-8") as f:
                        chat = json.load(f)

                ws = Workspace(
                    workspace_id=meta["workspace_id"],
                    repo=meta["repo"],
                    branch=meta.get("branch", "main"),
                    status=meta.get("status", "history"),
                    created_at=meta.get("created_at", ""),
                    last_accessed=meta.get("last_accessed", ""),
                    stats=meta.get("stats", {}),
                    chat_history=chat,
                    chromadb_collection=meta.get("chromadb_collection", ""),
                    neo4j_label_prefix=meta.get("neo4j_label_prefix", ""),
                )
                self._workspaces[ws.workspace_id] = ws

                # Track the most recently active workspace
                if ws.status == "active":
                    if (self._active_id is None or
                            ws.last_accessed > self._workspaces.get(
                                self._active_id, ws).last_accessed):
                        self._active_id = ws.workspace_id

            except (json.JSONDecodeError, KeyError):
                continue

    def to_summary(self) -> dict:
        """Export a summary for UI rendering."""
        active = self.get_active_workspaces()
        history = self.get_history_workspaces()
        return {
            "active_id": self._active_id,
            "active_workspaces": [_ws_summary(w) for w in active],
            "history_workspaces": [_ws_summary(w) for w in history],
        }


# ── Helpers ──

def _make_id(repo: str, branch: str) -> str:
    """Create a deterministic workspace ID from repo + branch."""
    raw = f"{repo}@{branch}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _now() -> str:
    """ISO timestamp."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _ws_summary(ws: Workspace) -> dict:
    """Compact summary for UI rendering."""
    repo_name = ws.repo.rstrip("/").split("/")[-1] if "/" in ws.repo else os.path.basename(ws.repo)
    last_query = ""
    for msg in reversed(ws.chat_history):
        if msg.get("role") == "user":
            content = msg["content"]
            last_query = content[:35] + "..." if len(content) > 35 else content
            break

    # Time formatting
    elapsed = ""
    try:
        from datetime import datetime, timezone
        accessed = datetime.fromisoformat(ws.last_accessed)
        now = datetime.now(timezone.utc)
        delta = (now - accessed).total_seconds()
        if delta < 60:
            elapsed = "now"
        elif delta < 3600:
            elapsed = f"{int(delta/60)}m ago"
        elif delta < 86400:
            elapsed = f"{int(delta/3600)}h ago"
        elif delta < 172800:
            elapsed = "yesterday"
        else:
            elapsed = f"{int(delta/86400)}d ago"
    except Exception:
        elapsed = ""

    return {
        "id": ws.workspace_id,
        "repo": ws.repo,
        "repo_name": repo_name,
        "branch": ws.branch,
        "time": elapsed,
        "stats": ws.stats,
        "last_query": last_query or "No queries yet",
        "chat_count": len(ws.chat_history),
        "status": ws.status,
    }
