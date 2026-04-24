/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Chat Panel
   Features: messages, mode toggle, retrieval trace,
             source chips, context tagging, send flow
   ═══════════════════════════════════════════════════════════ */

const Chat = {
  init() {
    const input = document.getElementById('cinput');
    const sendBtn = document.getElementById('btn-send');

    // Send on button click
    sendBtn.addEventListener('click', () => this.send());

    // Send on Enter (not Shift+Enter)
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });

    // Auto-resize textarea
    input.addEventListener('input', function () {
      this.style.height = '20px';
      this.style.height = Math.min(this.scrollHeight, 80) + 'px';
    });

    // Mode toggle
    document.querySelectorAll('#mode-toggle .mode-opt').forEach(opt => {
      opt.addEventListener('click', () => {
        document.querySelectorAll('#mode-toggle .mode-opt').forEach(o => o.classList.remove('on'));
        opt.classList.add('on');
        AppState.retrievalMode = opt.dataset.mode;
      });
    });

    // Load chat history on init
    Events.on('chat:init', () => this.loadHistory());
    Events.on('workspace:activated', () => this.loadHistory());
  },

  async loadHistory() {
    const data = await API.get('/chat/history');
    const msgs = document.getElementById('chat-msgs');
    msgs.innerHTML = '';
    
    if (data && data.history && data.history.length > 0) {
      for (const msg of data.history) {
        if (msg.role === 'user') {
          const userMsg = document.createElement('div');
          userMsg.className = 'msg-u';
          userMsg.innerHTML = `<div class="msg-u-bub">${this._escapeHTML(msg.content).replace(/`([^`]+)`/g, '<code>$1</code>')}</div>`;
          msgs.appendChild(userMsg);
        } else {
          this._renderAIMessage(msg);
        }
      }
      msgs.scrollTop = msgs.scrollHeight;
    }
  },

  /** Send user message */
  async send() {
    const input = document.getElementById('cinput');
    const text = input.value.trim();
    if (!text) return;

    const msgs = document.getElementById('chat-msgs');

    // Append user message
    const userMsg = document.createElement('div');
    userMsg.className = 'msg-u';
    userMsg.innerHTML = `<div class="msg-u-bub">${this._escapeHTML(text).replace(/`([^`]+)`/g, '<code>$1</code>')}</div>`;
    msgs.appendChild(userMsg);

    // Clear input
    input.value = '';
    input.style.height = '20px';
    msgs.scrollTop = msgs.scrollHeight;

    // Show loading
    const loadingMsg = document.createElement('div');
    loadingMsg.className = 'msg-a';
    loadingMsg.id = 'msg-loading';
    loadingMsg.innerHTML = `
      <div class="msg-a-av">G</div>
      <div class="msg-a-body">
        <p class="msg-loading">Searching knowledge graph and vector store...</p>
      </div>`;
    msgs.appendChild(loadingMsg);
    msgs.scrollTop = msgs.scrollHeight;

    // Call backend API
    const response = await API.post('/chat', {
      message: text,
      mode: AppState.retrievalMode,
      context_files: AppState.contextFiles,
    });

    // Remove loading
    loadingMsg.remove();

    if (response && response.response) {
      this._renderAIMessage(response.response);
    } else {
      // Fallback mock response
    // Fallback mock response
    this._renderAIMessage(this._mockResponse(text));
  } else {
    this._renderAIMessage(this._mockResponse(text));
  }

  msgs.scrollTop = msgs.scrollHeight;
},

/** Safe fallback if API fails */
_mockResponse(query) {
  return {
    content: "Sorry, the backend API is unreachable or returned an error. Please ensure the backend is running and connected.",
    trace: { vector_count: 0, graph_count: 0, merged_count: 0, sources: [] }
  };
},

/** Render an AI response message */
_renderAIMessage(resp) {
  const msgs = document.getElementById('chat-msgs');
  const msg = document.createElement('div');
  msg.className = 'msg-a';

  const content = resp.content || resp.answer || 'I couldn\'t generate a response.';
  const trace = resp.trace || {};
  const sources = trace.sources || [];

  // Parse markdown in content and sanitize to prevent XSS
  let bodyHTML = '';
  try {
    const rawHTML = marked.parse(content);
    // Use DOMPurify if loaded, else fallback to strict escaping
    if (typeof DOMPurify !== 'undefined') {
      bodyHTML = DOMPurify.sanitize(rawHTML);
    } else {
      bodyHTML = `<p>${this._escapeHTML(content)}</p>`;
    }
  } catch {
    bodyHTML = `<p>${this._escapeHTML(content)}</p>`;
  }

  // Source chips
  let chipsHTML = '';
  if (sources.length > 0) {
    chipsHTML = '<div class="chips">' + sources.map(s => {
      const isGraph = s.source === 'graph' || s.source === 'hybrid';
      const cls = isGraph ? 'chip-g' : 'chip-v';
      const dotColor = isGraph ? 'var(--green)' : 'var(--blue)';
      const score = s.score ? s.score.toFixed(2) : '';
      
      // Feature: Two-Tier visualization based on child count
      let connectionLabel = score;
      if (s.children_count > 0) {
        connectionLabel = `Vector (${s.children_count} matched) &rarr; Parent`;
      } else if (s.hops) {
        connectionLabel = `${s.hops}-hop dependency`;
      }
      
      return `<div class="chip ${cls}" data-name="${this._escapeHTML(s.name || '')}" data-file="${this._escapeHTML(s.file || '')}">
        <div class="chip-dot" style="background:${dotColor}"></div>
        ${s.file ? this._escapeHTML(s.file.split('/').pop()) : ''}${s.name ? ':' + this._escapeHTML(s.name) : ''} <span style="opacity:.6; margin-left:4px;">${connectionLabel}</span>
      </div>`;
    }).join('') + '</div>';
  }

    // Retrieval trace
    let traceHTML = '';
    if (trace.vector_count !== undefined) {
      const total = (trace.vector_count || 0) + (trace.graph_count || 0);
      traceHTML = `
        <div class="trace">
          <div class="trace-hd" onclick="let b=this.nextElementSibling,a=this.querySelector('.arr');b.classList.toggle('open');a.classList.toggle('open')">
            <span class="arr">&#9654;</span> Retrieval trace &mdash; ${trace.merged_count || total} chunks merged
          </div>
          <div class="trace-bd">
            <div class="trace-step"><div class="trace-num tn-v">1</div><div>Vector: <strong style="color:var(--text-1)">${trace.vector_count || 0} chunks</strong> (cosine similarity)</div></div>
            <div class="trace-step"><div class="trace-num tn-g">2</div><div>Graph: <strong style="color:var(--text-1)">+${trace.graph_count || 0} chunks</strong> via dependency edges</div></div>
            <div class="trace-step"><div class="trace-num tn-m">3</div><div>Merged: <strong style="color:var(--text-1)">${trace.merged_count || total} unique</strong> re-ranked by hybrid score</div></div>
          </div>
        </div>`;
    }

    msg.innerHTML = `
      <div class="msg-a-av">G</div>
      <div class="msg-a-body">
        ${bodyHTML}
        ${chipsHTML}
        ${traceHTML}
      </div>`;

    msgs.appendChild(msg);

    // Chip click handlers
    msg.querySelectorAll('.chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const name = chip.dataset.name;
        if (name) {
          Graph.selectNode(name);
          Events.emit('node:selected', { id: name, file: chip.dataset.file, type: 'function' });
        }
      });
    });

    // Highlight graph nodes from sources
    if (sources.length > 0) {
      const graphNodes = sources.filter(s => s.source === 'graph' || s.source === 'hybrid').map(s => s.name);
      Events.emit('graph:highlight', graphNodes);
    }
  },

  _escapeHTML(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },
};
