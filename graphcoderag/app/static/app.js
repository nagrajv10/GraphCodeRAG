/**
 * GraphCodeRAG — Frontend Application Logic v2
 * ==============================================
 * Full interactive web app connected to FastAPI backend.
 * Handles: workspace management, chat, graph rendering,
 * file browsing, activity bar navigation, code preview.
 */

const API = '';

// ═══════════════════════════════════════════════════════════════
//  STATE
// ═══════════════════════════════════════════════════════════════
let state = {
  workspaces: [],
  activeId: null,
  stats: {},
  files: [],
  graphData: { nodes: [], edges: [] },
  chatHistory: [],
  loading: false,
  neo4jOk: false,
  selectedFile: null,
  activePanel: 'explorer',  // 'explorer', 'search', 'graph'
};

// ═══════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', async () => {
  bindEvents();
  await loadAll();
});

async function loadAll() {
  await Promise.all([
    loadWorkspaces(),
    loadStats(),
    loadFiles(),
    loadGraph(),
    loadChatHistory(),
  ]);
  render();
}

// ═══════════════════════════════════════════════════════════════
//  API CALLS
// ═══════════════════════════════════════════════════════════════

async function loadWorkspaces() {
  try {
    const r = await fetch(`${API}/api/workspaces`);
    const data = await r.json();
    state.workspaces = data.workspaces || [];
    state.activeId = data.active_id;
  } catch (e) { console.error('loadWorkspaces:', e); }
}

async function loadStats() {
  try {
    const r = await fetch(`${API}/api/stats`);
    const data = await r.json();
    state.stats = data.stats || {};
    state.neo4jOk = data.neo4j;
  } catch (e) { console.error('loadStats:', e); }
}

async function loadFiles() {
  try {
    const r = await fetch(`${API}/api/files`);
    const data = await r.json();
    state.files = data.files || [];
  } catch (e) { console.error('loadFiles:', e); }
}

async function loadGraph() {
  try {
    const r = await fetch(`${API}/api/graph`);
    state.graphData = await r.json();
  } catch (e) { console.error('loadGraph:', e); }
}

async function loadChatHistory() {
  try {
    const r = await fetch(`${API}/api/chat/history`);
    const data = await r.json();
    state.chatHistory = data.history || [];
  } catch (e) { console.error('loadChatHistory:', e); }
}

