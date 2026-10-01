/* ================================================================
   Decision Tree Editor – Visual questionnaire builder
   Supports: text, yes_no, list, single_select, multi_select,
             branch, for_each, end
   Generates JSON compatible with /questionnarie_decision_tree
   ================================================================ */
(function () {
  'use strict';

  // ── Constants ──
  const NODE_TYPES = ['text','yes_no','list','single_select','multi_select','branch','for_each','end'];
  const CONDITION_TYPES = ['equals','in','contains_any','contains_all','is_true','is_false','non_empty'];
  const EFFECT_OPS = ['set','append','extend_set','merge_map'];

  // ── State ──
  let nodes = {};          // id -> { id, type, prompt, next, options, ... , _x, _y }
  let startNodeId = null;
  let selectedNodeId = null;
  let nextNodeCounter = 1;

  // Canvas pan/zoom
  let panX = 0, panY = 0, zoom = 1;
  let isPanning = false, panStartX = 0, panStartY = 0;

  // Dragging nodes
  let dragNode = null, dragOffX = 0, dragOffY = 0;

  // Connection drawing
  let isConnecting = false, connectFromId = null, connectMouseX = 0, connectMouseY = 0;

  // ── DOM refs ──
  const canvasArea     = document.getElementById('canvasArea');
  const flowCanvas     = document.getElementById('flowCanvas');
  const nodesContainer = document.getElementById('nodesContainer');
  const sidebarBody    = document.getElementById('sidebarBody');

  // File ops
  const treeFileSelect = document.getElementById('treeFileSelect');
  const btnLoadTree    = document.getElementById('btnLoadTree');
  const treeSaveName   = document.getElementById('treeSaveName');
  const btnSaveTree    = document.getElementById('btnSaveTree');
  const treeStartNode  = document.getElementById('treeStartNode');
  const btnSetStart    = document.getElementById('btnSetStart');
  const editorTreeName = document.getElementById('editorTreeName');

  // Node props
  const nodePropsPanel      = document.getElementById('nodePropsPanel');
  const noNodeSelected      = document.getElementById('noNodeSelected');
  const propNodeId           = document.getElementById('propNodeId');
  const propNodeType         = document.getElementById('propNodeType');
  const propNodePrompt       = document.getElementById('propNodePrompt');
  const propNodeNext         = document.getElementById('propNodeNext');
  const propOptionsSection   = document.getElementById('propOptionsSection');
  const propOptionsList      = document.getElementById('propOptionsList');
  const propNewOption        = document.getElementById('propNewOption');
  const btnAddOption         = document.getElementById('btnAddOption');
  const propOptionsFromAnswer= document.getElementById('propOptionsFromAnswer');
  const propSplit            = document.getElementById('propSplit');
  const propBranchSection    = document.getElementById('propBranchSection');
  const propUseAnswerFrom    = document.getElementById('propUseAnswerFrom');
  const propBranchRules      = document.getElementById('propBranchRules');
  const btnAddBranchRule     = document.getElementById('btnAddBranchRule');
  const propForEachSection   = document.getElementById('propForEachSection');
  const propSource           = document.getElementById('propSource');
  const propItemVar          = document.getElementById('propItemVar');
  const propAfter            = document.getElementById('propAfter');
  const propEffectsSection   = document.getElementById('propEffectsSection');
  const propEffectsList      = document.getElementById('propEffectsList');
  const btnAddEffect         = document.getElementById('btnAddEffect');
  const btnApplyProps        = document.getElementById('btnApplyProps');
  const btnDeleteNode        = document.getElementById('btnDeleteNode');

  // Canvas toolbar
  const btnZoomIn     = document.getElementById('btnZoomIn');
  const btnZoomOut    = document.getElementById('btnZoomOut');
  const btnZoomReset  = document.getElementById('btnZoomReset');
  const btnAutoLayout = document.getElementById('btnAutoLayout');
  const btnFitView    = document.getElementById('btnFitView');
  const btnPreviewJson= document.getElementById('btnPreviewJson');
  const btnCopyJson   = document.getElementById('btnCopyJson');

  // ══════════════════════════════════════════════════
  //  UTILITY HELPERS
  // ══════════════════════════════════════════════════

  function genId(type) {
    let base = type + '_' + nextNodeCounter;
    while (nodes[base]) { nextNodeCounter++; base = type + '_' + nextNodeCounter; }
    nextNodeCounter++;
    return base;
  }

  function toast(msg, variant) {
    variant = variant || 'info';
    const el = document.createElement('div');
    el.className = `alert alert-${variant} alert-dismissible fade show py-2 px-3`;
    el.style.cssText = 'font-size:.82rem;min-width:260px;box-shadow:0 4px 12px rgba(0,0,0,.12)';
    el.innerHTML = msg + '<button type="button" class="btn-close btn-close-sm" data-bs-dismiss="alert"></button>';
    document.getElementById('toastContainer').appendChild(el);
    setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.remove(), 300); }, 3500);
  }

  function nodeIdsExcept(excludeId) {
    return Object.keys(nodes).filter(id => id !== excludeId);
  }

  function buildNodeSelectOptions(selectEl, currentVal, excludeId) {
    const ids = nodeIdsExcept(excludeId);
    selectEl.innerHTML = '<option value="">— none —</option>' +
      ids.map(id => `<option value="${id}"${id === currentVal ? ' selected' : ''}>${id}</option>`).join('');
  }

  // ══════════════════════════════════════════════════
  //  TREE ↔ JSON
  // ══════════════════════════════════════════════════

  function treeToJson() {
    const out = { start: startNodeId, nodes: {} };
    for (const id in nodes) {
      const n = nodes[id];
      const node = { id: n.id, type: n.type, prompt: n.prompt || '' };
      // next
      if (n.type === 'branch' && Array.isArray(n.branchRules) && n.branchRules.length) {
        node.next = n.branchRules.map(r => {
          if (r.default) return { default: true, goto: r.goto || '' };
          const rule = { when: {}, goto: r.goto || '' };
          if (r.condType === 'is_true') rule.when.is_true = true;
          else if (r.condType === 'is_false') rule.when.is_false = true;
          else if (r.condType === 'non_empty') rule.when.non_empty = true;
          else if (r.condType === 'in' || r.condType === 'contains_any' || r.condType === 'contains_all') {
            rule.when[r.condType] = (r.condValue || '').split(',').map(s => s.trim()).filter(Boolean);
          } else {
            rule.when[r.condType || 'equals'] = r.condValue || '';
          }
          return rule;
        });
      } else if (n.next) {
        node.next = n.next;
      }
      // options
      if (n.options && n.options.length) node.options = n.options;
      if (n.options_from_answer_of) node.options_from_answer_of = n.options_from_answer_of;
      if (n.split) node.split = n.split;
      if (n.use_answer_from) node.use_answer_from = n.use_answer_from;
      if (n.effects && n.effects.length) node.effects = n.effects;
      if (n.source) node.source = n.source;
      if (n.item_var) node.item_var = n.item_var;
      if (n.after) node.after = n.after;
      out.nodes[id] = node;
    }
    return out;
  }

  function loadTreeFromJson(tree) {
    nodes = {};
    startNodeId = tree.start || null;
    const raw = tree.nodes || {};
    const ids = Object.keys(raw);
    // Assign positions: auto-layout if no _x/_y
    ids.forEach((id, idx) => {
      const n = raw[id];
      const node = {
        id: n.id || id,
        type: n.type || 'text',
        prompt: n.prompt || '',
        next: null,
        options: n.options || [],
        options_from_answer_of: n.options_from_answer_of || '',
        split: n.split || '',
        use_answer_from: n.use_answer_from || '',
        effects: n.effects || [],
        source: n.source || '',
        item_var: n.item_var || '',
        after: n.after || '',
        branchRules: [],
        _x: n._x || 80,
        _y: n._y || 80
      };
      // Parse next
      if (n.type === 'branch' && Array.isArray(n.next)) {
        node.branchRules = n.next.map(rule => {
          if (rule.default) return { default: true, goto: rule.goto || '' };
          const when = rule.when || {};
          let condType = 'equals', condValue = '';
          for (const ct of CONDITION_TYPES) {
            if (ct in when) {
              condType = ct;
              const v = when[ct];
              condValue = Array.isArray(v) ? v.join(', ') : String(v === true ? '' : v);
              break;
            }
          }
          return { default: false, condType, condValue, goto: rule.goto || '' };
        });
        node.next = null;
      } else if (typeof n.next === 'string') {
        node.next = n.next;
      }
      nodes[id] = node;
    });
    // Auto-layout
    autoLayoutNodes();
    selectedNodeId = null;
    renderAll();
  }

  // ══════════════════════════════════════════════════
  //  AUTO LAYOUT (topological/depth-first)
  // ══════════════════════════════════════════════════

  function autoLayoutNodes() {
    if (!Object.keys(nodes).length) return;
    const visited = new Set();
    const levels = {};  // id -> { col, row }
    let maxCol = 0;

    function getSuccessors(id) {
      const n = nodes[id]; if (!n) return [];
      const out = [];
      if (n.type === 'branch' && n.branchRules) {
        n.branchRules.forEach(r => { if (r.goto && nodes[r.goto]) out.push(r.goto); });
      }
      if (n.next && nodes[n.next]) out.push(n.next);
      if (n.after && nodes[n.after]) out.push(n.after);
      return [...new Set(out)];
    }

    function layout(id, row, col) {
      if (visited.has(id)) return row;
      visited.add(id);
      levels[id] = { col, row };
      if (col > maxCol) maxCol = col;
      const succs = getSuccessors(id);
      let nextRow = row;
      succs.forEach((sid, i) => {
        nextRow = layout(sid, nextRow, col + 1);
        if (i < succs.length - 1) nextRow++;
      });
      return Math.max(nextRow, row);
    }

    const start = startNodeId && nodes[startNodeId] ? startNodeId : Object.keys(nodes)[0];
    let currentRow = layout(start, 0, 0);

    // Layout disconnected nodes
    for (const id in nodes) {
      if (!visited.has(id)) {
        currentRow++;
        layout(id, currentRow, 0);
      }
    }

    const colW = 280, rowH = 120, padX = 60, padY = 40;
    for (const id in levels) {
      nodes[id]._x = padX + levels[id].col * colW;
      nodes[id]._y = padY + levels[id].row * rowH;
    }
  }

  // ══════════════════════════════════════════════════
  //  RENDER: Canvas nodes + SVG connections
  // ══════════════════════════════════════════════════

  function renderAll() {
    renderCanvasNodes();
    renderConnections();
    updateStartNodeInput();
  }

  function renderCanvasNodes() {
    nodesContainer.innerHTML = '';
    for (const id in nodes) {
      const n = nodes[id];
      const el = document.createElement('div');
      el.className = 'flow-node' + (id === selectedNodeId ? ' selected' : '');
      el.dataset.nodeId = id;
      el.style.left = (n._x * zoom + panX) + 'px';
      el.style.top = (n._y * zoom + panY) + 'px';
      el.style.transform = `scale(${zoom})`;
      el.style.transformOrigin = 'top left';

      const isStart = id === startNodeId;
      const startBadge = isStart ? '<span class="badge bg-success ms-1" style="font-size:.6rem">START</span>' : '';

      el.innerHTML = `
        <button class="delete-node" title="Delete node">&times;</button>
        <span class="node-type t-${n.type}">${n.type}</span>${startBadge}
        <div class="node-id">${n.id}</div>
        <div class="node-prompt">${escHtml(n.prompt || '—')}</div>
        <div class="port port-in" data-port="in" title="Drag here to connect"></div>
        <div class="port port-out" data-port="out" title="Drag from here to connect"></div>
      `;

      // Node click → select
      el.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('port') || e.target.classList.contains('delete-node')) return;
        selectNode(id);
        dragNode = id;
        const canvasRect = canvasArea.getBoundingClientRect();
        // Calculate offset in canvas coordinates, accounting for zoom/pan
        const canvasX = (e.clientX - canvasRect.left - panX) / zoom;
        const canvasY = (e.clientY - canvasRect.top - panY) / zoom;
        dragOffX = canvasX - nodes[id]._x;
        dragOffY = canvasY - nodes[id]._y;
        e.stopPropagation();
      });

      // Delete button
      el.querySelector('.delete-node').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteNode(id);
      });

      // Port out → start connection
      el.querySelector('.port-out').addEventListener('mousedown', (e) => {
        e.stopPropagation();
        isConnecting = true;
        connectFromId = id;
        connectMouseX = e.clientX;
        connectMouseY = e.clientY;
      });

      nodesContainer.appendChild(el);
    }
  }

  function escHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function renderConnections() {
    flowCanvas.innerHTML = '';
    // Defs for arrowheads
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = `
      <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10 z" fill="#94a3b8"/>
      </marker>
      <marker id="arrow-highlight" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
        <path d="M0 0 L10 5 L0 10 z" fill="#3b82f6"/>
      </marker>`;
    flowCanvas.appendChild(defs);

    for (const id in nodes) {
      const n = nodes[id];
      const targets = [];

      if (n.type === 'branch' && n.branchRules) {
        n.branchRules.forEach((r, i) => {
          if (r.goto && nodes[r.goto]) {
            const label = r.default ? 'default' : (r.condType || '');
            targets.push({ to: r.goto, label, color: '#f59e0b', idx: i });
          }
        });
      }
      if (n.next && nodes[n.next]) {
        targets.push({ to: n.next, label: '', color: '#94a3b8' });
      }
      if (n.type === 'for_each') {
        if (n.after && nodes[n.after]) targets.push({ to: n.after, label: 'after', color: '#8b5cf6' });
      }

      targets.forEach(t => {
        drawConnection(id, t.to, t.label, t.color);
      });
    }

    // Temp connection line while dragging
    if (isConnecting && connectFromId) {
      drawTempConnection();
    }
  }

  function getNodeCenter(id) {
    const n = nodes[id]; if (!n) return { x: 0, y: 0 };
    const el = nodesContainer.querySelector(`[data-node-id="${id}"]`);
    if (!el) return { x: n._x * zoom + panX + 90 * zoom, y: n._y * zoom + panY + 40 * zoom };
    const w = el.offsetWidth * zoom;
    const h = el.offsetHeight * zoom;
    return {
      x: n._x * zoom + panX + w / 2,
      y: n._y * zoom + panY + h / 2
    };
  }

  function getNodeBottom(id) {
    const n = nodes[id]; if (!n) return { x: 0, y: 0 };
    const el = nodesContainer.querySelector(`[data-node-id="${id}"]`);
    const w = el ? el.offsetWidth * zoom : 180 * zoom;
    const h = el ? el.offsetHeight * zoom : 80 * zoom;
    return {
      x: n._x * zoom + panX + w / 2,
      y: n._y * zoom + panY + h
    };
  }

  function getNodeTop(id) {
    const n = nodes[id]; if (!n) return { x: 0, y: 0 };
    const el = nodesContainer.querySelector(`[data-node-id="${id}"]`);
    const w = el ? el.offsetWidth * zoom : 180 * zoom;
    return {
      x: n._x * zoom + panX + w / 2,
      y: n._y * zoom + panY
    };
  }

  function drawConnection(fromId, toId, label, color) {
    const from = getNodeBottom(fromId);
    const to = getNodeTop(toId);
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const cp = Math.max(Math.abs(dy) * 0.5, 30);

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M${from.x},${from.y} C${from.x},${from.y + cp} ${to.x},${to.y - cp} ${to.x},${to.y}`);
    path.setAttribute('stroke', color || '#94a3b8');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('fill', 'none');
    path.setAttribute('marker-end', 'url(#arrow)');
    flowCanvas.appendChild(path);

    if (label) {
      const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', mid.x + 4);
      text.setAttribute('y', mid.y - 4);
      text.setAttribute('font-size', 10 * zoom);
      text.setAttribute('fill', color || '#64748b');
      text.setAttribute('font-family', 'Inter, sans-serif');
      text.textContent = label;
      flowCanvas.appendChild(text);
    }
  }

  function drawTempConnection() {
    const from = getNodeBottom(connectFromId);
    const canvasRect = canvasArea.getBoundingClientRect();
    const toX = connectMouseX - canvasRect.left;
    const toY = connectMouseY - canvasRect.top;
    const cp = Math.max(Math.abs(toY - from.y) * 0.5, 30);

    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', `M${from.x},${from.y} C${from.x},${from.y + cp} ${toX},${toY - cp} ${toX},${toY}`);
    path.setAttribute('stroke', '#3b82f6');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('stroke-dasharray', '6,4');
    path.setAttribute('fill', 'none');
    flowCanvas.appendChild(path);
  }

  // ══════════════════════════════════════════════════
  //  NODE CRUD
  // ══════════════════════════════════════════════════

  function addNode(type) {
    const id = genId(type);
    const canvasRect = canvasArea.getBoundingClientRect();
    const cx = (canvasRect.width / 2 - panX) / zoom;
    const cy = (canvasRect.height / 2 - panY) / zoom;
    // Offset randomly to avoid stacking
    const offX = (Math.random() - 0.5) * 100;
    const offY = (Math.random() - 0.5) * 100;

    nodes[id] = {
      id,
      type,
      prompt: type === 'end' ? 'Review & Submit' : '',
      next: '',
      options: [],
      options_from_answer_of: '',
      split: '',
      use_answer_from: '',
      effects: [],
      source: '',
      item_var: '',
      after: '',
      branchRules: type === 'branch' ? [{ default: true, goto: '' }] : [],
      _x: Math.max(20, cx + offX),
      _y: Math.max(20, cy + offY)
    };

    if (!startNodeId) startNodeId = id;
    selectNode(id);
    renderAll();
    toast(`Added <b>${type}</b> node: ${id}`, 'success');
  }

  function deleteNode(id) {
    if (!confirm(`Delete node "${id}"?`)) return;
    // Remove references to this node
    for (const oid in nodes) {
      const n = nodes[oid];
      if (n.next === id) n.next = '';
      if (n.after === id) n.after = '';
      if (n.source === id) n.source = '';
      if (n.options_from_answer_of === id) n.options_from_answer_of = '';
      if (n.use_answer_from === id) n.use_answer_from = '';
      if (n.branchRules) {
        n.branchRules.forEach(r => { if (r.goto === id) r.goto = ''; });
      }
    }
    delete nodes[id];
    if (startNodeId === id) startNodeId = Object.keys(nodes)[0] || null;
    if (selectedNodeId === id) { selectedNodeId = null; showPropsPanel(false); }
    renderAll();
    toast(`Deleted node: ${id}`, 'warning');
  }

  function selectNode(id) {
    selectedNodeId = id;
    renderCanvasNodes();
    renderConnections();
    showPropsPanel(true);
    populatePropsPanel(id);
  }

  function deselectNode() {
    selectedNodeId = null;
    renderCanvasNodes();
    renderConnections();
    showPropsPanel(false);
  }

  // ══════════════════════════════════════════════════
  //  PROPERTIES PANEL
  // ══════════════════════════════════════════════════

  function showPropsPanel(show) {
    nodePropsPanel.style.display = show ? 'block' : 'none';
    noNodeSelected.style.display = show ? 'none' : 'block';
  }

  function populatePropsPanel(id) {
    const n = nodes[id]; if (!n) return;
    propNodeId.value = n.id;
    propNodeType.value = n.type;
    propNodePrompt.value = n.prompt || '';

    // Next dropdown
    buildNodeSelectOptions(propNodeNext, n.next || '', id);

    // Show/hide sections based on type
    const isSelect = ['single_select', 'multi_select', 'list'].includes(n.type);
    const isBranch = n.type === 'branch';
    const isForEach = n.type === 'for_each';

    propOptionsSection.style.display = isSelect ? 'block' : 'none';
    propBranchSection.style.display = isBranch ? 'block' : 'none';
    propForEachSection.style.display = isForEach ? 'block' : 'none';
    propEffectsSection.style.display = isBranch || isForEach ? 'none' : 'block';

    // Options
    if (isSelect) {
      renderOptionsList(n.options || []);
      buildNodeSelectOptions(propOptionsFromAnswer, n.options_from_answer_of || '', id);
      propSplit.value = n.split || '';
    }

    // Branch rules
    if (isBranch) {
      buildNodeSelectOptions(propUseAnswerFrom, n.use_answer_from || '', id);
      renderBranchRules(n.branchRules || []);
    }

    // For Each
    if (isForEach) {
      buildNodeSelectOptions(propSource, n.source || '', id);
      propItemVar.value = n.item_var || '';
      buildNodeSelectOptions(propAfter, n.after || '', id);
    }

    // Effects
    if (!isBranch && !isForEach) {
      renderEffectsList(n.effects || []);
    }
  }

  // ── Options list ──
  function renderOptionsList(options) {
    propOptionsList.innerHTML = '';
    options.forEach((opt, i) => {
      const row = document.createElement('div');
      row.className = 'd-flex gap-1 align-items-center mb-1';
      row.innerHTML = `
        <input type="text" class="form-control form-control-sm opt-input" value="${escHtml(opt)}" data-idx="${i}">
        <button class="btn btn-sm btn-outline-danger opt-del" data-idx="${i}" title="Remove">&times;</button>
      `;
      propOptionsList.appendChild(row);
    });
    // Delete handlers
    propOptionsList.querySelectorAll('.opt-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.idx);
        const n = nodes[selectedNodeId]; if (!n) return;
        n.options.splice(idx, 1);
        renderOptionsList(n.options);
      });
    });
  }

  btnAddOption.addEventListener('click', () => {
    const val = propNewOption.value.trim();
    if (!val) return;
    const n = nodes[selectedNodeId]; if (!n) return;
    if (!n.options) n.options = [];
    n.options.push(val);
    propNewOption.value = '';
    renderOptionsList(n.options);
  });

  // ── Branch rules ──
  function renderBranchRules(rules) {
    propBranchRules.innerHTML = '';
    rules.forEach((rule, i) => {
      const row = document.createElement('div');
      row.className = 'rule-row';
      if (rule.default) {
        row.innerHTML = `
          <div class="d-flex gap-2 align-items-center">
            <span class="badge bg-secondary">DEFAULT</span>
            <select class="form-select form-select-sm rule-goto" data-idx="${i}">
              <option value="">— goto —</option>
              ${nodeIdsExcept(selectedNodeId).map(nid => `<option value="${nid}"${nid === rule.goto ? ' selected' : ''}>${nid}</option>`).join('')}
            </select>
            <button class="btn btn-sm btn-outline-danger rule-del" data-idx="${i}">&times;</button>
          </div>`;
      } else {
        row.innerHTML = `
          <div class="d-flex gap-2 align-items-center mb-1">
            <select class="form-select form-select-sm rule-cond-type" data-idx="${i}" style="max-width:140px">
              ${CONDITION_TYPES.map(ct => `<option value="${ct}"${ct === rule.condType ? ' selected' : ''}>${ct}</option>`).join('')}
            </select>
            <input type="text" class="form-control form-control-sm rule-cond-value" data-idx="${i}" placeholder="value (comma-sep for arrays)" value="${escHtml(rule.condValue || '')}">
          </div>
          <div class="d-flex gap-2 align-items-center">
            <span style="font-size:.7rem;color:#64748b">goto:</span>
            <select class="form-select form-select-sm rule-goto" data-idx="${i}">
              <option value="">— goto —</option>
              ${nodeIdsExcept(selectedNodeId).map(nid => `<option value="${nid}"${nid === rule.goto ? ' selected' : ''}>${nid}</option>`).join('')}
            </select>
            <button class="btn btn-sm btn-outline-danger rule-del" data-idx="${i}">&times;</button>
          </div>`;
      }
      propBranchRules.appendChild(row);
    });
    propBranchRules.querySelectorAll('.rule-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const n = nodes[selectedNodeId]; if (!n) return;
        n.branchRules.splice(parseInt(btn.dataset.idx), 1);
        renderBranchRules(n.branchRules);
      });
    });
  }

  btnAddBranchRule.addEventListener('click', () => {
    const n = nodes[selectedNodeId]; if (!n) return;
    if (!n.branchRules) n.branchRules = [];
    n.branchRules.splice(n.branchRules.length - (n.branchRules.some(r => r.default) ? 1 : 0), 0,
      { default: false, condType: 'equals', condValue: '', goto: '' });
    renderBranchRules(n.branchRules);
  });

  // ── Effects ──
  function renderEffectsList(effects) {
    propEffectsList.innerHTML = '';
    effects.forEach((eff, i) => {
      const row = document.createElement('div');
      row.className = 'effect-row';
      const isFromAnswer = eff.from_answer === true;
      const valueStr = isFromAnswer ? '' : (typeof eff.value === 'object' ? JSON.stringify(eff.value) : (eff.value || ''));
      row.innerHTML = `
        <select class="form-select eff-op" data-idx="${i}" style="max-width:110px">
          ${EFFECT_OPS.map(o => `<option value="${o}"${o === eff.op ? ' selected' : ''}>${o}</option>`).join('')}
        </select>
        <input type="text" class="form-control eff-path" data-idx="${i}" placeholder="path" value="${escHtml(eff.path || '')}">
        <input type="text" class="form-control eff-value" data-idx="${i}" placeholder="value / JSON" value="${escHtml(valueStr)}">
        <label class="form-check-label" style="font-size:.7rem;white-space:nowrap">
          <input type="checkbox" class="form-check-input eff-from-answer" data-idx="${i}" ${isFromAnswer ? 'checked' : ''}> from_answer
        </label>
        <button class="btn btn-sm btn-outline-danger eff-del" data-idx="${i}">&times;</button>
      `;
      propEffectsList.appendChild(row);
    });
    propEffectsList.querySelectorAll('.eff-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const n = nodes[selectedNodeId]; if (!n) return;
        n.effects.splice(parseInt(btn.dataset.idx), 1);
        renderEffectsList(n.effects);
      });
    });
  }

  btnAddEffect.addEventListener('click', () => {
    const n = nodes[selectedNodeId]; if (!n) return;
    if (!n.effects) n.effects = [];
    n.effects.push({ op: 'set', path: '', from_answer: true });
    renderEffectsList(n.effects);
  });

  // ── Apply changes ──
  btnApplyProps.addEventListener('click', () => {
    if (!selectedNodeId || !nodes[selectedNodeId]) return;
    const n = nodes[selectedNodeId];
    const newId = propNodeId.value.trim();
    const oldId = selectedNodeId;

    // Validate ID
    if (!newId) { toast('Node ID cannot be empty', 'danger'); return; }
    if (newId !== oldId && nodes[newId]) { toast('Node ID already exists', 'danger'); return; }

    // Update basic props
    n.type = propNodeType.value;
    n.prompt = propNodePrompt.value;
    n.next = propNodeNext.value || '';

    // Options
    if (['single_select', 'multi_select', 'list'].includes(n.type)) {
      const optInputs = propOptionsList.querySelectorAll('.opt-input');
      n.options = Array.from(optInputs).map(inp => inp.value.trim()).filter(Boolean);
      n.options_from_answer_of = propOptionsFromAnswer.value || '';
      n.split = propSplit.value.trim();
    }

    // Branch rules
    if (n.type === 'branch') {
      n.use_answer_from = propUseAnswerFrom.value || '';
      const ruleRows = propBranchRules.querySelectorAll('.rule-row');
      n.branchRules = [];
      ruleRows.forEach((row, i) => {
        const gotoSel = row.querySelector('.rule-goto');
        const condTypeSel = row.querySelector('.rule-cond-type');
        const condValInp = row.querySelector('.rule-cond-value');
        if (row.querySelector('.badge')) {
          n.branchRules.push({ default: true, goto: gotoSel?.value || '' });
        } else {
          n.branchRules.push({
            default: false,
            condType: condTypeSel?.value || 'equals',
            condValue: condValInp?.value || '',
            goto: gotoSel?.value || ''
          });
        }
      });
    }

    // For Each
    if (n.type === 'for_each') {
      n.source = propSource.value || '';
      n.item_var = propItemVar.value.trim() || '';
      n.after = propAfter.value || '';
    }

    // Effects
    if (n.type !== 'branch' && n.type !== 'for_each') {
      const effRows = propEffectsList.querySelectorAll('.effect-row');
      n.effects = [];
      effRows.forEach(row => {
        const eff = {
          op: row.querySelector('.eff-op')?.value || 'set',
          path: row.querySelector('.eff-path')?.value || ''
        };
        const fromAns = row.querySelector('.eff-from-answer')?.checked;
        if (fromAns) {
          eff.from_answer = true;
        } else {
          let val = row.querySelector('.eff-value')?.value || '';
          try { val = JSON.parse(val); } catch (e) { /* keep as string */ }
          eff.value = val;
        }
        n.effects.push(eff);
      });
    }

    // Handle ID rename
    if (newId !== oldId) {
      n.id = newId;
      nodes[newId] = n;
      delete nodes[oldId];
      // Update all references
      for (const oid in nodes) {
        const o = nodes[oid];
        if (o.next === oldId) o.next = newId;
        if (o.after === oldId) o.after = newId;
        if (o.source === oldId) o.source = newId;
        if (o.options_from_answer_of === oldId) o.options_from_answer_of = newId;
        if (o.use_answer_from === oldId) o.use_answer_from = newId;
        if (o.branchRules) {
          o.branchRules.forEach(r => { if (r.goto === oldId) r.goto = newId; });
        }
      }
      if (startNodeId === oldId) startNodeId = newId;
      selectedNodeId = newId;
    }

    renderAll();
    populatePropsPanel(selectedNodeId);
    toast('Node updated', 'success');
  });

  // ── Delete button ──
  btnDeleteNode.addEventListener('click', () => {
    if (selectedNodeId) deleteNode(selectedNodeId);
  });

  // ── Type change → show/hide sections ──
  propNodeType.addEventListener('change', () => {
    const type = propNodeType.value;
    const isSelect = ['single_select', 'multi_select', 'list'].includes(type);
    propOptionsSection.style.display = isSelect ? 'block' : 'none';
    propBranchSection.style.display = type === 'branch' ? 'block' : 'none';
    propForEachSection.style.display = type === 'for_each' ? 'block' : 'none';
    propEffectsSection.style.display = (type === 'branch' || type === 'for_each') ? 'none' : 'block';
  });

  // ══════════════════════════════════════════════════
  //  CANVAS: Pan, Zoom, Drag, Connect
  // ══════════════════════════════════════════════════

  canvasArea.addEventListener('mousedown', (e) => {
    if (e.target === canvasArea || e.target === flowCanvas || e.target.tagName === 'path') {
      isPanning = true;
      panStartX = e.clientX - panX;
      panStartY = e.clientY - panY;
      deselectNode();
      e.preventDefault();
    }
  });

  window.addEventListener('mousemove', (e) => {
    if (isPanning) {
      panX = e.clientX - panStartX;
      panY = e.clientY - panStartY;
      renderAll();
    }
    if (dragNode && nodes[dragNode]) {
      const canvasRect = canvasArea.getBoundingClientRect();
      nodes[dragNode]._x = (e.clientX - canvasRect.left - dragOffX - panX) / zoom;
      nodes[dragNode]._y = (e.clientY - canvasRect.top - dragOffY - panY) / zoom;
      renderAll();
      // Re-select to keep panel in sync
      if (selectedNodeId === dragNode) {
        const el = nodesContainer.querySelector(`[data-node-id="${dragNode}"]`);
        if (el) el.classList.add('selected');
      }
    }
    if (isConnecting) {
      connectMouseX = e.clientX;
      connectMouseY = e.clientY;
      renderConnections();
    }
  });

  window.addEventListener('mouseup', (e) => {
    if (isConnecting && connectFromId) {
      // Find if we dropped on a port-in
      const target = document.elementFromPoint(e.clientX, e.clientY);
      const nodeEl = target?.closest('.flow-node');
      if (nodeEl && nodeEl.dataset.nodeId !== connectFromId) {
        const toId = nodeEl.dataset.nodeId;
        const fromNode = nodes[connectFromId];
        if (fromNode) {
          if (fromNode.type === 'branch') {
            if (!fromNode.branchRules) fromNode.branchRules = [];
            const hasDefault = fromNode.branchRules.some(r => r.default);
            fromNode.branchRules.splice(hasDefault ? fromNode.branchRules.length - 1 : fromNode.branchRules.length, 0,
              { default: false, condType: 'equals', condValue: '', goto: toId });
            toast(`Branch rule added → ${toId}`, 'success');
          } else {
            fromNode.next = toId;
            toast(`Connected ${connectFromId} → ${toId}`, 'success');
          }
          renderAll();
          if (selectedNodeId === connectFromId) populatePropsPanel(connectFromId);
        }
      }
      isConnecting = false;
      connectFromId = null;
      renderConnections();
    }
    isPanning = false;
    dragNode = null;
  });

  // Zoom
  canvasArea.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.08 : 0.08;
    zoom = Math.max(0.2, Math.min(3, zoom + delta));
    renderAll();
  }, { passive: false });

  btnZoomIn.addEventListener('click', () => { zoom = Math.min(3, zoom + 0.15); renderAll(); });
  btnZoomOut.addEventListener('click', () => { zoom = Math.max(0.2, zoom - 0.15); renderAll(); });
  btnZoomReset.addEventListener('click', () => { zoom = 1; panX = 0; panY = 0; renderAll(); });

  btnAutoLayout.addEventListener('click', () => {
    autoLayoutNodes();
    renderAll();
    toast('Auto-layout applied', 'info');
  });

  btnFitView.addEventListener('click', () => {
    if (!Object.keys(nodes).length) return;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const id in nodes) {
      const n = nodes[id];
      if (n._x < minX) minX = n._x;
      if (n._y < minY) minY = n._y;
      if (n._x + 200 > maxX) maxX = n._x + 200;
      if (n._y + 100 > maxY) maxY = n._y + 100;
    }
    const rect = canvasArea.getBoundingClientRect();
    const treeW = maxX - minX + 80;
    const treeH = maxY - minY + 80;
    zoom = Math.min(rect.width / treeW, rect.height / treeH, 1.5);
    zoom = Math.max(0.2, zoom);
    panX = (rect.width - treeW * zoom) / 2 - minX * zoom;
    panY = (rect.height - treeH * zoom) / 2 - minY * zoom;
    renderAll();
  });

  // ══════════════════════════════════════════════════
  //  ADD NODE BUTTONS
  // ══════════════════════════════════════════════════

  document.querySelectorAll('.add-node-btn').forEach(btn => {
    btn.addEventListener('click', () => addNode(btn.dataset.type));
  });

  // ══════════════════════════════════════════════════
  //  FILE OPERATIONS (Load / Save)
  // ══════════════════════════════════════════════════

  async function fetchTreeList() {
    try {
      const res = await fetch('/trees');
      const arr = await res.json();
      treeFileSelect.innerHTML = '<option value="">— New tree —</option>' +
        (arr || []).map(x => `<option value="${x}">${x}</option>`).join('');
    } catch (e) {
      treeFileSelect.innerHTML = '<option value="">— No trees —</option>';
    }
  }

  btnLoadTree.addEventListener('click', async () => {
    const name = treeFileSelect.value;
    if (!name) {
      // New tree
      nodes = {};
      startNodeId = null;
      selectedNodeId = null;
      treeSaveName.value = '';
      editorTreeName.textContent = 'New tree';
      showPropsPanel(false);
      renderAll();
      toast('New empty tree', 'info');
      return;
    }
    try {
      const res = await fetch(`/get_tree?name=${encodeURIComponent(name)}`);
      const tree = await res.json();
      loadTreeFromJson(tree);
      treeSaveName.value = name;
      treeStartNode.value = tree.start || '';
      editorTreeName.textContent = name;
      toast(`Loaded: ${name}`, 'success');
    } catch (e) {
      toast('Failed to load tree', 'danger');
    }
  });

  btnSaveTree.addEventListener('click', async () => {
    let name = treeSaveName.value.trim();
    if (!name) { toast('Enter a file name', 'danger'); return; }
    if (!name.endsWith('.json')) name += '.json';

    const tree = treeToJson();
    try {
      const res = await fetch('/dt/save_suggested_tree', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: name, tree })
      });
      const data = await res.json();
      if (!res.ok) { toast(data?.error || 'Save failed', 'danger'); return; }
      editorTreeName.textContent = name;
      await fetchTreeList();
      treeFileSelect.value = name;
      toast(`Saved: ${name}`, 'success');
    } catch (e) {
      toast('Save failed', 'danger');
    }
  });

  function updateStartNodeInput() {
    treeStartNode.value = startNodeId || '';
  }

  btnSetStart.addEventListener('click', () => {
    const val = treeStartNode.value.trim();
    if (val && !nodes[val]) { toast('Node not found: ' + val, 'danger'); return; }
    startNodeId = val || null;
    renderAll();
    toast('Start node set to: ' + (startNodeId || 'none'), 'info');
  });

  // ══════════════════════════════════════════════════
  //  JSON PREVIEW
  // ══════════════════════════════════════════════════

  let jsonModal = null;
  btnPreviewJson.addEventListener('click', () => {
    const tree = treeToJson();
    document.getElementById('jsonPreviewContent').textContent = JSON.stringify(tree, null, 2);
    if (!jsonModal) jsonModal = new bootstrap.Modal(document.getElementById('jsonPreviewModal'));
    jsonModal.show();
  });

  btnCopyJson.addEventListener('click', () => {
    const text = document.getElementById('jsonPreviewContent').textContent;
    navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard', 'success'))
      .catch(() => toast('Copy failed', 'danger'));
  });

  // ══════════════════════════════════════════════════
  //  INIT
  // ══════════════════════════════════════════════════

  (async () => {
    await fetchTreeList();
    renderAll();
  })();

})();
