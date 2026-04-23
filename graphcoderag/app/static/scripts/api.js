/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — API Wrapper
   Centralized fetch calls to the FastAPI backend.
   ═══════════════════════════════════════════════════════════ */

const API = {
  /** GET request → JSON */
  async get(path) {
    try {
      const res = await fetch(`/api${path}`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json();
    } catch (e) {
      console.error(`API GET ${path}:`, e);
      Toast.error(`API error: ${e.message}`);
      return null;
    }
  },

  /** POST request → JSON */
  async post(path, body = {}) {
    try {
      const res = await fetch(`/api${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `${res.status} ${res.statusText}`);
      }
      return await res.json();
    } catch (e) {
      console.error(`API POST ${path}:`, e);
      Toast.error(`API error: ${e.message}`);
      return null;
    }
  },

  /** PUT request → JSON */
  async put(path, body = {}) {
    try {
      const res = await fetch(`/api${path}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      return await res.json();
    } catch (e) {
      console.error(`API PUT ${path}:`, e);
      return null;
    }
  },

  /** DELETE request */
  async del(path) {
    try {
      const res = await fetch(`/api${path}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(`${res.status}`);
      return await res.json();
    } catch (e) {
      console.error(`API DELETE ${path}:`, e);
      return null;
    }
  },
};

/* ─── Toast Notifications ─── */
const Toast = {
  _el: () => document.getElementById('toasts'),

  show(msg, type = '', duration = 4000) {
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = msg;
    this._el().appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, duration);
  },

  error(msg) { this.show(msg, 'error', 5000); },
  success(msg) { this.show(msg, 'success', 3000); },
};
