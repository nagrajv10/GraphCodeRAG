# GraphCodeRAG — Complete UI/UX & Backend Specification

> **Purpose of this document:** This is a pixel-level frontend specification and backend architecture guide. An AI or developer reading this document should be able to rebuild the entire GraphCodeRAG web application from scratch — the design system, every UI component, every interaction, every API endpoint, and how front and back connect — without ambiguity.

---

## 1. Project Overview

**What is GraphCodeRAG?**
A web-based developer assistant that ingests Python GitHub repositories, parses their code into an AST-aware knowledge graph, and lets developers ask natural language questions about the codebase. It uses hybrid retrieval (vector similarity search + knowledge graph traversal) to provide structurally complete context to an LLM for answer generation.

**What does the website do?**
The website is the interactive frontend (built with Streamlit or a custom HTML/JS app). It allows users to:
1. Add and ingest GitHub repositories (clone → parse → graph → embed → index)
2. Browse the repository's file structure and code
3. Visualize the knowledge graph of code dependencies
4. Chat with an AI assistant that retrieves context via hybrid retrieval
5. See retrieval traces showing how the system found its context (vector vs graph)
6. Switch between retrieval modes (Hybrid, Vector-only, Graph-only) for comparison

---

## 2. Design System

### 2.1 Color Palette

The entire UI uses a dark theme optimized for code readability. All colors are defined as CSS custom properties on `:root`.

| Token | Hex Value | Usage |
|-------|-----------|-------|
| `--bg-0` | `#0a0a0c` | Deepest background (activity bar, graph area) |
| `--bg-1` | `#101014` | Panel backgrounds (sidebar, chat, file explorer) |
| `--bg-2` | `#161619` | Elevated surfaces (code header, topbar) |
| `--bg-3` | `#1c1c21` | Modals, tooltips |
| `--border-1` | `rgba(255,255,255,0.05)` | Subtle dividers |
| `--border-2` | `rgba(255,255,255,0.08)` | Input borders |
| `--border-3` | `rgba(255,255,255,0.12)` | Hover state borders |
| `--text-0` | `#fafafa` | Primary text (headings, user input) |
| `--text-1` | `#d4d4d8` | Secondary text (body content, file names) |
| `--text-2` | `#a1a1aa` | Tertiary text (AI response body) |
| `--text-3` | `#71717a` | Muted text (labels, hints) |
| `--text-4` | `#3f3f46` | Dimmest text (timestamps, placeholders) |
| `--purple` | `#a855f7` | Primary accent — classes, active states, brand |
| `--purple-dim` | `rgba(168,85,247,0.12)` | Purple backgrounds (badges, active items) |
| `--blue` | `#60a5fa` | Functions, vector search indicators |
| `--blue-dim` | `rgba(96,165,250,0.12)` | Blue backgrounds |
| `--green` | `#4ade80` | Modules, graph search indicators, success states |
| `--green-dim` | `rgba(74,222,128,0.12)` | Green backgrounds |
| `--amber` | `#fbbf24` | Strings in code, merge/rank indicators, warnings |
| `--amber-dim` | `rgba(251,191,36,0.12)` | Amber backgrounds |
| `--coral` | `#f87171` | Notifications, errors, badges |

### 2.2 Typography

| Token | Font | Usage |
|-------|------|-------|
| `--font-body` | `'DM Sans', system-ui, sans-serif` | All UI text, labels, buttons, chat messages |
| `--font-mono` | `'Geist Mono', 'JetBrains Mono', monospace` | Code, file names, branch names, line numbers, source chips |

**Font sizes used throughout:**
- 9px: Badges, file badges, stat labels, chip text, trace step numbers
- 10px: Section labels, graph legend, timestamps, hints, mode toggles, branch tags
- 11px: File search, modal hints, progress steps, code body (11.5px)
- 12px: File items, tab text, branch selector, modal labels
- 12.5px: Chat messages (user and AI), textarea
- 13px: Sidebar card names, chat title, modal inputs, buttons
- 16-17px: Stat values (bold, tabular-nums)

### 2.3 Spacing & Layout

The entire app uses `box-sizing: border-box` with zero default margin/padding. The layout is a horizontal flexbox at the top level:

```
[Activity Bar 52px] [Sidebar 272px] [Main Area (flex:1)]
```

The main area is a vertical flexbox:
```
[Tab Bar 46px]
[Workspace (flex:1)]
  ├─ [File Explorer 224px]
  ├─ [Center Panel (flex:1)]
  │    ├─ [Graph Area (flex:1)]
  │    └─ [Code Pane 180px]
  └─ [Chat Panel 380px]
```

All panel widths are fixed pixel values except the center panel which takes remaining space. The entire body has `overflow: hidden` to prevent page scrolling — individual panels scroll independently.

### 2.4 Border Radius

