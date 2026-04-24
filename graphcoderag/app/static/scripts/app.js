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
  Search.init();
  Settings.init();

  /* ─── Cross-Feature Wiring ─── */

  let switchCounter = 0;

  Events.on('workspace:switch', async (wsId) => {
    switchCounter++;
    const currentSwitch = switchCounter;
    
    AppState.activeWorkspaceId = wsId;
    const ws = AppState.workspaces.find(w => w.id === wsId);
    if (ws) {
      AppState.activeRepo = ws.repo;
      AppState.activeBranch = ws.branch || 'main';
      Events.emit('workspace:activated', wsId);
      Events.emit('stats:loaded', ws.stats || {});
    }

    // Clear UI before loading
    Events.emit('files:loaded', []);
    Events.emit('graph:loaded', { nodes: [], edges: [] });
    document.getElementById('code-body').innerHTML = '<div class="code-empty">Loading code viewer...</div>';
    document.getElementById('chat-msgs').innerHTML = '<div class="code-empty">Loading chat history...</div>';

    // Activate on backend
    await API.put(`/workspaces/${wsId}/activate`);

    // Reload panels from API
    const [filesData, graphData, chatData] = await Promise.all([
      API.get('/files'),
      API.get('/graph'),
      API.get('/chat/history'),
    ]);
    
    if (currentSwitch !== switchCounter) return;

    Events.emit('files:loaded', (filesData && filesData.files) || []);
    Events.emit('graph:loaded', (graphData && graphData.nodes) ? graphData : { nodes: [], edges: [] });
    
    document.getElementById('code-body').innerHTML = '<div class="code-empty">Select a node or file to view code</div>';
    
    const msgs = document.getElementById('chat-msgs');
    msgs.innerHTML = '';
    if (chatData && chatData.history && chatData.history.length > 0) {
      chatData.history.forEach(msg => {
        if (msg.role === 'user') {
          const m = document.createElement('div');
          m.className = 'msg-u';
          m.innerHTML = `<div class="msg-u-body">${Chat._escapeHTML ? Chat._escapeHTML(msg.content) : msg.content}</div>`;
          msgs.appendChild(m);
        } else {
          Chat._renderAIMessage(msg);
        }
      });
    } else {
      Events.emit('chat:init');
    }
  });

  Events.on('workspace:close', async (wsId) => {
    await API.del(`/workspaces/${wsId}`);
    AppState.workspaces = AppState.workspaces.filter(w => w.id !== wsId);
    Events.emit('workspaces:loaded', AppState.workspaces);
    
    // If we closed the active workspace, switch to another one or clear
    if (wsId === AppState.activeWorkspaceId) {
      const activeTabs = AppState.workspaces.filter(w => w.status === 'active');
      if (activeTabs.length > 0) {
        Events.emit('workspace:switch', activeTabs[0].id);
      } else {
        // Clear UI
        AppState.activeWorkspaceId = null;
        Events.emit('files:loaded', []);
        Events.emit('graph:loaded', { nodes: [], edges: [] });
        document.getElementById('code-body').innerHTML = '<div class="code-empty">Select a node or file to view code</div>';
        document.getElementById('chat-msgs').innerHTML = '';
      }
    }
  });

  Events.on('workspace:reload', () => loadWorkspaces());

  // History button toggles sidebar
  document.getElementById('ab-history').addEventListener('click', () => {
    const sidebar = document.getElementById('sidebar');
    if (sidebar.classList.contains('collapsed')) {
      sidebar.classList.remove('collapsed');
    }
  });

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

    if (AppState.activeWorkspaceId) {
      Events.emit('workspace:switch', AppState.activeWorkspaceId);
    } else {
      Events.emit('chat:init');
    }
  }

  loadInitialData();
})();
