/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Settings Panel
   ═══════════════════════════════════════════════════════════ */

const Settings = {
  init() {
    document.getElementById('ab-settings').addEventListener('click', () => this.open());
    document.getElementById('settings-close').addEventListener('click', () => this.close());
    document.getElementById('settings-cancel').addEventListener('click', () => this.close());
    document.getElementById('settings-save').addEventListener('click', () => this.save());
    document.getElementById('settings-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('settings-overlay')) this.close();
    });
  },

  async open() {
    document.getElementById('settings-overlay').style.display = 'flex';
    try {
      const data = await API.get('/settings');
      if (data) {
        document.getElementById('setting-vector-backend').value = data.vector_backend || 'faiss';
        document.getElementById('setting-llm-provider').value = data.use_local_llm ? 'local' : 'api';
        document.getElementById('setting-llm-model').value = data.local_llm_model || 'qwen2.5-coder:7b-instruct';
      }
    } catch (e) {
      console.error("Failed to load settings", e);
    }
  },

  close() {
    document.getElementById('settings-overlay').style.display = 'none';
  },

  async save() {
    const payload = {
      vector_backend: document.getElementById('setting-vector-backend').value,
      use_local_llm: document.getElementById('setting-llm-provider').value === 'local',
      local_llm_model: document.getElementById('setting-llm-model').value,
      use_local_embeddings: true
    };
    
    try {
      await API.put('/settings', payload);
      this.close();
      // Show toast
      const toasts = document.getElementById('toasts');
      const toast = document.createElement('div');
      toast.className = 'toast show';
      toast.innerHTML = 'Settings saved successfully.';
      toasts.appendChild(toast);
      setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
      }, 3000);
    } catch (e) {
      console.error("Failed to save settings", e);
    }
  }
};
