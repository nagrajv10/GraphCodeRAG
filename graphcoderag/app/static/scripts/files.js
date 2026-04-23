/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — File Explorer
   ═══════════════════════════════════════════════════════════ */

const Files = {
  init() {
    // Search filtering
    document.getElementById('fsearch').addEventListener('input', function () {
      const q = this.value.toLowerCase();
      document.querySelectorAll('.file-item').forEach(f => {
        const name = f.querySelector('.file-name').textContent.toLowerCase();
        f.style.display = name.includes(q) ? 'flex' : 'none';
      });
    });

    Events.on('files:loaded', (files) => this.render(files));
    Events.on('stats:loaded', (stats) => this.updateStats(stats));
  },

  render(files) {
    const list = document.getElementById('flist');
    document.getElementById('file-count').textContent = files.length;

    list.innerHTML = files.map((f, i) => `
      <div class="file-item ${i === 0 ? 'active' : ''}" data-path="${f.path}" data-name="${f.name}">
        <span class="file-icon">&#128196;</span>
        <span class="file-name">${f.name}</span>
        <span class="file-badge">${f.chunks}</span>
      </div>`).join('');

    // Click handlers
    list.querySelectorAll('.file-item').forEach(item => {
      item.addEventListener('click', function () {
        list.querySelectorAll('.file-item').forEach(x => x.classList.remove('active'));
        this.classList.add('active');
        const filePath = this.dataset.path;
        const fileName = this.dataset.name;
        AppState.selectedFile = filePath;
        Events.emit('file:selected', { path: filePath, name: fileName });
      });
    });

    // Select first file by default
    if (files.length > 0) {
      AppState.selectedFile = files[0].path;
      Events.emit('file:selected', { path: files[0].path, name: files[0].name });
    }
  },

  updateStats(stats) {
    document.getElementById('stat-chunks').textContent = (stats.chunks || 0).toLocaleString();
    document.getElementById('stat-funcs').textContent = (stats.functions || 0).toLocaleString();
    document.getElementById('stat-edges').textContent = (stats.edges || 0).toLocaleString();
    document.getElementById('stat-classes').textContent = (stats.classes || 0).toLocaleString();
  },
};
