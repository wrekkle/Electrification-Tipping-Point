'use strict';
/* LabCharts —— 本项目前端专用的轻量 SVG/Canvas 图表组件（无外部依赖、无 CDN）。
   设计约束：仿真时钟 1Hz 快照 ⇒ 时间序列一律 step-after（不插值、不平滑）；
   更新时只改路径/点，不重建 SVG 骨架；坐标按容器宽度自适应（ResizeObserver）。 */
(function (global) {
  const NS = 'http://www.w3.org/2000/svg';

  const STATE = {
    0: { key: 'empty', label: '空闲', color: '#E9EFEC', ink: '#41534D' },
    1: { key: 'ice', label: '油车占用', color: '#3C4A4F', ink: '#FFFFFF' },
    2: { key: 'ev', label: '电车停车（未充电）', color: '#5F7F96', ink: '#FFFFFF' },
    3: { key: 'charging', label: '充电中', color: '#1F6F5C', ink: '#FFFFFF' },
    4: { key: 'completed', label: '充满仍占位', color: '#C98A16', ink: '#FFFFFF' }
  };
  const INK = '#172E2B', AXIS = '#7A8B85', GRID = '#E4EBE7', MUTED = '#70817D';

  function el(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    if (attrs) for (const key of Object.keys(attrs)) node.setAttribute(key, attrs[key]);
    if (parent) parent.append(node);
    return node;
  }
  function txt(parent, x, y, content, attrs) {
    const node = el('text', Object.assign({ x: x, y: y }, attrs || {}), parent);
    node.textContent = content;
    return node;
  }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); }
  function fmt(value, digits) {
    if (value === null || value === undefined || !isFinite(value)) return '—';
    const d = digits === undefined ? 1 : digits;
    let s = Number(value).toFixed(d);
    if (d > 0) s = s.replace(/\.?0+$/, '');
    return s === '-0' ? '0' : s;
  }
  function niceCeil(value) {
    if (!(value > 0)) return 1;
    const mag = Math.pow(10, Math.floor(Math.log10(value)));
    const n = value / mag;
    const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
    return step * mag;
  }
  function timeStep(span, target) {
    const steps = [1, 2, 5, 10, 15, 30, 60, 90, 120, 180, 240, 360, 480, 720, 1440];
    for (const step of steps) if (span / step <= (target || 6)) return step;
    return Math.ceil(span / (target || 6));
  }

  /* ------------------------------------------------------------ 热力图行高亮（纯函数）
     交互约束：任意时刻最多一个行框；悬停优先于点击选中；移出后恢复已选行；只描边不填充。 */
  const HIGHLIGHT_STYLE = {
    hover: { fill: 'none', stroke: '#172E2B', 'stroke-width': 1.6, 'pointer-events': 'none' },
    selected: { fill: 'none', stroke: '#1F5FA8', 'stroke-width': 1.4, 'stroke-dasharray': '4 3', 'pointer-events': 'none' }
  };
  function highlightStyle(kind) {
    const base = kind === 'selected' ? HIGHLIGHT_STYLE.selected : HIGHLIGHT_STYLE.hover;
    return Object.assign({}, base);
  }
  function resolveHighlightRows(hoverBay, selectedBay, rowOffset, rows) {
    const count = Math.max(0, Number(rows) || 0);
    const offset = Number(rowOffset) || 0;
    const valid = function (bay) {
      if (bay === null || bay === undefined || !Number.isInteger(Number(bay))) return null;
      const row = Number(bay) - offset;
      return row >= 0 && row < count ? Number(bay) : null;
    };
    // 悬停优先：有悬停时选中框必须隐藏；移出后才能恢复已选行。
    const hover = valid(hoverBay);
    return { hover: hover, selected: hover === null ? valid(selectedBay) : null,
             priority: hover === null ? 'selected' : 'hover' };
  }
  function heatmapRowRect(plot, rowH, rows, rowOffset, bay) {
    const resolved = resolveHighlightRows(bay, null, rowOffset, rows);
    if (!plot || !resolved.hover || !(rowH > 0)) return null;
    const row = resolved.hover - (Number(rowOffset) || 0);
    return { x: plot.x + 0.5, y: plot.y + row * rowH + 0.5,
             width: Math.max(0.5, plot.w - 1), height: Math.max(1.5, rowH - 1) };
  }

  /* ------------------------------------------------------------ 时间序列折线/堆叠面积 */
  class TimeChart {
    constructor(host, opts) {
      this.host = host;
      this.opts = Object.assign({
        height: 220, yTicks: 4, stacked: false, series: [], xDomain: [0, 1],
        yDomain: null, yFormat: function (v) { return fmt(v, 0); }, xFormat: function (t) { return String(t); },
        tooltip: null, reference: null, ariaLabel: '时间序列图'
      }, opts || {});
      this.visible = new Set((this.opts.series || []).map(function (s) { return s.key; }));
      this.svg = el('svg', { class: 'chart-svg', role: 'img', 'aria-label': this.opts.ariaLabel, preserveAspectRatio: 'none' });
      this.gGrid = el('g', {}, this.svg);
      this.gSeries = el('g', {}, this.svg);
      this.gHover = el('g', { class: 'chart-hover' }, this.svg);
      this.overlay = el('rect', { fill: 'transparent', 'pointer-events': 'all' }, this.svg);
      host.append(this.svg);
      this.data = [];
      this._yMax = 1;
      this.meta = {};
      const self = this;
      this.overlay.addEventListener('pointermove', function (e) { self.hover(e); });
      this.overlay.addEventListener('pointerdown', function (e) { self.hover(e); });
      this.overlay.addEventListener('pointerleave', function () { self.clearHover(); });
      this.ro = new ResizeObserver(function () { self.resize(); });
      this.ro.observe(host);
      this.resize();
    }
    computeYMax() {
      const domain = this.opts.yDomain;
      if (typeof domain === 'function') return Math.max(1, domain(this.data, this.meta));
      if (typeof domain === 'number' && domain > 0) return domain;
      let max = 0;
      const keys = this.opts.series.map(function (s) { return s.key; });
      for (const row of this.data) for (const key of keys) max = Math.max(max, Number(row[key]) || 0);
      return niceCeil(max || 1);
    }
    resize() {
      const width = Math.max(320, Math.round(this.host.clientWidth || 640));
      this.w = width;
      this.h = this.opts.height;
      this.svg.setAttribute('viewBox', '0 0 ' + width + ' ' + this.h);
      this.svg.setAttribute('width', '100%');
      this.svg.setAttribute('height', String(this.h));
      this.scaffold();
      this.draw();
    }
    setDomain(xDomain) { this.opts.xDomain = xDomain; this.resize(); }
    setVisible(key, on) {
      if (on) this.visible.add(key); else this.visible.delete(key);
      this.draw();
    }
    scaffold() {
      const pad = { top: 18, right: this.opts.series.some(function (s) { return s.endLabel; }) ? 52 : 16, bottom: 24, left: 46 };
      this.pad = pad;
      this.plot = { x: pad.left, y: pad.top, w: this.w - pad.left - pad.right, h: this.h - pad.top - pad.bottom };
      this._yMax = this.computeYMax();
      const plot = this.plot, self = this;
      clear(this.gGrid);
      const yTicks = this.opts.yTicks;
      const rawStep = this._yMax / Math.max(1, yTicks);
      const mag = Math.pow(10, Math.floor(Math.log10(rawStep || 1)));
      const norm = rawStep / mag;
      const tickStep = Math.max(1, (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag);
      for (let value = 0; value <= this._yMax + 1e-9; value += tickStep) {
        const y = this.y(value);
        el('line', { x1: plot.x, x2: plot.x + plot.w, y1: y, y2: y, stroke: value === 0 ? '#CFDAD4' : GRID, 'stroke-width': 1 }, this.gGrid);
        txt(this.gGrid, plot.x - 8, y + 3.5, this.opts.yFormat(value), { 'text-anchor': 'end', fill: AXIS, 'font-size': 10, 'font-variant-numeric': 'tabular-nums' });
      }
      const xmin = this.opts.xDomain[0], xmax = this.opts.xDomain[1];
      const step = timeStep(xmax - xmin, 6);
      const first = Math.ceil(xmin / step) * step;
      for (let t = first; t <= xmax + 1e-9; t += step) {
        const x = this.x(t);
        el('line', { x1: x, x2: x, y1: plot.y, y2: plot.y + plot.h, stroke: GRID, 'stroke-width': 1 }, this.gGrid);
        if (!this.opts.hideXLabels) txt(this.gGrid, x, plot.y + plot.h + 15, this.opts.xFormat(t), { 'text-anchor': 'middle', fill: AXIS, 'font-size': 10, 'font-variant-numeric': 'tabular-nums' });
      }
      txt(this.gGrid, plot.x, plot.y - 6, this.opts.yLabel || '', { fill: MUTED, 'font-size': 10 });
      if (this.opts.reference && isFinite(this.opts.reference.value)) {
        const y = this.y(this.opts.reference.value);
        if (y >= plot.y - 1 && y <= plot.y + plot.h + 1) {
          el('line', { x1: plot.x, x2: plot.x + plot.w, y1: y, y2: y, stroke: this.opts.reference.color || '#8A9A94', 'stroke-width': 1, 'stroke-dasharray': '4 3' }, this.gGrid);
          txt(this.gGrid, plot.x + plot.w - 4, y - 4, this.opts.reference.label || '', { 'text-anchor': 'end', fill: this.opts.reference.color || '#6C7C76', 'font-size': 9.5 });
        }
      }
      this.overlay.setAttribute('x', plot.x);
      this.overlay.setAttribute('y', plot.y);
      this.overlay.setAttribute('width', plot.w);
      this.overlay.setAttribute('height', plot.h);
      self.toTop = true;
    }
    x(t) { const d = this.opts.xDomain; return this.plot.x + (t - d[0]) / (d[1] - d[0]) * this.plot.w; }
    y(v) { return this.plot.y + this.plot.h - (Number(v) || 0) / this._yMax * this.plot.h; }
    update(rows, meta) {
      this.data = rows || [];
      this.meta = meta || {};
      const next = this.computeYMax();
      if (Math.abs(next - this._yMax) > 1e-9) { this.scaffold(); }
      this.draw();
    }
    draw() {
      clear(this.gSeries);
      const rows = this.data;
      if (!rows.length) { this.gSeries.append(el('g')); return; }
      const xs = rows.map((row) => this.x(row.time_min));
      const bottoms = new Array(rows.length).fill(0);
      const series = this.opts.series;
      let top = 0;
      for (const s of series) {
        if (!this.visible.has(s.key)) continue;
        const values = rows.map((row) => Number(row[s.key]) || 0);
        const cellTop = this.opts.stacked ? values.map((v, i) => bottoms[i] + v) : values;
        const bottomVals = this.opts.stacked ? bottoms.slice() : values.map(function () { return 0; });
        if (this.opts.stacked) for (let i = 0; i < bottoms.length; i++) bottoms[i] = cellTop[i];
        const topY = cellTop.map((v) => this.y(v));
        const botY = bottomVals.map((v) => this.y(v));
        if (s.fill) {
          let d = 'M ' + xs[0] + ' ' + botY[0];
          for (let i = 1; i < xs.length; i++) d += ' L ' + xs[i] + ' ' + botY[i - 1] + ' L ' + xs[i] + ' ' + botY[i];
          d += ' L ' + xs[xs.length - 1] + ' ' + topY[topY.length - 1];
          for (let i = xs.length - 1; i >= 1; i--) d += ' L ' + xs[i - 1] + ' ' + topY[i] + ' L ' + xs[i - 1] + ' ' + topY[i - 1];
          d += ' Z';
          el('path', { d: d, fill: s.fill, stroke: 'none' }, this.gSeries);
        }
        let line = 'M ' + xs[0] + ' ' + topY[0];
        for (let i = 1; i < xs.length; i++) line += ' L ' + xs[i] + ' ' + topY[i - 1] + ' L ' + xs[i] + ' ' + topY[i];
        const lineAttrs = { d: line, fill: 'none', stroke: s.color, 'stroke-width': s.width || 2, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' };
        if (s.dash) lineAttrs['stroke-dasharray'] = s.dash;
        el('path', lineAttrs, this.gSeries);
        if (s.endLabel) {
          const lastX = xs[xs.length - 1], lastY = topY[topY.length - 1];
          el('circle', { cx: lastX, cy: lastY, r: 2.6, fill: s.color }, this.gSeries);
          txt(this.gSeries, Math.min(lastX + 6, this.w - 8), lastY + 3.5, fmt(cellTop[cellTop.length - 1], s.endDigits === undefined ? 1 : s.endDigits) + (s.unit || ''), { fill: s.color, 'font-size': 10, 'font-weight': 600, 'font-variant-numeric': 'tabular-nums' });
        }
        top = Math.max(top, cellTop[cellTop.length - 1] || 0);
      }
    }
    hover(event) {
      if (!this.data.length || !this.opts.tooltip) return;
      const rect = this.svg.getBoundingClientRect();
      const scale = this.w / rect.width;
      const px = (event.clientX - rect.left) * scale;
      const t = this.opts.xDomain[0] + (px - this.plot.x) / this.plot.w * (this.opts.xDomain[1] - this.opts.xDomain[0]);
      let best = 0, bestDist = Infinity;
      for (let i = 0; i < this.data.length; i++) {
        const dist = Math.abs(this.data[i].time_min - t);
        if (dist < bestDist) { bestDist = dist; best = i; }
      }
      const row = this.data[best];
      clear(this.gHover);
      const x = this.x(row.time_min);
      el('line', { x1: x, x2: x, y1: this.plot.y, y2: this.plot.y + this.plot.h, stroke: '#8FA49C', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, this.gHover);
      const dots = [];
      const series = this.opts.series;
      let bottom = 0;
      for (const s of series) {
        if (!this.visible.has(s.key)) continue;
        const v = Number(row[s.key]) || 0;
        const vy = this.opts.stacked ? bottom + v : v;
        if (this.opts.stacked) bottom = vy;
        el('circle', { cx: x, cy: this.y(vy), r: 3, fill: '#FFFFFF', stroke: s.color, 'stroke-width': 2 }, this.gHover);
        dots.push({ label: s.label, value: v, color: s.color, unit: s.unit || '' });
      }
      this.opts.tooltip({ x: event.clientX, y: event.clientY, title: this.opts.xFormat(row.time_min), rows: dots });
    }
    clearHover() { clear(this.gHover); if (this.opts.onHoverEnd) this.opts.onHoverEnd(); }
    destroy() { if (this.ro) this.ro.disconnect(); if (this.svg && this.svg.parentNode) this.svg.parentNode.removeChild(this.svg); this.svg = null; }
  }

  /* ------------------------------------------------------------ 车位状态 × 时间 热力图 */
  class Heatmap {
    constructor(host, opts) {
      this.host = host;
      this.opts = Object.assign({ height: 380, maxRows: 140, stateColors: null, clock: function (t) { return String(t); }, tooltip: null, onHoverBay: null, onHoverEnd: null, onClickBay: null, ariaLabel: '车位状态热力图' }, opts || {});
      this.scale = window.devicePixelRatio || 1;
      this.wrap = document.createElement('div');
      this.wrap.className = 'heatmap-wrap';
      this.canvas = document.createElement('canvas');
      this.canvas.className = 'heatmap-canvas';
      this.canvas.setAttribute('role', 'img');
      this.canvas.setAttribute('aria-label', this.opts.ariaLabel);
      this.svg = el('svg', { class: 'heatmap-overlay', 'aria-hidden': 'true' });
      this.empty = document.createElement('p');
      this.empty.className = 'chart-empty';
      this.empty.textContent = '暂无车位状态帧：运行后用同一仿真时钟展开热力图。';
      this.wrap.append(this.canvas, this.svg, this.empty);
      host.append(this.wrap);
      this.frames = [];
      this.meta = {};
      this.ctx = this.canvas.getContext('2d');
      // 交互层在构造时创建一次、draw() 时重新挂载；每层只用一个复用的 rect/line 更新位置，
      // 不在 pointermove 中追加节点。pointer-events: none，保证不阻挡画布命中测试。
      this.selectedLayer = el('g', { class: 'heatmap-selected-layer', 'pointer-events': 'none' });
      this.hoverLayer = el('g', { class: 'heatmap-hover-layer', 'pointer-events': 'none' });
      this.hoverGroup = el('g', { class: 'heatmap-guide-layer', 'pointer-events': 'none' });
      this.selectedRect = el('rect', Object.assign({ visibility: 'hidden' }, highlightStyle('selected')), this.selectedLayer);
      this.hoverRect = el('rect', Object.assign({ visibility: 'hidden' }, highlightStyle('hover')), this.hoverLayer);
      this.hoverLine = el('line', { visibility: 'hidden', stroke: 'rgba(23,46,43,.55)', 'stroke-width': 1, 'stroke-dasharray': '3 3' }, this.hoverGroup);
      this.svg.append(this.selectedLayer, this.hoverLayer, this.hoverGroup);
      this.hoverBay = null;
      this.hoverT = null;
      const self = this;
      this.svg.addEventListener('pointermove', function (e) { self.hover(e); });
      this.svg.addEventListener('pointerleave', function () { self.clearHover(); });
      this.svg.addEventListener('click', function (e) { self.click(e); });
      this.ro = new ResizeObserver(function () { self.resize(); });
      this.ro.observe(host);
      this.resize();
    }
    resize() {
      this.w = Math.max(320, Math.round(this.host.clientWidth || 640));
      this.h = this.opts.height;
      this.canvas.style.width = this.w + 'px';
      this.canvas.style.height = this.h + 'px';
      this.canvas.width = Math.round(this.w * this.scale);
      this.canvas.height = Math.round(this.h * this.scale);
      this.ctx.setTransform(this.scale, 0, 0, this.scale, 0, 0);
      this.svg.setAttribute('viewBox', '0 0 ' + this.w + ' ' + this.h);
      this.svg.setAttribute('width', '100%');
      this.svg.setAttribute('height', String(this.h));
      this.draw();
    }
    layout() {
      this.pad = { left: 46, right: 18, top: 10, bottom: 26 };
      this.plot = { x: this.pad.left, y: this.pad.top, w: this.w - this.pad.left - this.pad.right, h: this.h - this.pad.top - this.pad.bottom };
      return this.plot;
    }
    xTime(t) {
      const m = this.meta, horizon = Math.max(1, m.horizon || 1);
      return this.plot.x + Math.max(0, Math.min(t, horizon)) / horizon * this.plot.w;
    }
    setGeometry(meta) {
      const prevOffset = this.meta.rowOffset;
      this.meta = Object.assign({}, this.meta, meta || {});
      // 分页后旧页码对应的悬停行已不在本页：立即清掉悬停框/辅助线/气泡/联动点。
      if (this.hoverBay !== null && this.meta.rowOffset !== prevOffset) this.clearHover();
      // 选中/分页等几何变化只更新复用矩形，不重建 SVG，也不追加高亮节点。
      this.drawHighlights();
      this.syncHoverGuide();
    }
    update(frames, meta) {
      this.frames = frames || [];
      this.meta = Object.assign({}, this.meta, meta || {});
      const rowCount = this.meta.rowCount || this.rows || 0;
      // 本页已看不到的悬停行（例如翻页/数据重置）不再保留悬停态；无数据时同样立即清理。
      if (this.hoverBay !== null && resolveHighlightRows(this.hoverBay, null, this.meta.rowOffset, rowCount).hover === null) this.clearHover();
      if (this.meta.highlightBay !== null && this.meta.highlightBay !== undefined
          && resolveHighlightRows(this.meta.highlightBay, null, this.meta.rowOffset, rowCount).hover === null) {
        this.meta.highlightBay = null;
        this.hoverBay = null;
        this.hoverT = null;
      }
      // 无数据时立即清掉悬停框/辅助线/提示气泡，不依赖下一次 pointermove 或轮询。
      if (!this.frames.length) this.clearHover();
      this.draw();
    }
    draw() {
      const plot = this.layout();
      const ctx = this.ctx;
      const frames = this.frames;
      const meta = this.meta;
      const nSpaces = meta.nSpaces || 0;
      const rowOffset = meta.rowOffset || 0;
      const rows = Math.max(1, Math.min(meta.rowCount || nSpaces, Math.max(0, nSpaces - rowOffset)));
      const rowH = plot.h / rows;
      ctx.clearRect(0, 0, this.w, this.h);
      clear(this.svg);
      const hasData = frames.length > 0 && nSpaces > 0;
      this.empty.hidden = hasData;
      this.canvas.style.display = hasData ? 'block' : 'none';
      this.svg.style.display = hasData ? 'block' : 'none';
      if (!hasData) { this.rows = rows; this.rowH = rowH; return; }
      const colors = this.opts.stateColors || {};
      const horizon = Math.max(1, meta.horizon || 1);
      const currentT = meta.currentT === undefined ? horizon : meta.currentT;
      for (let j = 0; j < frames.length; j++) {
        const t0 = frames[j].t;
        const t1 = j + 1 < frames.length ? frames[j + 1].t : Math.max(t0 + 1e-6, currentT);
        const x0 = this.xTime(t0);
        const x1 = Math.max(x0 + 0.7, this.xTime(t1));
        const states = frames[j].s || '';
        for (let r = 0; r < rows; r++) {
          const bay = rowOffset + r;
          const code = states[bay] || '0';
          ctx.fillStyle = (colors[code] || STATE[code].color);
          ctx.fillRect(x0, plot.y + r * rowH, x1 - x0 + 0.5, rowH + 0.4);
        }
      }
      // 回放快照补齐：最后一帧之后可能还有事件（帧是降采样，快照是真实状态）。
      // 用快照 bay_state 覆盖最后一列，使热力图右边界与回放时钟/点阵截止到同一时刻。
      if (meta.tailState && frames.length && currentT > frames[frames.length - 1].t + 1e-9) {
        const tailT = frames[frames.length - 1].t;
        const tx0 = this.xTime(tailT);
        const tx1 = Math.max(tx0 + 0.7, this.xTime(currentT));
        for (let r = 0; r < rows; r++) {
          const bay = rowOffset + r;
          const code = meta.tailState[bay] || '0';
          ctx.fillStyle = (colors[code] || STATE[code].color);
          ctx.fillRect(tx0, plot.y + r * rowH, tx1 - tx0 + 0.5, rowH + 0.4);
        }
      }
      const step = timeStep(horizon, 6);
      for (let t = 0; t <= horizon + 1e-9; t += step) {
        const x = this.xTime(t);
        el('line', { x1: x, x2: x, y1: plot.y, y2: plot.y + plot.h, stroke: 'rgba(23,46,43,.10)', 'stroke-width': 1 }, this.svg);
        txt(this.svg, x, plot.y + plot.h + 15, this.opts.clock(t), { 'text-anchor': 'middle', fill: AXIS, 'font-size': 10, 'font-variant-numeric': 'tabular-nums' });
      }
      const labelEvery = Math.max(1, Math.round(rows / 12));
      for (let r = 0; r < rows; r += labelEvery) {
        txt(this.svg, plot.x - 6, plot.y + r * rowH + rowH / 2 + 3, String(rowOffset + r + 1), { 'text-anchor': 'end', fill: AXIS, 'font-size': 9.5, 'font-variant-numeric': 'tabular-nums' });
      }
      txt(this.svg, plot.x - 6, plot.y - 1, '车位', { 'text-anchor': 'end', fill: MUTED, 'font-size': 9 });
      // 透明捕获层：保证空白单元格也能触发悬停/点击（SVG 只对已绘制元素做命中测试）
      el('rect', { x: plot.x, y: plot.y, width: plot.w, height: plot.h, fill: 'transparent', 'pointer-events': 'all' }, this.svg);
      // 交互层最后挂载：固定为“选中行框 / 悬停行框 / 悬停辅助线”三个复用节点，
      // draw() 只重新挂载，不创建新节点；图层本身 pointer-events:none。
      this.rows = rows;
      this.rowH = rowH;
      this.svg.append(this.selectedLayer, this.hoverLayer, this.hoverGroup);
      this.drawHighlights();
      this.syncHoverGuide();
    }
    drawHighlights() {
      if (!this.rows || !this.hoverRect || !this.selectedRect) return;
      // 任意时刻最多一个行框：有悬停时只显示悬停框，选中框隐藏；移出后恢复选中框。
      const resolved = resolveHighlightRows(this.meta.highlightBay, this.meta.selectedBay,
                                            this.meta.rowOffset, this.rows);
      this.placeHighlightRect(this.hoverRect, resolved.hover);
      this.placeHighlightRect(this.selectedRect, resolved.selected);
    }
    placeHighlightRect(rect, bay) {
      const box = heatmapRowRect(this.plot, this.rowH, this.rows, this.meta.rowOffset, bay);
      if (!box) { rect.setAttribute('visibility', 'hidden'); return; }
      // 只描边、无填充：不遮挡原始状态颜色。
      rect.setAttribute('visibility', 'visible');
      rect.setAttribute('x', String(box.x));
      rect.setAttribute('y', String(box.y));
      rect.setAttribute('width', String(box.width));
      rect.setAttribute('height', String(box.height));
    }
    syncHoverGuide() {
      if (!this.hoverLine) return;
      if (this.hoverBay === null || this.hoverBay === undefined
          || this.hoverT === null || this.hoverT === undefined || !this.rows) {
        this.hoverLine.setAttribute('visibility', 'hidden');
        return;
      }
      const plot = this.plot, x = this.xTime(this.hoverT);
      this.hoverLine.setAttribute('x1', String(x));
      this.hoverLine.setAttribute('x2', String(x));
      this.hoverLine.setAttribute('y1', String(plot.y));
      this.hoverLine.setAttribute('y2', String(plot.y + plot.h));
      this.hoverLine.setAttribute('visibility', 'visible');
    }
    hover(event) {
      if (!this.frames.length || !this.rows) return;
      const rect = this.svg.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const px = (event.clientX - rect.left) * (this.w / rect.width);
      const py = (event.clientY - rect.top) * (this.h / rect.height);
      const plot = this.plot;
      if (px < plot.x || px > plot.x + plot.w || py < plot.y || py > plot.y + plot.h) { this.clearHover(); return; }
      const row = Math.min(this.rows - 1, Math.max(0, Math.floor((py - plot.y) / this.rowH)));
      const bay = (this.meta.rowOffset || 0) + row;
      const horizon = Math.max(1, this.meta.horizon || 1);
      const t = Math.min(horizon, Math.max(0, (px - plot.x) / plot.w * horizon));
      let idx = 0;
      for (let i = 0; i < this.frames.length; i++) if (this.frames[i].t <= t + 1e-9) idx = i;
      const frame = this.frames[idx];
      if (!frame) { this.clearHover(); return; }
      const code = (frame.s || '')[bay] || '0';
      const changed = this.hoverBay !== bay;
      // 复用同一个悬停框和辅助线，只改坐标/可见性；行未变化时不触发联动点阵更新。
      this.hoverBay = bay;
      this.hoverT = frame.t;
      this.meta.highlightBay = bay;
      if (changed) this.drawHighlights();
      this.syncHoverGuide();
      if (changed && this.opts.onHoverBay) this.opts.onHoverBay(bay);
      if (this.opts.tooltip) this.opts.tooltip({ x: event.clientX, y: event.clientY, title: '车位 ' + (bay + 1) + ' · ' + this.opts.clock(frame.t), rows: [{ label: '状态', value: (STATE[code] || STATE[0]).label, color: (STATE[code] || STATE[0]).color }] });
    }
    clearHover() {
      const hadHover = this.hoverBay !== null || this.hoverT !== null
        || (this.meta.highlightBay !== null && this.meta.highlightBay !== undefined);
      // 只隐藏复用的悬停框/辅助线，并恢复已选行；不追加、不残留任何节点。
      this.hoverBay = null;
      this.hoverT = null;
      if (this.meta.highlightBay !== null && this.meta.highlightBay !== undefined) this.meta.highlightBay = null;
      this.drawHighlights();
      this.syncHoverGuide();
      if (hadHover && this.opts.onHoverEnd) this.opts.onHoverEnd();
    }
    click(event) {
      if (!this.rows || !this.opts.onClickBay) return;
      const rect = this.svg.getBoundingClientRect();
      const py = (event.clientY - rect.top) * (this.h / rect.height);
      const r = Math.min(this.rows - 1, Math.max(0, Math.floor((py - this.plot.y) / this.rowH)));
      this.opts.onClickBay((this.meta.rowOffset || 0) + r);
    }
    destroy() { if (this.ro) this.ro.disconnect(); if (this.wrap && this.wrap.parentNode) this.wrap.parentNode.removeChild(this.wrap); this.wrap = null; }
  }

  /* ------------------------------------------------------------ 策略对比条形图 */
  class PolicyBars {
    constructor(host, opts) {
      this.host = host;
      this.opts = Object.assign({ height: 180, tooltip: null }, opts || {});
      this.svg = el('svg', { class: 'chart-svg', role: 'img', 'aria-label': '共享策略对比条形图' });
      host.append(this.svg);
      this.rows = [];
      this.metric = null;
      const self = this;
      this.ro = new ResizeObserver(function () { self.draw(); });
      this.ro.observe(host);
    }
    update(rows, metric) {
      this.rows = rows || [];
      this.metric = metric;
      this.draw();
    }
    draw() {
      if (!this.svg) return;
      const w = Math.max(320, Math.round(this.host.clientWidth || 640));
      const rows = this.rows, metric = this.metric;
      const rowH = 34;
      const h = Math.max(64, rows.length * rowH + 16);
      this.svg.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
      this.svg.setAttribute('width', '100%');
      this.svg.setAttribute('height', String(h));
      clear(this.svg);
      if (!rows.length || !metric) return;
      const labelW = 128, valueW = 96;
      const plotW = w - labelW - valueW - 16;
      let max = 0;
      for (const row of rows) max = Math.max(max, (Number(row[metric.key]) || 0) + (Number(row[metric.key + '_std']) || 0));
      max = max || 1;
      rows.forEach(function (row, i) {
        const y = i * rowH + 12;
        const value = Number(row[metric.key]) || 0;
        const std = Number(row[metric.key + '_std']) || 0;
        const bw = Math.max(0, value / max * plotW);
        txt(this.svg, 0, y + 15, row.name || ('策略 ' + (i + 1)), { fill: INK, 'font-size': 11.5 });
        el('rect', { x: labelW, y: y + 3, width: plotW, height: rowH - 12, fill: '#F1F5F3', rx: 3 }, this.svg);
        el('rect', { x: labelW, y: y + 3, width: bw, height: rowH - 12, fill: metric.color || '#1F5FA8', rx: 3 }, this.svg);
        if (std > 0) {
          const x0 = labelW + Math.max(0, (value - std) / max * plotW);
          const x1 = labelW + Math.min(plotW, (value + std) / max * plotW);
          el('line', { x1: x0, x2: x1, y1: y + (rowH - 12) / 2 + 3, y2: y + (rowH - 12) / 2 + 3, stroke: 'rgba(23,46,43,.55)', 'stroke-width': 1 }, this.svg);
        }
        txt(this.svg, labelW + plotW + 8, y + 18, metric.format ? metric.format(value, std) : fmt(value, 1), { fill: INK, 'font-size': 11, 'font-variant-numeric': 'tabular-nums', 'font-weight': 600 });
      }, this);
    }
    destroy() { if (this.ro) this.ro.disconnect(); if (this.svg && this.svg.parentNode) this.svg.parentNode.removeChild(this.svg); this.svg = null; }
  }

  /* ------------------------------------------------------------ 迷你折线（预测概率等） */
  function sparkline(host, values, opts) {
    const o = Object.assign({ height: 40, color: '#1F5FA8', fill: 'rgba(31,95,168,.10)', min: 0, max: 1 }, opts || {});
    const w = Math.max(60, Math.round(host.clientWidth || 200));
    let svg = host.querySelector('svg');
    if (!svg) { svg = el('svg', { class: 'spark-svg', 'aria-hidden': 'true' }); host.append(svg); }
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + o.height);
    svg.setAttribute('width', '100%');
    svg.setAttribute('height', String(o.height));
    clear(svg);
    const data = (values || []).filter(function (v) { return v !== null && v !== undefined && isFinite(v); });
    if (data.length < 2) return;
    const min = o.min, max = o.max === o.min ? o.min + 1 : o.max;
    const x = function (i) { return i / (data.length - 1) * (w - 2) + 1; };
    const y = function (v) { return o.height - 3 - (v - min) / (max - min) * (o.height - 6); };
    let line = 'M ' + x(0) + ' ' + y(data[0]);
    for (let i = 1; i < data.length; i++) line += ' L ' + x(i) + ' ' + y(data[i]);
    if (o.fill) {
      el('path', { d: line + ' L ' + x(data.length - 1) + ' ' + (o.height - 1) + ' L ' + x(0) + ' ' + (o.height - 1) + ' Z', fill: o.fill, stroke: 'none' }, svg);
    }
    el('path', { d: line, fill: 'none', stroke: o.color, 'stroke-width': 1.8, 'stroke-linejoin': 'round' }, svg);
    el('circle', { cx: x(data.length - 1), cy: y(data[data.length - 1]), r: 2.4, fill: o.color }, svg);
  }

  global.LabCharts = { TimeChart: TimeChart, Heatmap: Heatmap, PolicyBars: PolicyBars, sparkline: sparkline,
    resolveHighlightRows: resolveHighlightRows, heatmapRowRect: heatmapRowRect, highlightStyle: highlightStyle,
    STATE: STATE, fmt: fmt, niceCeil: niceCeil, palette: { ink: INK, axis: AXIS, grid: GRID, muted: MUTED } };
})(window);
