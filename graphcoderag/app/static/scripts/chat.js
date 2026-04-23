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

    // Render initial demo conversation
    Events.on('chat:init', () => this._renderDemoChat());
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
      this._renderAIMessage(this._mockResponse(text));
    }

    msgs.scrollTop = msgs.scrollHeight;
  },

  /** Render an AI response message */
  _renderAIMessage(resp) {
    const msgs = document.getElementById('chat-msgs');
    const msg = document.createElement('div');
    msg.className = 'msg-a';

    const content = resp.content || resp.answer || 'I couldn\'t generate a response.';
    const trace = resp.trace || {};
    const sources = trace.sources || [];

    // Parse markdown in content
    let bodyHTML = '';
    try {
      bodyHTML = marked.parse(content);
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
        const score = s.score ? s.score.toFixed(2) : (s.hops ? `${s.hops}-hop` : '');
        return `<div class="chip ${cls}" data-name="${s.name || ''}" data-file="${s.file || ''}">
          <div class="chip-dot" style="background:${dotColor}"></div>
          ${s.file ? s.file.split('/').pop() : ''}${s.name ? ':' + s.name : ''} <span style="opacity:.5">${score}</span>
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

  /** Render the initial demo chat */
  _renderDemoChat() {
    const msgs = document.getElementById('chat-msgs');
    msgs.innerHTML = '';

    // User message
    const user = document.createElement('div');
    user.className = 'msg-u';
    user.innerHTML = `<div class="msg-u-bub">How does <code>invoke()</code> in Group handle subcommand routing?</div>`;
    msgs.appendChild(user);

    // AI response with all features
    this._renderAIMessage({
      content: '`Group.invoke()` handles routing through **two-phase resolution**:\n\n**1.** Calls `resolve_command()` to match input to a registered subcommand\n\n**2.** Creates a sub-context and delegates to the matched command\'s `invoke()`\n\nIf `invoke_without_command` is set and no subcommand is given, the Group runs as standalone.',
      trace: {
        vector_count: 4,
        graph_count: 3,
        merged_count: 7,
        sources: [
          { file: 'core.py', name: 'invoke', source: 'vector', score: 0.94 },
          { file: 'core.py', name: 'resolve_cmd', source: 'graph', hops: 1, score: 0.88 },
          { file: 'core.py', name: 'make_context', source: 'graph', hops: 2, score: 0.82 },
          { file: 'core.py', name: 'parse_args', source: 'vector', score: 0.87 },
        ],
      },
    });
  },

  /** Generate a mock response when backend is unavailable */
  _mockResponse(query) {
    return {
      role: 'assistant',
      content: `I analyzed the codebase for your query: **"${query}"**\n\nBased on the knowledge graph traversal and vector search, here are the relevant findings from the repository. The hybrid retrieval combined both similarity-based and structural context to provide a comprehensive answer.\n\n> *Note: This is a demo response. Connect the backend for real answers.*`,
      trace: {
        vector_count: 3,
        graph_count: 2,
        merged_count: 5,
        sources: [
          { file: 'core.py', name: 'invoke', source: 'vector', score: 0.91 },
          { file: 'core.py', name: 'resolve_cmd', source: 'graph', score: 0.85 },
        ],
      },
    };
  },

  _escapeHTML(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  },
};