- 3-4px: Small elements (code badges, branch tags, chip dots)
- 6-7px: Buttons, input fields, tooltip, file search
- 8-10px: Cards, code blocks, traces, graph legend, modal tabs
- 10-12px: Chat bubbles, sidebar cards, main input box
- 16px: Modal container
- 50%: Graph nodes (circles), notification badges

### 2.5 Transitions & Animations

All interactive elements use `transition: all 0.12-0.15s` for hover/active states. Specific animations:

- **Node pulse** (`npulse`): 2.5s ease-in-out infinite. Brightness oscillates between 1.0 and 1.3. Applied to "glowing" graph nodes (nodes discovered via graph traversal).
- **Status pulse** (`pulse`): 2s ease-in-out infinite. Opacity oscillates between 1.0 and 0.4. Applied to the green "Connected" status dot.
- **Modal entrance** (`modin`): 0.2s ease. Scales from 0.95 to 1.0 and translates Y from 10px to 0, with opacity 0 to 1.
- **Sidebar collapse**: width transitions from 272px to 0 over 0.25s with opacity 0.
- **Node hover**: `transform: scale(1.18)` with 0.2s transition.
- **Node selected**: `transform: scale(1.2)` with enhanced box-shadow glow.

---

## 3. Frontend Components — Detailed Specification

### 3.1 Activity Bar (leftmost column)

**Purpose:** Global navigation between app views, similar to VS Code's activity bar.

**Dimensions:** Width 52px, full viewport height. Background `--bg-0`. Right border 1px solid `--border-1`.

**Layout:** Vertical flexbox, centered items, 8px top padding, 2px gap between icons.

**Elements (top to bottom):**
1. **Logo mark** — 34×34px rounded square (border-radius 10px), purple gradient background (`linear-gradient(135deg, #7c3aed, #a855f7)`), white bold "G" letter centered inside. Margin-bottom 12px to separate from icons.
2. **Explorer icon** — Active by default. 38×38px clickable area, border-radius 10px. Active state: purple text color, purple-dim background. Toggles sidebar visibility.
3. **Search icon** — Inactive. Same dimensions. Future: opens global code search.
4. **Graph icon** — Inactive. Future: full-screen graph view.
5. **Divider** — 22px wide, 1px tall, `--border-1` color. 6px vertical margin.
6. **Evaluation icon** — Inactive. Future: evaluation dashboard.
7. **Ingest icon** — Inactive. Future: ingestion management view.
8. **Spacer** — `flex: 1` pushes remaining icons to bottom.
9. **History/Notifications icon** — Has a red notification badge (7×7px circle, coral background, 2px `--bg-0` border, positioned absolute top-right).
10. **Settings icon** — Bottom-most icon.

**Tooltip behavior:** Each icon has a `data-tip` attribute. On hover, a tooltip appears to the right of the icon (8px offset) showing the label. Tooltip: `--bg-3` background, `--text-1` color, 6px border-radius, 11px font size, 1px `--border-2` border.

**Interaction - sidebar toggle:** Clicking the Explorer icon (id `btn-sb`) toggles the `.collapsed` class on the sidebar element. When collapsed, sidebar width becomes 0, border disappears, opacity becomes 0.

### 3.2 Workspace Sidebar

**Purpose:** Shows ingested repository sessions — both active and historical.

**Dimensions:** Width 272px. Background `--bg-1`. Right border `--border-1`. Full height.

**Layout:** Vertical flexbox. Collapsible via `.collapsed` class.

**Sub-components:**

**3.2.1 Header**
- Padding 16px 18px. Bottom border `--border-1`.
- Left: "WORKSPACES" label (11px, bold 600, `--text-4`, uppercase, 1px letter-spacing)
- Right: Add button — 24×24px, border-radius 7px, dashed border (`--border-3`), "+" character. On hover: border and text turn purple.

**3.2.2 Section Labels**
- "Active Sessions" and "Recent History"
- 14px top padding, 6px bottom. 10px font, bold 600, `--text-4`, uppercase, 0.8px letter-spacing.

**3.2.3 Session Cards**
Each card represents an ingested repository session.

Structure:
```
[Card Container] — 10px 12px padding, 10px border-radius, 2px 10px margin
  ├─ [Row 1: dot + name + time]
  │    ├─ Color dot (8×8px circle, unique color per repo)
  │    ├─ Repo name (13px, font-weight 500, --text-1, truncate with ellipsis)
  │    └─ Timestamp (10px, --text-4, right-aligned)
  ├─ [Row 2: branch tag + stats] — left-padded 16px
  │    ├─ Branch tag (mono font, 10px, --text-3, 4px border-radius pill)
  │    └─ Stats string like "425 chunks · 85 edges" (10px, --text-4)
  └─ [Row 3: preview] — left-padded 16px
       └─ Last query preview (11px, --text-4, truncated)
```

**States:**
- Default: transparent background, transparent border.
- Hover: `rgba(255,255,255,0.02)` background.
- Active (selected): purple-dim background, subtle purple border (`rgba(168,85,247,0.18)`).

