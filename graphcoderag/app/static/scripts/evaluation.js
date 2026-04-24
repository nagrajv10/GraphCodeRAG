/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Evaluation Panel (Real Metrics)
   Renders retrieval metrics + generation quality from actual runs
   ═══════════════════════════════════════════════════════════ */

const Evaluation = {
  data: null,

  init() {
    document.getElementById('ab-eval').addEventListener('click', () => this.open());
    document.getElementById('eval-close').addEventListener('click', () => this.close());
    document.getElementById('eval-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('eval-overlay')) this.close();
    });

    // Ingest button opens modal
    document.getElementById('ab-ingest').addEventListener('click', () => {
      document.getElementById('modal').classList.add('show');
    });
  },

  async open() {
    const overlay = document.getElementById('eval-overlay');
    overlay.style.display = 'flex';
    if (!this.data) {
      this.data = await API.get('/evaluation');
    }
    if (this.data) this.render(this.data);
  },

  close() {
    document.getElementById('eval-overlay').style.display = 'none';
  },

  render(d) {
    const body = document.getElementById('eval-body');

    if (!d || !d.methods || d.methods.length === 0) {
      body.innerHTML = '<div class="code-empty">No evaluation data available yet. Run the evaluation script to populate results.</div>';
      return;
    }

    // --- Method legend (only 2 methods now) ---
    const legendHTML = d.methods.map(m => `
      <div class="ev-method">
        <div class="ev-dot" style="background:${m.color}"></div>
        <div><strong>${m.name}</strong><br><span style="opacity:.6;font-size:12px">${m.description}</span></div>
      </div>`).join('');

    // --- Retrieval bar charts ---
    const metricsHTML = Object.entries(d.metrics).map(([key, m]) => {
      const vals = m.values;
      const entries = Object.entries(vals);
      const maxVal = Math.max(...entries.map(e => e[1]));
      const colorMap = { graphcoderag: '#a855f7', standard_rag: '#60a5fa' };
      const labelMap = { graphcoderag: 'GraphCodeRAG', standard_rag: 'Standard RAG' };

      const barsHTML = entries.map(([mk, val]) => {
        const pct = maxVal > 0 ? (val / maxVal * 100).toFixed(0) : 0;
        const isWinner = val === maxVal;
        const color = colorMap[mk] || '#888';
        return `
          <div class="ev-bar-row">
            <span class="ev-bar-label">${labelMap[mk] || mk}</span>
            <div class="ev-bar-track">
              <div class="ev-bar-fill${isWinner ? ' winner' : ''}" style="width:${pct}%;background:${color}"></div>
            </div>
            <span class="ev-bar-val${isWinner ? ' winner' : ''}">${val.toFixed(3)}</span>
          </div>`;
      }).join('');

      const repoTag = m.repo ? ` <span style="opacity:.4;font-size:10px">(${m.repo})</span>` : '';
      return `
        <div class="ev-metric">
          <div class="ev-metric-title">${m.label}${repoTag}</div>
          <div class="ev-metric-desc">${m.description}</div>
          ${barsHTML}
        </div>`;
    }).join('');

    // --- Per-repo breakdown ---
    const repoHTML = d.per_repo.map(r => {
      const gMrr = r.graphcoderag_mrr || 0;
      const sMrr = r.standard_mrr || 0;
      const maxMrr = Math.max(gMrr, sMrr, 0.01);
      const gPct = (gMrr / maxMrr * 100).toFixed(0);
      const sPct = (sMrr / maxMrr * 100).toFixed(0);
      const delta = r.delta_mrr || '';
      return `
        <div class="ev-repo">
          <div class="ev-repo-name">${r.repo} <span style="opacity:.5">(${r.instances} instances)</span> <span style="font-size:11px;color:${delta.startsWith('+') ? 'var(--green)' : 'var(--coral)'};font-weight:600">${delta}</span></div>
          <div class="ev-mini-bars">
            <div class="ev-mini-bar" style="width:${gPct}%;background:#a855f7" title="GraphCodeRAG MRR: ${gMrr.toFixed(3)}"></div>
            <div class="ev-mini-bar" style="width:${sPct}%;background:#60a5fa" title="Standard RAG MRR: ${sMrr.toFixed(3)}"></div>
          </div>
          <div class="ev-repo-finding">${r.finding}</div>
        </div>`;
    }).join('');

    // --- Generation quality section ---
    let genHTML = '';
    if (d.generation) {
      const g = d.generation;
      const sc = g.scores;
      const rows = ['rag_hybrid', 'vector_only', 'plain_llm'];
      const labels = { rag_hybrid: 'RAG + Hybrid', vector_only: 'Vector-Only', plain_llm: 'Plain LLM' };
      const colors = { rag_hybrid: '#a855f7', vector_only: '#4ade80', plain_llm: '#60a5fa' };

      const genBarsHTML = rows.map(rk => {
        const s = sc[rk];
        const pct = (s.avg / 5 * 100).toFixed(0);
        return `
          <div class="ev-bar-row">
            <span class="ev-bar-label">${labels[rk]}</span>
            <div class="ev-bar-track">
              <div class="ev-bar-fill" style="width:${pct}%;background:${colors[rk]}"></div>
            </div>
            <span class="ev-bar-val">${s.avg.toFixed(2)}/5</span>
          </div>`;
      }).join('');

      // Pairwise
      const pw = g.pairwise;
      const pwHTML = `
        <div style="display:flex;gap:16px;margin-top:10px">
          <div class="ev-pw-card">
            <div class="ev-pw-title">RAG vs Plain LLM</div>
            <div class="ev-pw-row"><span class="ev-pw-w">W ${pw.rag_vs_plain.rag_wins}</span> <span class="ev-pw-t">T ${pw.rag_vs_plain.ties}</span> <span class="ev-pw-l">L ${pw.rag_vs_plain.plain_wins}</span></div>
          </div>
          <div class="ev-pw-card">
            <div class="ev-pw-title">RAG vs Vector-Only</div>
            <div class="ev-pw-row"><span class="ev-pw-w">W ${pw.rag_vs_vector.rag_wins}</span> <span class="ev-pw-t">T ${pw.rag_vs_vector.ties}</span> <span class="ev-pw-l">L ${pw.rag_vs_vector.vector_wins}</span></div>
          </div>
        </div>`;

      genHTML = `
        <div class="ev-section">
          <h3>Generation Quality — LLM Judge</h3>
          <div class="ev-metric">
            <div class="ev-metric-title">${g.title}</div>
            <div class="ev-metric-desc">Judge: ${g.judge_model} | Scale: ${g.scale}</div>
            ${genBarsHTML}
            ${pwHTML}
            <div style="margin-top:10px;font-size:11px;color:var(--text-4);font-style:italic">${g.note}</div>
          </div>
        </div>`;
    }

    // --- Key findings ---
    const findingsHTML = d.key_findings.map(f => `<li>${f}</li>`).join('');

    body.innerHTML = `
      <div class="ev-study">
        <div class="ev-study-title">${d.study.title}</div>
        <div class="ev-study-meta">${d.study.instances} instances across ${d.study.repositories.join(', ')}</div>
      </div>

      <div class="ev-legend">${legendHTML}</div>

      <div class="ev-section">
        <h3>Retrieval Metrics (Click — Best Case)</h3>
        ${metricsHTML}
      </div>

      <div class="ev-section">
        <h3>Per-Repository Breakdown (MRR@5)</h3>
        ${repoHTML}
      </div>

      ${genHTML}

      <div class="ev-section">
        <h3>Key Findings</h3>
        <ul class="ev-findings">${findingsHTML}</ul>
      </div>
    `;
  },
};
