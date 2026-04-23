# GraphCodeRAG UI Design Specification

## Reference Mockups

- `ui_mockup_v3.html` — Final interactive mockup (open in browser to explore)
- `ui_mockup_v2.html` — Earlier iteration (single-workspace)
- `ui_mockup.html` — First iteration (Streamlit dashboard style)

---

## 1. Design Philosophy

### Core Principle: "The Graph IS the Product"
The knowledge graph is GraphCodeRAG's core innovation — it must be front and center, not hidden behind a tab. Users should **see** how code entities connect, **click** nodes to inspect code, and **watch** retrieval paths light up during queries.

### Design Inspirations
| Source | What We Borrowed |
|--------|-----------------|
| VS Code / Cursor | 3-panel IDE layout, activity bar, file explorer, tab-based navigation |
| Obsidian | Graph as the primary navigation surface, interactive node exploration |
| Linear | Dark theme, glassmorphism, subtle gradients, clean typography |
| GitHub | Branch switcher dropdown, repo context display |
| Postman | Session history persistence, workspace collections |
| Chrome | Tab-based multi-session, closeable tabs, restore recent |

### Visual Identity
- **Color palette**: Dark background (#09090b) with purple accent (#7c3aed / #a855f7)
- **Typography**: Inter for UI text, JetBrains Mono for code
- **Node colors**: Blue (#3b82f6) = Functions, Purple (#7c3aed) = Classes, Green (#22c55e) = Modules
- **Retrieval colors**: Blue = Vector-found chunks, Green = Graph-traversed chunks, Yellow = Highlighted edges

---

## 2. Layout Architecture

The UI uses a **4-zone horizontal layout** that fills the entire viewport (no scrolling on the main page):

```
+----------+-------------+------+----------------------------+-----------+
| Activity | Workspace   | File |    Center Panel            |   Chat    |
|   Bar    | Sidebar     | Tree |  (Graph + Code Viewer)     |   Panel   |
|  48px    |   260px     |220px |       flex: 1              |   360px   |
|          | collapsible |      |                            |           |
+----------+-------------+------+----------------------------+-----------+
                         ^                                    ^
                    Top Bar with Repo Tabs + Branch Selector spans here
```

### 2.1 Activity Bar (Far Left — 48px wide)

**Purpose**: Quick-access navigation icons, always visible. Inspired by VS Code's activity bar.

**Icons (top to bottom)**:
1. **Explorer** (active by default) — toggles the Workspace Sidebar open/closed
2. **Search** — global code search across all ingested repos
3. **Graph** — focuses the center panel on full-screen graph view
4. *divider*
5. **Evaluation** — switches to evaluation results page
6. **Ingest** — switches to repository ingestion page
7. *spacer (pushes remaining to bottom)*
8. **History** — shows all past sessions (with red notification dot for unseen)
9. **Settings** — app configuration (API keys, Neo4j connection, model selection)

**Visual**: Dark background matching body (#09090b), icons are muted gray (#52525b), active icon gets purple highlight with rgba(124,58,237,0.1) background.

### 2.2 Workspace Sidebar (260px, collapsible)

**Purpose**: Session persistence and multi-repo management. This solves the core problem: "I want to switch repos without losing my previous work."

**Data Model — What is a "Workspace"?**
```
Workspace = {
    id: unique identifier,
    repo_name: "owner/repo" or local path,
    branch: "main",
    ingestion_state: {
        chunks_count: 425,
        edges_count: 85,
        files_count: 142,
        functions_count: 387,
        classes_count: 38
    },
    chat_history: [
        { role: "user", content: "How does invoke()..." },
        { role: "assistant", content: "The invoke() method...", sources: [...] }
    ],
    graph_state: {
        selected_node: "Group",
        zoom_level: 1.0,
        pan_offset: { x: 0, y: 0 }
    },
    last_accessed: "2026-04-15T10:30:00Z",
    status: "active" | "history"
}
```

**Sections**:

**Section 1: "Active Sessions"** — Currently open workspaces (shown as repo tabs in the top bar)
- Each card shows:
  - Colored icon (assigned per-repo, cycles through purple/blue/green/amber)
  - Repository name (e.g., "pallets/click")
  - Time indicator ("now", "2h ago")
  - Branch badge in monospace (e.g., `main`, `feature/pipeline`)
  - Stats summary ("425 chunks, 85 edges")
  - Last query preview (truncated, e.g., "Last: 'How does invoke() handle...'")
- Click a card to switch to that workspace (restores graph, code viewer, and chat)
- The active card has a purple left-border highlight

**Section 2: "Recent History"** — Previously closed workspaces
- Same card layout but with older timestamps ("yesterday", "2 days", "Apr 10")
- Click to re-open (restores full state from saved session)
- These are persisted to disk (JSON or SQLite) so they survive app restarts

**"+" Button**: Opens the "Add Repository" modal (see Section 5)

**Collapse behavior**: Clicking the Explorer icon in the Activity Bar toggles the sidebar. When collapsed, width transitions to 0px. The workspace data is still accessible from the Activity Bar's History icon.

### 2.3 Top Bar (44px height, spans center + right panels)

**Purpose**: Tab-based navigation between open repos + branch switching.

**Components (left to right)**:

**Repo Tabs** (like browser tabs):
- Each tab shows: colored dot + repo name + branch badge + close (x) button
- Active tab has a purple bottom border (2px solid #7c3aed)
- Close button appears on hover only (opacity transition)
- "+" button at the end to open a new repo
- Tabs are horizontally scrollable if there are many
- Switching tabs switches the entire workspace (graph, file tree, code viewer, chat — all update)

**Branch Selector** (right side of top bar):
- Shows current branch icon + name in monospace
- Clicking opens a dropdown overlay (see Section 4)
- Styled as a bordered pill: background rgba(255,255,255,0.04), border rgba(255,255,255,0.08)

**Compare Button**:
- Blue-styled pill: "Compare"
- Clicking opens a split-view comparison mode (see Section 6)

**Status Pill**:
- Shows connection state: green dot + "Connected" when Neo4j is reachable
- Red dot + "Disconnected" when Neo4j is unreachable

### 2.4 File Explorer Panel (220px wide)

**Purpose**: Browse the ingested repository structure with edge-count indicators.

**Components (top to bottom)**:

**Stats Row**: 4 mini-stat cells in a horizontal row
- Chunks (purple, 425), Functions (blue, 387), Edges (green, 85), Classes (amber, 38)
- Compact: value in 16px bold, label in 9px uppercase below
- These update dynamically when switching workspaces

**File List**:
- Header: "Files" with total count (142)
- Each file item shows:
  - File icon (muted)
  - Filename (e.g., "core.py")
  - Edge count badge on the right (e.g., "24") — shows how many graph edges originate from this file
- Files sorted by edge count (most connected files first — these are usually the most important)
- Active file (the one whose code is shown in the viewer) gets purple highlight
- Clicking a file:
  1. Shows the file's functions/classes in the code viewer
  2. Highlights the file's nodes in the graph
  3. Updates the file tree selection

### 2.5 Center Panel — Knowledge Graph + Code Viewer

This is the **hero section** of the UI, split vertically:
- **Top ~70%**: Interactive knowledge graph canvas
- **Bottom ~30%**: Code viewer pane (resizable via drag handle)

#### 2.5.1 Knowledge Graph Canvas

**Background**: Dark with subtle effects
- Base: #09090b
- Radial gradients: purple glow at top-left (30% opacity), blue glow at bottom-right (20% opacity)
- Dot grid overlay: 20px spacing, dots at rgba(255,255,255,0.04) — gives depth without distraction

**Graph Nodes**:
- **Functions**: Blue radial gradient (#60a5fa to #2563eb), 24-34px diameter
- **Classes**: Purple radial gradient (#c084fc to #7c3aed), 42-56px diameter (larger = more important)
- **Modules**: Green radial gradient (#4ade80 to #16a34a), 32-42px diameter
- All nodes: circular, with 3D-like radial gradient (highlight at top-left), subtle border (2px, 30% opacity of node color)
- Labels below each node: 9px JetBrains Mono, muted gray, text-shadow for readability
- Hover: scale(1.15) with z-index boost
- Selected: scale(1.2), brighter border, colored box-shadow glow (20px spread)
- Highlighted (part of retrieval path): pulsing brightness animation (2s ease-in-out infinite)

**Graph Edges**:
- **CALLS** edges: Solid blue line (rgba(96,165,250,0.2)), stroke-width 1
- **IMPORTS** edges: Dashed green line (rgba(74,222,128,0.15)), stroke-dasharray 4 3
- **CONTAINS** edges: Solid purple line (rgba(192,132,252,0.15)), stroke-width 1
- **Highlighted** edges (retrieval path): Yellow (rgba(250,204,21,0.4)), stroke-width 1.5
- All edges rendered as SVG `<line>` elements behind nodes (z-index 1 vs nodes z-index 2)

**Graph Controls** (top-right corner):
- Zoom In (+), Zoom Out (-), Reset View, Filter — each is a 28x28px rounded button
- Glassmorphism style: rgba(9,9,11,0.7) background with backdrop-filter blur(6px)

**Graph Legend** (bottom-left corner):
- Horizontal bar showing: Function (blue dot), Class (purple dot), Module (green dot), Calls (blue line), Imports (green dashed line), Contains (purple line)
- Same glassmorphism style as controls

**Interactions**:
- **Click a node**: Selects it, shows its source code in the code viewer below, highlights its edges
- **During a query**: The retrieval path lights up — vector-found nodes glow blue, graph-traversed nodes glow green, traversal edges turn yellow
- **Drag nodes**: Pan them around (implemented via mouse events or a graph library)
- **Scroll**: Zoom in/out
- **Double-click a node**: Opens its full source file in the code viewer

#### 2.5.2 Code Viewer Pane

**Purpose**: Shows the source code of the selected graph node.

**Header bar**:
- Badge: "CLASS" (purple) or "FUNC" (blue) indicating the node type
- File path in monospace (e.g., "click/core.py")
- Line range badge (e.g., "L1247-1312")
- Right-aligned: "Selected: {node_name}"

**Code display**:
- Line numbers (left-aligned, muted gray #27272a, non-selectable)
- Syntax-highlighted code:
  - Keywords (class, def, if, return, etc.): purple (#c084fc)
  - Function names: blue (#60a5fa)
  - Strings: amber (#fbbf24)
  - Comments: dark gray (#3f3f46), italic
  - Parameters: pink (#f472b6)
  - Operators: gray (#52525b)
- Highlighted lines (the specific function/class body): purple left border (2px solid #7c3aed) + subtle purple background (rgba(124,58,237,0.06))
- Scrollable vertically and horizontally

### 2.6 AI Chat Panel (360px wide, right side)

**Purpose**: Conversational interface for querying the codebase with full retrieval transparency.

#### Header
- Title: "AI Assistant" with star icon
- Mode toggle: "Hybrid" | "Vector" — switches retrieval strategy for the next query
  - Hybrid (default): purple highlight when active
  - This toggle is per-workspace (each workspace remembers its setting)

#### Chat Messages

**User messages**:
- Right-aligned, max-width 85%
- Light border bubble (rgba(255,255,255,0.06)), rounded corners (10px 10px 3px 10px — bottom-right is sharp)
- Code within messages uses purple monospace styling

**AI responses** (the key differentiation):
Each AI response contains these layered components:

1. **Avatar**: 24x24px rounded square, purple gradient, "G" letter
2. **Answer text**: Clean markdown-rendered explanation
3. **Code block**: Dark background with file path header and syntax-highlighted code
4. **Source chips**: Color-coded retrieval sources
   - **Blue chips** = found by vector search (show similarity score, e.g., "0.94")
   - **Green chips** = discovered by graph traversal (show hop count, e.g., "1-hop", "2-hop")
   - Clicking a chip highlights that node in the graph and scrolls the code viewer to it
5. **Retrieval trace** (expandable): Shows the 3-step retrieval process
   - Step 1 (blue circle): "Vector: 4 chunks found"
   - Step 2 (green circle): "Graph: +3 chunks via edges"
   - Step 3 (yellow circle): "Merged: 7 unique re-ranked"
   - This is the "show your work" feature — it proves the hybrid approach is doing something useful

#### Chat Input
- Textarea with placeholder "Ask about the codebase..."
- Purple gradient send button (26x26px rounded)
- Hint text below: "Enter to send, Shift+Enter for newline"

#### Chat Persistence
- Each workspace stores its own chat_history array
- Switching workspaces swaps the entire chat panel contents
- Chat history is saved to disk and restored on re-open

---

## 3. Page Views

While the "Explore" view (described above) is the main interface, two additional views are accessible from the Activity Bar:

### 3.1 Evaluation View

**Layout**: Full-width content area (no file tree or graph), scrollable.

**Components (top to bottom)**:

1. **Verdict Banner**:
   - Purple gradient background with lightning bolt icon
   - Bold headline: "Hybrid Retrieval Wins"
   - Subtitle: "+23% MRR improvement, +31% Recall@5 over vector-only baseline on 50 test cases"

2. **Metric Cards** (5 cards in a horizontal row):
   Each card shows:
   - Metric name (uppercase, small): MRR, RECALL@5, PRECISION@5, NDCG@5, LLM JUDGE
   - Large value (28px bold): 0.82, 0.76, 0.68, 0.79, 4.2/5
   - Delta text (green): "+23% vs baseline"
   - Two thin progress bars:
     - Top bar: colored gradient (unique color per metric) showing hybrid score
     - Bottom bar: gray (#3f3f46) showing baseline score
   - The visual contrast between the two bars instantly shows the improvement

3. **Legend**: "Hybrid (Vector + Graph)" with colored bar, "Vector Only (Baseline)" with gray bar

4. **Per-Query Breakdown Table**:
   - Columns: Query | MRR | Recall@5 | Method | Winner
   - Each row shows an individual test case
   - Winner column shows green checkmark for "Hybrid" wins, dash for ties
   - Method column shows purple "Hybrid" badge or gray "Both" badge

### 3.2 Ingest View

**Layout**: Centered content (max-width 720px), clean and minimal.

**Components (top to bottom)**:

1. **Header**: "Ingest Repository" title + subtitle

2. **Input Row**:
   - Large text input with link icon: "GitHub URL or local path..."
   - Purple "Ingest" button

3. **Pipeline Steps** (4 vertical cards):
   Each step shows:
   - Status icon: green checkmark (done), purple spinner (active), gray circle (pending)
   - Step name: File Scanner, AST Parser, Code Chunker, Knowledge Graph
   - Description: "Scanned repository structure"
   - Result count on the right: "142 files", "387 funcs, 38 classes", "425 chunks", "85 edges"
   - Done steps: green-tinted background with green border
   - Active step: purple-tinted background with animated spinner icon
   - Pending steps: neutral dark background

4. **Footer text**: "Vectors stored in ChromaDB, Graph stored in Neo4j, Embeddings: all-MiniLM-L6-v2"

---

## 4. Branch Switching Dropdown

**Trigger**: Clicking the branch selector pill in the top bar.

**Overlay position**: Anchored below the branch selector, right-aligned. Appears as a floating dropdown (280px wide).

**Styling**: Dark card (#18181b), 1px border, 10px border-radius, heavy box-shadow for depth.

**Components**:

1. **Search bar**: Text input with magnifying glass icon, "Search branches..."
   - Filters the branch list as user types

2. **Current section**:
   - Label: "CURRENT" (uppercase, tiny)
   - Shows current branch with checkmark icon on the right
   - Purple text color to indicate selected

3. **Other Branches section**:
   - Label: "OTHER BRANCHES"
   - Each branch shows: branch icon + name (monospace) + "X days ago" timestamp
   - Hover: subtle background highlight

4. **"Ingest new branch..." option** (bottom, separated by divider):
   - Blue text color
   - Clicking this triggers re-ingestion of the same repo on a different branch
   - Creates a NEW workspace (preserves the old branch's workspace)

**Behavior when switching branches**:
- If the branch was previously ingested: instantly switch (restore saved state)
- If the branch is new: show ingestion progress, then switch when done
- The old branch's workspace is preserved in "Recent History"

---

## 5. Add Repository Modal

**Trigger**: Clicking "+" in the Workspace Sidebar header, or "+" in the repo tabs.

**Overlay**: Centered modal (480px wide) with dark backdrop blur.

**Components**:

1. **Header**: "Add Repository" with close (x) button

2. **Tabs**: "GitHub URL" (default) | "Local Path"

3. **Fields (GitHub URL mode)**:
   - Repository URL: text input, placeholder "https://github.com/owner/repo"
   - Hint: "Supports any public GitHub repository"
   - Branch (optional): text input, placeholder "main (default)"
   - Hint: "Leave empty to use the default branch"

4. **Fields (Local Path mode)**:
   - Repository Path: text input, placeholder "/path/to/repo"
   - Hint: "Absolute path to a local Python repository"
   - Branch: auto-detected from git, shown as read-only

5. **Footer**: "Cancel" (ghost button) + "Ingest Repository" (purple primary button)

**Behavior**:
- Submitting creates a new workspace, opens it as an active tab, and starts ingestion
- The modal closes and the Ingest View shows pipeline progress
- When ingestion completes, automatically switches to Explore view

---

## 6. Compare Mode (Branch Comparison)

**Trigger**: Clicking the "Compare" button in the top bar.

**Layout**: Split-screen view with two workspaces side by side.

```
+---------------------------+---------------------------+
|     Branch A: main        |   Branch B: fix/parser    |
+---------------------------+---------------------------+
|                           |                           |
|   Graph (main)            |   Graph (fix/parser)      |
|                           |                           |
+---------------------------+---------------------------+
|   Code Viewer (main)      |   Code Viewer (branch)    |
+---------------------------+---------------------------+
```

**Features**:
- Side-by-side graphs showing the same repo on different branches
- Nodes that exist in both branches: normal color
- Nodes added in Branch B: highlighted green border (new code)
- Nodes removed in Branch B: highlighted red border (deleted code)
- Nodes modified: highlighted yellow border (changed code)
- Shared chat panel at the bottom: "What changed between main and fix/parser-bug?"

**Use case**: Understanding what a branch changed in terms of code structure and dependencies, not just file diffs.

---

## 7. Data Persistence Architecture

### What Gets Saved Per Workspace
```
~/.graphcoderag/workspaces/
  {workspace_id}/
    metadata.json        # repo, branch, timestamps, stats
    chat_history.json    # full conversation with sources
    graph_state.json     # selected node, zoom, pan position
    retrieval_cache/     # cached retrieval results for repeated queries
```

### Session Lifecycle
1. **Create**: User adds a repo via modal or "+" button -> new workspace created
2. **Active**: Workspace is open as a tab, chat and graph are interactive
3. **Backgrounded**: User switches to another tab -> state is saved but not destroyed
4. **Closed**: User closes the tab -> workspace moves to "Recent History" (still persisted)
5. **Restored**: User clicks a history card -> workspace reopens with full state
6. **Deleted**: User explicitly deletes from history -> files removed from disk

### What Gets Shared Across Workspaces
- Neo4j graph data (stays in the database, tagged by repo+branch)
- ChromaDB vector data (stays in the collection, tagged by repo+branch)
- App settings (API keys, model preferences, UI preferences)

---

## 8. Implementation Notes for Streamlit

### Streamlit Limitations & Workarounds

| Design Feature | Streamlit Approach |
|----------------|-------------------|
| Activity Bar | Use `st.sidebar` with icon buttons at the top |
| Workspace Sidebar | Nested in `st.sidebar` below activity icons |
| Repo Tabs | `st.tabs()` — one tab per active workspace |
| Branch Dropdown | `st.selectbox()` or `st.popover()` (Streamlit 1.33+) |
| Knowledge Graph | `streamlit-agraph` component (interactive nodes + edges) |
| Code Viewer | `st.code()` with syntax highlighting |
| Chat Interface | `st.chat_message()` + `st.chat_input()` |
| Mode Toggle | `st.toggle()` or `st.radio()` horizontal |
| Stats Cards | `st.metric()` in `st.columns()` |
| Pipeline Steps | `st.status()` with expandable steps |
| Modal | `st.dialog()` (Streamlit 1.34+) or `st.popover()` |
| Compare Mode | Two `st.columns()` side by side |
| Persistence | `st.session_state` + JSON files on disk |

### Recommended Libraries
```
streamlit>=1.34.0          # For st.dialog, st.popover
streamlit-agraph>=0.0.45   # Interactive graph visualization
plotly>=5.18.0             # Evaluation charts (optional alternative to bars)
streamlit-extras           # Metric cards, colored headers
```

### Session State Structure
```python
st.session_state = {
    "workspaces": {
        "ws_001": {
            "repo": "pallets/click",
            "branch": "main",
            "stats": {"chunks": 425, "edges": 85, ...},
            "chat_history": [...],
            "graph_state": {"selected": "Group", ...},
            "last_accessed": "2026-04-15T10:30:00Z"
        },
        "ws_002": { ... }
    },
    "active_workspace": "ws_001",
    "open_tabs": ["ws_001", "ws_002"],
    "history": ["ws_003", "ws_004", "ws_005"],
    "settings": { ... }
}
```

### Key Streamlit Patterns

**Tab Switching (preserves state)**:
```python
# Each tab renders from its workspace's saved state
tabs = st.tabs([ws["repo"] for ws in open_workspaces])
for tab, ws in zip(tabs, open_workspaces):
    with tab:
        render_workspace(ws)  # Graph + Code + Chat from ws state
```

**Chat Persistence**:
```python
# Messages stored per-workspace
ws = st.session_state.workspaces[active_id]
for msg in ws["chat_history"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("sources"):
            render_sources(msg["sources"])  # Color-coded chips

if prompt := st.chat_input("Ask about the codebase..."):
    ws["chat_history"].append({"role": "user", "content": prompt})
    response = hybrid_retrieve_and_generate(prompt, ws)
    ws["chat_history"].append({"role": "assistant", ...})
    save_workspace(ws)  # Persist to disk
```

**Graph Visualization (streamlit-agraph)**:
```python
from streamlit_agraph import agraph, Node, Edge, Config

nodes = [
    Node(id="Group", label="Group", size=30, color="#7c3aed", shape="dot"),
    Node(id="invoke", label="invoke()", size=20, color="#3b82f6", shape="dot"),
    ...
]
edges = [
    Edge(source="Group", target="invoke", label="CONTAINS", color="#c084fc"),
    Edge(source="invoke", target="resolve_cmd", label="CALLS", color="#60a5fa"),
    ...
]
config = Config(
    width="100%", height=400, directed=True,
    physics=True, hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#fbbf24",
    backgroundColor="#09090b"
)
selected = agraph(nodes=nodes, edges=edges, config=config)
if selected:
    show_code_viewer(selected)  # Update code pane
```

---

## 9. User Flows

### Flow 1: First-Time User
1. Opens app -> sees empty workspace sidebar + "Add Repository" prompt
2. Enters GitHub URL -> clicks "Ingest Repository"
3. Watches pipeline progress (File Scanner -> AST Parser -> Chunker -> Graph Builder)
4. Pipeline completes -> auto-switches to Explore view
5. Sees the knowledge graph populated, file tree on left, chat on right
6. Asks first question -> sees retrieval trace showing how hybrid retrieval worked

### Flow 2: Switching Between Repos
1. User is exploring `pallets/click` on `main` branch
2. Clicks "+" tab -> enters `scikit-learn/sklearn` URL
3. New tab opens, ingestion starts for sklearn
4. While waiting, user clicks back to the `click` tab -> full state preserved
5. Sklearn ingestion completes -> user switches to sklearn tab
6. Asks a question about sklearn -> chat is separate from click's chat
7. Clicks back to `click` tab -> click's chat history is still there

### Flow 3: Comparing Branches
1. User is on `pallets/click` branch `main`
2. Clicks branch dropdown -> selects `fix/parser-bug`
3. System checks: was this branch ingested before?
   - Yes: instantly restore that workspace
   - No: prompt to ingest -> new workspace created
4. Now user has two workspaces: `click/main` and `click/fix/parser-bug`
5. Clicks "Compare" -> split-screen view showing both graphs
6. Asks: "What functions changed between main and fix/parser-bug?"

### Flow 4: Returning to a Previous Session
1. User opens app the next day
2. Workspace sidebar shows "Recent History" with yesterday's sessions
3. Clicks `django/django` card from yesterday
4. Full state restored: graph, code viewer, chat history with all previous Q&A
5. User continues asking questions where they left off

---

## 10. Color Reference

### Backgrounds
| Element | Color |
|---------|-------|
| Body / main background | #09090b |
| Panel backgrounds | rgba(255,255,255,0.01) |
| Cards / elevated surfaces | #18181b |
| Hover states | rgba(255,255,255,0.03) |
| Active/selected | rgba(124,58,237,0.08) |
| Borders | rgba(255,255,255,0.06) |

### Text
| Element | Color |
|---------|-------|
| Primary text | #fafafa |
| Secondary text | #d4d4d8 |
| Muted text | #a1a1aa |
| Subtle text | #71717a |
| Disabled text | #52525b |
| Ghost text | #3f3f46 |
| Invisible text (line numbers) | #27272a |

### Accents
| Element | Color |
|---------|-------|
| Primary accent | #7c3aed (purple 600) |
| Primary light | #a855f7 (purple 500) |
| Primary faint | #c084fc (purple 400) |
| Functions | #3b82f6 (blue 500) / #60a5fa (blue 400) |
| Classes | #7c3aed (purple 600) / #c084fc (purple 400) |
| Modules | #22c55e (green 500) / #4ade80 (green 400) |
| Success | #4ade80 (green 400) |
| Warning | #fbbf24 (amber 400) |
| Error | #ef4444 (red 500) |
| Highlight (retrieval path) | #facc15 (yellow 400) |

### Syntax Highlighting (Code Viewer)
| Token | Color |
|-------|-------|
| Keywords (def, class, if, return) | #c084fc |
| Function names | #60a5fa |
| Strings | #fbbf24 |
| Comments | #3f3f46 (italic) |
| Parameters | #f472b6 |
| Operators | #52525b |
| Decorators | #4ade80 |