**Interaction:** Clicking a card sets it as active (removes active from all others, adds to clicked one). In production, this should load that repository's data into the main workspace.

**Backend data for each card:**
```json
{
  "repo": "pallets/click",
  "branch": "main",
  "color": "#a855f7",
  "chunks_count": 425,
  "edges_count": 85,
  "last_query": "How does invoke() handle...",
  "last_active": "2026-04-21T14:30:00Z",
  "status": "active"
}
```

### 3.3 Tab Bar (top of main area)

**Purpose:** Switch between multiple open repositories, like browser tabs.

**Dimensions:** Height 46px. Background `rgba(10,10,12,0.85)` with `backdrop-filter: blur(16px)`. Bottom border `--border-1`.

**Layout:** Horizontal flexbox. Tabs on left (flex:1, overflow-x auto), controls on right.

**3.3.1 Repository Tabs**
Each tab:
- Horizontal flex, center-aligned, 18px horizontal padding, 8px gap.
- Contains: color dot (8×8px), repo name (12px, weight 500), branch badge (mono, 10px, `--text-4`, pill background), close button (16×16px "×", opacity 0 by default, shown on hover).
- Active tab: white text, slightly brighter background, 2px purple bottom border (via `::after` pseudo-element).
- Inactive tab: `--text-3` color.
- Right border `--border-1` between tabs.

**3.3.2 Tab Add Button**
- "+" character, 36px wide, `--text-4`, opens the Add Repository modal.

**3.3.3 Controls (right side)**
- **Branch selector:** Flex row with git branch icon, branch name in mono font, dropdown arrow. Background `rgba(255,255,255,0.03)`, border `--border-2`, 7px radius. Clicking should open a branch dropdown (to be implemented).
- **Status pill:** Rounded pill (20px radius) with pulsing green dot + "Connected" text. Green-dim background, green text, subtle green border.

### 3.4 File Explorer (left panel of workspace)

**Purpose:** Browse the repository's Python files and see chunk counts per file.

**Dimensions:** Width 224px. Background `--bg-1` (inherits). Right border `--border-1`.

**3.4.1 Stats Bar**
Horizontal row of 4 stat boxes, each showing a metric about the ingested repo:

| Stat | Color | Label |
|------|-------|-------|
| Chunks count | `--purple` | CHUNKS |
| Functions count | `--blue` | FUNCS |
| Edges count | `--green` | EDGES |
| Classes count | `--amber` | CLASSES |

Each box: flex:1, 10px 6px padding, centered text, right border `--border-1`. Value: 17px bold font, tabular-nums. Label: 9px uppercase, `--text-4`.

**Backend data:** These values come from the ingestion pipeline after processing a repo:
```json
{
  "total_chunks": 425,
  "total_functions": 387,
  "total_edges": 85,
  "total_classes": 38
}
```

**3.4.2 File Header**
"FILES" label with count. 10px uppercase, `--text-4`, 10px 14px padding, bottom border.

**3.4.3 Search Input**
Full-width input field inside a 6px 10px padded container. Background `rgba(255,255,255,0.03)`, border `--border-1`, 6px radius, 11px font size. Focus: purple border. Placeholder: "Search files..."

**Interaction:** `input` event listener filters file items in real-time. Matches file name substring (case-insensitive). Non-matching items get `display: none`.

**3.4.4 File Items**
Each file row:
- Horizontal flex, 5px 14px padding, 7px gap.
- File icon (document emoji or SVG), file name (mono font, 11.5px), chunk count badge (9px, pill-shaped, `--text-4`).
- Hover: subtle background highlight, text becomes `--text-2`.
- Active: purple-dim background, purple text.
- Click: sets this item as active, deactivates all others.

**Backend data per file:**
```json
{
  "path": "click/core.py",
  "name": "core.py",
  "chunk_count": 24,
  "functions": ["invoke", "resolve_command", "parse_args", ...],
  "classes": ["Group", "Command", ...]
}
```

### 3.5 Knowledge Graph Visualization (center panel, top)

**Purpose:** Interactive visualization of the code dependency graph. Shows functions, classes, and modules as nodes, with edges representing CALLS, IMPORTS, and CONTAINS relationships.

**Dimensions:** Takes remaining vertical space in center panel (flex:1). Background: composite of radial gradients on `--bg-0`:
- Purple glow at 20% 30% position
- Blue glow at 80% 70% position
- Dot grid overlay via `::before` pseudo-element: `radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)` with 24px spacing.

**3.5.1 Graph Header (top-left)**
- "KNOWLEDGE GRAPH" label (10px uppercase, `--text-4`)
- Edge type filter pills: "All | Calls | Imports | Contains". Active pill has purple-dim background. Clicking a filter dims edges that don't match (opacity 0.05 for hidden, 1 for visible).

**3.5.2 Toolbar (top-right)**
4 square buttons: Zoom In (+), Zoom Out (−), Reset (⟲), Fullscreen (⛶). Each 30×30px, 7px radius, `--border-1` border, `--bg-0` at 70% opacity with blur(8px). Hover: brighter border and text.

