/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — App Init + Cross-Feature Wiring (Phase 5)
   ═══════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // Initialize all modules
  Sidebar.init();
  Tabs.init();
  Files.init();
  Graph.init();
  CodeViewer.init();
  Chat.init();
  Modal.init();
  Evaluation.init();

  /* ─── Cross-Feature Wiring ─── */

  Events.on('workspace:switch', async (wsId) => {
    AppState.activeWorkspaceId = wsId;
    const ws = AppState.workspaces.find(w => w.id === wsId);
    if (ws) {
      AppState.activeRepo = ws.repo;
      AppState.activeBranch = ws.branch || 'main';
      Events.emit('workspace:activated', wsId);
      Events.emit('stats:loaded', ws.stats || {});
    }

    // Activate on backend
    await API.put(`/workspaces/${wsId}/activate`);

    // Reload panels from API
    const [filesData, graphData] = await Promise.all([
      API.get('/files'),
      API.get('/graph'),
    ]);
    Events.emit('files:loaded', (filesData && filesData.files) || []);
    Events.emit('graph:loaded', (graphData && graphData.nodes) ? graphData
      : { nodes: [], edges: [] });
  });

  Events.on('workspace:close', async (wsId) => {
    await API.del(`/workspaces/${wsId}`);
    AppState.workspaces = AppState.workspaces.filter(w => w.id !== wsId);
    Events.emit('workspaces:loaded', AppState.workspaces);
  });

  Events.on('workspace:reload', () => loadWorkspaces());

  /* ─── Initial Load ─── */

  async function loadWorkspaces() {
    const data = await API.get('/workspaces');
    if (data && data.workspaces && data.workspaces.length > 0) {
      AppState.workspaces = data.workspaces.map(w => ({
        ...w,
        color: w.color || (w.is_active ? '#a855f7' : '#3b82f6'),
        last_active: w.last_active || 'now',
        last_query: w.last_query || '',
        status: w.is_active ? 'active' : 'active',
      }));
      AppState.activeWorkspaceId = data.active_id || AppState.workspaces[0].id;
    } else {
      AppState.workspaces = [];
    }

    Events.emit('workspaces:loaded', AppState.workspaces);

    const active = AppState.workspaces.find(w => w.id === AppState.activeWorkspaceId)
      || AppState.workspaces[0];
    if (active) {
      AppState.activeWorkspaceId = active.id;
      AppState.activeRepo = active.repo;
      AppState.activeBranch = active.branch || 'main';
      Events.emit('workspace:activated', active.id);
      Events.emit('stats:loaded', active.stats || {});
    }
  }

  async function loadInitialData() {
    await loadWorkspaces();

    // Backend status check
    const statsData = await API.get('/stats');
    if (statsData) {
      AppState.neo4jConnected = statsData.neo4j;
      const pill = document.getElementById('status-pill');
      const text = document.getElementById('status-text');
      if (statsData.neo4j) {
        pill.classList.remove('offline');
        text.textContent = 'Connected';
      } else {
        pill.classList.add('offline');
        text.textContent = 'Neo4j Offline';
      }
      if (statsData.stats) Events.emit('stats:loaded', statsData.stats);
    } else {
      document.getElementById('status-text').textContent = 'Offline';
      document.getElementById('status-pill').classList.add('offline');
    }

    // Load files from API
    const filesData = await API.get('/files');
    Events.emit('files:loaded', (filesData && filesData.files) || []);

    // Load graph from API
    const graphData = await API.get('/graph');
    Events.emit('graph:loaded', (graphData && graphData.nodes)
      ? graphData : { nodes: [], edges: [] });

    // Load chat history
    const chatData = await API.get('/chat/history');
    if (chatData && chatData.history && chatData.history.length > 0) {
      // TODO: render existing chat history
    }

    // Init chat demo only if no real history
    Events.emit('chat:init');
  }

  loadInitialData();
})();
