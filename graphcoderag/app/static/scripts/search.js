/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Global Search Panel
   ═══════════════════════════════════════════════════════════ */

const Search = {
  timeout: null,

  init() {
    document.getElementById('ab-search').addEventListener('click', () => this.open());
    document.getElementById('search-close').addEventListener('click', () => this.close());
    document.getElementById('search-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('search-overlay')) this.close();
    });

    const input = document.getElementById('global-search-input');
    input.addEventListener('input', (e) => {
      clearTimeout(this.timeout);
      this.timeout = setTimeout(() => this.doSearch(e.target.value), 300);
    });
  },

  open() {
    document.getElementById('search-overlay').style.display = 'flex';
    const input = document.getElementById('global-search-input');
    input.focus();
    input.select();
  },

  close() {
    document.getElementById('search-overlay').style.display = 'none';
  },

  async doSearch(query) {
    if (!query.trim()) {
      document.getElementById('search-results').innerHTML = '';
      return;
    }

    document.getElementById('search-results').innerHTML = '<div style="padding:16px; color:var(--text-4)">Searching...</div>';
    
    try {
      const data = await API.post('/search', { query: query, top_k: 15 });
      this.renderResults(data.results || []);
    } catch (e) {
      document.getElementById('search-results').innerHTML = '<div style="padding:16px; color:var(--coral)">Search failed</div>';
    }
  },

  _escapeHTML(str) {
    if (!str) return '';
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },

  renderResults(results) {
    const container = document.getElementById('search-results');
    if (!results.length) {
      container.innerHTML = '<div style="padding:16px; color:var(--text-4)">No results found.</div>';
      return;
    }

    container.innerHTML = results.map(r => {
      const sim = (r.similarity * 100).toFixed(1);
      const isFunc = r.type === 'function';
      const color = isFunc ? 'var(--blue)' : 'var(--purple)';
      
      const safeName = this._escapeHTML(r.name || r.file.split('/').pop());
      const safeFile = this._escapeHTML(r.file);
      const safeDoc = this._escapeHTML(r.docstring);
      
      return `
        <div class="search-item" style="padding:12px 16px; border-bottom:1px solid var(--border-1); cursor:pointer; transition:background 0.2s;" 
             onmouseover="this.style.background='rgba(255,255,255,0.03)'" 
             onmouseout="this.style.background='transparent'" 
             data-file="${safeFile}" data-start="${r.line_start}" data-end="${r.line_end}">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <div style="font-family:var(--font-mono); font-size:12px; color:var(--text-1)">
              <span style="color:${color}; margin-right:6px">■</span>${safeName}
            </div>
            <div style="font-size:10px; color:var(--text-4); background:var(--bg-0); padding:2px 6px; border-radius:4px; border:1px solid var(--border-1)">
              ${sim}% match
            </div>
          </div>
          <div style="font-size:11px; color:var(--text-3); margin-bottom:6px;">${safeFile} • Lines ${r.line_start}-${r.line_end}</div>
          ${safeDoc ? `<div style="font-size:11px; color:var(--text-2); opacity:0.8; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${safeDoc}</div>` : ''}
        </div>
      `;
    }).join('');

    container.querySelectorAll('.search-item').forEach(item => {
      item.addEventListener('click', () => {
        this.viewCode(item.dataset.file, parseInt(item.dataset.start), parseInt(item.dataset.end));
      });
    });
  },

  viewCode(file, start, end) {
    this.close();
    Events.emit('code:load', { file: file, line_start: start, line_end: end });
  }
};
