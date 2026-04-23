# GraphCodeRAG — Frontend Feature Guide

> This document explains every feature of the GraphCodeRAG frontend in complete detail. It covers what each feature is, why it exists, exactly how it looks, how users interact with it, what happens on click/hover/type, and how it connects to the backend. An AI reading this document should be able to perfectly recreate the entire frontend.

---

## 1. Overall Layout & Design Philosophy

### What it is
The application is a single-page dark-themed IDE-like interface inspired by VS Code. The entire viewport is used — no scrolling on the body level. The interface is split into fixed panels that each scroll independently.

### Why this design
Developers spend their day inside VS Code and similar tools. By mirroring that layout paradigm — activity bar on the left, sidebar, tabbed workspace, panels — the interface feels instantly familiar. The dark theme reduces eye strain during extended code review sessions and provides high contrast for syntax highlighting.

### The layout structure
The page is one horizontal flexbox (the body) containing these elements left to right:

```
[Activity Bar 52px] [Sidebar 272px] [Main Area (flex:1)]
```

The Main Area is a vertical flexbox:
```
[Tab Bar 46px height]
[Workspace (flex:1)]
  ├─ [File Explorer 224px width]
  ├─ [Center Panel (flex:1)]
  │    ├─ [Graph Area (flex:1)]
  │    └─ [Code Pane 180px height]
  └─ [Chat Panel 380px width]
```

Critical CSS rules:
- `html, body { height: 100%; overflow: hidden }` — prevents page scrolling
- `body { display: flex }` — horizontal layout
- All panels use `flex-shrink: 0` with fixed widths except the center panel which uses `flex: 1`
- Each panel handles its own scrolling via `overflow-y: auto` on scrollable containers

---

## 2. Design System — Colors, Fonts, Spacing

### 2.1 Color System

The color palette uses a layered darkness approach. There are 4 background levels creating visual depth:

| Level | Variable | Hex | Where used |
|-------|----------|-----|------------|
| Deepest | `--bg-0` | `#0a0a0c` | Activity bar, graph area |
| Dark | `--bg-1` | `#101014` | Sidebar, file explorer, chat panel |
| Medium | `--bg-2` | `#161619` | Code header, elevated surfaces |
| Light | `--bg-3` | `#1c1c21` | Modals, tooltips |

Why layered backgrounds matter: When panels sit next to each other, subtle background differences create perceived depth. The activity bar at `--bg-0` (darkest) feels "behind" the sidebar at `--bg-1`, which feels "behind" the modal at `--bg-3`.

Accent colors have a purpose-driven mapping that is consistent across the entire UI:
- Purple (`#a855f7`): Brand color. Active states, selected items, class nodes in graph, primary buttons, code keywords, the logo. `--purple-dim` (`rgba(168,85,247,0.12)`) for subtle backgrounds.
- Blue (`#60a5fa`): Functions and vector search. Everywhere blue appears, it represents either a function in the code graph or a result from vector similarity search.
- Green (`#4ade80`): Modules and graph search. Green represents Python modules/files and results found via knowledge graph traversal.
- Amber (`#fbbf24`): Merge/rank step and strings. Used in retrieval trace merge step, string literals in syntax highlighting, and highlighted graph edges.
- Coral (`#f87171`): Alerts and notifications only.

This consistent color-coding eliminates the need for labels in many places. A blue chip in chat = vector search result. A green chip = graph traversal result. A blue node in the graph = function. A purple node = class.

### 2.2 Typography

Two font families used throughout:

DM Sans (`--font-body`): All interface text — labels, buttons, chat messages, headings. Geometric sans-serif, highly legible at small sizes (9-13px).

Geist Mono / JetBrains Mono (`--font-mono`): Everything code-related — file names, branch names, code blocks, line numbers, source chips. Creates instant visual distinction between "interface text" and "code text."