async function sendChat(message) {
  if (!message.trim() || state.loading) return;
  state.loading = true;

  // Disable send button
  const sendBtn = document.getElementById('btn-send');
  if (sendBtn) { sendBtn.disabled = true; sendBtn.style.opacity = '0.5'; }

  // Add user message immediately
  state.chatHistory.push({ role: 'user', content: message });
  renderChat();

  // Show typing indicator
  const typingEl = addTypingIndicator();

  try {
    const r = await fetch(`${API}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });
    const data = await r.json();

    if (r.ok) {
      state.chatHistory.push(data.response);
    } else {
      state.chatHistory.push({ role: 'assistant', content: `Error: ${data.detail || 'Unknown error'}`, trace: {} });
    }
  } catch (e) {
    state.chatHistory.push({ role: 'assistant', content: `Network error: ${e.message}`, trace: {} });
  }

  typingEl?.remove();
  state.loading = false;
  if (sendBtn) { sendBtn.disabled = false; sendBtn.style.opacity = '1'; }
  renderChat();
}

async function ingestRepo(url, branch) {
  const btn = document.getElementById('btn-ingest');
  const origText = btn?.textContent;
  try {
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="typing-dot">●</span> Ingesting...'; }
    showNotification('⏳ Starting ingestion...', 'info');

    const r = await fetch(`${API}/api/workspaces`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_url: url, branch: branch || 'main' }),
    });
    const data = await r.json();

    if (r.ok) {
      document.getElementById('modal-new').style.display = 'none';
      showNotification('✅ Repository ingested successfully!', 'success');
      await loadAll();
    } else {
      showNotification(`❌ ${data.detail || 'Ingestion failed'}`, 'error');
    }
  } catch (e) {
    showNotification(`❌ Network error: ${e.message}`, 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = origText || 'Ingest Repository'; }
  }
}

async function switchWorkspace(wsId) {
  try {
    await fetch(`${API}/api/workspaces/${wsId}/activate`, { method: 'PUT' });
    await loadAll();
  } catch (e) { console.error('switchWorkspace:', e); }
}

async function closeWorkspace(wsId) {
  try {
    await fetch(`${API}/api/workspaces/${wsId}`, { method: 'DELETE' });
    await loadAll();
  } catch (e) { console.error('closeWorkspace:', e); }
}

// ═══════════════════════════════════════════════════════════════
//  RENDER
// ═══════════════════════════════════════════════════════════════

function render() {
  renderWorkspaces();
  renderTabs();
  renderStats();
  renderFiles();
  renderGraph();
  renderChat();
  renderStatusPill();
  renderCodePane();
}

// ── Workspaces Sidebar ──
function renderWorkspaces() {
  const container = document.getElementById('ws-list');
  if (!container) return;

  const active = state.workspaces.filter(w => w.status === 'active');
  const history = state.workspaces.filter(w => w.status === 'history');
  const colors = ['purple', 'blue', 'green', 'amber'];

  let html = '';
  if (active.length) {
    html += '<div class="ws-section-label">Active Sessions</div>';
    active.forEach((ws, i) => {
      const isActive = ws.id === state.activeId;
      const color = colors[i % colors.length];
      const chunks = ws.stats?.chunks || 0;
      const edges = ws.stats?.edges || 0;
      html += `
        <div class="ws-card ${isActive ? 'active' : ''}" onclick="switchWorkspace('${ws.id}')">
          <div class="ws-card-top">
            <div class="ws-card-icon ${color}">&#9672;</div>
            <div class="ws-card-name">${esc(ws.repo_name || ws.repo)}</div>
            <div class="ws-card-time">now</div>
          </div>
          <div class="ws-card-meta">
            <div class="ws-card-branch">${esc(ws.branch)}</div>
            <div class="ws-card-stats">${chunks} chunks &middot; ${edges} edges</div>
          </div>
        </div>`;
    });
  }
  if (history.length) {
    html += '<div class="ws-section-label">Recent History</div>';
    history.forEach((ws, i) => {
      const color = colors[(i + active.length) % colors.length];
      html += `
        <div class="ws-card" onclick="switchWorkspace('${ws.id}')">
          <div class="ws-card-top">
            <div class="ws-card-icon ${color}">&#9672;</div>
            <div class="ws-card-name">${esc(ws.repo_name || ws.repo)}</div>
          </div>
          <div class="ws-card-meta">
            <div class="ws-card-branch">${esc(ws.branch)}</div>
          </div>
        </div>`;
    });
  }
  if (!state.workspaces.length) {
    html = '<div style="padding:20px 16px;color:#3f3f46;font-size:12px;text-align:center;">No workspaces yet.<br>Click <strong>+</strong> to add a repository.</div>';
  }
  container.innerHTML = html;
}

// ── Top Tabs ──
function renderTabs() {
  const container = document.getElementById('repo-tabs');
  if (!container) return;

  const colors = ['#7c3aed', '#3b82f6', '#22c55e', '#f59e0b'];
  const active = state.workspaces.filter(w => w.status === 'active');

  let html = '';
  active.forEach((ws, i) => {
    const isActive = ws.id === state.activeId;
    html += `
      <div class="repo-tab ${isActive ? 'active' : ''}" onclick="switchWorkspace('${ws.id}')">
        <div class="tab-dot" style="background:${colors[i % colors.length]};"></div>
        <span class="tab-name">${esc(ws.repo_name || ws.repo)}</span>
        <span class="tab-branch">${esc(ws.branch)}</span>
        <span class="tab-close" onclick="event.stopPropagation();closeWorkspace('${ws.id}')">&times;</span>
      </div>`;
  });
  html += '<div class="tab-add" onclick="document.getElementById(\'modal-new\').style.display=\'flex\'" title="Open Repository">+</div>';
  container.innerHTML = html;
}

// ── Stats Row ──
function renderStats() {
  const s = state.stats;
  setText('stat-chunks', s.chunks || 0);
  setText('stat-funcs', s.functions || 0);
  setText('stat-edges', s.edges || 0);
  setText('stat-classes', s.classes || 0);
  setText('file-count', state.files.length);

  const activeWs = state.workspaces.find(w => w.id === state.activeId);
  if (activeWs) {
    setText('branch-name-display', activeWs.branch || 'main');
  }
}

// ── File List ──
function renderFiles() {
  const container = document.getElementById('file-list');
  if (!container) return;

  let html = '';
  state.files.forEach((f, i) => {
    const isActive = state.selectedFile === f.path || (i === 0 && !state.selectedFile);
    html += `
      <div class="file-item ${isActive ? 'active' : ''}" onclick="selectFile('${esc(f.path)}', '${esc(f.name)}', ${f.chunks})">
        <span class="fi-icon">&#128196;</span>
        <span class="fi-name">${esc(f.name)}</span>
        <span class="fi-badge">${f.chunks}</span>
      </div>`;
  });
  if (!state.files.length) {
    html = '<div style="padding:14px;color:#3f3f46;font-size:11px;text-align:center;">No files ingested yet.</div>';
  }
  container.innerHTML = html;
}

// ── Graph (force-directed circle layout) ──
function renderGraph() {
  const area = document.getElementById('graph-canvas');
  if (!area) return;

  // Only remove dynamically-added nodes, keep label/toolbar/legend/svg
  area.querySelectorAll('.node').forEach(n => n.remove());

  const nodes = state.graphData.nodes || [];
  const edges = state.graphData.edges || [];
  const svg = area.querySelector('.graph-svg');

  if (!nodes.length) {
    if (svg) svg.innerHTML = '';
    return;
  }

  const W = area.clientWidth || 600;
  const H = area.clientHeight || 350;
  const cx = W / 2, cy = H / 2;

  // Position nodes in a circular layout with slight randomness
  const positioned = nodes.map((n, i) => {
    const angle = (i / nodes.length) * 2 * Math.PI - Math.PI / 2;
    const radius = Math.min(W, H) * 0.38;
    return {
      ...n,
      x: cx + Math.cos(angle) * radius + (Math.random() - 0.5) * 30,
      y: cy + Math.sin(angle) * radius + (Math.random() - 0.5) * 20,
    };
  });

  // Draw SVG edges
  if (svg) {
    let edgeHtml = '';
    edges.forEach(e => {
      const a = positioned.find(n => n.name === e.source);
      const b = positioned.find(n => n.name === e.target);
      if (!a || !b) return;
      const cls = e.type === 'CALLS' ? 'edge-call' : e.type === 'IMPORTS' ? 'edge-import' : 'edge-contain';
      edgeHtml += `<line class="edge ${cls}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"/>`;
    });
    svg.innerHTML = edgeHtml;
  }

  // Draw HTML nodes
  positioned.forEach((n, idx) => {
    const cls = n.label === 'Class' ? 'node-c' : n.label === 'Module' ? 'node-m' : 'node-f';
    const size = n.label === 'Class' ? 42 : n.label === 'Module' ? 34 : 28;
    const lbl = n.name.length > 12 ? n.name.slice(0, 12) + '..' : n.name;
    const glow = idx === 0 ? ' glow' : '';

    const div = document.createElement('div');
    div.className = `node ${cls}${glow}`;
    div.style.cssText = `width:${size}px;height:${size}px;left:${n.x - size / 2}px;top:${n.y - size / 2}px;`;
    div.innerHTML = `<div class="node-lbl">${esc(lbl)}</div>`;
    div.onclick = () => selectNode(n);
    area.appendChild(div);
  });
}

// ── Chat Messages ──
function renderChat() {
  const container = document.getElementById('chat-messages');
  if (!container) return;

  let html = '';
  if (!state.chatHistory.length) {
    html = `
      <div style="text-align:center;color:#27272a;padding:60px 20px;">
        <div style="font-size:32px;margin-bottom:10px;">🔮</div>
        <div style="font-size:14px;color:#52525b;font-weight:500;">Ask a question about the codebase</div>
        <div style="font-size:11px;color:#27272a;margin-top:6px;">GraphCodeRAG uses hybrid vector + graph retrieval</div>
        <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin-top:16px;">
          ${['How does the CLI parser work?', 'What classes inherit from Command?', 'How are options handled?'].map(q =>
            `<div class="chip chip-v" onclick="document.getElementById('chat-input').value='${q}';sendChat('${q}')" style="cursor:pointer;padding:4px 10px;">${q}</div>`
          ).join('')}
        </div>
      </div>`;
  }

  state.chatHistory.forEach(msg => {
    if (msg.role === 'user') {
      html += `<div class="msg-u"><div class="msg-u-bubble">${escContent(msg.content)}</div></div>`;
    } else {
      const trace = msg.trace || {};
      const sources = trace.sources || [];
      html += `
        <div class="msg-a">
          <div class="msg-a-av">G</div>
          <div class="msg-a-body">
            ${formatAnswer(msg.content)}
            ${sources.length ? renderSourceChips(sources) : ''}
            ${trace.vector_count !== undefined ? renderTrace(trace) : ''}
          </div>
        </div>`;
    }
  });
  container.innerHTML = html;
  container.scrollTop = container.scrollHeight;
}

function renderSourceChips(sources) {
  return `<div class="chips">${sources.map(s => {
    const cls = s.source === 'graph' ? 'chip-g' : 'chip-v';
    const dotColor = s.source === 'graph' ? '#22c55e' : '#3b82f6';
    const name = (s.file || s.name || '').split('/').pop();
    return `<div class="chip ${cls}"><div class="chip-dot" style="background:${dotColor};"></div> ${esc(name)} <span style="opacity:0.5;">${s.score}</span></div>`;
  }).join('')}</div>`;
}

function renderTrace(trace) {
  return `
    <div class="trace">
      <div class="trace-title">▾ Retrieval trace — ${trace.merged_count || 0} chunks</div>
      <div class="trace-step"><div class="trace-num tn-v">1</div><div>Vector: <strong>${trace.vector_count || 0} chunks</strong></div></div>
      <div class="trace-step"><div class="trace-num tn-g">2</div><div>Graph: <strong>+${trace.graph_count || 0} chunks</strong> via edges</div></div>
      <div class="trace-step"><div class="trace-num tn-m">3</div><div>Merged: <strong>${trace.merged_count || 0} unique</strong> re-ranked</div></div>
    </div>`;
}

function renderStatusPill() {
  const pill = document.getElementById('status-pill');
  if (!pill) return;
  if (state.neo4jOk) {
    pill.innerHTML = '<div class="status-dot"></div> Connected';
    pill.style.background = 'rgba(34,197,94,0.08)'; pill.style.color = '#4ade80';
    pill.style.borderColor = 'rgba(34,197,94,0.15)';
  } else {
    pill.innerHTML = '<div class="status-dot" style="background:#ef4444;"></div> Offline';
    pill.style.background = 'rgba(239,68,68,0.08)'; pill.style.color = '#ef4444';
    pill.style.borderColor = 'rgba(239,68,68,0.15)';
  }
}

function renderCodePane() {
  const pane = document.getElementById('code-pane');
  if (!pane) return;
  // Code pane shows selected file/node info
  const f = state.selectedFile;
  if (f) {
    const header = pane.querySelector('.code-pane-header');
    if (header) {
      const name = f.split('/').pop();
      header.innerHTML = `
        <div class="code-pane-left">
          <span class="cp-badge cp-func">FILE</span>
          <span class="cp-path">${esc(f)}</span>
        </div>
        <span style="font-size:10px;color:#3f3f46;">Selected</span>`;
    }
  }
}

// ── Typing Indicator ──
function addTypingIndicator() {
  const container = document.getElementById('chat-messages');
  if (!container) return null;
  const div = document.createElement('div');
  div.className = 'msg-a';
  div.id = 'typing-indicator';
  div.innerHTML = `
    <div class="msg-a-av">G</div>
    <div class="msg-a-body">
      <p style="color:#52525b;">
        <span class="typing-dot">●</span>
        <span class="typing-dot" style="animation-delay:0.2s">●</span>
        <span class="typing-dot" style="animation-delay:0.4s">●</span>
        Thinking...
      </p>
    </div>`;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

// ═══════════════════════════════════════════════════════════════
//  INTERACTION HANDLERS
// ═══════════════════════════════════════════════════════════════

function selectFile(path, name, chunks) {
  state.selectedFile = path;
  renderFiles();

  // Update code pane header
  const pane = document.getElementById('code-pane');
  if (pane) {
    const header = pane.querySelector('.code-pane-header');
    if (header) {
      header.innerHTML = `
        <div class="code-pane-left">
          <span class="cp-badge cp-func">FILE</span>
          <span class="cp-path">${esc(path)}</span>
          <span class="cp-lines">${chunks} chunks</span>
        </div>
        <span style="font-size:10px;color:#52525b;">Selected: ${esc(name)}</span>`;
    }
  }

  // Highlight that file's nodes in the graph
  highlightFileNodes(name);
}

function selectNode(node) {
  // Update code pane header with node info
  const pane = document.getElementById('code-pane');
  if (pane) {
    const header = pane.querySelector('.code-pane-header');
    const badgeCls = node.label === 'Class' ? 'cp-cls' : 'cp-func';
    const badgeText = node.label === 'Class' ? 'CLASS' : 'FUNC';
    if (header) {
      header.innerHTML = `
        <div class="code-pane-left">
          <span class="cp-badge ${badgeCls}">${badgeText}</span>
          <span class="cp-path">${esc(node.name)}</span>
        </div>
        <span style="font-size:10px;color:#52525b;">Selected: ${esc(node.name)}</span>`;
    }
  }

  // Highlight the selected node visually
  document.querySelectorAll('#graph-canvas .node').forEach(n => n.classList.remove('sel'));
  document.querySelectorAll('#graph-canvas .node').forEach(n => {
    const lbl = n.querySelector('.node-lbl');
    if (lbl && (lbl.textContent === node.name || node.name.startsWith(lbl.textContent.replace('..', '')))) {
      n.classList.add('sel');
    }
  });
}

function highlightFileNodes(fileName) {
  // Visual feedback: brief pulse on sidebar
  showNotification(`📄 Selected: ${fileName}`, 'info');
}

// ── Activity Bar Panel Switching ──
function setActivePanel(panel) {
  state.activePanel = panel;

  // Update activity icons
  document.querySelectorAll('.activity-icon').forEach(i => i.classList.remove('active'));

  const sidebar = document.getElementById('ws-sidebar');
  const filePanel = document.querySelector('.panel-left');

  switch (panel) {
    case 'explorer':
      document.getElementById('btn-ws')?.classList.add('active');
      sidebar?.classList.remove('collapsed');
      if (filePanel) filePanel.style.display = 'flex';
      break;
    case 'search':
      document.getElementById('btn-search')?.classList.add('active');
      sidebar?.classList.add('collapsed');
      if (filePanel) filePanel.style.display = 'flex';
      // Focus chat input as "search"
      setTimeout(() => document.getElementById('chat-input')?.focus(), 100);
      break;
    case 'graph':
      document.getElementById('btn-graph')?.classList.add('active');
      sidebar?.classList.add('collapsed');
      if (filePanel) filePanel.style.display = 'none';
      break;
    case 'ingest':
      document.getElementById('btn-ingest-ab')?.classList.add('active');
      document.getElementById('modal-new').style.display = 'flex';
      break;
    case 'history':
      document.getElementById('btn-history')?.classList.add('active');
      sidebar?.classList.remove('collapsed');
      break;
  }
}

// ═══════════════════════════════════════════════════════════════
//  NOTIFICATIONS
// ═══════════════════════════════════════════════════════════════

function showNotification(msg, type = 'info') {
  // Remove existing
  document.querySelectorAll('.notification').forEach(n => n.remove());

  const el = document.createElement('div');
  el.className = 'notification';
  const colors = {
    success: { bg: 'rgba(34,197,94,0.12)', border: 'rgba(34,197,94,0.3)', color: '#4ade80' },
    error: { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)', color: '#f87171' },
    info: { bg: 'rgba(124,58,237,0.12)', border: 'rgba(124,58,237,0.3)', color: '#c084fc' },
  };
  const c = colors[type] || colors.info;
  el.style.cssText = `
    position:fixed;top:16px;right:16px;z-index:1000;
    padding:10px 18px;border-radius:8px;font-size:12px;color:${c.color};
    background:${c.bg};border:1px solid ${c.border};
    backdrop-filter:blur(12px);box-shadow:0 8px 24px rgba(0,0,0,0.3);
    animation:slideIn 0.3s ease;font-weight:500;
  `;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { if (el.parentNode) el.remove(); }, 3500);
}

// ═══════════════════════════════════════════════════════════════
//  EVENT BINDINGS
// ═══════════════════════════════════════════════════════════════

function bindEvents() {
  // ── Activity Bar ──
  document.getElementById('btn-ws')?.addEventListener('click', () => setActivePanel('explorer'));
  document.getElementById('btn-search')?.addEventListener('click', () => setActivePanel('search'));
  document.getElementById('btn-graph')?.addEventListener('click', () => setActivePanel('graph'));
  document.getElementById('btn-ingest-ab')?.addEventListener('click', () => setActivePanel('ingest'));
  document.getElementById('btn-history')?.addEventListener('click', () => setActivePanel('history'));

  // ── Sidebar + New Repo modal ──
  document.getElementById('btn-new-repo')?.addEventListener('click', () => {
    document.getElementById('modal-new').style.display = 'flex';
  });
  document.getElementById('btn-modal-close')?.addEventListener('click', () => {
    document.getElementById('modal-new').style.display = 'none';
  });
  document.getElementById('btn-cancel')?.addEventListener('click', () => {
    document.getElementById('modal-new').style.display = 'none';
  });

  // Close modal on overlay click
  document.getElementById('modal-new')?.addEventListener('click', (e) => {
    if (e.target.id === 'modal-new') e.target.style.display = 'none';
  });

  // ── Ingest Button ──
  document.getElementById('btn-ingest')?.addEventListener('click', () => {
    // Check which tab is active (GitHub URL vs Local Path)
    const localField = document.getElementById('field-local');
    const isLocal = localField && localField.style.display !== 'none';

    let repoValue;
    if (isLocal) {
      repoValue = document.getElementById('input-local-path')?.value?.trim();
    } else {
      repoValue = document.getElementById('input-repo-url')?.value?.trim();
    }

    const branch = document.getElementById('input-repo-branch')?.value?.trim() || 'main';
    if (repoValue) {
      ingestRepo(repoValue, branch);
    } else {
      showNotification('Please enter a repository URL or path', 'error');
    }
  });

  // ── Modal Tabs (GitHub URL / Local Path) ──
  document.querySelectorAll('.modal-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');

      const isLocal = tab.textContent.includes('Local');
      const urlField = document.getElementById('field-url');
      const localField = document.getElementById('field-local');
      if (urlField) urlField.style.display = isLocal ? 'none' : 'block';
      if (localField) localField.style.display = isLocal ? 'block' : 'none';
    });
  });

  // ── Chat ──
  const chatInput = document.getElementById('chat-input');
  const sendBtn = document.getElementById('btn-send');

  sendBtn?.addEventListener('click', () => {
    const msg = chatInput?.value?.trim();
    if (msg) { sendChat(msg); chatInput.value = ''; chatInput.style.height = '18px'; }
  });

  chatInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const msg = chatInput.value.trim();
      if (msg) { sendChat(msg); chatInput.value = ''; chatInput.style.height = '18px'; }
    }
  });

  // Auto-resize textarea
  chatInput?.addEventListener('input', () => {
    chatInput.style.height = '18px';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 80) + 'px';
  });

  // ── Branch Dropdown ──
  document.getElementById('btn-branch')?.addEventListener('click', () => {
    const dd = document.getElementById('branch-dropdown');
    dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
  });

  // ── Mode Toggle (Hybrid / Vector) ──
  document.querySelectorAll('.mode-opt').forEach(opt => {
    opt.addEventListener('click', () => {
      document.querySelectorAll('.mode-opt').forEach(o => o.classList.remove('on'));
      opt.classList.add('on');
      showNotification(`Mode: ${opt.textContent}`, 'info');
    });
  });

  // ── Global: close dropdowns ──
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#btn-branch') && !e.target.closest('#branch-dropdown')) {
      const dd = document.getElementById('branch-dropdown');
      if (dd) dd.style.display = 'none';
    }
  });

  // ── Keyboard shortcuts ──
  document.addEventListener('keydown', (e) => {
    // Ctrl+K = focus chat
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      chatInput?.focus();
    }
    // Escape = close modals
    if (e.key === 'Escape') {
      document.getElementById('modal-new').style.display = 'none';
      document.getElementById('branch-dropdown').style.display = 'none';
    }
  });
}

// ═══════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════

function esc(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function escContent(str) {
  return esc(str).replace(/`([^`]+)`/g, '<code>$1</code>');
}

function formatAnswer(text) {
  if (!text) return '<p></p>';
  // Split into paragraphs and handle code blocks
  let html = '';
  const lines = text.split('\n');
  let inCode = false;
  let codeLang = '';
  let codeLines = [];

  for (const line of lines) {
    if (line.startsWith('```')) {
      if (inCode) {
        // End code block
        html += `<div class="msg-code"><div class="msg-code-top"><span>${esc(codeLang || 'code')}</span></div><div class="msg-code-content">${esc(codeLines.join('\n'))}</div></div>`;
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
        codeLang = line.slice(3).trim();
      }
    } else if (inCode) {
      codeLines.push(line);
    } else if (line.trim()) {
      const formatted = esc(line)
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');
      html += `<p>${formatted}</p>`;
    }
  }
  // Unclosed code block
  if (inCode && codeLines.length) {
    html += `<div class="msg-code"><div class="msg-code-top"><span>${esc(codeLang || 'code')}</span></div><div class="msg-code-content">${esc(codeLines.join('\n'))}</div></div>`;
  }
  return html || '<p></p>';
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}