**3.5.3 Nodes**
Three types, all circular with radial gradient backgrounds:

| Type | CSS class | Gradient | Border | Represents |
|------|-----------|----------|--------|------------|
| Function | `.node-f` | `#60a5fa → #2563eb` | `rgba(96,165,250,0.25)` | Python functions |
| Class | `.node-c` | `#c084fc → #7c3aed` | `rgba(192,132,252,0.25)` | Python classes |
| Module | `.node-m` | `#4ade80 → #16a34a` | `rgba(74,222,128,0.25)` | Python files/modules |

Node sizes vary (24-50px diameter) to indicate importance/centrality. Each node is absolutely positioned with `left` and `top` CSS properties. Nodes have a label below them (9px mono font, `--text-3`, absolutely positioned, centered via `translateX(-50%)`).

**Node states:**
- Default: 2px border, `box-shadow: 0 0 20px rgba(0,0,0,0.4)`.
- Hover: `transform: scale(1.18)`, z-index 10.
- Selected (`.sel`): `transform: scale(1.2)`, z-index 10, matching color border, colored glow shadow (24px spread, 0.4 opacity).
- Glowing (`.glow`): `npulse` animation, indicates nodes discovered via graph traversal.

**Interaction:** Click a node to select it. This should update the code pane below to show the code for that function/class. Deselects all other nodes.

**3.5.4 Edges**
SVG `<line>` elements drawn between nodes. Three types:

| Type | CSS class | Stroke | Style |
|------|-----------|--------|-------|
| Calls | `.edge-call` | `rgba(96,165,250,0.18)` | Solid, 1px |
| Imports | `.edge-import` | `rgba(74,222,128,0.14)` | Dashed (5 4), 1px |
| Contains | `.edge-contain` | `rgba(192,132,252,0.14)` | Solid, 1px |
| Highlighted | `.edge-hl` | `rgba(251,191,36,0.45)` | Solid, 1.8px, drop-shadow |

Highlighted edges indicate the retrieval path used for the current query. The SVG sits absolutely inside the graph container at z-index 1 (behind nodes at z-index 2).

**Edge filter interaction:** When a user clicks a filter pill (e.g., "Calls"), all edges that don't have the matching class get `opacity: 0.05`. "All" resets all edges to `opacity: 1`.

**3.5.5 Legend (bottom-left)**
Positioned absolute, bottom 12px left 14px. Background `rgba(10,10,12,0.75)` with blur. 8px radius, `--border-1` border. Contains 6 items: Function (blue dot), Class (purple dot), Module (green dot), Calls (blue line), Imports (green dashed line), Contains (purple line).

**Backend data for graph:**
The graph data comes from Neo4j. The API should return:
```json
{
  "nodes": [
    {"id": "Group", "type": "class", "file": "core.py", "line_start": 1247, "line_end": 1312, "size": 50},
    {"id": "invoke", "type": "function", "file": "core.py", "line_start": 1284, "line_end": 1295, "size": 36, "parent_class": "Group"},
    {"id": "utils.py", "type": "module", "file": "utils.py", "size": 38}
  ],
  "edges": [
    {"source": "Group", "target": "invoke", "type": "contains"},
    {"source": "invoke", "target": "resolve_command", "type": "calls"},
    {"source": "Option", "target": "utils.py", "type": "imports"}
  ]
}
```

**Production implementation:** Replace the static SVG with a JavaScript graph rendering library like D3.js force-directed layout or vis.js. Nodes should be draggable, the graph should support pan/zoom, and clicking a node should trigger an API call to load that entity's code.

### 3.6 Code Viewer (center panel, bottom)

**Purpose:** Shows the source code for the currently selected graph node or file.

**Dimensions:** Fixed height 180px, pinned to bottom of center panel. Top border `--border-1`.

**3.6.1 Code Header**
- Left side: Type badge (CLASS/FUNC, 9px uppercase, colored pill), file path (mono font, `--text-3`), line range badge (mono, 10px, subtle pill).
- Right side: "Selected: [name]" indicator (10px, `--text-4`).

**3.6.2 Code Body**
- Mono font, 11.5px, line-height 1.7. Scrollable overflow.
- Each line is a flex row: line number (40px wide, right-aligned, `--text-4` at 40% opacity, non-selectable) + code content.
- Highlighted lines (`.cl.hl`): purple-dim background with 2px left purple border.
- Hover: subtle `rgba(255,255,255,0.012)` background.

**Syntax highlighting classes:**
| Class | Color | Purpose |
|-------|-------|---------|
| `.kw` | `--purple` | Keywords (def, class, if, return, etc.) |
| `.fn` | `--blue` | Function names |
| `.st` | `--amber` | Strings |
| `.cm` | `--text-4` italic | Comments |
| `.pr` | `#f472b6` (pink) | Parameters (self, ctx, etc.) |
| `.op` | `--text-4` | Operators |