Font size reference:
- 9px: Badges, stat labels, chip text, trace numbers
- 10px: Section labels, graph legend, timestamps, hints, mode toggles
- 11px: File search, modal hints, progress steps
- 11.5px: Code body, file names in explorer
- 12px: File items, tab text, branch selector
- 12.5px: Chat messages (user and AI), textarea input
- 13px: Card names, chat title, buttons
- 16-17px: Stat values (bold, tabular-nums)

### 2.3 Border System

Three border opacity levels:
- `--border-1` (5% white opacity): Subtle panel dividers. Barely visible but creates separation.
- `--border-2` (8%): Input field borders, card borders. More visible for interactive elements.
- `--border-3` (12%): Hover states, dashed add-button borders. Most visible, indicates interactivity.

### 2.4 Text Opacity Hierarchy

Five levels from brightest to dimmest:
- `--text-0` (#fafafa): Primary headings, user input, most important content only.
- `--text-1` (#d4d4d8): Body text, file names, AI bold text.
- `--text-2` (#a1a1aa): AI response body, secondary descriptions.
- `--text-3` (#71717a): Labels, inactive tabs, graph node labels.
- `--text-4` (#3f3f46): Timestamps, placeholders, line numbers, hints. Dimmest.

### 2.5 Animation & Transition Reference

All interactive elements use `transition: all 0.12-0.15s` for hover/active states.

Named animations:
- `pulse`: 2s ease-in-out infinite. Opacity oscillates 1.0 → 0.4 → 1.0. Used on the green status dot.
- `npulse`: 2.5s ease-in-out infinite. Brightness oscillates 1.0 → 1.3 → 1.0. Used on graph nodes discovered via retrieval.
- `modin`: 0.2s ease. Scale 0.95 → 1.0, translateY 10px → 0, opacity 0 → 1. Used for modal entrance.
- Sidebar collapse: width 272px → 0 over 0.25s with opacity 1 → 0.

---

## 3. Feature 1: Activity Bar

### What it is
A 52px-wide vertical strip on the far left containing icon buttons for global app navigation.

### Why it exists
Persistent, always-visible navigation without consuming horizontal space. Same pattern as VS Code's activity bar.

### Visual details
- Background: `--bg-0`, right border: 1px `--border-1`
- Layout: vertical flexbox, centered items, 8px top padding, 2px gap

### Elements top to bottom

1. Logo mark — 34×34px rounded square (10px radius), purple gradient (`linear-gradient(135deg, #7c3aed, #a855f7)`), white bold "G" (14px), 12px bottom margin. Not clickable.

2. Explorer icon — Active by default. 38×38px, 10px radius. Active state: purple text, purple-dim background. Click: toggles sidebar visibility. ID: `btn-sb`.

3. Search icon — Inactive. Future: global code search.

4. Graph icon — Inactive. Future: full-screen graph view.

5. Divider — 22px wide, 1px tall, `--border-1`. 6px vertical margin.

6. Evaluation icon — Future: evaluation dashboard.

7. Ingest icon — Future: ingestion management.

8. Spacer — `flex: 1` pushes remaining icons to bottom.

9. Notifications icon — Has a red badge: 7×7px coral circle, 2px `--bg-0` border, positioned absolute top-6px right-6px.

10. Settings icon — Future: configuration panel.

### Icon states
- Default: `--text-4` (very dim), transparent background
- Hover: `--text-2`, `rgba(255,255,255,0.03)` background
- Active: `--purple` text, `--purple-dim` background

### Tooltip behavior
Each icon has `data-tip` attribute. CSS `::after` pseudo-element shows tooltip 8px to the right on hover. Tooltip: `--bg-3` background, `--text-1` text, 6px radius, 11px font, `--border-2` border.

### Sidebar toggle interaction
Click Explorer icon → JavaScript toggles `.collapsed` class on `#sidebar` → sidebar width animates to 0, opacity to 0 over 0.25s → main area expands automatically via flex.

---

## 4. Feature 2: Workspace Sidebar

### What it is
A 272px panel showing all ingested repository sessions, grouped into "Active Sessions" and "Recent History."

### Why it exists
Developers work across multiple repositories. The sidebar provides instant switching between codebases without re-ingesting. At-a-glance metadata (chunk count, edge count, branch, last query) helps users remember what each workspace contains.

### Visual details
Width: 272px, background `--bg-1`, right border `--border-1`, full height, vertical flexbox. Collapsible via `.collapsed` class.

### Sub-components

**Header:** Padding 16px 18px. "WORKSPACES" (11px, bold, `--text-4`, uppercase, 1px letter-spacing). "+" button (24×24px, dashed border `--border-3`, hover turns purple). Click opens Add Repository modal.

**Section labels:** "Active Sessions" / "Recent History". 14px top padding, 6px bottom. 10px bold uppercase, `--text-4`.

**Session cards** — Each card has 3 rows:

Row 1 (Identity): Color dot (8×8px, unique per repo) + repo name (13px, weight 500, `--text-1`, truncate with ellipsis) + timestamp (10px, `--text-4`).

Row 2 (Metadata): 16px left indent. Branch tag (mono, 10px, pill background) + stats like "425 chunks · 85 edges" (10px, `--text-4`).

Row 3 (Preview): 16px left indent. Last query preview, truncated (11px, `--text-4`).

Card states:
- Default: transparent background and border
- Hover: 2% white background
- Active: `--purple-dim` background, 18% purple border

Card click: removes `.active` from all cards, adds to clicked one. In production: loads that repo's data into all panels.

### Backend data shape
```json
{
  "id": "pallets-click-main",
  "repo": "pallets/click",
  "branch": "main",
  "color": "#a855f7",
  "chunks_count": 425,
  "edges_count": 85,
  "functions_count": 387,
  "classes_count": 38,
  "last_query": "How does invoke() handle...",
  "last_active": "2026-04-21T14:30:00Z",
  "status": "active"
}
```

---

## 5. Feature 3: Repository Tab Bar

### What it is
A 46px horizontal bar at the top of the main area with browser-style tabs for open repositories and controls on the right.

### Why it exists
Tabs provide instant switching between loaded repos without losing context. The branch selector and status pill give at-a-glance system state.

### Visual details
Height 46px, background: `rgba(10,10,12,0.85)` with `backdrop-filter: blur(16px)` (frosted glass effect). Bottom border `--border-1`.

### Tab design
Each tab: horizontal flex, 18px horizontal padding, 8px gap. Contains: color dot (8×8px) + repo name (12px, weight 500) + branch badge (mono, 10px, `--text-4`, pill) + close "×" (16×16px, hidden by default, shown on hover at opacity 1).

Tab states:
- Inactive: `--text-3` text, transparent background
- Hover: `--text-2` text, 1.5% white background, close button appears
- Active: `--text-0` (white) text, 3% white background, 2px purple bottom border via `::after`

"+" button: 36px wide, `--text-4`, hover brightens. Click: opens modal.

### Controls (right side)

Branch selector: git icon + "main" in mono font + dropdown arrow. Background 3% white, border `--border-2`, 7px radius. Hover: border brightens. Future: opens branch dropdown.

Status pill: 20px radius pill, pulsing green dot (5×5px, `pulse` animation) + "Connected" text. Green-dim background, green text, subtle green border. Indicates backend services are reachable.

---

## 6. Feature 4: File Explorer Panel

### What it is
A 224px panel listing all Python files in the repository with per-file chunk counts and a search filter.

### Why it exists
Lets developers browse repo structure before asking questions. Chunk count badges show file complexity at a glance. The search filter handles large repos (Django has hundreds of files).

### Stats bar
Four equal boxes at top showing aggregate metrics. Each has a colored value (17px bold, tabular-nums) and a label (9px uppercase, `--text-4`):
- Chunks (purple), Funcs (blue), Edges (green), Classes (amber)

These numbers update when switching repos. Backend source: `GET /api/repos/{id}`.

### Search input
Full-width, 3% white background, `--border-1` border, 6px radius. Focus: purple border.

Real-time filtering: JavaScript `input` event listener gets query, lowercases it, loops through all `.file-item` elements. If `.file-name` text includes the query, item stays visible. Otherwise `display: none`. Instant — no debounce needed.

### File items
Each: horizontal flex, 5px 14px padding. Document icon + file name (mono, 11.5px) + chunk count badge (9px, pill shape, `--text-4`).

States: default (`--text-3`) → hover (2% white bg, `--text-2`) → active (purple-dim bg, purple text).

Click: activates that file, deactivates others. In production: loads file code in code viewer, filters graph to that file's nodes.

---

## 7. Feature 5: Knowledge Graph Visualization

### What it is
An interactive visualization showing functions, classes, and modules as colored circular nodes connected by dependency edges. This is the centerpiece of the entire UI — it visualizes the knowledge graph that makes GraphCodeRAG unique.

### Why it exists
Standard RAG treats code as flat text. This graph shows users how code is structurally connected. When the AI retrieves context, the graph highlights the retrieval path, showing why certain code was included via dependency edges.

### Background design
Multiple layers create visual depth:
1. Base: `--bg-0` (deepest dark)
2. Purple radial glow at 20% left, 30% top (warm spot near class nodes)
3. Blue radial glow at 80% left, 70% top (visual balance)
4. Dot grid via `::before`: `radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)` at 24px spacing (blueprint/technical aesthetic)

### Node types

| Type | CSS class | Gradient | Represents |
|------|-----------|----------|------------|
| Function | `.node-f` | Blue (#60a5fa → #2563eb) | Python functions/methods |
| Class | `.node-c` | Purple (#c084fc → #7c3aed) | Python classes |
| Module | `.node-m` | Green (#4ade80 → #16a34a) | Python files |

Node sizes: 24-50px diameter. Larger = more important/central. Each has radial gradient (bright center at 35% 35% creates 3D sphere effect), 2px colored border, drop shadow, and a label below (9px mono, `--text-3`, centered, text-shadow for readability).

### Node states
- Default: As described above
- Hover: `scale(1.18)`, z-index 10, 0.2s transition
- Selected (`.sel`): `scale(1.2)`, z-index 10, border brightens to full color, colored glow shadow (24px, 40% opacity)
- Glowing (`.glow`): brightness animation 1.0 → 1.3, indicates nodes discovered via graph traversal

### Edge types

| Type | Class | Color | Style | Meaning |
|------|-------|-------|-------|---------|
| Calls | `.edge-call` | Blue 18% | Solid 1px | Function calls function |
| Imports | `.edge-import` | Green 14% | Dashed (5 4) 1px | Module imports from module |
| Contains | `.edge-contain` | Purple 14% | Solid 1px | Class contains method |
| Highlighted | `.edge-hl` | Amber 45% | Solid 1.8px + shadow | Retrieval path edge |

Edges are intentionally low-opacity — nodes are primary, edges are secondary context.

### Header elements
Top-left: "KNOWLEDGE GRAPH" label + edge type filter pills (Feature 13).
Top-right: Toolbar — Zoom In, Zoom Out, Reset, Fullscreen (30×30px buttons, blur backdrop).

### Legend
Bottom-left, absolute positioned, `--bg-0` at 75% opacity with blur. Six items: 3 node types (colored dots) + 3 edge types (colored lines).

### Node click interaction
1. All nodes lose `.sel`
2. Clicked node gains `.sel`
3. Production: updates code viewer with that entity's code, highlights connected edges
4. API call: `GET /api/repos/{id}/graph/node/{name}`

### Production upgrade
Replace static SVG + positioned divs with D3.js force-directed layout for: automatic positioning, drag, pan/zoom, dynamic edge routing, animated transitions.

### Backend data shape
```json
{
  "nodes": [
    {"id": "Group", "type": "class", "file": "core.py", "line_start": 1247, "line_end": 1312, "size": 50},
    {"id": "invoke", "type": "function", "file": "core.py", "line_start": 1284, "parent_class": "Group", "size": 36}
  ],
  "edges": [
    {"source": "Group", "target": "invoke", "type": "contains"},
    {"source": "invoke", "target": "resolve_command", "type": "calls"}
  ]
}
```

---

## 8. Feature 6: Code Viewer Panel

### What it is
A 180px-tall panel at the bottom of the center panel showing syntax-highlighted Python source code for the selected graph node or file.

### Why it exists
Creates a direct link between the abstract graph view and concrete code. When a user clicks a node (like `Group`), they immediately see its source code with the most relevant lines highlighted.

### Code header
Left: Type badge ("CLASS"/"FUNC", 9px uppercase, colored pill — purple for class, blue for function) + file path (mono, `--text-3`) + line range badge (mono, 10px, subtle pill).
Right: "Selected: [name]" indicator (10px, `--text-4`).

### Code body
Mono font, 11.5px, line-height 1.7, scrollable.
Each line: flex row with line number (40px, right-aligned, `--text-4` at 40% opacity, non-selectable) + code content (`white-space: pre`).

Highlighted lines (`.hl`): purple-dim background + 2px left purple border. Draws attention to the key lines.
Line hover: barely-perceptible 1.2% white background.

### Syntax highlighting

| Class | Color | Token type | Examples |
|-------|-------|-----------|----------|
| `.kw` | Purple | Keywords | def, class, if, return, None, with, as, not, is, or |
| `.fn` | Blue | Function names | invoke, resolve_command, __init__ |
| `.st` | Amber | Strings | """docstrings""", 'literals' |
| `.cm` | `--text-4` italic | Comments | # comment |
| `.pr` | Pink (#f472b6) | Parameters | self, ctx, value |
| `.op` | `--text-4` | Operators | =, **, + |

### Backend data
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

---

## 9. Feature 7: AI Chat Panel

### What it is
A 380px right panel providing a conversational AI assistant. Users ask natural language questions about the codebase; the system retrieves context via hybrid retrieval and generates grounded answers.

### Why it exists
The primary interaction point. The graph and code viewer are supporting tools — chat is where users get answers. Integrated into the IDE layout so users can reference the graph and code while reading responses.

### Chat header
Left: Purple gradient avatar (22×22px, "G" letter) + "AI Assistant" (13px, bold 600).
Right: Mode toggle (Feature 9).

### User messages
- Right-aligned, max-width 88%
- Bubble: 4% white background, `--border-2` border, 12px radius with flat 4px bottom-right (speech tail effect)
- 12.5px, `--text-1`. Inline code: purple-dim background, purple text, mono font

### AI messages
Flex row: avatar (24×24px purple gradient, "G") + body.
Body contains: paragraphs (12.5px, `--text-2`, bold text at `--text-1`), code blocks, source chips (Feature 11), retrieval trace (Feature 10).

### Code blocks in messages
Dark background (`rgba(0,0,0,0.35)`), `--border-1` border, 8px radius.
Header: file:line left, function name right (purple), mono 10px.
Body: mono 11px, line-height 1.6, `--text-2`, whitespace-pre, overflow-x auto.

### Chat input area

**Context chips:** Shows active file context. Each chip: mono 10px, purple-dim background, purple text, "×" close button. Prefix "Context:" label.

**Input box:** Flex row — textarea + send button. Container: 2% white bg, `--border-2` border, 10px radius. Focus: purple border glow.
- Textarea: no bg/border, 12.5px, auto-resize (min 20px, max 80px). Resize logic: on `input` event, reset height to 20px then set to `Math.min(scrollHeight, 80)`.
- Send button: 30×30px purple gradient, 8px radius, white arrow. Hover: brightness 1.15.
- Hint: "Enter to send · Shift+Enter for newline · @file to add context" (9px, `--text-4`, centered)

### Send interaction flow
1. User presses Enter (not Shift+Enter) or clicks send
2. Check input not empty (trim whitespace)
3. Create user message div, append to `.chat-msgs`
4. Convert backtick text to `<code>` elements via regex
5. Clear textarea, reset height to 20px
6. After 300ms: append AI placeholder "Searching knowledge graph and vector store..."
7. Scroll to bottom
8. Production: `POST /api/query` with query, repo_id, mode, context_files. Stream response via SSE.

### Backend API
```
POST /api/query
Request: { query, repo_id, mode, top_k, graph_hops, context_files }
Response: { answer, sources[], retrieval_trace, code_snippets[] }
```

---

## 10. Feature 8: Add Repository Modal

### What it is
A modal dialog for adding new GitHub repositories. Collects repo URL and branch, runs ingestion with visual progress.

### Why it exists
Repository ingestion is the entry point for the entire system. The modal provides a focused interface for this critical step. The progress tracker shows users what's happening during the multi-minute ingestion process.

### Triggers
Three entry points: sidebar "+" button, tab bar "+" button, any future "Add Repository" button.

### Overlay
Fixed, full viewport, `rgba(0,0,0,0.6)` with `backdrop-filter: blur(6px)`. Click outside modal closes it. Initially `display: none`, `.show` class enables `display: flex` with centering.

### Modal container
500px wide, `--bg-3` background, `--border-2` border, 16px radius. Entrance animation: 0.2s, scale 0.95→1, translateY 10→0, opacity 0→1. Shadow: `0 24px 64px rgba(0,0,0,0.5)`.

### Form fields
Source tabs: "GitHub URL | Local Path" pills. Active: purple-dim background.
URL input: placeholder "https://github.com/owner/repo", hint "Supports any public GitHub repository".
Branch input: placeholder "main (default)", hint "Leave empty to use default branch".
All inputs: 3% white bg, `--border-2` border, 9px radius, 13px font. Focus: purple border.

### Buttons
Cancel (ghost): `--text-3` text, border, no bg. Closes modal + resets progress.
Ingest (primary): white on purple gradient, weight 600. Starts ingestion.

### Close behavior
Three ways: "×" button, "Cancel", or overlay click. All call same reset function: removes `.show`, resets progress steps to default (○ symbol), resets progress bar to 0%.

---

## 11. Feature 9: Retrieval Mode Switching

### What it is
Toggle control in the chat header for switching between Hybrid, Vector-only, and Graph-only retrieval modes.

### Why it exists
Critical for the project's evaluation story. Users can compare: Hybrid (vector + graph, merged), Vector (standard RAG, cosine similarity only), Graph (graph traversal only). Demonstrates GraphCodeRAG's advantage by letting users see the difference.

### Design
Pill-shaped toggle. Active option: purple-dim background, purple text. Inactive: `--text-4`. 10px font, weight 500.

### Two separate toggles exist
1. Chat header: "Hybrid | Vector | Graph" — controls retrieval mode for queries
2. Graph area: "All | Calls | Imports | Contains" — controls visible edge types (Feature 13)

### Interaction
Click option → remove active class from siblings → add to clicked. In production: updates state variable sent with `POST /api/query` as `mode` parameter.

---

## 12. Feature 10: Retrieval Trace Viewer

### What it is
Collapsible section in AI responses showing the retrieval pipeline: vector found N chunks → graph added M more → merged to K unique.

### Why it exists
Transparency builds trust. Shows users exactly how context was found. Demonstrates hybrid retrieval advantage visually. Crucial for project evaluation.

### Design
Container: 1.5% white bg, `--border-1` border, 8px radius. Collapsed by default.

Header: clickable, arrow (▶, rotates 90° when open) + "Retrieval trace — N chunks merged" (10px, `--text-4`).

Body (hidden by default): Three steps with colored numbered circles (18×18px):
- Step 1 (blue): "Vector: 4 chunks (cosine > 0.82)"
- Step 2 (green): "Graph: +3 chunks via CALLS edges (2 hops)"
- Step 3 (amber): "Merged: 7 unique re-ranked by hybrid score"

### Interaction
Click header → toggle body `.open` class (display none ↔ block) → toggle arrow `.open` class (rotate 0° ↔ 90°).

---

## 13. Feature 11: Source Chips

### What it is
Small pill-shaped tags below AI responses showing exactly where each piece of retrieved code came from, with similarity scores or hop counts.

### Why it exists
Lets users trace AI answers back to specific code locations. Color-coding instantly shows which results came from vector search vs graph traversal.

### Design
Flex wrap row, 4px gap. Each chip: 9px mono font, 3px 8px padding, 5px radius, colored border.

Two types:
- Vector chips (`.chip-v`): blue-dim background, blue text, blue 12% border. Shows "file:line" + cosine similarity score (dimmed at 50% opacity). Example: "core.py:1284 0.94"
- Graph chips (`.chip-g`): green-dim background, green text, green 12% border. Shows "file:line" + hop count. Example: "core.py:1198 1-hop"

Hover: brightness 1.25 filter.

### Planned interaction
Click chip → highlight corresponding node in graph → scroll code viewer to that line.

---

## 14. Feature 12: Context File Tagging

### What it is
A row above the chat input showing which files are set as context scope for the next query.

### Why it exists
Large repos have hundreds of files. Context tagging lets users focus their question on specific files, improving retrieval precision. "Ask about invoke() but only look in core.py"

### Design
Row with "Context:" label (10px, `--text-4`) + context chips. Each chip: mono 10px, purple-dim background, purple text, purple 12% border, "×" close button (opacity 0.5, hover 1.0).

### Interaction
"×" click removes that file from context. In production: the `context_files` array in `POST /api/query` reflects the active chips. Future: typing "@" in the textarea should show a file autocomplete dropdown.

---

## 15. Feature 13: Edge Type Filtering

### What it is
Filter pills in the graph header that control which edge types are visible: All, Calls, Imports, Contains.

### Why it exists
A complex graph with all edge types visible can be overwhelming. Filtering lets users focus on one relationship type at a time — "show me only the call chain" or "show me only the import structure."

### Design
Pills inside a container with 2px padding, 6px radius, blur backdrop. Each pill: 3px 8px padding, 9px font, weight 500. Active (`.on`): purple-dim background, purple text.

### Interaction
Click a filter → remove `.on` from all → add to clicked. JavaScript then iterates all `.edge` SVG elements. If filter is "all": all edges get `opacity: 1`. Otherwise: edges with matching class (e.g., `.edge-call` for "Calls") get `opacity: 1`, all others get `opacity: 0.05` (nearly invisible but not gone).

The `data-f` attribute on each pill stores the filter type: "all", "call", "import", "contain".

---

## 16. Feature 14: Ingestion Progress Tracker

### What it is
An animated progress indicator inside the Add Repository modal that shows each step of the ingestion pipeline.

### Why it exists
Ingestion can take several minutes for large repos. Without progress feedback, users wonder if the system is frozen. The step-by-step tracker shows exactly what's happening and how far along the process is.

### Design
Hidden by default (`.ingest-prog` with `display: none`). Shown when ingestion starts (`.show` class adds `display: block`).

Progress bar: 6px tall, 3px radius. Track: 5% white. Fill: purple gradient (`linear-gradient(90deg, #7c3aed, #a855f7)`). Width transitions from 0% to 100% over the ingestion steps.

Five steps listed vertically:
1. Cloning repository
2. Scanning Python files
3. Parsing AST with Tree-sitter
4. Building knowledge graph
5. Generating embeddings

Step states:
- Pending: ○ symbol, `--text-4` color
- Active: ◉ symbol, purple color (`.active` class)
- Done: ✓ symbol, green color (`.done` class)

### Animation logic
When "Ingest Repository" is clicked:
1. Show progress section (add `.show`)
2. Start interval at 900ms
3. Each tick: mark previous step as done (✓, green), mark current step as active (◉, purple), update progress bar width to `(currentStep / totalSteps) * 100%`
4. After all steps: wait 800ms → close modal → reset everything

### Production implementation
Replace the timer-based simulation with Server-Sent Events (SSE) from the backend. The backend sends progress events as each pipeline stage completes:
```
event: progress
data: {"step": "parsing", "percent": 50, "message": "Parsed 425 AST chunks"}
```
The frontend updates the progress bar and step states in response to each event.

---

## 17. Cross-Feature Interactions

These are interactions where multiple features update simultaneously:

**Selecting a graph node → updates code viewer:** Clicking a function node should load that function's code in the code pane, update the header badge (FUNC/CLASS), path, and line range.

**Selecting a file → updates graph + code viewer:** Clicking a file in the explorer should filter the graph to show only nodes from that file (plus their cross-file connections), and load the file in the code viewer.

**Sending a chat query → updates graph + trace + chips:** When the AI responds, the graph should highlight nodes that were retrieved, glow nodes found via graph traversal, and highlight the traversal edges in amber.

**Clicking a source chip → updates graph + code viewer:** Should select that node in the graph, scroll the code viewer to that line, and highlight the relevant lines.

**Switching retrieval mode → affects next chat response:** Changes which retrieval strategy is used (hybrid/vector/graph), which changes the source chips and trace in the response.

**Switching sidebar workspace → updates everything:** Changes the active repo tab, file explorer, graph, code viewer, and loads that repo's chat history.

---

## 18. Complete JavaScript Event Map

| Element | Event | Handler |
|---------|-------|---------|
| `#btn-sb` (Explorer icon) | click | Toggle sidebar `.collapsed` class |
| `#btn-new` (Sidebar + button) | click | Open modal (add `.show` to `#modal`) |
| `#btn-tab` (Tab bar + button) | click | Open modal |
| `#btn-mx` (Modal × button) | click | Close modal + reset progress |
| `#btn-cancel` (Modal cancel) | click | Close modal + reset progress |
| `#modal` (Overlay) | click | If target is overlay (not modal), close + reset |
| `#btn-ingest` (Ingest button) | click | Show progress, start step animation interval |
| `.modal-tab` elements | click | Toggle `.active` among siblings |
| `#fsearch` (File search) | input | Filter `.file-item` visibility by name substring |
| `.file-item` elements | click | Toggle `.active` among siblings |
| `.gf-opt` elements (Edge filters) | click | Toggle `.on`, filter edge opacity by type |
| `.node` elements (Graph nodes) | click | Toggle `.sel` among siblings |
| `.mode-opt` elements (Mode toggle) | click | Toggle `.on` among siblings |
| `.trace-hd` (Trace header) | click | Toggle `.open` on body and arrow |
| `#btn-send` (Send button) | click | Call `send()` function |
| `#cinput` (Chat textarea) | keydown | If Enter (not Shift): prevent default, call `send()` |
| `#cinput` (Chat textarea) | input | Auto-resize: height = min(scrollHeight, 80) |

### The send() function
```
1. Get textarea value, trim whitespace
2. If empty, return (do nothing)
3. Create user message div with class "msg-u"
4. Set innerHTML to bubble div, replacing backtick text with <code> tags
5. Append to #chat-msgs
6. Clear textarea value, reset height to 20px
7. After 300ms timeout:
   a. Create AI message div with class "msg-a"
   b. Set innerHTML to avatar + body with searching placeholder
   c. Append to #chat-msgs
   d. Scroll to bottom
8. Scroll to bottom immediately
```
