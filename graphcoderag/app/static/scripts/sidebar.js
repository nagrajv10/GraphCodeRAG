/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Sidebar (Activity Bar + Workspace Cards)
   ═══════════════════════════════════════════════════════════ */

const Sidebar = {
  init() {
    // Sidebar toggle
    document.getElementById('btn-sb').addEventListener('click', () => {
      document.getElementById('sidebar').classList.toggle('collapsed');
    });

    // Listen for workspace updates
    Events.on('workspaces:loaded', (workspaces) => this.render(workspaces));
    Events.on('workspace:activated', (id) => this.setActive(id));
  },

  render(workspaces) {
    const container = document.getElementById('sb-cards');
    const active = workspaces.filter(w => w.status === 'active');
    const history = workspaces.filter(w => w.status === 'history');

    let html = '';

    if (active.length > 0) {
      html += active.map(w => this._cardHTML(w)).join('');
    }

    if (history.length > 0) {
      html += '<div class="sb-section">Recent History</div>';
      html += history.map(w => this._cardHTML(w)).join('');
    }

    container.innerHTML = html;

    // Card click handlers
    container.querySelectorAll('.sb-card').forEach(card => {
      card.addEventListener('click', () => {
        const wsId = card.dataset.id;
        Events.emit('workspace:switch', wsId);
      });
    });
  },

  _cardHTML(w) {
    const isActive = w.id === AppState.activeWorkspaceId;
    const stats = w.stats || {};
    return `
      <div class="sb-card ${isActive ? 'active' : ''}" data-id="${w.id}">
        <div class="sb-card-row">
          <div class="sb-card-dot" style="background:${w.color || 'var(--purple)'}"></div>
          <div class="sb-card-name">${w.repo || w.repo_name || ''}</div>
          <div class="sb-card-time">${w.last_active || ''}</div>
        </div>
        <div class="sb-card-meta">
          <div class="sb-card-tag">${w.branch || 'main'}</div>
          <div class="sb-card-stats">${stats.chunks || 0} chunks · ${stats.edges || 0} edges</div>
        </div>
        ${w.last_query ? `<div class="sb-card-preview">Last: "${w.last_query}"</div>` : ''}
      </div>`;
  },

  setActive(id) {
    document.querySelectorAll('.sb-card').forEach(c => {
      c.classList.toggle('active', c.dataset.id === id);
    });
  },
};