**Backend data:**
```json
{
  "file": "click/core.py",
  "entity_name": "Group",
  "entity_type": "class",
  "line_start": 1247,
  "line_end": 1312,
  "source_code": "class Group(MultiCommand):\n    ...",
  "highlighted_lines": [1284, 1285, 1286, 1287, 1288]
}
```

### 3.7 Chat Panel (right panel)

**Purpose:** The AI assistant interface. Users ask questions about the codebase, and the system retrieves context via hybrid retrieval and generates answers.

**Dimensions:** Width 380px. Background `--bg-1`. Left border `--border-1`.

**3.7.1 Chat Header**
- Left: Avatar (22×22px, purple gradient, "G" letter) + "AI Assistant" (13px, bold 600).
- Right: Mode toggle — "Hybrid | Vector" pills. Active pill: purple-dim background, purple text. Clicking switches the retrieval mode.

**3.7.2 Message Area**
Scrollable container, 16px padding, 16px gap between messages.

**User messages (`.msg-u`):**
- Right-aligned (`align-self: flex-end`), max-width 88%.
- Bubble: `rgba(255,255,255,0.04)` background, `--border-2` border, 12px radius (bottom-right 4px for tail effect).
- 12.5px font, `--text-1` color.
- Inline code: purple-dim background, purple text, mono font, 3px radius.

**AI messages (`.msg-a`):**
- Left-aligned, full width. Flex row: avatar (24×24px) + body.
- Body paragraphs: 12.5px, `--text-2` color, 7px bottom margin.
- Bold text: `--text-1`, weight 600.
- Inline code: same style as user messages.

**Code blocks in messages (`.msg-code`):**
- Dark background (`rgba(0,0,0,0.35)`), `--border-1` border, 8px radius.
- Header bar: file:line on left, function name on right (purple). Mono font, 10px, `--text-4`.
- Body: mono font, 11px, `--text-2`, whitespace-pre, horizontal scroll.
- Syntax highlighting uses same classes as code viewer.

**Source chips (`.chips`):**
- Row of small pills showing where context was retrieved from.
- Vector chips (`.chip-v`): blue-dim background, blue text, blue dot. Shows file:line and cosine similarity score.
- Graph chips (`.chip-g`): green-dim background, green text, green dot. Shows file:line and hop count.
- 9px mono font. Hoverable with brightness boost.

**Retrieval trace (`.trace`):**
- Collapsible section showing the retrieval pipeline steps.
- Header: clickable "▶ Retrieval trace — N chunks merged" (10px, `--text-4`). Arrow rotates 90° when open.
- Body (hidden by default, toggled via click):
  - Step 1 (Vector): blue numbered circle + "4 chunks found (cosine > 0.82)"
  - Step 2 (Graph): green numbered circle + "+3 chunks via CALLS edges (2 hops)"
  - Step 3 (Merge): amber numbered circle + "7 unique re-ranked by hybrid score"

**3.7.3 Chat Input Area**
Bottom of panel, 12px 16px padding, top border.

**Context chips row:** Shows currently active file context. Each chip: mono font, 10px, purple-dim background, purple text, with an "×" button to remove.

**Input box:**
- Flex row: textarea + send button.
- Container: `rgba(255,255,255,0.02)` background, `--border-2` border, 10px radius. Focus: purple border glow.
- Textarea: no background/border, 12.5px font, auto-resize on input (min 20px, max 80px height).
- Send button: 30×30px, 8px radius, purple gradient, white arrow icon. Hover: brightness 1.15.

**Hint text:** "Enter to send · Shift+Enter for newline · @file to add context" — 9px, `--text-4`, centered, 60% opacity.

**Chat interaction flow:**
1. User types message and presses Enter (or clicks Send).
2. Message appears as user bubble (right-aligned).
3. After 300ms delay, AI response appears with "Searching knowledge graph and vector store..." italic text.
4. In production: the frontend sends the query to the backend API, which runs the hybrid retriever, calls the LLM, and streams back the response.

**Backend API for chat:**
```
POST /api/query
Request:
{
  "query": "How does invoke() in Group handle subcommand routing?",
  "repo_id": "pallets-click-main",
  "mode": "hybrid",  // "hybrid" | "vector" | "graph"
  "top_k": 10,
  "graph_hops": 2,
  "context_files": ["core.py"]
}

Response:
{
  "answer": "Group.invoke() handles routing via two-phase resolution...",
  "sources": [
    {"file": "core.py", "line": 1284, "function": "invoke", "source_type": "vector", "score": 0.94},
    {"file": "core.py", "line": 1198, "function": "resolve_command", "source_type": "graph", "hops": 1},
    {"file": "core.py", "line": 1165, "function": "make_context", "source_type": "graph", "hops": 2}
  ],
  "retrieval_trace": {
    "vector_count": 4,
    "graph_count": 3,
    "merged_count": 7,
    "vector_threshold": 0.82
  },
  "code_snippets": [
    {"file": "core.py", "line_start": 1284, "line_end": 1295, "code": "def invoke(self, ctx):..."}
  ]
}
```

