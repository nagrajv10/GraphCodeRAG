/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Code Viewer (Phase 5: wired to backend)
   ═══════════════════════════════════════════════════════════ */

const CodeViewer = {
  init() {
    Events.on('node:selected', (node) => this.loadNodeCode(node));
    Events.on('code:show', (data) => this.render(data));
  },

  /** Load code for a graph node from the backend API */
  async loadNodeCode(node) {
    // Try real API
    const data = await API.get(`/graph/node/${encodeURIComponent(node.id)}`);
    if (data && data.source_code) {
      const lines = data.source_code.split('\n').map((line, i) => ({
        num: (data.line_start || 1) + i,
        code: this._highlightPython(line),
        hl: false,
      }));
      this.render({
        file: data.file || '',
        entity_name: data.entity_name,
        entity_type: data.entity_type || 'function',
        line_start: data.line_start || 1,
        line_end: data.line_end || lines.length,
        source_lines: lines,
      });
    } else {
      // Minimal fallback
      this.render({
        file: node.file ? `click/${node.file}` : '',
        entity_name: node.id,
        entity_type: node.type || 'function',
        line_start: 1, line_end: 1,
        source_lines: [{num:1, code: `<span class="cm"># Code for ${node.id} (connect backend for full source)</span>`, hl: false}],
      });
    }
  },

  /** Simple Python syntax highlighter */
  _highlightPython(line) {
    let s = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    // Comments
    s = s.replace(/(#.*)$/, '<span class="cm">$1</span>');
    // Strings (triple-quoted and single/double)
    s = s.replace(/(""".*?"""|'''.*?'''|"[^"]*"|'[^']*')/g, '<span class="st">$1</span>');
    // Keywords
    const kw = /\b(def|class|if|elif|else|for|while|return|import|from|as|with|try|except|finally|raise|yield|async|await|None|True|False|and|or|not|is|in|lambda|pass|break|continue|global|nonlocal)\b/g;
    s = s.replace(kw, '<span class="kw">$1</span>');
    // self/cls
    s = s.replace(/\b(self|cls)\b/g, '<span class="pr">$1</span>');
    return s;
  },

  /** Render code with line numbers and highlighting */
  render(data) {
    const badgeEl = document.getElementById('code-badge');
    const pathEl = document.getElementById('code-path');
    const linesEl = document.getElementById('code-lines');
    const selEl = document.getElementById('code-sel');

    const typeMap = { class: 'CLASS', function: 'FUNC', module: 'MOD' };
    const cssMap = { class: 'cp-cls', function: 'cp-func', module: 'cp-mod' };

    badgeEl.textContent = typeMap[data.entity_type] || 'FUNC';
    badgeEl.className = `cp-badge ${cssMap[data.entity_type] || 'cp-func'}`;
    pathEl.textContent = data.file || '';
    linesEl.textContent = data.line_start ? `L${data.line_start}-${data.line_end}` : '';
    selEl.textContent = data.entity_name ? `Selected: ${data.entity_name}` : '';

    const body = document.getElementById('code-body');
    if (!data.source_lines || data.source_lines.length === 0) {
      body.innerHTML = '<div class="code-empty">No code available</div>';
      return;
    }
    body.innerHTML = data.source_lines.map(line => `
      <div class="cl ${line.hl ? 'hl' : ''}">
        <span class="ln">${line.num}</span>
        <span class="lc">${line.code}</span>
      </div>`).join('');
  },

  scrollToLine(lineNum) {
    const body = document.getElementById('code-body');
    for (const line of body.querySelectorAll('.cl')) {
      const ln = line.querySelector('.ln');
      if (ln && parseInt(ln.textContent) === lineNum) {
        line.scrollIntoView({ behavior: 'smooth', block: 'center' });
        line.style.background = 'rgba(168,85,247,.12)';
        setTimeout(() => { line.style.background = ''; }, 2000);
        break;
      }
    }
  },
};
