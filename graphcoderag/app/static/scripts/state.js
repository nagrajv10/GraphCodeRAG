/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — State Management + Event Bus (Phase 5)
   ═══════════════════════════════════════════════════════════ */

const AppState = {
  activeWorkspaceId: null,
  activeRepo: '',
  activeBranch: 'main',
  selectedFile: null,
  selectedNode: null,
  retrievalMode: 'hybrid',    // 'hybrid' | 'vector' | 'graph'
  contextFiles: [],
  workspaces: [],
  stats: { chunks: 0, functions: 0, edges: 0, classes: 0 },
  neo4jConnected: false,
};

/* ─── Event Bus ─── */
const Events = {
  _h: {},
  on(evt, fn) { (this._h[evt] ??= []).push(fn); },
  off(evt, fn) { this._h[evt] = (this._h[evt] || []).filter(f => f !== fn); },
  emit(evt, data) { (this._h[evt] || []).forEach(fn => fn(data)); },
};