### 3.8 Add Repository Modal

**Purpose:** Allows users to add a new GitHub repository for ingestion.

**Trigger:** Clicking the "+" button in the sidebar header, or the "+" tab button.

**3.8.1 Overlay**
Full-screen fixed overlay. `rgba(0,0,0,0.6)` background with `backdrop-filter: blur(6px)`. Clicking the overlay (outside the modal) closes it.

**3.8.2 Modal Container**
- 500px wide, `--bg-3` background, `--border-2` border (heavier), 16px radius.
- Entrance animation: 0.2s, scale 0.95→1.0, translateY 10→0, opacity 0→1.
- Shadow: `0 24px 64px rgba(0,0,0,0.5)`.

**3.8.3 Modal Header**
"Add Repository" title (16px, bold 600) + close "×" button (28×28px, 7px radius, hover background).

**3.8.4 Modal Body**

**Source tabs:** "GitHub URL | Local Path" — toggled pills inside a container with 3px padding, 8px radius, subtle background and border. Active tab: purple-dim background.

**Form fields:**
1. **Repository URL** — Full-width text input. Placeholder: "https://github.com/owner/repo". Hint: "Supports any public GitHub repository".
2. **Branch (optional)** — Full-width text input. Placeholder: "main (default)". Hint: "Leave empty to use the default branch".

Input styling: `rgba(255,255,255,0.03)` background, `--border-2` border, 9px radius, 11px 14px padding, 13px font. Focus: purple border glow.

**3.8.5 Ingestion Progress (hidden by default)**

Shown after clicking "Ingest Repository". Contains:

1. **Progress bar:** 6px tall, `rgba(255,255,255,0.05)` track, purple gradient fill (`linear-gradient(90deg, #7c3aed, #a855f7)`). Width animates from 0% to 100%.

2. **Progress steps:** 5 sequential steps with status:
   - ○ Cloning repository
   - ○ Scanning Python files
   - ○ Parsing AST with Tree-sitter
   - ○ Building knowledge graph
   - ○ Generating embeddings

Step states: default (○, `--text-4`), active (◉, purple), done (✓, green).

**Simulation logic:** On click, an interval fires every 900ms, advancing through each step: marks current as active, marks previous as done, updates progress bar width. After all steps complete, waits 800ms then closes the modal and resets.

**3.8.6 Footer**
- Cancel button (ghost style): `--text-3`, `--border-2` border, no background. Hover: brighter.
- Ingest button (primary): white text on purple gradient. Hover: brightness 1.1.

**Backend for ingestion:**
```
POST /api/ingest
Request:
{
  "repo_url": "https://github.com/pallets/click",
  "branch": "main"
}

Response (Server-Sent Events for progress):
event: progress
data: {"step": "cloning", "percent": 10, "message": "Cloning repository..."}

event: progress
data: {"step": "scanning", "percent": 25, "message": "Found 142 Python files"}

event: progress
data: {"step": "parsing", "percent": 50, "message": "Parsed 425 AST chunks"}

event: progress
data: {"step": "graphing", "percent": 75, "message": "Built 85 edges in Neo4j"}

event: progress
data: {"step": "embedding", "percent": 95, "message": "Generating embeddings..."}

event: complete
data: {"repo_id": "pallets-click-main", "chunks": 425, "functions": 387, "classes": 38, "edges": 85}
```

---

## 4. Backend Architecture

### 4.1 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web Framework | FastAPI (Python) or Flask | REST API + SSE for progress streaming |
| Code Parsing | Tree-sitter (py-tree-sitter) | AST-aware code chunking |
| Knowledge Graph | Neo4j (via neo4j Python driver) | Store nodes/edges, Cypher queries |
| Vector Database | ChromaDB | Store embeddings, similarity search |
| Embedding Model | OpenAI text-embedding-3-small | Code chunk vectorization |
| LLM | Qwen2.5-Coder 7B (via Ollama) | Answer generation |
| LLM Judge | Gemini 2.5 Flash (via Google API) | Evaluation scoring |
| Frontend | HTML/CSS/JS (static) or Streamlit | User interface |

### 4.2 API Endpoints

#### 4.2.1 Repository Management

```
POST   /api/ingest              — Ingest a new repository (SSE progress)
GET    /api/repos                — List all ingested repositories
GET    /api/repos/{id}           — Get repo details (stats, files)
DELETE /api/repos/{id}           — Remove an ingested repository
GET    /api/repos/{id}/files     — List files with chunk counts
GET    /api/repos/{id}/file/{path} — Get file content with syntax highlighting data
```

#### 4.2.2 Graph Operations

```
GET    /api/repos/{id}/graph              — Get full graph (nodes + edges) for visualization
GET    /api/repos/{id}/graph/node/{name}  — Get specific node details + code
GET    /api/repos/{id}/graph/neighbors/{name}?hops=2 — Get N-hop neighborhood
```

