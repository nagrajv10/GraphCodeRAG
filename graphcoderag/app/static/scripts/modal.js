/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — Modal (Add Repo + Ingestion Progress)
   ═══════════════════════════════════════════════════════════ */

const Modal = {
  init() {
    const modal = document.getElementById('modal');
    // Add accessibility attributes
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-labelledby', 'modal-title');
    
    const open = () => { 
      modal.classList.add('show'); 
      document.getElementById('input-repo').focus(); 
      document.body.style.overflow = 'hidden';
    };
    const close = () => { 
      modal.classList.remove('show'); 
      this._reset(); 
      document.body.style.overflow = '';
    };

    document.getElementById('btn-new').addEventListener('click', open);
    document.getElementById('btn-tab').addEventListener('click', open);
    document.getElementById('btn-mx').addEventListener('click', close);
    document.getElementById('btn-cancel').addEventListener('click', close);
    modal.addEventListener('click', e => { if (e.target === modal) close(); });
    
    // Esc key to close
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && modal.classList.contains('show')) close();
    });
    
    // Simple Focus Trap
    const focusable = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const firstFocusable = focusable[0];
    const lastFocusable = focusable[focusable.length - 1];
    modal.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        if (e.shiftKey && document.activeElement === firstFocusable) {
          lastFocusable.focus();
          e.preventDefault();
        } else if (!e.shiftKey && document.activeElement === lastFocusable) {
          firstFocusable.focus();
          e.preventDefault();
        }
      }
    });

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

    // Start loading animation immediately
    const iv = setInterval(() => {
      if (current > 0 && current < steps.length - 1) { 
        steps[current-1].classList.remove('active'); 
        steps[current-1].classList.add('done'); 
        steps[current-1].querySelector('.check').textContent = '✓'; 
      }
      if (current < steps.length - 1) {
        steps[current].classList.add('active'); 
        steps[current].querySelector('.check').textContent = '◉';
        fill.style.width = ((current+1)/steps.length*100) + '%'; 
        current++;
      }
    }, 1500); // Progress every 1.5s but stop before the last step

    try {
      const result = await API.post('/workspaces', { repo_url: repoUrl, branch });
      clearInterval(iv);
      if (result && result.status === 'ok') {
        // Finish remaining steps instantly
        for (let i = current; i < steps.length; i++) {
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
    } catch(e) { 
      clearInterval(iv);
      // Fall through to error handling
      Toast.error(`Ingestion failed: ${e.message}`);
      this._reset();
    }
  },

  _reset() {
    const prog = document.getElementById('iprog');
    prog.classList.remove('show');
    prog.querySelectorAll('.prog-step').forEach(s => { s.classList.remove('done','active'); s.querySelector('.check').textContent = '○'; });
    document.getElementById('pfill').style.width = '0%';
    document.getElementById('btn-ingest').disabled = false;
  },
};
