/* ═══════════════════════════════════════════════════════════
   GraphCodeRAG — D3.js Knowledge Graph (Overlay Panel)
   ═══════════════════════════════════════════════════════════ */

const Graph = {
  svg: null,
  sim: null,
  zoom: null,
  g: null,
  nodeEls: null,
  edgeEls: null,
  currentFilter: 'all',
  pendingData: null,   // Stored graph data for lazy rendering
  rendered: false,

  COLORS: {
    function: { fill: '#2563eb', grad: ['#60a5fa', '#2563eb'], stroke: 'rgba(96,165,250,0.3)' },
    class:    { fill: '#7c3aed', grad: ['#c084fc', '#7c3aed'], stroke: 'rgba(192,132,252,0.3)' },
    module:   { fill: '#16a34a', grad: ['#4ade80', '#16a34a'], stroke: 'rgba(74,222,128,0.3)' },
  },

  EDGE_MAP: { calls: 'call', CALLS: 'call', imports: 'import', IMPORTS: 'import', contains: 'contain', CONTAINS: 'contain' },

  init() {
    // Open/close overlay
    document.getElementById('ab-graph').addEventListener('click', () => this.open());
    document.getElementById('graph-close').addEventListener('click', () => this.close());
    document.getElementById('graph-overlay').addEventListener('click', (e) => {
      if (e.target === document.getElementById('graph-overlay')) this.close();
    });

    // Edge filter pills
    document.querySelectorAll('.gf-opt').forEach(o => {
      o.addEventListener('click', () => {
        document.querySelectorAll('.gf-opt').forEach(x => x.classList.remove('on'));
        o.classList.add('on');
        this.currentFilter = o.dataset.f;
        this._applyEdgeFilter();
      });
    });

    // Zoom buttons
    document.getElementById('g-zoom-in').addEventListener('click', () => this._zoomBy(1.3));
    document.getElementById('g-zoom-out').addEventListener('click', () => this._zoomBy(0.7));
    document.getElementById('g-reset').addEventListener('click', () => this._resetZoom());

    // Events — store data for lazy render
    Events.on('graph:loaded', (data) => {
      this.pendingData = data;
      this.rendered = false;  // Force re-render on next open
    });
    Events.on('graph:highlight', (nodeIds) => this._highlightNodes(nodeIds));
  },

  open() {
    const overlay = document.getElementById('graph-overlay');
    overlay.style.display = 'flex';
    // Render after overlay is visible (needs dimensions)
    requestAnimationFrame(() => {
      if (this.pendingData && !this.rendered) {
        this.render(this.pendingData);
        this.rendered = true;
      } else if (!this.pendingData) {
        // Fetch if we don't have data yet
        API.get('/graph').then(data => {
          if (data) {
            this.pendingData = data;
            this.render(data);
            this.rendered = true;
          }
        });
      }
    });
  },

  close() {
    document.getElementById('graph-overlay').style.display = 'none';
    if (this.sim) this.sim.stop();
  },

  render(data) {
    const container = document.getElementById('graph-area');
    d3.select('#graph-area > svg.graph-svg').remove();

    const width = container.clientWidth || 900;
    const height = container.clientHeight || 550;

    this.svg = d3.select('#graph-area')
      .append('svg')
      .attr('class', 'graph-svg')
      .attr('width', width)
      .attr('height', height);

    this.zoom = d3.zoom()
      .scaleExtent([0.3, 4])
      .on('zoom', (e) => this.g.attr('transform', e.transform));
    this.svg.call(this.zoom);

    this.g = this.svg.append('g');

    // Gradients
    const defs = this.svg.append('defs');
    Object.entries(this.COLORS).forEach(([type, c]) => {
      const grad = defs.append('radialGradient')
        .attr('id', `grad-${type}`)
        .attr('cx', '35%').attr('cy', '35%').attr('r', '65%');
      grad.append('stop').attr('offset', '0%').attr('stop-color', c.grad[0]);
      grad.append('stop').attr('offset', '100%').attr('stop-color', c.grad[1]);
    });

    // Normalize API data
    const nodes = data.nodes.map(n => {
      const type = (n.type || n.label || 'function').toLowerCase();
      const fullName = n.id || n.name;
      const file = n.file || '';
      // Build a meaningful display name: "ClassName" for classes, "method()" for functions
      let displayName = n.display || fullName;
      // If name is too short/ambiguous (1-2 chars), add file context
      if (displayName.replace('()', '').length <= 2 && file) {
        displayName = file.replace('.py', '') + '.' + displayName;
      }
      return {
        id: fullName,
        type: type,
        file: file,
        displayName: displayName,
        parent: n.parent || '',
        radius: n.size || (type === 'class' ? 26 : (type === 'module' ? 22 : 16)),
      };
    });
    const edges = data.edges.map(e => ({
      source: e.source,
      target: e.target,
      type: e.type || e.rel || 'calls',
    }));

    // Force simulation
    this.sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(110))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d => d.radius + 18));

    // Edges
    this.edgeEls = this.g.selectAll('.graph-edge')
      .data(edges).enter().append('line')
      .attr('class', d => {
        const t = this.EDGE_MAP[d.type] || 'call';
        return `graph-edge edge-${t}`;
      });

    // Nodes
    this.nodeEls = this.g.selectAll('.graph-node')
      .data(nodes).enter().append('g')
      .attr('class', d => `graph-node ${d.id === AppState.selectedNode ? 'selected' : ''}`)
      .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) this.sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) this.sim.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    this.nodeEls.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => `url(#grad-${d.type || 'function'})`)
      .attr('stroke', d => (this.COLORS[d.type] || this.COLORS.function).stroke)
      .attr('stroke-width', 2);

    this.nodeEls.append('text')
      .attr('dy', d => d.radius + 14)
      .text(d => d.displayName);

    // Click → select node & show code
    this.nodeEls.on('click', (e, d) => {
      e.stopPropagation();
      this.nodeEls.classed('selected', false);
      d3.select(e.currentTarget).classed('selected', true);
      AppState.selectedNode = d.id;
      Events.emit('node:selected', d);
    });

    // Tick
    this.sim.on('tick', () => {
      this.edgeEls
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      this.nodeEls.attr('transform', d => `translate(${d.x},${d.y})`);
    });
  },

  _applyEdgeFilter() {
    if (!this.edgeEls) return;
    this.edgeEls.classed('dimmed', d => {
      if (this.currentFilter === 'all') return false;
      const t = this.EDGE_MAP[d.type] || 'call';
      return t !== this.currentFilter;
    });
  },

  _zoomBy(factor) {
    if (!this.svg || !this.zoom) return;
    this.svg.transition().duration(300).call(this.zoom.scaleBy, factor);
  },

  _resetZoom() {
    if (!this.svg || !this.zoom) return;
    this.svg.transition().duration(500).call(this.zoom.transform, d3.zoomIdentity);
  },

  _highlightNodes(nodeIds) {
    if (!this.nodeEls) return;
    const idSet = new Set(nodeIds || []);
    this.nodeEls.classed('glow', d => idSet.has(d.id));
  },

  selectNode(nodeId) {
    if (!this.nodeEls) return;
    this.nodeEls.classed('selected', d => d.id === nodeId);
    AppState.selectedNode = nodeId;
  },
};