#### 4.2.3 Query / Chat

```
POST   /api/query               — Run hybrid retrieval + LLM generation
POST   /api/query/retrieve-only — Run retrieval without LLM (for debugging)
```

#### 4.2.4 Evaluation

```
POST   /api/eval/run             — Run evaluation on SWE-bench instances
GET    /api/eval/results/{id}    — Get evaluation results
```

### 4.3 Ingestion Pipeline (Backend Flow)

When `POST /api/ingest` is called:

1. **Clone repository** — `git clone --depth 1 --branch {branch} {url}` into a temp directory.
2. **Scan Python files** — Walk directory, find all `.py` files, filter out `__pycache__`, `.git`, `node_modules`, test files (configurable).
3. **Parse AST** — For each `.py` file, use Tree-sitter to parse into AST. Walk the tree to extract:
   - Function definitions (name, args, body, docstring, line range)
   - Class definitions (name, bases, methods, docstring, line range)
   - Module-level code (imports, constants)
4. **Extract dependencies** — Second AST pass:
   - Import edges: `from X import Y` → edge from current module to X
   - Call edges: `foo.bar()` → edge from current function to `bar`
   - Containment edges: method inside class → CONTAINS edge
   - Inheritance edges: `class A(B)` → INHERITS edge
5. **Build graph** — Write nodes and edges to Neo4j using batch Cypher queries.
6. **Generate embeddings** — For each code chunk, call the embedding API. Batch requests (20-50 chunks per call) to minimize API calls.
7. **Index in ChromaDB** — Store each embedding with metadata (file, function name, class name, line range, chunk text).

### 4.4 Hybrid Retrieval (Backend Flow)

When `POST /api/query` is called:

1. **Embed query** — Convert the user's question to a vector using the same embedding model.
2. **Vector search** — Query ChromaDB for top-K (default 10) most similar code chunks. Each result includes file, function name, line range, similarity score.
3. **Graph expansion** — Take the function/class names from vector results as starting nodes. Run Cypher query in Neo4j:
   ```cypher
   MATCH (start)-[*1..{hops}]-(connected)
   WHERE start.name IN $start_names
   RETURN connected
   ```
   This returns all code entities within N hops.
4. **Merge and deduplicate** — Combine vector results and graph results. Remove duplicates by chunk ID. Assign hybrid score: `score = α × vector_similarity + (1-α) × (1 / (1 + hops))` where α is a tunable weight (default 0.6).
5. **Rank** — Sort by hybrid score descending. Take top K_final (default 7).
6. **Generate prompt** — Assemble the retrieved chunks into a structured prompt with the user's question.
7. **Call LLM** — Send prompt to Qwen2.5-Coder via Ollama API (`http://localhost:11434/api/generate`).
8. **Return response** — Send back the generated answer, source list, retrieval trace, and code snippets.

### 4.5 Database Schemas

**Neo4j Node Properties:**
```
(:Function {name, file, line_start, line_end, signature, docstring, parent_class})
(:Class {name, file, line_start, line_end, docstring, bases})
(:Module {name, file, line_count})
```

**Neo4j Edge Types:**
```
(:Function)-[:CALLS]->(:Function)
(:Module)-[:IMPORTS]->(:Function|Class)
(:Class)-[:CONTAINS]->(:Function)
(:Class)-[:INHERITS]->(:Class)
```

**ChromaDB Collection Schema:**
```
Collection: "{repo_id}_chunks"
Document: chunk source code text
Metadata: {
  "file": "core.py",
  "entity_name": "invoke",
  "entity_type": "function",  // "function" | "class" | "module"
  "line_start": 1284,
  "line_end": 1295,
  "parent_class": "Group",  // null if not a method
  "signature": "def invoke(self, ctx)",
  "docstring": "Invokes the command..."
}
Embedding: float[1536] from text-embedding-3-small
```

---

## 5. Interaction Map — Every Clickable Element

| Element | Action | What Happens |
|---------|--------|-------------|
| Explorer icon (activity bar) | Click | Toggle sidebar collapsed/expanded |
| Sidebar "+" button | Click | Open Add Repository modal |
| Sidebar card | Click | Set as active, load that repo's data into workspace |
| Tab | Click | Switch active tab, load that repo |
| Tab close "×" | Click | Close that tab, remove repo from workspace |
| Tab "+" button | Click | Open Add Repository modal |
| Branch selector | Click | Open branch dropdown (to be implemented) |
| File search input | Type | Filter file list in real-time by name substring |
| File item | Click | Set as active, load file's code in code viewer, update graph to show that file's nodes |
| Graph node | Click | Select node (deselect others), load node's code in code viewer, highlight connected edges |
| Graph edge filter | Click | Show only selected edge type, dim others to 0.05 opacity |
| Graph zoom +/−/reset | Click | Zoom in/out/reset graph view (to be implemented with D3.js) |
| Retrieval trace header | Click | Toggle trace body visibility, rotate arrow icon |
| Mode toggle (chat header) | Click | Switch retrieval mode: Hybrid, Vector-only |
| Graph mode filter | Click | Switch between All, Calls, Imports, Contains views |
| Source chip | Click | Highlight corresponding node in graph, scroll code viewer to that line |
| Chat textarea | Type | Auto-resize height. Enter sends, Shift+Enter adds newline |
| Send button | Click | Send message, append to chat, trigger AI response |
| Context chip "×" | Click | Remove that file from context filter |
| Modal tab | Click | Switch between GitHub URL and Local Path input |
| Modal "Ingest" button | Click | Start ingestion, show progress animation |
| Modal "Cancel" / "×" / overlay | Click | Close modal, reset progress state |

