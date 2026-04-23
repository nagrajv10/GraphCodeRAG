/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Modal (Add Repo + Ingestion Progress)
   ═══════════════════════════════════════════════════════════ */

const Modal = {
  init() {
    const modal = document.getElementById('modal');
    const open = () => modal.classList.add('show');
    const close = () => { modal.classList.remove('show'); this._reset(); };

    document.getElementById('btn-new').addEventListener('click', open);
    document.getElementById('btn-tab').addEventListener('click', open);
    document.getElementById('btn-mx').addEventListener('click', close);
    document.getElementById('btn-cancel').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });

    // Modal tabs
    document.querySelectorAll('#modal-tabs .modal-tab').forEach(t => {
      t.addEventListener('click', () => {
        document.querySelectorAll('#modal-tabs .modal-tab').forEach(x => x.classList.remove('active'));
        t.classList.add('active');
      });
    });

    // Ingest button
    document.getElementById('btn-ingest').addEventListener('click', () => this._startIngestion());
  },

  async _startIngestion() {
    const repoUrl = document.getElementById('input-repo').value.trim();
    const branch = document.getElementById('input-branch').value.trim() || 'main';
    if (!repoUrl) { Toast.error('Please enter a repository URL'); return; }

    const prog = document.getElementById('iprog');
    prog.classList.add('show');
    document.getElementById('btn-ingest').disabled = true;

    const steps = prog.querySelectorAll('.prog-step');
    const fill = document.getElementById('pfill');
    let current = 0;

    // Try real API first, fall back to simulation
    try {
      const result = await API.post('/workspaces', { repo_url: repoUrl, branch });
      if (result && result.status === 'ok') {
        // Animate through all steps quickly
        for (let i = 0; i < steps.length; i++) {
          if (i > 0) { steps[i-1].classList.remove('active'); steps[i-1].classList.add('done'); steps[i-1].querySelector('.check').textContent = '✓'; }
          steps[i].classList.add('active'); steps[i].querySelector('.check').textContent = '◉';
          fill.style.width = ((i+1)/steps.length*100) + '%';
          await new Promise(r => setTimeout(r, 200));
        }
        steps[steps.length-1].classList.remove('active'); steps[steps.length-1].classList.add('done'); steps[steps.length-1].querySelector('.check').textContent = '✓';
        Toast.success(`Ingested ${repoUrl} successfully`);
        setTimeout(() => { document.getElementById('modal').classList.remove('show'); this._reset(); Events.emit('workspace:reload'); }, 600);
        return;
      }
    } catch(e) { /* Fall through to simulation */ }

    // Simulation fallback (mock mode)
    const iv = setInterval(() => {
      if (current > 0) { steps[current-1].classList.remove('active'); steps[current-1].classList.add('done'); steps[current-1].querySelector('.check').textContent = '✓'; }
      if (current < steps.length) {
        steps[current].classList.add('active'); steps[current].querySelector('.check').textContent = '◉';
        fill.style.width = ((current+1)/steps.length*100) + '%'; current++;
      } else {
        clearInterval(iv);
        Toast.success(`Ingested ${repoUrl} (demo mode)`);
        setTimeout(() => { document.getElementById('modal').classList.remove('show'); this._reset(); }, 800);
      }
    }, 900);
  },

  _reset() {
    const prog = document.getElementById('iprog');
    prog.classList.remove('show');
    prog.querySelectorAll('.prog-step').forEach(s => { s.classList.remove('done','active'); s.querySelector('.check').textContent = '○'; });
    document.getElementById('pfill').style.width = '0%';
    document.getElementById('btn-ingest').disabled = false;
  },
};
