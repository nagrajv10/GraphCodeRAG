/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Tab Bar
   ═══════════════════════════════════════════════════════════ */

const Tabs = {
  init() {
    Events.on('workspaces:loaded', (workspaces) => this.render(workspaces));
    Events.on('workspace:activated', (id) => this.setActive(id));
  },

  render(workspaces) {
    const container = document.getElementById('tabs-container');
    const plus = document.getElementById('btn-tab');
    // Remove existing tabs (keep the + button)
    container.querySelectorAll('.tab').forEach(t => t.remove());

    const activeWs = workspaces.filter(w => w.status === 'active');
    activeWs.forEach(w => {
      const tab = document.createElement('div');
      tab.className = `tab ${w.id === AppState.activeWorkspaceId ? 'active' : ''}`;
      tab.dataset.id = w.id;
      tab.innerHTML = `
        <div class="tab-dot" style="background:${w.color || '#7c3aed'}"></div>
        <span class="tab-name">${w.repo || ''}</span>
        <span class="tab-branch">${w.branch || 'main'}</span>
        <span class="tab-close">&times;</span>`;
      container.insertBefore(tab, plus);

      // Tab click → switch workspace
      tab.addEventListener('click', (e) => {
        if (e.target.classList.contains('tab-close')) {
          Events.emit('workspace:close', w.id);
          return;
        }
        Events.emit('workspace:switch', w.id);
      });
    });
  },

  setActive(id) {
    document.querySelectorAll('.tab').forEach(t => {
      t.classList.toggle('active', t.dataset.id === id);
    });
    // Update branch display
    const ws = AppState.workspaces.find(w => w.id === id);
    if (ws) {
      document.getElementById('branch-name').textContent = ws.branch || 'main';
    }
  },
};