---

## 6. Files and Folder Structure for Production

```
graphcoderag/
├── frontend/
│   ├── index.html              — Main single-page application
│   ├── styles/
│   │   ├── variables.css       — CSS custom properties (colors, fonts)
│   │   ├── layout.css          — Activity bar, sidebar, panels, workspace grid
│   │   ├── components.css      — Cards, tabs, badges, pills, chips, traces
│   │   ├── graph.css           — Graph nodes, edges, legend, toolbar
│   │   ├── code.css            — Code viewer, syntax highlighting
│   │   ├── chat.css            — Chat messages, input, mode toggle
│   │   └── modal.css           — Modal overlay, form fields, progress
│   ├── scripts/
│   │   ├── app.js              — Main app initialization, event listeners
│   │   ├── sidebar.js          — Sidebar toggle, card selection, data loading
│   │   ├── tabs.js             — Tab switching, adding, closing
│   │   ├── files.js            — File list rendering, search filtering
│   │   ├── graph.js            — D3.js force graph rendering, zoom, pan, node click
│   │   ├── code-viewer.js      — Code display, syntax highlighting, line highlighting
│   │   ├── chat.js             — Message sending, streaming, markdown rendering
│   │   ├── modal.js            — Modal open/close, ingestion progress, SSE handling
│   │   └── api.js              — Fetch wrapper for all backend API calls
│   └── assets/
│       └── logo.svg
├── backend/
│   ├── main.py                 — FastAPI app entry point
│   ├── config.py               — Environment variables, model names, DB URIs
│   ├── routers/
│   │   ├── repos.py            — /api/repos endpoints
│   │   ├── graph.py            — /api/repos/{id}/graph endpoints
│   │   ├── query.py            — /api/query endpoints
│   │   └── eval.py             — /api/eval endpoints
│   ├── ingestion/
│   │   ├── file_scanner.py
│   │   ├── ast_parser.py
│   │   ├── code_chunker.py
│   │   └── dependency_extractor.py
│   ├── storage/
│   │   ├── graph_store.py      — Neo4j CRUD operations
│   │   └── vector_store.py     — ChromaDB operations
│   ├── retrieval/
│   │   ├── vector_retriever.py
│   │   ├── graph_retriever.py
│   │   └── hybrid_retriever.py
│   ├── generation/
│   │   ├── prompt_templates.py
│   │   └── generator.py
│   └── evaluation/
│       ├── metrics.py
│       ├── llm_judge.py
│       └── baseline_comparison.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## 7. Critical Implementation Notes

### 7.1 Graph Visualization
The current HTML uses static SVG lines and absolutely-positioned divs for nodes. For production, replace with D3.js force-directed layout. The backend provides node/edge JSON, D3 renders them as draggable circles with animated force simulation. Use `d3-zoom` for pan/zoom. When the user selects a file in the file explorer, filter the graph to show only nodes from that file plus their cross-file connections.

### 7.2 Code Syntax Highlighting
The current HTML uses manual `<span>` elements with CSS classes. For production, use a library like Highlight.js or Prism.js to auto-highlight Python code received from the backend. The backend should return raw source code; the frontend should handle highlighting client-side.

### 7.3 Chat Streaming
For production, the chat should use Server-Sent Events (SSE) or WebSocket to stream the LLM response token-by-token. The typing effect makes the UI feel responsive. The retrieval trace should appear first (before the LLM starts generating), showing the user what context was found.

### 7.4 Responsive Behavior
The current layout is desktop-only (fixed pixel widths). For mobile, the sidebar and file explorer should collapse into overlay drawers, the chat panel should become a full-screen view, and the graph should be independently scrollable/zoomable.

### 7.5 State Management
The frontend needs to track: currently selected repo, active file, selected graph node, chat history per repo, retrieval mode (hybrid/vector/graph), and ingestion status. For a simple app, use a global JavaScript object. For a complex app, consider a state management approach or framework.

### 7.6 Error Handling
All API calls should handle: network errors (show toast notification), 404 (repo not found), 500 (server error), rate limits (embedding API), Neo4j connection failures, and Ollama unavailable (LLM offline). Show user-friendly error messages in the chat panel or as toast notifications.
