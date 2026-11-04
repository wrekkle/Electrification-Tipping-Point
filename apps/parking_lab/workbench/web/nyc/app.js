'use strict';
/* NYC 半合成研究结果查看器 —— 只读前端。
   数据全部来自后端只读接口（/api/nyc/*），页面不重算账本、成本或缺口；
   未知字段显示“未知”，R0 不显示拒绝率与 J(n)。 */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var UNKNOWN = '未知';
  var SVG_NS = 'http://www.w3.org/2000/svg';
  var MODE_ORDER = ['R0', 'R1', 'R2'];
  var COLORS = ['#2F6E5B', '#C9803A', '#3C6E9F', '#8A5A9E', '#B23A48'];
  var MAX_TABLE_ROWS = 200;
  var DEFAULT_MODE_LABELS = {
    R0: { label: 'R0 观测重放', provenance: 'observed',
          note: '真实会话占用与交付重放；不计算真实请求缺口或拒绝率' },
    R1: { label: 'R1 充电会话半合成', provenance: 'scenario',
          note: '以真实充电会话为锚点补齐未知量；条件性情景，不是纽约真实完整需求' },
    R2: { label: 'R2 三类车半合成', provenance: 'scenario',
          note: '在 R1 上加燃油车与不充电电动车停车流；场景假设，不是实测' }
  };

  var state = {
    dataset: 'v2', schemaKind: null,
    index: null, mode: null, siteId: null, scenarioId: null, runId: null,
    run: null, binMinutes: 15, requestSeq: 0,
    v3: { siteId: null, scenarioId: null, runs: {}, picked: {}, csv: {},
          csvErrors: {}, sources: {}, seq: 0 }
  };

  /* ------------------------------------------------------------ 格式与查找 */
  function isMissing(value) {
    return value === null || value === undefined ||
      (typeof value === 'number' && !isFinite(value));
  }
  function text(value, fallback) {
    var miss = fallback === undefined ? UNKNOWN : fallback;
    if (isMissing(value) || value === '') return miss;
    if (typeof value === 'boolean') return value ? '是' : '否';
    if (typeof value === 'object') {
      try { return JSON.stringify(value); } catch (error) { return String(value); }
    }
    return String(value);
  }
  function num(value, digits) {
    if (typeof value !== 'number' || !isFinite(value)) return UNKNOWN;
    var places = digits === undefined ? 0 : digits;
    return value.toLocaleString('zh-CN', {
      minimumFractionDigits: places, maximumFractionDigits: places
    });
  }
  function pct(value, digits) {
    if (typeof value !== 'number' || !isFinite(value)) return UNKNOWN;
    return (value * 100).toFixed(digits === undefined ? 2 : digits) + '%';
  }
  function kwh(value, digits) {
    if (typeof value !== 'number' || !isFinite(value)) return UNKNOWN;
    return num(value, digits === undefined ? 1 : digits) + ' kWh';
  }
  function countOf(value) {
    if (typeof value !== 'number' || !isFinite(value)) return UNKNOWN;
    return num(value, 0);
  }
  function uniq(values) {
    var seen = {};
    var out = [];
    values.forEach(function (value) {
      if (value === null || value === undefined) return;
      var key = String(value);
      if (seen[key]) return;
      seen[key] = true;
      out.push(value);
    });
    return out;
  }
  function indexRuns() {
    var runs = state.index && Array.isArray(state.index.runs) ? state.index.runs : [];
    return runs.filter(function (run) { return run && typeof run === 'object'; });
  }
  function indexRunFor(runId) {
    var found = null;
    indexRuns().forEach(function (run) { if (!found && run.run_id === runId) found = run; });
    return found;
  }
  function siteEntry(siteId) {
    var sites = state.index && Array.isArray(state.index.sites) ? state.index.sites : [];
    var found = null;
    sites.forEach(function (site) { if (!found && site && site.site_id === siteId) found = site; });
    return found || {};
  }
  function scenarioEntry(scenarioId) {
    var scenarios = state.index && Array.isArray(state.index.scenarios) ? state.index.scenarios : [];
    var found = null;
    scenarios.forEach(function (scenario) {
      if (!found && scenario && scenario.scenario_id === scenarioId) found = scenario;
    });
    return found || {};
  }
  function modeInfo(mode) {
    var labels = state.index && state.index.mode_labels;
    if (labels && typeof labels === 'object' && labels[mode] !== undefined) {
      var value = labels[mode];
      if (typeof value === 'string') {
        var fallback = DEFAULT_MODE_LABELS[mode] || {};
        return {
          label: value,
          provenance: mode === 'R0' ? 'observed' : 'scenario',
          note: fallback.note || null
        };
      }
      if (value && typeof value === 'object') return value;
    }
    return DEFAULT_MODE_LABELS[mode] || {};
  }
  function modeLabel(mode) { return text(modeInfo(mode).label, String(mode)); }
  function provenanceText(value) {
    if (value === 'observed') return '观测';
    if (value === 'scenario') return '情景假设';
    if (value === 'generated') return '生成';
    return text(value);
  }
  function provenanceClass(value) {
    if (value === 'observed' || value === 'scenario') return value;
    return '';
  }
  function siteLabel(siteId) {
    var site = siteEntry(siteId);
    return site.label ? site.label + '（' + text(siteId) + '）' : text(siteId);
  }
  function scenarioLabel(scenarioId) {
    var scenario = scenarioEntry(scenarioId);
    return scenario.label ? scenario.label + '（' + text(scenarioId) + '）' : text(scenarioId);
  }
  function runLabel(runId) {
    var run = indexRunFor(runId);
    if (!run) return text(runId);
    if (state.schemaKind === 'v2') {
      var partsV2 = [
        text(run.mode_label, modeLabel(run.mode)),
        evidenceLabel(run.evidence_kind),
        '阶段 ' + text(run.stage),
        '块 ' + text(run.block_id),
        'θ ' + text(run.theta_id),
        '规则 ' + text(run.rule)
      ];
      if (!isMissing(run.n_choice)) partsV2.push('n=' + text(run.n_choice));
      if (!isMissing(run.J_choice)) partsV2.push('J=' + text(run.J_choice));
      return partsV2.join(' · ');
    }
    var block = run.block && typeof run.block === 'object' ? run.block : {};
    var parts = [
      text(run.rule), 'rep ' + text(run.replicate),
      '块 ' + text(block.W_local), '周 ' + text(block.week_index),
      '预热 ' + text(block.warmup_days) + ' 天', '核算 ' + text(block.accounting_days) + ' 天'
    ];
    return parts.join(' · ');
  }

  /* ------------------------------------------------------------ DOM 构造 */
  function appendChildren(node, children) {
    if (children === null || children === undefined || children === false) return;
    if (Array.isArray(children)) {
      children.forEach(function (child) { appendChildren(node, child); });
      return;
    }
    if (children instanceof Node) { node.appendChild(children); return; }
    node.appendChild(document.createTextNode(String(children)));
  }
  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) {
        var value = attrs[key];
        if (value === null || value === undefined || value === false) return;
        if (key === 'class') node.className = value;
        else if (key === 'text') node.textContent = value;
        else if (key === 'style') node.setAttribute('style', value);
        else node.setAttribute(key, value === true ? '' : String(value));
      });
    }
    appendChildren(node, children);
    return node;
  }
  function svgNode(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (key) { node.setAttribute(key, String(attrs[key])); });
    }
    return node;
  }
  function setChildren(node, children) {
    node.replaceChildren();
    appendChildren(node, children);
  }
  function fillFacts(host, pairs) {
    setChildren(host, pairs.map(function (pair) {
      return el('div', { class: 'fact' }, [
        el('dt', { text: pair[0] }),
        el('dd', { text: pair[1] === null || pair[1] === undefined ? UNKNOWN : String(pair[1]) })
      ]);
    }));
  }
  function fillTable(host, headers, rows) {
    host.replaceChildren();
    if (!rows || !rows.length) {
      host.appendChild(el('p', { class: 'table-empty', text: '无记录' }));
      return;
    }
    var table = el('table');
    var headRow = el('tr');
    headers.forEach(function (header) { headRow.appendChild(el('th', { text: header })); });
    table.appendChild(el('thead', null, [headRow]));
    var body = el('tbody');
    rows.forEach(function (cells) {
      var tr = el('tr');
      cells.forEach(function (cell) {
        tr.appendChild(el('td', {
          text: cell === null || cell === undefined ? UNKNOWN : String(cell)
        }));
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    host.appendChild(table);
  }
  function fillLimitedTable(host, headers, rows, limit) {
    if (rows.length <= limit) { fillTable(host, headers, rows); return; }
    fillTable(host, headers, rows.slice(0, limit));
    host.appendChild(el('p', {
      class: 'table-empty',
      text: '仅显示前 ' + limit + ' 条（共 ' + rows.length + ' 条）；完整数据请导出运行 JSON。'
    }));
  }
  function fillSelect(id, values, labelFn) {
    var select = $(id);
    select.replaceChildren();
    values.forEach(function (value) {
      select.appendChild(el('option', { value: value, text: labelFn(value) }));
    });
  }
  function emptyChart(host, message) {
    setChildren(host, el('p', { class: 'chart-empty', text: message }));
  }
  function renderLegend(host, items) {
    setChildren(host, items.map(function (item) {
      return el('span', { class: 'legend-item' }, [
        el('i', { class: 'swatch', style: 'background:' + item.color }),
        item.name
      ]);
    }));
  }

  /* ------------------------------------------------------------ 接口访问 */
  async function getJSON(url) {
    var response = await fetch(url, { headers: { Accept: 'application/json' }, cache: 'no-store' });
    var payload = null;
    try { payload = await response.json(); } catch (error) { payload = null; }
    if (!response.ok) {
      var message = payload && payload.error ? payload.error : 'HTTP ' + response.status;
      throw new Error(message);
    }
    return payload;
  }

  /* ------------------------------------------------------------ 状态显示 */
  function renderStatusAndBanners() {
    var index = state.index || {};
    var status = index.status;
    var isV2 = state.schemaKind === 'v2';
    var isV3 = state.schemaKind === 'v3';
    var pill = $('data-status');
    var banner = $('banner');
    var label = isV3 ? 'v3' : (isV2 ? 'v2' : 'v1');
    if (status === 'sample') {
      pill.className = 'status-pill sample';
      pill.textContent = '样例数据（非研究结果）';
      banner.hidden = false;
      banner.className = 'banner sample';
      banner.textContent = '开发样例，不是研究结果' +
        (index.warning ? '：' + index.warning : '') + '（index.status = sample）';
    } else if (status === 'empty') {
      pill.className = 'status-pill empty';
      pill.textContent = label + ' 尚未生成结果';
      if (isV3) {
        banner.hidden = false;
        banner.className = 'banner warn';
        banner.textContent = index.message || ('v3 数据尚未生成：研究端运行 v3 查看器导出后刷新页面。');
      } else {
        banner.hidden = true;
      }
    } else {
      pill.className = 'status-pill';
      pill.textContent = label + ' · 只读 · 已连接';
      if (status && status !== 'ready') {
        banner.hidden = false;
        banner.className = 'banner warn';
        banner.textContent = '数据状态：' + status + (index.message ? ' — ' + index.message : '');
      } else {
        banner.hidden = true;
      }
    }
    var note = $('dataset-note');
    if (note) {
      if (isV3) {
        note.textContent = '当前数据集：v3（机制对照 M0/M1/M2 与 n*、R0 真实锚点回放-不参与选择、固定配置评价、稳健 A/B、逐世界事后最优 CSV-仅诊断、留出 A/B 与噪声底、归因对照）。契约版本由 index.json 的 schema_version 区分。';
      } else if (isV2) {
        note.textContent = '当前数据集：v2（四类证据对象：期望成本选择 / 固定配置评价 / 稳健 A·B / 单世界事后最优-仅诊断）。契约版本由 index.json 的 schema_version 区分。';
      } else {
        note.textContent = '当前数据集：v1（观测重放与单世界运行；固定配置评价与稳健表只存在于 v2/v3 数据集）。';
      }
    }
  }
  function renderModeCards() {
    var host = $('mode-cards');
    var runs = indexRuns();
    setChildren(host, MODE_ORDER.map(function (mode) {
      var info = modeInfo(mode);
      var count = runs.filter(function (run) { return run.mode === mode; }).length;
      var active = state.mode === mode;
      return el('article', { class: 'mode-card' + (active ? ' active' : '') }, [
        el('div', { class: 'mode-card-head' }, [
          el('strong', { text: mode + ' · ' + text(info.label, UNKNOWN) }),
          el('span', { class: 'prov ' + provenanceClass(info.provenance), text: provenanceText(info.provenance) })
        ]),
        el('p', { class: 'mode-note', text: text(info.note) }),
        el('span', { class: 'mode-count', text: count ? count + ' 个运行' : '无运行' })
      ]);
    }));
  }
  function showEmpty(message) {
    var host = $('empty-state');
    host.hidden = false;
    if (message) $('empty-message').textContent = message;
    $('content').hidden = true;
    $('v2-content').hidden = true;
    $('v3-content').hidden = true;
    ['mode-select', 'site-select', 'scenario-select', 'run-select'].forEach(function (id) {
      var select = $(id);
      select.disabled = true;
      select.replaceChildren();
    });
    $('run-meta').textContent = '没有可显示的运行';
  }

  /* ------------------------------------------------------------ 选择级联：模式 → 站点 → 情景 → 运行 */
  function populateModes() {
    var runs = indexRuns();
    var modes = MODE_ORDER.filter(function (mode) {
      return runs.some(function (run) { return run.mode === mode; });
    });
    if (!modes.length) {
      renderModeCards();
      showEmpty('index.json 中没有运行记录，无法选择结果。');
      return;
    }
    ['mode-select', 'site-select', 'scenario-select', 'run-select'].forEach(function (id) {
      $(id).disabled = false;
    });
    fillSelect('mode-select', modes, function (mode) { return modeLabel(mode); });
    var initialMode = state.schemaKind === 'v2' && modes.indexOf('R1') >= 0 ? 'R1' : modes[0];
    selectMode(initialMode);
  }
  function selectMode(mode) {
    state.mode = mode;
    $('mode-select').value = mode;
    renderModeCards();
    populateSites();
  }
  function populateSites() {
    var runs = indexRuns().filter(function (run) { return run.mode === state.mode; });
    var sites = uniq(runs.map(function (run) { return run.site_id; }));
    if (!sites.length) { clearTail('该模式下没有站点记录。'); return; }
    fillSelect('site-select', sites, siteLabel);
    state.siteId = sites[0];
    $('site-select').value = state.siteId;
    populateScenarios();
  }
  function scenarioKeyOf(run) {
    if (!run) return '';
    return isMissing(run.scenario_id) ? '' : String(run.scenario_id);
  }
  function scenarioOptionLabel(key) {
    if (!key) return '观测（无情景）';
    return scenarioLabel(key);
  }
  function populateScenarios() {
    var runs = indexRuns().filter(function (run) {
      return run.mode === state.mode && run.site_id === state.siteId;
    });
    var scenarios = uniq(runs.map(scenarioKeyOf));
    if (!scenarios.length) { clearTail('该站点在该模式下没有情景记录。'); return; }
    fillSelect('scenario-select', scenarios, scenarioOptionLabel);
    state.scenarioId = scenarios[0];
    $('scenario-select').value = state.scenarioId;
    populateRuns();
  }
  function populateRuns() {
    var runs = indexRuns().filter(function (run) {
      return run.mode === state.mode && run.site_id === state.siteId &&
        scenarioKeyOf(run) === state.scenarioId;
    });
    if (!runs.length) { clearTail('该情景下没有运行记录。'); return; }
    fillSelect('run-select', runs.map(function (run) { return run.run_id; }), runLabel);
    state.runId = runs[0].run_id;
    $('run-select').value = state.runId;
    $('empty-state').hidden = true;
    loadRun(state.runId);
  }
  function clearTail(message) {
    ['scenario-select', 'run-select'].forEach(function (id) { $(id).replaceChildren(); });
    state.scenarioId = null;
    state.runId = null;
    state.run = null;
    $('content').hidden = true;
    $('v2-content').hidden = true;
    $('v3-content').hidden = true;
    $('run-meta').textContent = message;
  }

  /* ------------------------------------------------------------ 载入运行 */
  async function loadRun(runId) {
    var seq = ++state.requestSeq;
    try {
      var run = await getJSON('/api/nyc/run/' + encodeURIComponent(runId) +
        '?dataset=' + encodeURIComponent(state.dataset));
      if (seq !== state.requestSeq) return;
      state.run = run;
      state.runId = runId;
      $('empty-state').hidden = true;
      var isV2 = state.schemaKind === 'v2';
      $('content').hidden = isV2;
      $('v2-content').hidden = !isV2;
      renderAll();
    } catch (error) {
      if (seq !== state.requestSeq) return;
      state.run = null;
      $('content').hidden = true;
      $('v2-content').hidden = true;
      var host = $('empty-state');
      host.hidden = false;
      $('empty-message').textContent = '无法加载运行 ' + runId + '：' + error.message;
    }
  }
  function renderAll() {
    if (state.schemaKind === 'v2') {
      renderV2All();
      return;
    }
    renderRunMeta();
    renderKpis();
    renderSeries();
    renderArrivals();
    renderCost();
    renderMeta();
    renderObserved();
    renderExports();
  }

  /* ------------------------------------------------------------ 运行元信息 */
  function renderRunMeta() {
    var run = state.run;
    var indexed = indexRunFor(run.run_id) || {};
    var block = run.block || indexed.block || {};
    var site = siteEntry(run.site_id);
    var parts = [
      el('strong', { text: modeLabel(run.mode) }),
      ' · ' + siteLabel(run.site_id),
      ' · ' + scenarioLabel(run.scenario_id),
      ' · 规则 ' + text(run.rule),
      ' · 重复 ' + text(run.replicate),
      ' · 时间块 ' + text(block.W_local),
      ' · 预热 ' + text(block.warmup_days) + ' 天 / 核算 ' + text(block.accounting_days) + ' 天',
      ' · 单枪 ' + (isMissing(run.station_power_kw) ? UNKNOWN : num(run.station_power_kw, 1) + ' kW')
    ];
    var rest = document.createDocumentFragment();
    parts.forEach(function (part) {
      rest.appendChild(part instanceof Node ? part : document.createTextNode(String(part)));
    });
    rest.appendChild(el('br'));
    rest.appendChild(el('span', {
      class: 'muted',
      text: 'run_id：' + text(run.run_id) + ' ｜ 模式性质：' + provenanceText(modeInfo(run.mode).provenance) +
        (run.mode === 'R0' ? ' ｜ R0 不计算 J(n)' : ' ｜ 成本曲线/拒绝/缺口为模型输出')
    }));
    setChildren($('run-meta'), rest);
  }

  /* ------------------------------------------------------------ 分箱与序列 */
  function baseBinMinutes() {
    var series = state.run && state.run.series;
    var value = series && series.bin_minutes;
    return typeof value === 'number' && value > 0 ? value : 15;
  }
  function factorFor(minutes) {
    return Math.max(1, Math.round(minutes / baseBinMinutes()));
  }
  function numeric(value) {
    return typeof value === 'number' && isFinite(value) ? value : null;
  }
  function sumOf(values) {
    var total = 0;
    var seen = false;
    values.forEach(function (value) {
      if (value === null || value === undefined || !isFinite(value)) return;
      total += value;
      seen = true;
    });
    return seen ? total : null;
  }
  function meanOf(values) {
    var total = 0;
    var count = 0;
    values.forEach(function (value) {
      if (value === null || value === undefined || !isFinite(value)) return;
      total += value;
      count += 1;
    });
    return count ? total / count : null;
  }
  function aggregateBins(bins, factor) {
    if (!Array.isArray(bins)) return [];
    if (factor <= 1) return bins;
    var out = [];
    for (var index = 0; index < bins.length; index += factor) {
      var group = bins.slice(index, index + factor);
      var row = { t_local: group[0] ? group[0].t_local : null };
      ['charge_bays_used', 'ordinary_bays_used', 'charging_kw'].forEach(function (key) {
        row[key] = meanOf(group.map(function (item) { return numeric(item[key]); }));
      });
      ['arrivals', 'rejected', 'delivered_kwh', 'unmet_kwh', 'shortfall_kwh'].forEach(function (key) {
        row[key] = sumOf(group.map(function (item) { return numeric(item[key]); }));
      });
      out.push(row);
    }
    return out;
  }
  function currentBins() {
    var series = state.run && state.run.series;
    var bins = series && Array.isArray(series.bins) ? series.bins : [];
    return aggregateBins(bins, factorFor(state.binMinutes));
  }
  function binLabel(tLocal) {
    if (typeof tLocal !== 'string' || !tLocal) return UNKNOWN;
    var match = tLocal.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
    if (!match) return tLocal;
    return match[2] + '-' + match[3] + ' ' + match[4] + ':' + match[5];
  }
  function valuesOf(bins, key) {
    return bins.map(function (item) { return numeric(item[key]); });
  }

  /* ------------------------------------------------------------ SVG 折线图 */
  function niceMax(value) {
    if (!(value > 0) || !isFinite(value)) return 1;
    var exponent = Math.pow(10, Math.floor(Math.log(value) / Math.LN10));
    var fraction = value / exponent;
    var nice = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10;
    return nice * exponent;
  }
  function axisValue(value) {
    if (Math.abs(value) >= 1000) return (value / 1000).toFixed(1) + 'k';
    if (Math.abs(value) >= 10) return value.toFixed(0);
    if (Math.abs(value) >= 1) return value.toFixed(1);
    return value.toFixed(2);
  }
  function chartHeight(host) {
    return (host.clientWidth || 640) < 560 ? 200 : 250;
  }
  function renderLineChart(host, seriesList, labels, options) {
    host.replaceChildren();
    var opts = options || {};
    var width = Math.max(260, host.clientWidth || 640);
    var height = chartHeight(host);
    var margin = { l: 48, r: 14, t: 16, b: 26 };
    var plotW = Math.max(10, width - margin.l - margin.r);
    var plotH = Math.max(10, height - margin.t - margin.b);
    var svg = svgNode('svg', {
      viewBox: '0 0 ' + width + ' ' + height, width: width, height: height,
      role: 'img', 'aria-label': opts.ariaLabel || '折线图'
    });
    var allValues = [];
    seriesList.forEach(function (series) {
      (series.values || []).forEach(function (value) {
        if (typeof value === 'number' && isFinite(value)) allValues.push(value);
      });
    });
    if (!labels.length || !allValues.length) {
      emptyChart(host, opts.emptyMessage || '没有可绘制的数值。');
      return;
    }
    var yMax = niceMax(Math.max.apply(null, allValues));
    var n = labels.length;
    var plotRight = margin.l + plotW;
    var plotBottom = margin.t + plotH;
    function xAt(index) {
      return n <= 1 ? margin.l + plotW / 2 : margin.l + (index * plotW) / (n - 1);
    }
    function yAt(value) { return plotBottom - (value / yMax) * plotH; }
    for (var tick = 0; tick <= 4; tick += 1) {
      var tickValue = (yMax * tick) / 4;
      var tickY = yAt(tickValue);
      svg.appendChild(svgNode('line', {
        x1: margin.l, y1: tickY, x2: plotRight, y2: tickY, class: 'grid-line'
      }));
      var yLabel = svgNode('text', {
        x: margin.l - 8, y: tickY + 4, class: 'axis-label', 'text-anchor': 'end'
      });
      yLabel.textContent = axisValue(tickValue);
      svg.appendChild(yLabel);
    }
    var maxTicks = Math.max(3, Math.floor(plotW / 92));
    var step = Math.max(1, Math.ceil(n / maxTicks));
    for (var xIndex = 0; xIndex < n; xIndex += step) {
      var xLabel = svgNode('text', {
        x: xAt(xIndex), y: plotBottom + 16, class: 'axis-label',
        'text-anchor': xIndex === 0 ? 'start' : 'middle'
      });
      xLabel.textContent = labels[xIndex];
      svg.appendChild(xLabel);
    }
    svg.appendChild(svgNode('line', {
      x1: margin.l, y1: plotBottom, x2: plotRight, y2: plotBottom, class: 'axis-line'
    }));
    seriesList.forEach(function (series) {
      var d = '';
      var pen = false;
      (series.values || []).forEach(function (value, index) {
        if (typeof value !== 'number' || !isFinite(value)) { pen = false; return; }
        d += (pen ? ' L ' : ' M ') + xAt(index).toFixed(1) + ' ' + yAt(value).toFixed(1);
        pen = true;
      });
      if (!d) return;
      var path = svgNode('path', {
        d: d, fill: 'none', stroke: series.color,
        'stroke-width': series.width || 1.8,
        'stroke-linejoin': 'round', 'stroke-linecap': 'round'
      });
      if (series.dash) path.setAttribute('stroke-dasharray', series.dash);
      var title = svgNode('title');
      title.textContent = series.name;
      path.appendChild(title);
      svg.appendChild(path);
    });
    if (opts.marker && typeof opts.marker.index === 'number' &&
        opts.marker.index >= 0 && opts.marker.index < n) {
      var markerX = xAt(opts.marker.index);
      svg.appendChild(svgNode('line', {
        x1: markerX, y1: margin.t, x2: markerX, y2: plotBottom, class: 'marker-line'
      }));
      var markerLabel = svgNode('text', {
        x: markerX + 4, y: margin.t + 10, class: 'marker-label'
      });
      markerLabel.textContent = opts.marker.label || '';
      svg.appendChild(markerLabel);
    }
    host.appendChild(svg);
  }

  /* ------------------------------------------------------------ KPI */
  function renderKpis() {
    var run = state.run;
    var bins = currentBins();
    var isR0 = run.mode === 'R0';
    var arrivals = sumOf(valuesOf(bins, 'arrivals'));
    var rejected = sumOf(valuesOf(bins, 'rejected'));
    var delivered = sumOf(valuesOf(bins, 'delivered_kwh'));
    var cohort = run.cohort && typeof run.cohort === 'object' ? run.cohort : {};
    var demand = numeric(cohort.demand_kwh);
    var observed = run.observed && typeof run.observed === 'object' ? run.observed : {};
    var unmet = (!isR0 && demand !== null && delivered !== null) ? Math.max(0, demand - delivered) : null;
    $('kpi-arrivals').textContent = countOf(arrivals);
    $('kpi-arrivals-sub').textContent = isR0 ? '观测重放：分箱求和到达数' : '分箱求和；含被拒到达（入口观察）';
    if (isR0) {
      $('kpi-rejected').textContent = 'R0 不计算';
      $('kpi-rejected-sub').textContent = '观测重放不计算拒绝率与缺口';
    } else {
      $('kpi-rejected').textContent = countOf(rejected);
      $('kpi-rejected-sub').textContent = (arrivals !== null && arrivals > 0 && rejected !== null)
        ? '拒绝率 ' + pct(rejected / arrivals, 2) : '拒绝率 ' + UNKNOWN;
    }
    $('kpi-delivered').textContent = kwh(delivered, 1);
    if (isR0) {
      $('kpi-delivered-sub').textContent = '观测交付电量 ' + kwh(observed.energy_kwh_observed, 1) + '（observed 块）';
    } else {
      var share = demand !== null && demand > 0 && delivered !== null ? delivered / demand : null;
      $('kpi-delivered-sub').textContent = '需求 ' + kwh(demand, 1) + ' · 交付/需求 ' + pct(share, 2);
    }
    if (isR0) {
      $('kpi-unmet').textContent = 'R0 不计算';
      $('kpi-unmet-sub').textContent = '观测重放不计算未满足需求';
    } else {
      $('kpi-unmet').textContent = kwh(unmet, 1);
      $('kpi-unmet-sub').textContent = '需求 − 分箱交付合计（模型输出，不是实测）';
    }
  }

  /* ------------------------------------------------------------ 占用/充电时间序列 */
  function renderSeries() {
    var bins = currentBins();
    var labels = bins.map(function (item) { return binLabel(item.t_local); });
    var charge = valuesOf(bins, 'charge_bays_used');
    var ordinary = valuesOf(bins, 'ordinary_bays_used');
    var power = valuesOf(bins, 'charging_kw');
    if (!bins.length) {
      emptyChart($('chart-occupancy'), '没有时间序列数据（运行 JSON 的 series.bins 为空或缺失）。');
      emptyChart($('chart-power'), '没有时间序列数据。');
      $('series-range').textContent = '时间序列：' + UNKNOWN;
      $('series-note').textContent = '';
      renderLegend($('occupancy-legend'), []);
      renderLegend($('power-legend'), []);
      return;
    }
    var occupancySeries = [
      { name: '充电车位占用', color: COLORS[0], values: charge },
      { name: '普通车位占用', color: COLORS[1], values: ordinary }
    ];
    var powerSeries = [{ name: '充电功率（kW）', color: COLORS[2], values: power }];
    renderLegend($('occupancy-legend'), occupancySeries);
    renderLegend($('power-legend'), powerSeries);
    renderLineChart($('chart-occupancy'), occupancySeries, labels, {
      ariaLabel: '充电车位与普通车位占用时间序列（' + state.binMinutes + ' 分钟分箱）',
      emptyMessage: '该运行没有占用序列数值。'
    });
    renderLineChart($('chart-power'), powerSeries, labels, {
      ariaLabel: '充电功率时间序列（' + state.binMinutes + ' 分钟分箱）',
      emptyMessage: '该运行没有充电功率序列数值。'
    });
    var timeContract = state.run.time_contract || {};
    var first = labels[0];
    var last = labels[labels.length - 1];
    $('series-range').textContent = '时间范围 ' + first + ' — ' + last + ' · ' +
      bins.length + ' 个 ' + state.binMinutes + ' 分钟分箱 · 本地时钟 ' +
      text(timeContract.local_profile_clock, '未知时区');
    $('series-note').textContent = '分箱：契约数据为 ' + baseBinMinutes() +
      ' 分钟一箱，本页按所选分箱汇总（占用/功率取均值，计数与电量取求和）。' +
      '时间标签来自各分箱 t_local；缺测数值留空断开，不补 0。';
  }

  /* ------------------------------------------------------------ 到达/拒绝/交付 */
  function renderArrivals() {
    var run = state.run;
    var isR0 = run.mode === 'R0';
    var bins = currentBins();
    if (!bins.length) {
      emptyChart($('chart-arrivals'), '没有时间序列数据。');
      emptyChart($('chart-delivered'), '没有时间序列数据。');
      renderLegend($('arrivals-legend'), []);
      renderLegend($('delivered-legend'), []);
      $('arrivals-summary').textContent = '';
      return;
    }
    var labels = bins.map(function (item) { return binLabel(item.t_local); });
    var arrivals = valuesOf(bins, 'arrivals');
    var rejected = valuesOf(bins, 'rejected');
    var delivered = valuesOf(bins, 'delivered_kwh');
    var arrivalSeries = [{ name: '到达（辆）', color: COLORS[0], values: arrivals }];
    if (!isR0) {
      arrivalSeries.push({ name: '被拒（辆，模型输出）', color: COLORS[4], values: rejected });
    }
    var deliveredSeries = [{ name: '交付电量（kWh，模型输出）', color: COLORS[2], values: delivered }];
    renderLegend($('arrivals-legend'), arrivalSeries);
    renderLegend($('delivered-legend'), deliveredSeries);
    renderLineChart($('chart-arrivals'), arrivalSeries, labels, {
      ariaLabel: '到达与被拒时间序列（' + state.binMinutes + ' 分钟分箱）',
      emptyMessage: '该运行没有被拒/到达序列数值。'
    });
    renderLineChart($('chart-delivered'), deliveredSeries, labels, {
      ariaLabel: '交付电量时间序列（' + state.binMinutes + ' 分钟分箱）',
      emptyMessage: '该运行没有交付电量序列数值。'
    });
    var arrivalsTotal = sumOf(arrivals);
    var rejectedTotal = sumOf(rejected);
    var deliveredTotal = sumOf(delivered);
    var parts = [];
    parts.push('到达合计 ' + countOf(arrivalsTotal));
    if (isR0) {
      parts.push('R0 不计算拒绝率与缺口');
    } else {
      parts.push('被拒合计 ' + countOf(rejectedTotal));
      parts.push('拒绝率 ' + ((arrivalsTotal && rejectedTotal !== null) ? pct(rejectedTotal / arrivalsTotal, 2) : UNKNOWN));
    }
    parts.push('交付合计 ' + kwh(deliveredTotal, 1));
    $('arrivals-summary').textContent = parts.join(' · ') + '。未满足需求见上方 KPI。';
  }

  /* ------------------------------------------------------------ 成本曲线 */
  function renderCost() {
    var run = state.run;
    var isR0 = run.mode === 'R0';
    var rows = Array.isArray(run.rows) ? run.rows.filter(function (row) { return row && typeof row === 'object'; }) : [];
    var emptyNote = $('cost-empty');
    if (isR0) {
      emptyNote.hidden = false;
      emptyNote.textContent = 'R0 不计算 J(n)：观测重放没有配置—成本优化结果。';
    } else if (!rows.length) {
      emptyNote.hidden = false;
      emptyNote.textContent = '该运行没有配置—成本曲线（rows 为空或缺失），无法显示 J(n)。';
    } else {
      emptyNote.hidden = true;
      emptyNote.textContent = '';
    }
    if (isR0 || !rows.length) {
      setChildren($('cost-head'), []);
      renderLegend($('cost-legend'), []);
      emptyChart($('chart-cost'), isR0 ? 'R0 不计算 J(n)' : '没有配置—成本曲线数据。');
      fillTable($('cost-table'), [], []);
      $('cost-table').replaceChildren();
      fillTable($('cost-detail'), [], []);
      $('cost-detail').replaceChildren();
      $('cost-note').textContent = isR0
        ? 'R0 只有观测会话与占用重放，不产生拒绝率、缺口或 J(n)；成本参数与假设仅在 R1/R2 运行中展示。'
        : '';
      return;
    }
    var sorted = rows.slice().sort(function (a, b) { return (a.n || 0) - (b.n || 0); });
    var labels = sorted.map(function (row) { return 'n=' + text(row.n); });
    var series = [
      { name: 'J(n) 总成本', color: COLORS[0], values: sorted.map(function (row) { return numeric(row.J); }) },
      { name: '资本/运营成本', color: COLORS[2], values: sorted.map(function (row) { return numeric(row.capital); }), dash: '5 3' },
      { name: '服务损失', color: COLORS[1], values: sorted.map(function (row) { return numeric(row.service_loss); }), dash: '2 3' }
    ];
    renderLegend($('cost-legend'), series);
    var summary = run.summary && typeof run.summary === 'object' ? run.summary : {};
    var bestN = summary.best_n;
    var bestIndex = -1;
    sorted.forEach(function (row, index) { if (bestIndex < 0 && row.n === bestN) bestIndex = index; });
    renderLineChart($('chart-cost'), series, labels, {
      ariaLabel: '各配置 n 的 J(n)、资本成本与服务损失',
      marker: bestIndex >= 0 ? { index: bestIndex, label: '最优点 n=' + text(bestN) } : null,
      emptyMessage: '没有可绘制的成本数值。'
    });
    var headParts = [];
    headParts.push('最优点 n = ' + text(bestN));
    headParts.push('argmin ' + text(Array.isArray(summary.argmin) ? '[' + summary.argmin.join(', ') + ']' : summary.argmin));
    headParts.push('近优 ' + text(Array.isArray(summary.near_optimal) ? '[' + summary.near_optimal.join(', ') + ']' : summary.near_optimal));
    var registered = summary.at_registered_ev_bays;
    if (registered && typeof registered === 'object') {
      headParts.push('登记 EV 位 n = ' + text(registered.n) + '（J = ' + text(registered.J) + '）');
    }
    var atBest = summary.at_best;
    if (atBest && typeof atBest === 'object') {
      headParts.push('最优点 at_best：J = ' + text(atBest.J));
    }
    $('cost-head').textContent = headParts.join(' · ');
    fillTable($('cost-table'),
      ['n', '资本/运营成本', '服务损失', 'J(n)', '被拒总量', '交付比例'],
      sorted.map(function (row) {
        return [text(row.n), text(row.capital), text(row.service_loss), text(row.J),
          text(row.rejected_total), pct(row.delivered_share, 2)];
      }));
    var selected = run.selected && typeof run.selected === 'object' ? run.selected : {};
    var selectedN = isMissing(selected.n) ? bestN : selected.n;
    var selectedRow = null;
    sorted.forEach(function (row) { if (!selectedRow && row.n === selectedN) selectedRow = row; });
    if (!selectedRow) selectedRow = sorted[bestIndex >= 0 ? bestIndex : 0];
    var detailRows = [];
    if (selectedRow) {
      detailRows.push(['n', text(selectedRow.n)]);
      Object.keys(selectedRow).forEach(function (key) {
        if (key === 'n' || key === 'features') return;
        detailRows.push([key, text(selectedRow[key])]);
      });
      var features = selectedRow.features && typeof selectedRow.features === 'object' ? selectedRow.features : {};
      Object.keys(features).forEach(function (key) {
        detailRows.push(['features.' + key, text(features[key])]);
      });
    }
    fillTable($('cost-detail'), ['分项', '取值'], detailRows);
    $('cost-note').textContent = '成本与 J(n) 是模型输出，不是实测；缺失字段显示“未知”，不以 0 代替。' +
      '成本参数 θ、假设与来源见下方元信息面板。';
  }
  function renderCostChartOnly() {
    var run = state.run;
    if (!run || run.mode === 'R0') return;
    var rows = Array.isArray(run.rows) ? run.rows.filter(function (row) { return row && typeof row === 'object'; }) : [];
    var host = $('chart-cost');
    if (!rows.length) return;
    var sorted = rows.slice().sort(function (a, b) { return (a.n || 0) - (b.n || 0); });
    var labels = sorted.map(function (row) { return 'n=' + text(row.n); });
    var series = [
      { name: 'J(n) 总成本', color: COLORS[0], values: sorted.map(function (row) { return numeric(row.J); }) },
      { name: '资本/运营成本', color: COLORS[2], values: sorted.map(function (row) { return numeric(row.capital); }), dash: '5 3' },
      { name: '服务损失', color: COLORS[1], values: sorted.map(function (row) { return numeric(row.service_loss); }), dash: '2 3' }
    ];
    var summary = run.summary && typeof run.summary === 'object' ? run.summary : {};
    var bestIndex = -1;
    sorted.forEach(function (row, index) { if (bestIndex < 0 && row.n === summary.best_n) bestIndex = index; });
    renderLineChart(host, series, labels, {
      ariaLabel: '各配置 n 的 J(n)、资本成本与服务损失',
      marker: bestIndex >= 0 ? { index: bestIndex, label: '最优点 n=' + text(summary.best_n) } : null
    });
  }

  /* ------------------------------------------------------------ 元信息 */
  function renderMeta() {
    var run = state.run;
    var index = state.index || {};
    var indexed = indexRunFor(run.run_id) || {};
    var block = run.block || indexed.block || {};
    var timeContract = run.time_contract || {};
    var cohort = run.cohort && typeof run.cohort === 'object' ? run.cohort : {};
    var origins = cohort.origin_counts && typeof cohort.origin_counts === 'object' ? cohort.origin_counts : {};
    var provenance = run.provenance && typeof run.provenance === 'object' ? run.provenance : {};
    var indexProvenance = index.provenance && typeof index.provenance === 'object' ? index.provenance : {};
    var seeds = provenance.seed_registry && typeof provenance.seed_registry === 'object' ? provenance.seed_registry : {};
    var seedComponents = seeds.components && typeof seeds.components === 'object' ? seeds.components : {};
    var site = siteEntry(run.site_id);
    var registered = site.registered && typeof site.registered === 'object' ? site.registered : {};
    var coverage = site.coverage && typeof site.coverage === 'object' ? site.coverage : {};
    var theta = run.cost_theta && typeof run.cost_theta === 'object' ? run.cost_theta : {};
    var thetaProvenance = theta.provenance && typeof theta.provenance === 'object' ? theta.provenance : Object.assign({}, indexProvenance);

    fillFacts($('facts-run'), [
      ['run_id', text(run.run_id)],
      ['模式', modeLabel(run.mode) + '（' + provenanceText(modeInfo(run.mode).provenance) + '）'],
      ['站点', siteLabel(run.site_id)],
      ['情景', scenarioLabel(run.scenario_id)],
      ['规则 / 重复', text(run.rule) + ' / rep ' + text(run.replicate)],
      ['单枪功率', isMissing(run.station_power_kw) ? UNKNOWN : num(run.station_power_kw, 1) + ' kW'],
      ['时间块 W_local', text(block.W_local) + '（周 ' + text(block.week_index) + '，' + text(block.segment) + '）'],
      ['核算 / 预热', text(block.accounting_days) + ' 天 / ' + text(block.warmup_days) + ' 天'],
      ['世界哈希', text(run.world_hash === undefined ? indexed.world_hash : run.world_hash)],
      ['时钟', text(timeContract.clock)],
      ['时区', text(timeContract.local_profile_clock)],
      ['W → T', text(timeContract.W_local) + ' → ' + text(timeContract.T_local)],
      ['H 本地窗口末', text(timeContract.H_local)],
      ['取整规则', text(timeContract.rounding)]
    ]);

    fillFacts($('facts-provenance'), [
      ['schema_version', text(index.schema_version)],
      ['生成时间', text(index.generated_at)],
      ['code_version', text(provenance.code_version, text(indexProvenance.code_version))],
      ['命令', text(provenance.command)],
      ['fit_hash', text(provenance.fit_hash)],
      ['配色 / 版本来源', text(provenance.config_sha256)]
    ]);

    var seedRows = [];
    var rootSeed = seeds.root_seed === undefined ? indexProvenance.root_seed : seeds.root_seed;
    seedRows.push(['root_seed', text(rootSeed)]);
    Object.keys(seedComponents).forEach(function (key) {
      seedRows.push([key, text(seedComponents[key])]);
    });
    fillTable($('table-seeds'), ['随机流', '种子'], seedRows);

    fillFacts($('facts-coverage'), [
      ['登记总车位', text(registered.total_spaces)],
      ['登记 EV 位', text(registered.ev_bays_registered)],
      ['登记来源', text(registered.provenance)],
      ['历史容量已知', text(registered.historical_capacity_known)],
      ['观测天数', text(coverage.observed_days)],
      ['跨期天数', text(coverage.span_days)],
      ['首日 → 末日', text(coverage.first_day) + ' → ' + text(coverage.last_day)],
      ['未知日', text(coverage.unknown_days)],
      ['确认零值日', text(coverage.confirmed_zero_days)],
      ['关闭日', text(coverage.closed_days)],
      ['缺报日', text(coverage.missing_report_days)]
    ]);

    fillFacts($('facts-cohort'), [
      ['队列规模', text(cohort.size)],
      ['E1（需充电电车）', text(cohort.n_E1)],
      ['I（燃油车）', text(cohort.n_I)],
      ['E0（不充电电车）', text(cohort.n_E0)],
      ['需求电量', isMissing(cohort.demand_kwh) ? UNKNOWN : kwh(cohort.demand_kwh, 1)],
      ['锚点会话', text(origins.observed_anchor)],
      ['生成隐藏 E1', text(origins.generated_hidden_E1)],
      ['生成 I', text(origins.generated_I)],
      ['生成 E0', text(origins.generated_E0)]
    ]);

    var thetaKeys = ['a', 'b_I', 'b_E0', 'b_E1', 'c_E', 'c_res'];
    var thetaRows = [];
    thetaKeys.forEach(function (key) {
      thetaRows.push([key, text(theta[key]), text(thetaProvenance[key])]);
    });
    if (theta.theta_id) thetaRows.unshift(['theta_id', text(theta.theta_id), '']);
    fillTable($('table-theta'), ['参数', '取值', '来源'], thetaRows);

    var assumptions = [];
    var scenario = scenarioEntry(run.scenario_id);
    (Array.isArray(scenario.assumptions) ? scenario.assumptions : []).forEach(function (item) {
      if (item && typeof item === 'object') assumptions.push(item);
    });
    (Array.isArray(run.assumptions) ? run.assumptions : []).forEach(function (item) {
      if (item && typeof item === 'object') assumptions.push(item);
    });
    fillTable($('table-assumptions'), ['字段', '取值', '来源性质', '来源', '说明'],
      assumptions.map(function (item) {
        return [text(item.field), text(item.value), provenanceText(item.provenance),
          text(item.source_ref), text(item.note)];
      }));

    var notesHost = $('source-notes');
    notesHost.replaceChildren();
    function notesBlock(title, items) {
      var values = Array.isArray(items) ? items.filter(function (item) {
        return item !== null && item !== undefined && item !== '';
      }) : [];
      if (!values.length) return;
      notesHost.appendChild(el('h4', { class: 'subhead', text: title }));
      notesHost.appendChild(el('ul', null, values.map(function (item) {
        return el('li', { text: typeof item === 'string' ? item : JSON.stringify(item) });
      })));
    }
    notesBlock('来源说明', indexProvenance.source_notes);
    notesBlock('限制', indexProvenance.limits);
    var inputHashes = indexProvenance.input_hashes && typeof indexProvenance.input_hashes === 'object'
      ? indexProvenance.input_hashes : {};
    notesBlock('输入哈希', Object.keys(inputHashes).map(function (key) {
      return key + ' = ' + text(inputHashes[key]);
    }));
    var modeNotes = [];
    MODE_ORDER.forEach(function (mode) {
      var info = modeInfo(mode);
      if (info && info.note) modeNotes.push(mode + '（' + provenanceText(info.provenance) + '）：' + info.note);
    });
    notesBlock('模式说明', modeNotes);
    if (site.mode_notes && typeof site.mode_notes === 'object') {
      notesBlock('站点模式备注', Object.keys(site.mode_notes).map(function (key) {
        return key + '：' + text(site.mode_notes[key]);
      }));
    }
  }

  /* ------------------------------------------------------------ R0 观测数据 */
  function renderObserved() {
    var run = state.run;
    var host = $('observed-panel');
    var observed = run.observed && typeof run.observed === 'object' ? run.observed : null;
    if (run.mode !== 'R0' || !observed) {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    var sessions = Array.isArray(observed.sessions) ? observed.sessions : [];
    var dayStatus = Array.isArray(observed.day_status) ? observed.day_status : [];
    var peaks = Array.isArray(observed.peak_concurrency_by_day) ? observed.peak_concurrency_by_day : [];
    fillFacts($('facts-observed'), [
      ['登记 EV 位', text(observed.registered_bays)],
      ['观测交付电量', isMissing(observed.energy_kwh_observed) ? UNKNOWN : kwh(observed.energy_kwh_observed, 1)],
      ['观测会话条数', countOf(sessions.length)],
      ['日状态条数', countOf(dayStatus.length)],
      ['峰值并发条数', countOf(peaks.length)],
      ['口径', 'R0 只重放观测：拒绝率、缺口与 J(n) 都不计算']
    ]);
    fillLimitedTable($('table-observed-sessions'),
      ['session_id', '到达（本地）', '停留分钟', '充电分钟', '观测 kWh', '状态', '可用于需求', '不可用原因'],
      sessions.map(function (item) {
        return [text(item.session_id), text(item.arrival_local), text(item.dwell_min),
          text(item.charge_min), text(item.observed_kwh), text(item.status),
          text(item.usable_for_demand), text(item.unusable_reason)];
      }), MAX_TABLE_ROWS);
    fillLimitedTable($('table-observed-days'), ['日期', '状态', '会话数', '证据'],
      dayStatus.map(function (item) {
        return [text(item.day), text(item.status), text(item.sessions), text(item.evidence)];
      }), MAX_TABLE_ROWS);
    fillTable($('table-observed-peaks'), ['日期', '峰值并发'],
      peaks.map(function (item) { return [text(item.day), text(item.peak)]; }));
  }

  /* ------------------------------------------------------------ 导出 */
  function renderExports() {
    var run = state.run;
    var indexed = indexRunFor(run.run_id) || {};
    var runId = encodeURIComponent(run.run_id);
    var rows = Array.isArray(run.rows) ? run.rows : [];
    var vehicles = run.selected && Array.isArray(run.selected.vehicles) ? run.selected.vehicles : [];
    var exportBlock = run.export && typeof run.export === 'object' ? run.export : {};
    var worldFile = exportBlock.world_file || indexed.world_file || null;
    var isR0 = run.mode === 'R0';
    var links = [];
    function exportLink(format, label, enabled, reason) {
      if (enabled) {
        return el('a', {
          class: 'export-btn',
          href: '/api/nyc/export/' + runId + '?format=' + format,
          download: ''
        }, label);
      }
      return el('span', { class: 'export-btn disabled', 'aria-disabled': 'true', title: reason || '不可用' },
        [label, el('span', { class: 'hint', text: '（' + (reason || '不可用') + '）' })]);
    }
    links.push(exportLink('json', '下载运行 JSON', true));
    links.push(exportLink('curve_csv', '配置—成本曲线 CSV', rows.length > 0,
      isR0 ? 'R0 不计算 J(n)' : 'rows 为空'));
    links.push(exportLink('outcomes_csv', '逐车结果 CSV', vehicles.length > 0,
      isR0 ? 'R0 无逐车选择结果' : 'selected.vehicles 为空'));
    links.push(exportLink('world_json', '冻结世界 JSON', !!worldFile,
      worldFile ? '' : '运行未关联 world 文件'));
    setChildren($('export-links'), links);
    fillFacts($('facts-export'), [
      ['world_hash（运行）', text(run.world_hash)],
      ['world_hash（index）', text(indexed.world_hash)],
      ['world_file（index）', text(indexed.world_file)],
      ['export.world_file（运行）', text(exportBlock.world_file)],
      ['export.curve_csv', text(exportBlock.curve_csv)],
      ['export.outcomes_csv', text(exportBlock.outcomes_csv)],
      ['世界文件状态', worldFile ? '有关联记录：' + worldFile + '（可导出）' : '未关联 world 文件（world_json 不可导出）']
    ]);
  }

  /* ============================================================ v2 证据类型 */
  var EVIDENCE = {
    observed_replay: {
      label: '观测重放', kind: 'observed',
      note: 'R0 真实会话观测重放；不计算 J(n)、拒绝率或模拟交付。'
    },
    expected_cost: {
      label: '期望成本选择', kind: 'implementable',
      note: '对重复取期望后的 J̄(n) 与 argmin（选择阶段时间块 + 重复数）；可实施选择。'
    },
    fixed_config_eval: {
      label: '固定配置评价', kind: 'eval',
      note: '冻结选择阶段得到的 n，在独立时间块×独立重复上评价；必须标 block_id 与评价重复数。'
    },
    robust_A: {
      label: '稳健 A（设计对象）', kind: 'robust',
      note: '先对 ω 求期望，再对 φ/θ 取最坏；这是设计对象。'
    },
    robust_B: {
      label: '稳健 B（压力测试对象）', kind: 'robust',
      note: '对单次实现取最坏；单独命名，不是设计选择，不得与 robust_A 合并。'
    },
    single_world_hindsight: {
      label: '单世界事后最优（仅诊断）', kind: 'diagnostic',
      note: '单个世界内的事后最优 n 与其 J(n)；仅诊断，不得称推荐配置。'
    }
  };
  var EVIDENCE_ORDER = ['observed_replay', 'expected_cost', 'fixed_config_eval',
    'robust_A', 'robust_B', 'single_world_hindsight'];

  function evidenceInfo(kind) {
    if (typeof kind === 'string' && EVIDENCE[kind]) return EVIDENCE[kind];
    return { label: text(kind, '未知证据类型'), kind: 'missing', note: '未知证据类型' };
  }
  function evidenceLabel(kind) { return evidenceInfo(kind).label; }
  function runCoverageText(source) {
    var coverage = source && typeof source === 'object' ? source : {};
    var parts = [];
    Object.keys(coverage).forEach(function (key) {
      var value = coverage[key];
      if (value === null || value === undefined || value === '') return;
      parts.push(key + '=' + text(value));
    });
    return parts.length ? parts.join(' · ') : UNKNOWN;
  }
  function shortFingerprint(value) {
    if (typeof value !== 'string' || !value) return UNKNOWN;
    if (value.length <= 18) return value;
    return value.slice(0, 10) + '…' + value.slice(-6);
  }
  function curveOf(run) {
    var curve = run && run.curve;
    if (!curve || typeof curve !== 'object' || !Array.isArray(curve.n)) return null;
    return curve;
  }
  function curveHeader(key) {
    var names = {
      J: 'J̄(n) 期望总成本', capital: '资本/运营成本', refusal: '拒绝罚项',
      energy: '能量成本', resource: '资源成本', R_I: 'R_I', R_E0: 'R_E0',
      R_EP: 'R_EP', shortfall_kwh: 'shortfall_kwh', delivered_kwh: 'delivered_kwh',
      days: 'days'
    };
    return names[key] || key;
  }
  function provenanceCountsText() {
    var sources = state.index && Array.isArray(state.index.sources) ? state.index.sources : [];
    var counts = {};
    sources.forEach(function (item) {
      var provenance = item && item.provenance;
      if (typeof provenance !== 'string') return;
      counts[provenance] = (counts[provenance] || 0) + 1;
    });
    var keys = Object.keys(counts);
    if (!keys.length) return UNKNOWN;
    return keys.map(function (key) { return key + '=' + counts[key]; }).join(' · ') + ' 条 sources';
  }

  function renderEvidenceBadges() {
    var host = $('evidence-badges');
    if (!host) return;
    if (state.schemaKind === 'v3') {
      var v3Index = state.index || {};
      var v3Panels = v3Index.panels && typeof v3Index.panels === 'object' ? v3Index.panels : {};
      var v3Decision = v3Panels.decision && typeof v3Panels.decision === 'object' ? v3Panels.decision : {};
      var v3Worlds = Array.isArray(v3Index.worlds) ? v3Index.worlds : [];
      var v3Runs = indexRuns();
      var v3Fixed = Array.isArray(v3Decision.fixed_eval) ? v3Decision.fixed_eval : [];
      var v3Robust = Array.isArray(v3Decision.robust) ? v3Decision.robust : [];
      var v3Counts = v3Index.counts && typeof v3Index.counts === 'object' ? v3Index.counts : {};
      var v3Badges = [
        { cls: 'observed', label: 'R0 真实锚点回放', note: '不参与选择；不计算 J(n)',
          suffix: '（' + v3Worlds.filter(function (world) { return world && world.mechanism === 'R0'; }).length + '）' },
        { cls: 'implementable', label: '期望曲线 M0/M1/M2 与 n*', note: 'n* 来自期望成本 argmin',
          suffix: '（' + v3Runs.length + ' 个 run）' },
        { cls: 'eval', label: '固定配置评价', note: '跨机制 · 登记充电位 · n=0 基线',
          suffix: '（' + v3Fixed.length + '）' },
        { cls: 'robust', label: '稳健 A（设计对象）', note: '先对 ω 取期望再取最坏',
          suffix: '（' + v3Robust.filter(function (row) { return row && (row.object === 'A' || row.object === 'robust_A'); }).length + '）' },
        { cls: 'robust', label: '稳健 B（压力测试）', note: '对单次实现取最坏；不是设计选择',
          suffix: '（' + v3Robust.filter(function (row) { return row && (row.object === 'B' || row.object === 'robust_B'); }).length + '）' },
        { cls: 'diagnostic', label: '逐世界事后最优（CSV·仅诊断）', note: '读 panels.hindsight.csv 的真实行',
          suffix: '（' + v3Text(v3Counts.hindsight_rows) + '）' },
        { cls: 'eval', label: '留出 A/B + 噪声底', note: 'A 只评形状，B 预测数量+形状，A≠B',
          suffix: '（' + v3Text(v3Counts.holdout_table_a_rows) + ' / ' + v3Text(v3Counts.holdout_table_b_rows) + '）' },
        { cls: 'robust', label: '归因对照', note: '每次只改一个机制',
          suffix: '（' + v3Text(v3Counts.attribution_rows) + '）' }
      ];
      setChildren(host, v3Badges.map(function (item) {
        return el('span', { class: 'evidence-badge ' + item.cls, title: item.note },
          item.label + ' · ' + item.suffix);
      }));
      return;
    }
    var isV2 = state.schemaKind === 'v2';
    var runs = indexRuns();
    var fixedRows = state.index && Array.isArray(state.index.fixed_eval) ? state.index.fixed_eval : [];
    var robustRows = state.index && Array.isArray(state.index.robust) ? state.index.robust : [];
    var counts = {
      observed_replay: runs.filter(function (run) { return run.evidence_kind === 'observed_replay'; }).length,
      expected_cost: runs.filter(function (run) { return run.evidence_kind === 'expected_cost'; }).length,
      fixed_config_eval: fixedRows.length,
      robust_A: robustRows.filter(function (row) { return row && row.object === 'robust_A'; }).length,
      robust_B: robustRows.filter(function (row) { return row && row.object === 'robust_B'; }).length,
      single_world_hindsight: runs.filter(function (run) { return run.evidence_kind === 'single_world_hindsight'; }).length
    };
    var items = EVIDENCE_ORDER.map(function (kind) {
      var info = EVIDENCE[kind];
      var suffix = isV2 ? '（' + counts[kind] + '）' : '（v2）';
      return el('span', { class: 'evidence-badge ' + info.kind, title: info.note },
        info.label + ' · ' + kind + suffix);
    });
    if (!isV2) {
      items.push(el('span', { class: 'evidence-badge missing',
        text: 'v1 契约只含观测重放 / 单世界运行；四类证据对象在 v2 数据集提供' }));
    }
    setChildren(host, items);
  }

  /* ============================================================ v2 渲染 */
  function renderV2All() {
    renderV2RunMeta();
    renderV2Expected();
    renderV2Fixed();
    renderV2Robust();
    renderV2Hindsight();
    renderV2Observed();
    renderV2EvidenceMeta();
    renderV2Exports();
  }

  function renderV2RunMeta() {
    var run = state.run || {};
    var isR0 = run.evidence_kind === 'observed_replay';
    var curve = curveOf(run);
    var badge = $('v2-run-evidence');
    var info = evidenceInfo(run.evidence_kind);
    badge.className = 'evidence-badge ' + info.kind;
    badge.textContent = info.label + ' · ' + text(run.evidence_kind);
    badge.setAttribute('title', info.note);
    var head = [
      el('strong', { text: text(run.mode_label, modeLabel(run.mode)) }),
      ' · ' + siteLabel(run.site_id),
      ' · ' + (isMissing(run.scenario_id) ? '观测（无情景）' : scenarioLabel(run.scenario_id)),
      ' · 证据 ' + info.label,
      ' · 阶段 ' + text(run.stage),
      ' · 块 ' + text(run.block_id),
      ' · θ ' + text(run.theta_id),
      ' · 规则 ' + text(run.rule)
    ];
    setChildren($('v2-run-meta'), head);
    fillFacts($('v2-run-facts'), [
      ['run_id', text(run.run_id)],
      ['模式 / mode_label', text(run.mode) + ' · ' + text(run.mode_label, modeLabel(run.mode))],
      ['evidence_kind', info.label + '（' + text(run.evidence_kind) + '）'],
      ['stage / block_id', text(run.stage) + ' / ' + text(run.block_id) +
        (isMissing(run.block_date) ? '' : '（' + text(run.block_date) + '）')],
      ['theta_id / rule', text(run.theta_id) + ' / ' + text(run.rule)],
      ['n_choice / J_choice', isR0 ? 'R0 不计算' : text(run.n_choice) + ' / ' + text(run.J_choice)],
      ['n_registered_ev', isR0 ? 'R0 不计算' : text(run.n_registered_ev)],
      ['n_envelope（声明上限）', isR0 ? 'R0 不计算' : text(run.n_envelope)],
      ['n_worlds（选择重复数）', isR0 ? 'R0 不计算' : text(run.n_worlds)],
      ['曲线点数', isR0 ? 'R0 不计算' : (curve ? String(curve.n.length) : UNKNOWN)],
      ['curve_file / world_file', text(run.curve_file) + ' / ' + text(run.world_file)],
      ['覆盖范围', runCoverageText(run.coverage)],
      ['labels 说明', text(run.labels && run.labels.note)],
      ['数据来源（sources 计数）', provenanceCountsText()]
    ]);
    $('v2-run-note').textContent = isR0
      ? 'R0 观测重放：不显示 J(n)、拒绝率或模拟交付；未知项显示“未知”，不以 0 代替。'
      : (curve
        ? 'J(n) 与曲线来自研究产物；本页只展示，不重算成本。期望成本选择是可实施选择；单世界事后最优仅诊断。'
        : '该运行没有可用的成本曲线（未知）。');
  }

  function renderV2Expected() {
    var run = state.run || {};
    var curve = curveOf(run);
    var empty = $('v2-cost-empty');
    var head = $('v2-cost-head');
    var table = $('v2-cost-table');
    var note = $('v2-cost-note');
    var isExpected = run.evidence_kind === 'expected_cost';
    if (!isExpected || !curve) {
      empty.hidden = false;
      empty.textContent = run.evidence_kind === 'observed_replay'
        ? 'R0 不计算 J(n)：观测重放没有配置—成本优化结果。'
        : '该运行不是期望成本选择（evidence_kind = ' + text(run.evidence_kind) + '），没有 J̄(n) 曲线。';
      setChildren(head, []);
      renderLegend($('v2-cost-legend'), []);
      emptyChart($('v2-chart-cost'), empty.textContent);
      table.replaceChildren();
      note.textContent = '只展示研究产物中的期望成本曲线，不在页面重算成本。';
      return;
    }
    empty.hidden = true;
    var n = curve.n;
    var order = n.map(function (value, index) { return index; });
    order.sort(function (a, b) { return (Number(n[a]) || 0) - (Number(n[b]) || 0); });
    var labels = order.map(function (index) { return 'n=' + text(n[index]); });
    function pick(column) {
      var values = Array.isArray(curve[column]) ? curve[column] : [];
      return order.map(function (index) { return numeric(values[index]); });
    }
    var series = [
      { name: 'J̄(n) 期望总成本', color: COLORS[0], values: pick('J') },
      { name: '资本/运营成本', color: COLORS[2], values: pick('capital'), dash: '5 3' },
      { name: '拒绝罚项', color: COLORS[4], values: pick('refusal'), dash: '2 3' },
      { name: '能量成本', color: COLORS[1], values: pick('energy'), dash: '1 3' },
      { name: '资源成本', color: COLORS[3], values: pick('resource'), dash: '6 2 1 2' }
    ];
    renderLegend($('v2-cost-legend'), series);
    var jValues = Array.isArray(curve.J) ? curve.J : [];
    var minValue = null;
    var argmins = [];
    jValues.forEach(function (value, index) {
      if (typeof value !== 'number' || !isFinite(value)) return;
      if (minValue === null || value < minValue - 1e-9) {
        minValue = value;
        argmins = [n[index]];
      } else if (Math.abs(value - minValue) <= 1e-9) {
        argmins.push(n[index]);
      }
    });
    var markerIndex = -1;
    order.forEach(function (index, position) {
      if (markerIndex < 0 && n[index] === run.n_choice) markerIndex = position;
    });
    renderLineChart($('v2-chart-cost'), series, labels, {
      ariaLabel: '期望成本 J̄(n) 与成本分项曲线（选择阶段，n 为充电位数量）',
      marker: markerIndex >= 0 && !isMissing(run.n_choice)
        ? { index: markerIndex, label: 'n_choice=' + text(run.n_choice) } : null,
      emptyMessage: '曲线没有可绘制的成本数值。'
    });
    var headParts = [
      'n_choice = ' + text(run.n_choice),
      'J_choice = ' + text(run.J_choice),
      isMissing(run.n_registered_ev) ? null : '登记 EV 位 n = ' + text(run.n_registered_ev),
      isMissing(run.n_envelope) ? null : '声明上限 n = ' + text(run.n_envelope),
      'curve argmin = [' + (argmins.length ? argmins.join(', ') : UNKNOWN) + ']',
      '曲线点数 = ' + n.length,
      isMissing(run.n_worlds) ? null : '选择重复数 = ' + text(run.n_worlds)
    ].filter(function (part) { return part !== null; });
    head.textContent = headParts.join(' · ');
    var columns = ['n'].concat(Object.keys(curve).filter(function (key) {
      return key !== 'n' && Array.isArray(curve[key]);
    }));
    fillTable(table, columns.map(curveHeader), order.map(function (index) {
      return columns.map(function (key) { return text(curve[key][index]); });
    }));
    note.textContent = 'J̄(n) 为对重复取期望后的总成本；argmin 由页面从曲线数值取最小值，仅作展示，不重算成本。';
  }

  function fixedHeader(key) {
    var names = {
      block_id: 'block_id（评价块）', block_date: 'block_date',
      n_selected_on_select_block: '冻结 n（选择块上）', n_worlds: '评价重复数',
      J_mean_fixed: 'J_mean_fixed', J_se_fixed: 'J_se_fixed',
      J_hindsight_mean: 'J_hindsight_mean（冻结 n 的均值）', hindsight_gap: 'hindsight_gap',
      J_mean_registered_ev: 'J_mean_registered_ev',
      paired_diff_EF_minus_registered_ev: '配对差（EF − 登记 EV）',
      delivered_kwh_at_selected: '交付 kWh（结果变量）',
      refusals_at_selected: '拒绝数（结果变量）', J_mean_at_0: 'J_mean_at_0',
      deterministic_worlds: 'deterministic_worlds', mode: 'mode', scenario_id: 'scenario_id',
      theta_id: 'theta_id', rule: 'rule'
    };
    return names[key] || key;
  }
  function renderV2Fixed() {
    var run = state.run || {};
    var all = state.index && Array.isArray(state.index.fixed_eval) ? state.index.fixed_eval : [];
    var rows = all.filter(function (row) {
      if (!row || typeof row !== 'object') return false;
      if (row.site_id !== run.site_id) return false;
      if (!isMissing(run.scenario_id) && !isMissing(row.scenario_id) &&
          row.scenario_id !== run.scenario_id) return false;
      return true;
    });
    var summary = $('v2-fixed-summary');
    var table = $('v2-fixed-table');
    var note = $('v2-fixed-note');
    if (!rows.length) {
      summary.textContent = '该站点×情景没有固定配置评价行：' + UNKNOWN + '（数据未提供或该情景未做评价）。';
      table.replaceChildren();
      note.textContent = '';
      return;
    }
    summary.textContent = '固定配置评价 ' + rows.length + ' 行 · block_id = ' +
      uniq(rows.map(function (row) { return text(row.block_id); })).join(' / ') +
      ' · 评价重复数 n_worlds = ' +
      uniq(rows.map(function (row) { return text(row.n_worlds); })).join(' / ');
    var columns = ['block_id', 'block_date', 'n_selected_on_select_block', 'n_worlds',
      'J_mean_fixed', 'J_se_fixed', 'J_hindsight_mean', 'hindsight_gap',
      'J_mean_registered_ev', 'paired_diff_EF_minus_registered_ev',
      'delivered_kwh_at_selected', 'refusals_at_selected', 'J_mean_at_0',
      'deterministic_worlds', 'mode', 'scenario_id'];
    fillTable(table, columns.map(fixedHeader), rows.map(function (row) {
      return columns.map(function (key) { return text(row[key]); });
    }));
    note.textContent = '固定配置评价：n 在选择阶段冻结后，在独立时间块×独立重复上评价。配对差 = J_mean_fixed − J_mean_registered_ev；负值表示冻结选择比登记 EV 位更便宜。评价不是推荐配置。';
  }

  function renderV2Robust() {
    var run = state.run || {};
    var all = state.index && Array.isArray(state.index.robust) ? state.index.robust : [];
    var mode = isMissing(run.mode) || run.mode === 'R0' ? null : run.mode;
    var rows = all.filter(function (row) {
      if (!row || typeof row !== 'object') return false;
      if (row.site_id !== run.site_id) return false;
      if (mode && row.mode && row.mode !== mode) return false;
      return true;
    });
    var rowsA = rows.filter(function (row) {
      return row.object === 'robust_A' || (isMissing(row.object) && !isMissing(row.n_robust));
    });
    var rowsB = rows.filter(function (row) {
      return row.object === 'robust_B' || (isMissing(row.object) && !isMissing(row.n_robust_stress));
    });
    function renderBlock(rowsOfBlock, summaryId, tableId, noteId, columns, emptyText, extraNote) {
      var summary = $(summaryId);
      var table = $(tableId);
      var note = $(noteId);
      if (!rowsOfBlock.length) {
        summary.textContent = emptyText;
        table.replaceChildren();
        note.textContent = '';
        return;
      }
      summary.textContent = '对象 ' + text(rowsOfBlock[0].object) + ' · 行数 ' + rowsOfBlock.length +
        ' · 覆盖 ' + uniq(rowsOfBlock.map(function (row) { return text(row.coverage); })).join(' / ');
      fillTable(table, columns.map(function (key) { return key; }), rowsOfBlock.map(function (row) {
        return columns.map(function (key) { return text(row[key]); });
      }));
      note.textContent = extraNote;
    }
    renderBlock(rowsA, 'v2-robust-a-summary', 'v2-robust-a-table', 'v2-robust-a-note',
      ['mode', 'n_robust', 'worst_case_regret', 'n_scenarios', 'n_theta', 'coverage',
        'definition'],
      '该站点×模式没有 robust_A 记录：' + UNKNOWN,
      'robust_A 先对 ω 求期望、再对 φ/θ 取最坏；它是设计对象（不是单次实现的压力测试）。');
    renderBlock(rowsB, 'v2-robust-b-summary', 'v2-robust-b-table', 'v2-robust-b-note',
      ['mode', 'n_robust_stress', 'worst_case_regret_stress', 'n_realizations', 'n_theta',
        'coverage', 'definition'],
      '该站点×模式没有 robust_B 记录：' + UNKNOWN,
      'robust_B 对单次实现取最坏；它是单独命名的压力测试对象，不是设计选择，也不是 robust_A。');
    $('v2-robust-note').textContent = 'robust_A 与 robust_B 是不同对象：A 是设计对象（先对 ω 取期望再取最坏），B 是压力测试对象（对单次实现取最坏）。两者不合并展示、不互相替代；缺失时显示“未知”。';
  }

  function hindsightRowText(row) {
    var keys = Object.keys(row).filter(function (key) {
      return key !== 'per_world_hindsight_n';
    });
    return keys;
  }
  function renderV2Hindsight() {
    var run = state.run || {};
    var index = state.index || {};
    var summary = $('v2-hindsight-summary');
    var table = $('v2-hindsight-table');
    var note = $('v2-hindsight-note');
    var direct = [];
    if (Array.isArray(index.single_world_hindsight)) direct = index.single_world_hindsight;
    else if (Array.isArray(index.hindsight)) direct = index.hindsight;
    var hindsightRuns = indexRuns().filter(function (entry) {
      return entry.evidence_kind === 'single_world_hindsight';
    });
    var expectedRows = Array.isArray(index.expected_choice) ? index.expected_choice
      : (Array.isArray(index.expected) ? index.expected : []);
    var fixedRows = (Array.isArray(index.fixed_eval) ? index.fixed_eval : []).filter(function (row) {
      if (!row || typeof row !== 'object') return false;
      if (row.site_id !== run.site_id) return false;
      if (!isMissing(run.scenario_id) && !isMissing(row.scenario_id) &&
          row.scenario_id !== run.scenario_id) return false;
      return true;
    });
    if (direct.length) {
      var keys = hindsightRowText(direct[0]);
      summary.textContent = '逐世界事后最优记录 ' + direct.length + ' 条（仅诊断，不得作为推荐配置）';
      fillTable(table, keys, direct.map(function (row) {
        return keys.map(function (key) { return text(row[key]); });
      }));
      note.textContent = '单世界事后最优来自研究产物（index.single_world_hindsight）；仅用于诊断。';
      return;
    }
    if (run.evidence_kind === 'single_world_hindsight') {
      summary.textContent = '当前运行为单世界事后最优记录（evidence_kind = single_world_hindsight），仅诊断。';
      fillFactsTableFallback(table, run);
      note.textContent = '该 run 的逐世界数值见运行 JSON 导出（format=json）；本页不重算。';
      return;
    }
    var expectedMatch = expectedRows.filter(function (row) {
      if (!row || typeof row !== 'object') return false;
      if (!isMissing(run.site_id) && row.site_id !== run.site_id) return false;
      if (!isMissing(run.scenario_id) && row.scenario_id !== run.scenario_id) return false;
      return true;
    });
    if (expectedMatch.length) {
      var columns = ['site_id', 'scenario_id', 'hindsight_median_n', 'hindsight_mean_cost',
        'hindsight_gap_vs_EF', 'per_world_hindsight_n'];
      summary.textContent = '逐世界事后最优（来自 index.expected_choice）：' + expectedMatch.length +
        ' 行；仅诊断，不得作为推荐配置。';
      fillTable(table, columns.map(function (key) {
        return key === 'per_world_hindsight_n' ? '每个世界的事后最优 n 列表' : key;
      }), expectedMatch.map(function (row) {
        return columns.map(function (key) {
          if (key !== 'per_world_hindsight_n') return text(row[key]);
          var raw = row[key];
          var values = [];
          if (typeof raw === 'string') {
            try { values = JSON.parse(raw); } catch (error) { values = raw; }
          } else if (Array.isArray(raw)) {
            values = raw;
          }
          if (Array.isArray(values)) {
            return values.length + ' 个世界：[' + values.slice(0, 12).join(', ') +
              (values.length > 12 ? ', …' : '') + ']';
          }
          return text(values);
        });
      }));
      note.textContent = '事后最优 n（hindsight）与期望成本 argmin 是不同对象：前者仅诊断，后者才可实施。';
      return;
    }
    if (fixedRows.length && fixedRows.some(function (row) { return !isMissing(row.J_hindsight_mean); })) {
      var rowColumns = ['block_id', 'n_worlds', 'J_mean_fixed', 'J_hindsight_mean',
        'hindsight_gap', 'J_mean_registered_ev'];
      summary.textContent = '仅诊断 · 评价块上的事后最优均值：' + fixedRows.length +
        ' 行；数据未提供逐世界明细时，仅展示 fixed_eval 的 J_hindsight_mean / hindsight_gap。';
      fillTable(table, rowColumns.map(function (key) {
        return key === 'J_hindsight_mean' ? 'J_hindsight_mean（事后最优均值）' : key;
      }), fixedRows.map(function (row) {
        return rowColumns.map(function (key) { return text(row[key]); });
      }));
      note.textContent = '单世界事后最优仅诊断，不是推荐配置；本数据集的逐世界最优明细为“未知”（未登记 single_world_hindsight / expected_choice）。';
      return;
    }
    summary.textContent = '单世界事后最优：' + UNKNOWN + '（该数据集未提供逐世界明细，也没有可就近展示的事后最优字段）。';
    table.replaceChildren();
    note.textContent = '仅诊断对象；不得把期望成本 argmin 当作单世界事后最优，反之亦然。';
  }
  function fillFactsTableFallback(host, run) {
    var keys = ['run_id', 'site_id', 'mode', 'scenario_id', 'stage', 'block_id', 'theta_id',
      'rule', 'n_choice', 'J_choice'];
    fillTable(host, keys, [keys.map(function (key) { return text(run[key]); })]);
  }

  function renderV2Observed() {
    var run = state.run || {};
    var host = $('v2-observed-panel');
    if (run.evidence_kind !== 'observed_replay') {
      host.hidden = true;
      return;
    }
    host.hidden = false;
    var days = Array.isArray(run.days) ? run.days : [];
    var coverage = run.coverage && typeof run.coverage === 'object' ? run.coverage : {};
    fillFacts($('v2-observed-facts'), [
      ['run_id', text(run.run_id)],
      ['日期范围', days.length
        ? text(days[0].date) + ' → ' + text(days[days.length - 1].date) : UNKNOWN],
      ['覆盖（周内会话 / 天数）', text(coverage.sessions_in_week) + ' / ' + text(coverage.days)],
      ['J(n) / 拒绝率 / 模拟交付', 'R0 不计算'],
      ['unknown', Array.isArray(run.unknown) ? run.unknown.join('；') : UNKNOWN]
    ]);
    fillTable($('v2-observed-days'),
      ['日期', '会话数', '连接分钟', '观测 kWh', '日状态'],
      days.map(function (day) {
        return [text(day.date), text(day.sessions), text(day.connected_min),
          text(day.observed_kwh), text(day.day_status)];
      }));
  }

  function renderV2EvidenceMeta() {
    var index = state.index || {};
    var run = state.run || {};
    var counts = index.counts && typeof index.counts === 'object' ? index.counts : {};
    var registration = index.registration && typeof index.registration === 'object'
      ? index.registration : {};
    fillFacts($('v2-facts-dataset'), [
      ['schema_version', text(index.schema_version)],
      ['dataset / schema_kind', text(index.dataset) + ' / ' + text(index.schema_kind)],
      ['generated_at', text(index.generated_at)],
      ['code_version', text(index.code_version)],
      ['counts.runs', text(counts.runs)],
      ['counts.worlds', text(counts.worlds)],
      ['counts.fixed_eval_rows', text(counts.fixed_eval_rows)],
      ['counts.robust_rows', text(counts.robust_rows)],
      ['registration.design', shortFingerprint(registration.design_sha256 ||
        registration.design)],
      ['registration.code', shortFingerprint(registration.code_sha256 ||
        registration.code)],
      ['data_dir', text(index.data_dir)]
    ]);
    var coverageFacts = [];
    var coverage = run.coverage && typeof run.coverage === 'object' ? run.coverage : {};
    Object.keys(coverage).forEach(function (key) {
      coverageFacts.push([key, text(coverage[key])]);
    });
    var site = siteEntry(run.site_id);
    ['registered_ev_bays', 'registered_total_spaces', 'N_R1', 'N_R2'].forEach(function (key) {
      if (site && site[key] !== undefined) coverageFacts.push([key, text(site[key])]);
    });
    if (!coverageFacts.length) coverageFacts.push(['覆盖范围', UNKNOWN]);
    fillFacts($('v2-facts-coverage'), coverageFacts);
    var unknownHost = $('v2-unknown-list');
    var unknowns = Array.isArray(run.unknown) ? run.unknown.slice() : [];
    if (!unknowns.length) {
      setChildren(unknownHost, el('li', { class: 'missing', text: '未知（该运行未登记 unknown 清单）' }));
    } else {
      setChildren(unknownHost, unknowns.map(function (item) {
        return el('li', { text: typeof item === 'string' ? item : JSON.stringify(item) });
      }));
    }
    var sources = Array.isArray(index.sources) ? index.sources : [];
    fillTable($('v2-sources-table'), ['来源文件（path）', '来源性质（provenance）'],
      sources.map(function (item) {
        return [text(item && item.path), text(item && item.provenance)];
      }));
    var limits = Array.isArray(index.limits) ? index.limits : [];
    var limitsHost = $('v2-limits-list');
    if (!limits.length) {
      setChildren(limitsHost, el('li', { class: 'missing', text: '未知（数据未登记 limits）' }));
    } else {
      setChildren(limitsHost, limits.map(function (item) {
        return el('li', { text: typeof item === 'string' ? item : JSON.stringify(item) });
      }));
    }
    $('v2-labels-rule').textContent = index.labels_rule
      ? '标签规则：' + index.labels_rule : '标签规则：' + UNKNOWN;
  }

  function renderV2Exports() {
    var run = state.run || {};
    var runId = encodeURIComponent(run.run_id || '');
    var curve = curveOf(run);
    var indexed = indexRunFor(run.run_id) || {};
    var worldFile = run.world_file || indexed.world_file || null;
    function exportLink(format, label, enabled, reason, filename) {
      if (enabled) {
        return el('a', {
          class: 'export-btn',
          href: '/api/nyc/export/' + runId + '?format=' + format +
            '&dataset=' + encodeURIComponent(state.dataset),
          download: filename || ''
        }, label);
      }
      return el('span', { class: 'export-btn disabled', 'aria-disabled': 'true',
        title: reason || '不可用' },
        [label, el('span', { class: 'hint', text: '（' + (reason || '不可用') + '）' })]);
    }
    var fileBase = 'nyc-' + (run.run_id || 'unknown');
    setChildren($('v2-export-links'), [
      exportLink('json', '下载运行 JSON', true, '', fileBase + '.json'),
      exportLink('curve_csv', '下载曲线 CSV',
        !!curve && run.evidence_kind === 'expected_cost',
        run.evidence_kind === 'observed_replay' ? 'R0 不计算 J(n)' : '没有 curve',
        fileBase + '-curve.csv'),
      exportLink('world_json', '下载冻结世界 JSON', !!worldFile,
        worldFile ? '' : '该运行未关联 world 文件', fileBase + '-world.json')
    ]);
    fillFacts($('v2-facts-export'), [
      ['run JSON URL', '/api/nyc/export/' + text(run.run_id) + '?format=json&dataset=v2'],
      ['curve CSV URL', curve && run.evidence_kind === 'expected_cost'
        ? '/api/nyc/export/' + text(run.run_id) + '?format=curve_csv&dataset=v2' : UNKNOWN],
      ['world JSON URL', worldFile
        ? '/api/nyc/export/' + text(run.run_id) + '?format=world_json&dataset=v2' : UNKNOWN],
      ['curve_file（研究产物）', text(run.curve_file)],
      ['world_file（研究产物）', text(worldFile)],
      ['页面数值锚点', 'n_choice=' + text(run.n_choice) + ' · J_choice=' +
        text(run.J_choice) + ' · 曲线点数=' + (curve ? String(curve.n.length) : UNKNOWN)]
    ]);
  }

  /* ============================================================ v3 机制对照数据集 */
  var V3_MECH_ORDER = ['M0', 'M1', 'M2'];
  var V3_MECH = {
    M0: { label: 'M0 冻结 v2 模板（校正前对照）',
          note: '冻结 v2 生成模板作对照；不是校正后的机制。' },
    M1: { label: 'M1 到达时间条件属性（训练集收缩）',
          note: '到达时间与属性联合抽样，按训练集收缩；只改属性形成方式。' },
    M2: { label: 'M2 经验连续周/多日块',
          note: '用训练期连续周/多日块作为生成单元；保留跨日会话与前史。' }
  };
  var V3_MISSING = '未定义';

  function isV3() { return state.schemaKind === 'v3'; }
  function v3Val(value, digits) {
    if (isMissing(value) || value === '') return V3_MISSING;
    if (typeof value === 'number') return num(value, digits === undefined ? 2 : digits);
    if (typeof value === 'boolean') return value ? '是' : '否';
    if (typeof value === 'object') {
      try { return JSON.stringify(value); } catch (error) { return String(value); }
    }
    return String(value);
  }
  function v3Int(value) { return v3Val(value, 0); }
  function v3Text(value) {
    if (isMissing(value) || value === '') return V3_MISSING;
    return String(value);
  }
  function v3Mechanism(mech) {
    return V3_MECH[mech] || { label: v3Text(mech), note: '' };
  }
  function v3Basename(path) {
    if (typeof path !== 'string' || !path) return null;
    var parts = path.split('/');
    return parts[parts.length - 1] || null;
  }
  function v3TableURL(path) {
    var name = v3Basename(path);
    return name ? '/api/nyc/table/' + encodeURIComponent(name) + '?dataset=v3' : null;
  }
  function v3RunURL(runId) {
    return '/api/nyc/run/' + encodeURIComponent(runId) + '?dataset=v3';
  }
  function v3ExportURL(runId, format) {
    return '/api/nyc/export/' + encodeURIComponent(runId) + '?format=' +
      encodeURIComponent(format) + '&dataset=v3';
  }
  function v3WorldURL(worldId) {
    return '/api/nyc/world/' + encodeURIComponent(worldId) + '?dataset=v3';
  }
  function v3Link(label, href, filename) {
    return el('a', { class: 'export-btn', href: href, download: filename || '' }, label);
  }
  function v3DisabledLink(label, reason) {
    return el('span', { class: 'export-btn disabled', 'aria-disabled': 'true',
      title: reason }, [label, el('span', { class: 'hint', text: '（' + reason + '）' })]);
  }
  function v3DownloadsTables() {
    var downloads = state.index && state.index.downloads;
    var tables = downloads && Array.isArray(downloads.tables) ? downloads.tables : [];
    return tables.filter(function (path) { return typeof path === 'string'; });
  }
  function v3TableFor(part) {
    var tables = v3DownloadsTables();
    for (var index = 0; index < tables.length; index += 1) {
      if (tables[index].indexOf(part) >= 0) return tables[index];
    }
    return null;
  }
  function v3JsonAdd(host, entries) {
    var links = [];
    entries.forEach(function (entry) {
      if (!entry) return;
      if (entry.href) links.push(v3Link(entry.label, entry.href, entry.filename));
      else links.push(v3DisabledLink(entry.label, entry.reason || '不可用'));
    });
    setChildren(host, links);
  }

  /* ------------------------------------------------------------ CSV 解析（只读真实文件） */
  function parseCSVText(source) {
    var value = String(source === null || source === undefined ? '' : source);
    if (value.charCodeAt(0) === 0xFEFF) value = value.slice(1);
    var records = [];
    var row = [];
    var field = '';
    var quoted = false;
    for (var index = 0; index < value.length; index += 1) {
      var ch = value[index];
      if (quoted) {
        if (ch === '"') {
          if (value[index + 1] === '"') { field += '"'; index += 1; }
          else quoted = false;
        } else {
          field += ch;
        }
      } else if (ch === '"') {
        quoted = true;
      } else if (ch === ',') {
        row.push(field);
        field = '';
      } else if (ch === '\n') {
        row.push(field);
        records.push(row);
        row = [];
        field = '';
      } else if (ch !== '\r') {
        field += ch;
      }
    }
    if (field !== '' || row.length) {
      row.push(field);
      records.push(row);
    }
    if (!records.length) return { headers: [], rows: [] };
    var headers = records[0].map(function (cell) { return String(cell).trim(); });
    var body = [];
    records.slice(1).forEach(function (cells) {
      if (cells.length === 1 && cells[0] === '') return;
      var item = {};
      headers.forEach(function (head, position) {
        item[head] = cells[position] === undefined ? '' : cells[position];
      });
      body.push(item);
    });
    return { headers: headers, rows: body };
  }
  async function getCSV(url) {
    var response = await fetch(url, { headers: { Accept: 'text/csv' }, cache: 'no-store' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    return response.text();
  }

  /* ------------------------------------------------------------ v3 数据加载 */
  async function loadV3Dataset() {
    var seq = state.requestSeq;
    var index = state.index || {};
    var panels = index.panels && typeof index.panels === 'object' ? index.panels : {};
    var holdout = panels.holdout && typeof panels.holdout === 'object' ? panels.holdout : {};
    var attribution = panels.attribution && typeof panels.attribution === 'object' ? panels.attribution : {};
    var hindsight = panels.hindsight && typeof panels.hindsight === 'object' ? panels.hindsight : {};
    var sources = {
      holdoutA: holdout.table_a_csv, holdoutB: holdout.table_b_csv,
      noise: holdout.noise_floor_csv, drift: holdout.drift_csv,
      hindsight: hindsight.csv,
      attribution: attribution.csv, selection: attribution.selection_csv
    };
    state.v3.sources = sources;
    var csv = {};
    var errors = {};
    await Promise.all(Object.keys(sources).map(function (key) {
      var path = sources[key];
      var url = v3TableURL(path);
      if (!url) return Promise.resolve();
      return getCSV(url).then(function (body) {
        csv[key] = parseCSVText(body);
      }).catch(function (error) {
        errors[key] = error.message;
      });
    }));
    if (seq !== state.requestSeq) return;
    state.v3.csv = csv;
    state.v3.csvErrors = errors;
    populateV3Controls();
    await loadV3Runs();
  }

  function populateV3Controls() {
    var index = state.index || {};
    var runs = indexRuns();
    var sites = Array.isArray(index.sites) ? index.sites.filter(function (item) {
      return typeof item === 'string';
    }) : [];
    if (!sites.length) sites = uniq(runs.map(function (run) { return run.site_id; }));
    var scenarios = Array.isArray(index.scenarios) ? index.scenarios.filter(function (item) {
      return typeof item === 'string';
    }) : [];
    if (!scenarios.length) scenarios = uniq(runs.map(function (run) { return run.scenario_id; }));
    if (!sites.length) {
      $('v3-expected-summary').textContent = 'v3 index 中没有可选择的站点记录：' + V3_MISSING;
      return;
    }
    if (!state.v3.siteId || sites.indexOf(state.v3.siteId) < 0) state.v3.siteId = sites[0];
    fillSelect('v3-site-select', sites, function (site) { return text(site); });
    $('v3-site-select').value = state.v3.siteId;
    populateV3Scenarios(scenarios);
  }
  function populateV3Scenarios(scenarioPool) {
    var index = state.index || {};
    var pool = Array.isArray(scenarioPool) ? scenarioPool : [];
    var runs = indexRuns().filter(function (run) { return run.site_id === state.v3.siteId; });
    var fromRuns = uniq(runs.map(function (run) { return run.scenario_id; }));
    var scenarios = pool.filter(function (scenario) { return fromRuns.indexOf(scenario) >= 0; });
    if (!scenarios.length) scenarios = fromRuns;
    if (!scenarios.length) {
      $('v3-expected-summary').textContent = '该站点在 v3 中没有情景记录：' + V3_MISSING;
      return;
    }
    if (!state.v3.scenarioId || scenarios.indexOf(state.v3.scenarioId) < 0) {
      state.v3.scenarioId = scenarios[0];
    }
    fillSelect('v3-scenario-select', scenarios, function (scenario) { return text(scenario); });
    $('v3-scenario-select').value = state.v3.scenarioId;
  }
  async function loadV3Runs() {
    var seq = ++state.v3.seq;
    var runs = indexRuns().filter(function (run) {
      return run.site_id === state.v3.siteId && run.scenario_id === state.v3.scenarioId;
    });
    var picked = {};
    V3_MECH_ORDER.forEach(function (mech) {
      var found = null;
      runs.forEach(function (run) { if (!found && run.mechanism === mech) found = run; });
      if (found) picked[mech] = found;
    });
    state.v3.picked = picked;
    var loaded = {};
    await Promise.all(Object.keys(picked).map(function (mech) {
      return getJSON(v3RunURL(picked[mech].run_id)).then(function (run) {
        loaded[mech] = run;
      }).catch(function (error) {
        loaded[mech] = { error: error.message };
      });
    }));
    if (seq !== state.v3.seq) return;
    state.v3.runs = loaded;
    renderV3Expected();
  }

  /* ------------------------------------------------------------ v3 面板渲染 */
  function renderV3All() {
    renderV3Overview();
    renderV3R0();
    renderV3Expected();
    renderV3Fixed();
    renderV3Robust();
    renderV3Hindsight();
    renderV3Holdout();
    renderV3Attribution();
    renderV3Meta();
    renderV3Downloads();
  }
  function renderV3Overview() {
    var index = state.index || {};
    var counts = index.counts && typeof index.counts === 'object' ? index.counts : {};
    var registration = index.registration && typeof index.registration === 'object' ? index.registration : {};
    fillFacts($('v3-overview-facts'), [
      ['schema_version', v3Text(index.schema_version)],
      ['dataset / schema_kind', v3Text(index.dataset) + ' / ' + v3Text(index.schema_kind)],
      ['generated_at', v3Text(index.generated_at)],
      ['code_version', v3Text(index.code_version)],
      ['counts.runs / worlds', v3Text(counts.runs) + ' / ' + v3Text(counts.worlds)],
      ['counts.fixed_rows / hindsight_rows', v3Text(counts.fixed_rows) + ' / ' + v3Text(counts.hindsight_rows)],
      ['counts.holdout A / B', v3Text(counts.holdout_table_a_rows) + ' / ' + v3Text(counts.holdout_table_b_rows)],
      ['counts.attribution_rows', v3Text(counts.attribution_rows)],
      ['registration.design', shortFingerprint(registration.design_fingerprint)],
      ['registration.code', shortFingerprint(registration.code_fingerprint)],
      ['data_dir', v3Text(index.data_dir)]
    ]);
    $('v3-overview-note').textContent = 'R0 真实锚点回放不参与选择；M0/M1/M2 期望曲线的 n* 是期望成本 argmin；固定配置评价、逐世界事后最优、留出 A/B 与归因对照都不参与选择。null/缺失字段显示“未定义”，不显示 0。';
  }

  function renderV3R0() {
    var index = state.index || {};
    var worlds = Array.isArray(index.worlds) ? index.worlds : [];
    var rows = worlds.filter(function (world) {
      return world && (world.mechanism === 'R0' || world.label && String(world.label).indexOf('R0') === 0);
    });
    if (!rows.length) {
      $('v3-r0-summary').textContent = 'R0 真实锚点回放：' + V3_MISSING + '（v3 index 未提供 mechanism=R0 的世界记录）。';
      $('v3-r0-table').replaceChildren();
      setChildren($('v3-r0-links'), []);
      $('v3-r0-note').textContent = '';
      return;
    }
    $('v3-r0-summary').textContent = 'R0 真实锚点回放 ' + rows.length + ' 条：' +
      uniq(rows.map(function (world) { return v3Text(world.site_id); })).join(' / ') +
      ' · 情景 ' + uniq(rows.map(function (world) { return v3Text(world.scenario_id); })).join(' / ') +
      ' · 块 ' + uniq(rows.map(function (world) { return v3Text(world.block_id); })).join(' / ');
    fillTable($('v3-r0-table'),
      ['world_id', 'site_id', 'scenario_id', 'block_id', 'replicate', 'world_hash', 'sha256'],
      rows.map(function (world) {
        return ['world_id', 'site_id', 'scenario_id', 'block_id', 'replicate',
          'world_hash', 'sha256'].map(function (key) { return v3Text(world[key]); });
      }));
    var links = [];
    rows.forEach(function (world) {
      if (!world.world_id) return;
      links.push(v3Link('下载世界 JSON：' + world.world_id, v3WorldURL(world.world_id),
        'nyc-v3-world-' + world.world_id + '.json'));
    });
    if (!links.length) {
      links.push(v3DisabledLink('下载世界 JSON', '世界记录没有 world_id'));
    }
    setChildren($('v3-r0-links'), links);
    $('v3-r0-note').textContent = 'R0 仅回放真实观测锚点：不计算 J(n)，不参与配置选择；不能与 M0/M1/M2 的期望成本曲线混合比较。';
  }

  function renderV3Expected() {
    var host = $('v3-chart-expected');
    var summary = $('v3-expected-summary');
    var runs = state.v3.runs || {};
    var picked = state.v3.picked || {};
    var available = V3_MECH_ORDER.filter(function (mech) { return !!runs[mech] && !runs[mech].error; });
    if (!available.length) {
      summary.textContent = 'M0/M1/M2 期望曲线：' + V3_MISSING +
        (Object.keys(picked).length ? '（运行 JSON 读取失败，见下方说明）' : '（该站点×情景没有 run 记录）');
      renderLegend($('v3-expected-legend'), []);
      emptyChart(host, '没有可绘制的期望曲线。');
      $('v3-expected-table').replaceChildren();
      setChildren($('v3-expected-links'), []);
      $('v3-expected-note').textContent = '曲线与 n* 取自 runs/run_*.json 的 curve 与 choice 字段；本页不重算成本。';
      return;
    }
    var nSet = {};
    available.forEach(function (mech) {
      var curve = runs[mech].curve;
      (curve && Array.isArray(curve.n) ? curve.n : []).forEach(function (value) {
        if (typeof value === 'number') nSet[value] = true;
      });
    });
    var nValues = Object.keys(nSet).map(Number).sort(function (a, b) { return a - b; });
    var labels = nValues.map(function (value) { return 'n=' + value; });
    var colors = { M0: '#6B7A8F', M1: '#2F6E5B', M2: '#C9803A' };
    var series = available.map(function (mech) {
      var curve = runs[mech].curve || {};
      var lookup = {};
      (curve.n || []).forEach(function (nValue, index) {
        lookup[nValue] = Array.isArray(curve.total) ? numeric(curve.total[index]) : null;
      });
      var nStar = runs[mech].choice && runs[mech].choice.n_star;
      return {
        name: v3Mechanism(mech).label + ' · n*=' + v3Val(nStar, 0),
        color: colors[mech] || COLORS[0],
        values: nValues.map(function (nValue) { return lookup[nValue]; })
      };
    });
    renderLegend($('v3-expected-legend'), series);
    renderLineChart(host, series, labels, {
      ariaLabel: 'M0/M1/M2 期望成本曲线（total vs n，选择阶段）',
      emptyMessage: '期望曲线没有可绘制的数值。'
    });
    var parts = available.map(function (mech) {
      var choice = runs[mech].choice || {};
      return mech + ' n*=' + v3Val(choice.n_star, 0) +
        '（J=' + v3Val(choice.Jbar_at_n_star, 2) + '）';
    });
    summary.textContent = '站点 ' + v3Text(state.v3.siteId) + ' · 情景 ' + v3Text(state.v3.scenarioId) +
      ' · ' + parts.join(' · ') + ' · 曲线点数 = ' + nValues.length;
    fillTable($('v3-expected-table'),
      ['机制', 'run_id', 'n*（argmin）', 'Jbar_at_n_star', 'Jbar_min', 'Jbar_minus_chosen',
        '曲线点数', '曲线文件（curve_csv）'],
      available.map(function (mech) {
        var run = runs[mech];
        var choice = run.choice || {};
        var curve = run.curve || {};
        var pickedRun = picked[mech] || {};
        return [v3Mechanism(mech).label, v3Text(run.run_id || pickedRun.run_id),
          v3Val(choice.n_star, 0), v3Val(choice.Jbar_at_n_star, 2),
          v3Val(choice.Jbar_min, 2), v3Val(choice.Jbar_minus_chosen, 2),
          v3Val(Array.isArray(curve.n) ? curve.n.length : null, 0),
          v3Text(pickedRun.curve_csv)];
      }));
    var links = [];
    available.forEach(function (mech) {
      var runId = runs[mech].run_id || (picked[mech] && picked[mech].run_id);
      if (!runId) return;
      links.push({ label: '下载 ' + mech + ' 运行 JSON', href: v3ExportURL(runId, 'json'),
        filename: 'nyc-v3-' + runId + '.json' });
      links.push({ label: '下载 ' + mech + ' 曲线 CSV', href: v3ExportURL(runId, 'curve_csv'),
        filename: 'nyc-v3-' + runId + '-curve.csv' });
    });
    v3JsonAdd($('v3-expected-links'), links);
    $('v3-expected-note').textContent = 'n* 是期望成本 argmin（选择对象）；曲线数据来自 run JSON 的 curve，不在页面重算成本。J̄ 与分项的数值单位沿用研究产物。';
  }

  function renderV3Fixed() {
    var index = state.index || {};
    var panels = index.panels && typeof index.panels === 'object' ? index.panels : {};
    var decision = panels.decision && typeof panels.decision === 'object' ? panels.decision : {};
    var rows = Array.isArray(decision.fixed_eval) ? decision.fixed_eval : [];
    rows = rows.filter(function (row) {
      return row && row.site_id === state.v3.siteId &&
        (isMissing(state.v3.scenarioId) || isMissing(row.scenario_id) ||
         row.scenario_id === state.v3.scenarioId);
    });
    if (!rows.length) {
      $('v3-fixed-summary').textContent = '固定配置评价：' + V3_MISSING + '（该站点×情景没有 fixed_eval 行）。';
      $('v3-fixed-table').replaceChildren();
      $('v3-fixed-note').textContent = '';
      var noLink = v3TableFor('fixed_cross_mechanism');
      v3JsonAdd($('v3-fixed-links'), noLink ? [{ label: '下载固定配置评价 CSV',
        href: v3TableURL(noLink), filename: 'nyc-v3-fixed.csv' }] : []);
      return;
    }
    $('v3-fixed-summary').textContent = '固定配置评价 ' + rows.length + ' 行 · block_id = ' +
      uniq(rows.map(function (row) { return v3Text(row.block_id); })).join(' / ') +
      ' · 登记充电位 registered_ev_bays = ' +
      uniq(rows.map(function (row) { return v3Val(row.registered_ev_bays, 0); })).join(' / ') +
      ' · n=0 基线 J_mean_at_0 = ' +
      uniq(rows.map(function (row) { return v3Val(row.J_mean_at_0, 2); })).join(' / ');
    fillTable($('v3-fixed-table'),
      ['block_id', 'eval_mechanism', 'n_source_mechanism', 'n_selected', 'n_worlds',
        'J_mean_fixed', 'J_mean_at_0（n=0 基线）', 'registered_ev_bays（登记充电位）',
        'J_mean_registered_ev', '配对差（fixed − 登记）', 'J_hindsight_mean', 'hindsight_gap_mean'],
      rows.map(function (row) {
        return [
          v3Text(row.block_id), v3Text(row.eval_mechanism), v3Text(row.n_source_mechanism),
          v3Val(row.n_selected, 0), v3Val(row.n_worlds, 0), v3Val(row.J_mean_fixed, 2),
          v3Val(row.J_mean_at_0, 2), v3Val(row.registered_ev_bays, 0),
          v3Val(row.J_mean_registered_ev, 2),
          v3Val(row.paired_diff_fixed_minus_registered, 2),
          v3Val(row.J_hindsight_mean, 2), v3Val(row.hindsight_gap_mean, 2)
        ];
      }));
    var table = v3TableFor('fixed_cross_mechanism');
    v3JsonAdd($('v3-fixed-links'), table ? [{ label: '下载固定配置评价 CSV',
      href: v3TableURL(table), filename: 'nyc-v3-fixed-cross-mechanism.csv' }] : []);
    $('v3-fixed-note').textContent = 'fixed_config_eval 把选择阶段冻结的 n 放到独立时间块上评价，并做跨机制评价（eval_mechanism × n_source_mechanism）；配对差 = J_fixed − J_mean_registered_ev。评价不是推荐配置，也不参与选择。';
  }

  function renderV3Robust() {
    var index = state.index || {};
    var panels = index.panels && typeof index.panels === 'object' ? index.panels : {};
    var decision = panels.decision && typeof panels.decision === 'object' ? panels.decision : {};
    var rows = Array.isArray(decision.robust) ? decision.robust : [];
    rows = rows.filter(function (row) {
      if (!row || row.site_id !== state.v3.siteId) return false;
      return true;
    });
    function objectRows(kind) {
      return rows.filter(function (row) {
        if (!row) return false;
        if (kind === 'A') return row.object === 'A' || row.object === 'robust_A';
        return row.object === 'B' || row.object === 'robust_B';
      });
    }
    var rowsA = objectRows('A');
    var rowsB = objectRows('B');
    function summaryText(block, label, name) {
      if (!block.length) return label + '：' + V3_MISSING;
      return label + ' ' + block.length + ' 行 · ' + name + ' · 站点 ' +
        uniq(block.map(function (row) { return v3Text(row.site_id); })).join(' / ') +
        ' · 覆盖 coverage = ' + uniq(block.map(function (row) { return v3Val(row.coverage, 2); })).join(' / ');
    }
    $('v3-robust-a-summary').textContent = summaryText(rowsA, '稳健 A（设计对象）', 'robust_A');
    $('v3-robust-b-summary').textContent = summaryText(rowsB, '稳健 B（压力测试对象）', 'robust_B');
    fillTable($('v3-robust-a-table'),
      ['mode', 'n_robust', 'worst_case_regret', 'n_mechanisms', 'n_scenarios', 'n_theta',
        'coverage', 'definition'],
      rowsA.map(function (row) {
        return [v3Text(row.mode), v3Val(row.n_robust, 0), v3Val(row.worst_case_regret, 4),
          v3Val(row.n_mechanisms, 0), v3Val(row.n_scenarios, 0), v3Val(row.n_theta, 0),
          v3Val(row.coverage, 2), v3Text(row.definition)];
      }));
    fillTable($('v3-robust-b-table'),
      ['mode', 'n_robust_stress', 'worst_case_regret_stress', 'n_realizations',
        'n_mechanisms', 'n_scenarios', 'n_theta', 'coverage', 'definition'],
      rowsB.map(function (row) {
        return [v3Text(row.mode), v3Val(row.n_robust_stress, 0),
          v3Val(row.worst_case_regret_stress, 4), v3Val(row.n_realizations, 0),
          v3Val(row.n_mechanisms, 0), v3Val(row.n_scenarios, 0), v3Val(row.n_theta, 0),
          v3Val(row.coverage, 2), v3Text(row.definition)];
      }));
    $('v3-robust-a-note').textContent = 'robust_A：先对 ω 求期望、再对机制/情景/θ 取最坏；n_robust 是设计对象。';
    $('v3-robust-b-note').textContent = 'robust_B：对单次实现取最坏；n_robust_stress 是压力测试对象，不是设计选择，也不得与 robust_A 合并。';
    var robustCsv = v3TableFor('robust');
    v3JsonAdd($('v3-robust-links'), robustCsv ? [{ label: '下载稳健配置 CSV',
      href: v3TableURL(robustCsv), filename: 'nyc-v3-robust.csv' }] : []);
    $('v3-robust-note').textContent = 'robust_A 与 robust_B 是不同对象：A 是设计对象（先期望再最坏）；B 是压力测试对象（对单次实现取最坏）。两表分开命名、不互相替代；缺失显示“未定义”。';
  }

  function renderV3Hindsight() {
    var csv = state.v3.csv && state.v3.csv.hindsight;
    var source = state.v3.sources && state.v3.sources.hindsight;
    var summary = $('v3-hindsight-summary');
    var sourceLine = $('v3-hindsight-source');
    var table = $('v3-hindsight-table');
    var error = state.v3.csvErrors && state.v3.csvErrors.hindsight;
    if (!csv) {
      summary.textContent = '逐世界事后最优：' + V3_MISSING + '（panels.hindsight.csv 读取失败' +
        (error ? '：' + error : '') + '）。不使用固定评价兜底。';
      sourceLine.textContent = 'CSV 来源：' + v3Text(source);
      table.replaceChildren();
      setChildren($('v3-hindsight-links'), source ? [v3Link('下载逐世界事后最优 CSV',
        v3TableURL(source), 'nyc-v3-per-world-hindsight.csv')] : []);
      $('v3-hindsight-note').textContent = '该面板必须来自 CSV；CSV 缺失时显示“未定义”，不回退到固定配置评价。';
      return;
    }
    var rows = csv.rows.filter(function (row) {
      if (!row) return false;
      return isMissing(state.v3.siteId) || row.site_id === state.v3.siteId;
    });
    var columns = ['world_id', 'scenario_id', 'block_id', 'eval_mechanism',
      'n_source_mechanism', 'n_selected', 'J_fixed', 'J_hindsight_min', 'n_hindsight',
      'hindsight_gap'];
    summary.textContent = '逐世界事后最优 ' + rows.length + ' 行（来自 panels.hindsight.csv 的真实 CSV 行；仅诊断）';
    sourceLine.textContent = 'CSV 来源：' + v3Text(source) + ' · 定义：' +
      v3Text(state.index && state.index.panels && state.index.panels.hindsight
        ? state.index.panels.hindsight.definition : null);
    fillLimitedTable(table, columns, rows.map(function (row) {
      return columns.map(function (key) { return v3Text(row[key]); });
    }), MAX_TABLE_ROWS);
    setChildren($('v3-hindsight-links'), source ? [v3Link('下载逐世界事后最优 CSV',
      v3TableURL(source), 'nyc-v3-per-world-hindsight.csv')] : []);
    $('v3-hindsight-note').textContent = 'hindsight_gap = 固定 n 的 J_fixed − 该世界最小 J（≥0）；逐世界最优 n 只做诊断，不能当作推荐配置或期望成本 argmin。';
  }

  function renderV3Holdout() {
    function renderCsvTable(key, part, summaryId, tableId, emptyText) {
      var csv = state.v3.csv && state.v3.csv[key];
      var source = state.v3.sources && state.v3.sources[key];
      var error = state.v3.csvErrors && state.v3.csvErrors[key];
      var summary = $(summaryId);
      if (!csv) {
        summary.textContent = emptyText + '：' + V3_MISSING + (error ? '（' + error + '）' : '');
        $(tableId).replaceChildren();
        return;
      }
      summary.textContent = emptyText + ' ' + csv.rows.length + ' 行 · 字段 ' +
        csv.headers.length + ' 列 · 文件 ' + v3Text(source);
      fillLimitedTable($(tableId), csv.headers, csv.rows.map(function (row) {
        return csv.headers.map(function (key) { return v3Text(row[key]); });
      }), 40);
    }
    renderCsvTable('holdoutA', 'table_a', 'v3-holdout-a-summary', 'v3-holdout-a-table',
      '留出 A（给定计数，只评形状）');
    renderCsvTable('holdoutB', 'table_b', 'v3-holdout-b-summary', 'v3-holdout-b-table',
      '留出 B（训练信息预测数量+形状）');
    renderCsvTable('noise', 'noise_floor', 'v3-noise-summary', 'v3-noise-table',
      '噪声底（重复生成波动）');
    var links = [];
    [['holdoutA', '留出 A CSV'], ['holdoutB', '留出 B CSV'], ['noise', '噪声底 CSV'], ['drift', '漂移参考 CSV']]
      .forEach(function (pair) {
        var source = state.v3.sources && state.v3.sources[pair[0]];
        if (source) {
          links.push({ label: '下载' + pair[1], href: v3TableURL(source), filename: v3Basename(source) });
        }
      });
    v3JsonAdd($('v3-holdout-links'), links);
    $('v3-holdout-note').textContent = 'A 给定留出周计数、只评形状；B 用训练期信息预测数量+形状；A 不得当作 B。噪声底是同一观测重复生成的波动尺度，不是真实数据上的置信区间。缺失字段显示“未定义”。';
  }

  function renderV3Attribution() {
    var panels = state.index && state.index.panels && typeof state.index.panels === 'object'
      ? state.index.panels : {};
    var attribution = panels.attribution && typeof panels.attribution === 'object' ? panels.attribution : {};
    var csv = state.v3.csv && state.v3.csv.attribution;
    var rows = [];
    if (csv) {
      rows = csv.rows.filter(function (row) { return row && row.record === 'contrast'; });
    } else if (Array.isArray(attribution.rows)) {
      rows = attribution.rows.filter(function (row) { return row && row.record === 'contrast'; });
    }
    var summary = $('v3-attr-summary');
    if (!rows.length) {
      summary.textContent = '归因对照：' + V3_MISSING + '（没有 contrast 行）。';
      $('v3-attr-table').replaceChildren();
    } else {
      var columns = ['contrast', 'variant_a', 'variant_b', 'metric', 'value', 'ci_low',
        'ci_high', 'n_sites', 'sign_positive', 'sign_negative', 'missing_reason'];
      var present = columns.filter(function (key) {
        return rows.some(function (row) { return row[key] !== undefined; });
      });
      var samePositive = 0;
      var sameNegative = 0;
      rows.forEach(function (row) {
        var positive = Number(row.sign_positive);
        var negative = Number(row.sign_negative);
        if (isFinite(positive)) samePositive += positive;
        if (isFinite(negative)) sameNegative += negative;
      });
      summary.textContent = '归因对照 ' + rows.length + ' 行 · 同向站点计数合计：正 ' +
        samePositive + ' / 负 ' + sameNegative + '（每次只改一个机制）';
      fillLimitedTable($('v3-attr-table'), present, rows.map(function (row) {
        return present.map(function (key) { return v3Text(row[key]); });
      }), 80);
    }
    var selection = state.v3.csv && state.v3.csv.selection;
    var selectionSummary = $('v3-selection-summary');
    if (!selection) {
      selectionSummary.textContent = '选择诊断：' + V3_MISSING + '（selection_csv 不可用）。';
      $('v3-selection-table').replaceChildren();
    } else {
      selectionSummary.textContent = '选择诊断 ' + selection.rows.length + ' 行 · 文件 ' +
        v3Text(state.v3.sources && state.v3.sources.selection);
      fillLimitedTable($('v3-selection-table'), selection.headers, selection.rows.map(function (row) {
        return selection.headers.map(function (key) { return v3Text(row[key]); });
      }), 40);
    }
    var links = [];
    if (state.v3.sources && state.v3.sources.attribution) {
      links.push({ label: '下载归因对照 CSV', href: v3TableURL(state.v3.sources.attribution),
        filename: v3Basename(state.v3.sources.attribution) });
    }
    if (state.v3.sources && state.v3.sources.selection) {
      links.push({ label: '下载选择诊断 CSV', href: v3TableURL(state.v3.sources.selection),
        filename: v3Basename(state.v3.sources.selection) });
    }
    v3JsonAdd($('v3-attr-links'), links);
    $('v3-attr-note').textContent = '归因对照按配对方式每次只改一个机制；两个机制同向偏差不构成“某一机制主导”的证明。缺少数值的格子显示“未定义”，不以 0 代替。';
  }

  function renderV3Meta() {
    var index = state.index || {};
    var counts = index.counts && typeof index.counts === 'object' ? index.counts : {};
    var registration = index.registration && typeof index.registration === 'object' ? index.registration : {};
    fillFacts($('v3-meta-facts'), [
      ['schema_version', v3Text(index.schema_version)],
      ['dataset / schema_kind', v3Text(index.dataset) + ' / ' + v3Text(index.schema_kind)],
      ['generated_at', v3Text(index.generated_at)],
      ['code_version', v3Text(index.code_version)],
      ['counts.runs', v3Text(counts.runs)],
      ['counts.worlds', v3Text(counts.worlds)],
      ['counts.fixed_rows', v3Text(counts.fixed_rows)],
      ['counts.hindsight_rows', v3Text(counts.hindsight_rows)],
      ['registration.design', shortFingerprint(registration.design_fingerprint)],
      ['registration.code', shortFingerprint(registration.code_fingerprint)],
      ['data_dir', v3Text(index.data_dir)]
    ]);
    var sources = index.sources && typeof index.sources === 'object' && !Array.isArray(index.sources)
      ? index.sources : {};
    var sourceRows = Object.keys(sources).map(function (key) { return [key, v3Text(sources[key])]; });
    fillTable($('v3-sources-table'), ['来源字段', '路径 / 说明'], sourceRows.length ? sourceRows : [['（无）', V3_MISSING]]);
    var limits = Array.isArray(index.limits) ? index.limits : [];
    if (!limits.length) {
      setChildren($('v3-limits-list'), el('li', { class: 'missing', text: '限制：' + V3_MISSING }));
    } else {
      setChildren($('v3-limits-list'), limits.map(function (item) {
        return el('li', { text: typeof item === 'string' ? item : JSON.stringify(item) });
      }));
    }
  }

  function renderV3Downloads() {
    var links = [];
    v3DownloadsTables().forEach(function (path) {
      var name = v3Basename(path);
      if (!name) return;
      links.push({ label: '下载 ' + name, href: v3TableURL(path), filename: name });
    });
    v3JsonAdd($('v3-downloads'), links.length ? links : [{ label: '表格下载', reason: 'index.downloads.tables 为空' }]);
    var note = $('v3-downloads-note');
    if (note) {
      note.textContent = '下载全部指向研究端真实文件（export/*.csv 与 runs/*.json、world/*.json）；页面不把渲染文本当数据。运行 JSON 与曲线 CSV 在“M0/M1/M2 期望曲线”面板逐 run 下载。';
    }
  }

  /* ============================================================ 数据集切换与初始化 */
  function setDatasetButtons() {
    var host = $('dataset-switch');
    if (!host) return;
    Array.prototype.forEach.call(host.querySelectorAll('[data-dataset]'), function (button) {
      var active = button.getAttribute('data-dataset') === state.dataset;
      if (active) button.classList.add('active');
      else button.classList.remove('active');
      button.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
  }
  function preferredDataset() {
    try {
      var value = new URLSearchParams(window.location.search).get('dataset');
      if (value === 'v1' || value === 'v2' || value === 'v3') return value;
    } catch (error) { /* ignore */ }
    return 'v2';
  }
  function resetViews() {
    state.index = null;
    state.schemaKind = null;
    state.mode = null;
    state.siteId = null;
    state.scenarioId = null;
    state.runId = null;
    state.run = null;
    $('content').hidden = true;
    $('v2-content').hidden = true;
    $('v3-content').hidden = true;
    $('empty-state').hidden = true;
    $('banner').hidden = true;
    $('mode-panel').hidden = false;
    $('select-panel').hidden = false;
    ['mode-select', 'site-select', 'scenario-select', 'run-select'].forEach(function (id) {
      var select = $(id);
      select.disabled = true;
      select.replaceChildren();
    });
    ['v3-site-select', 'v3-scenario-select'].forEach(function (id) {
      var select = $(id);
      if (select) select.replaceChildren();
    });
    state.v3 = { siteId: null, scenarioId: null, runs: {}, picked: {}, csv: {},
                 csvErrors: {}, sources: {}, seq: 0 };
    $('run-meta').textContent = '尚未选择运行';
    setChildren($('evidence-badges'), []);
  }
  function applyDatasetLayout() {
    var v3 = state.schemaKind === 'v3';
    $('mode-panel').hidden = v3;
    $('select-panel').hidden = v3;
    $('v3-content').hidden = !v3 || !state.index || state.index.status === 'empty';
  }
  async function loadDataset(name, options) {
    var opts = options || {};
    var seq = ++state.requestSeq;
    state.dataset = name;
    state.schemaKind = name === 'v3' ? 'v3' : (name === 'v2' ? 'v2' : 'v1');
    setDatasetButtons();
    try {
      var index = await getJSON('/api/nyc/index?dataset=' + encodeURIComponent(name));
      if (seq !== state.requestSeq) return false;
      state.index = index;
      var version = String(index.schema_version || '');
      state.schemaKind = index.schema_kind ||
        (version.indexOf('nyc_viewer_v3/') === 0 ? 'v3'
          : (version.indexOf('nyc_viewer_v2/') === 0 ? 'v2' : 'v1'));
      applyDatasetLayout();
      renderStatusAndBanners();
      renderEvidenceBadges();
      renderModeCards();
      if (index.status === 'empty') {
        showEmpty(index.message || '尚未生成 NYC 半合成研究结果。');
        return true;
      }
      $('empty-state').hidden = true;
      if (state.schemaKind === 'v3') {
        await loadV3Dataset();
        if (seq !== state.requestSeq) return false;
        renderV3All();
        return true;
      }
      populateModes();
      return true;
    } catch (error) {
      if (seq !== state.requestSeq) return false;
      state.index = null;
      renderEvidenceBadges();
      var pill = $('data-status');
      pill.className = 'status-pill empty';
      pill.textContent = '接口不可用';
      var banner = $('banner');
      banner.hidden = false;
      banner.className = 'banner warn';
      banner.textContent = '无法连接只读接口（' + name + '）：' + error.message;
      showEmpty('无法连接后端只读接口（' + name + '）：' + error.message);
      return false;
    }
  }

  function wire() {
    var switchHost = $('dataset-switch');
    if (switchHost) {
      switchHost.addEventListener('click', function (event) {
        var target = event.target;
        if (!target || !target.closest) return;
        var button = target.closest('[data-dataset]');
        if (!button) return;
        var name = button.getAttribute('data-dataset');
        if (name === state.dataset) return;
        resetViews();
        loadDataset(name);
      });
    }
    $('mode-select').addEventListener('change', function (event) { selectMode(event.target.value); });
    $('site-select').addEventListener('change', function (event) {
      state.siteId = event.target.value;
      populateScenarios();
    });
    $('scenario-select').addEventListener('change', function (event) {
      state.scenarioId = event.target.value;
      populateRuns();
    });
    $('run-select').addEventListener('change', function (event) {
      state.runId = event.target.value;
      loadRun(state.runId);
    });
    if ($('v3-site-select')) {
      $('v3-site-select').addEventListener('change', function (event) {
        state.v3.siteId = event.target.value;
        populateV3Scenarios();
        loadV3Runs().then(function () { if (isV3()) renderV3All(); });
      });
    }
    if ($('v3-scenario-select')) {
      $('v3-scenario-select').addEventListener('change', function (event) {
        state.v3.scenarioId = event.target.value;
        loadV3Runs().then(function () { if (isV3()) renderV3All(); });
      });
    }
    $('bin-select').addEventListener('change', function (event) {
      state.binMinutes = Number(event.target.value) || 15;
      renderSeries();
      renderArrivals();
    });
    var resizeTimer = null;
    window.addEventListener('resize', function () {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (state.schemaKind === 'v3') {
          renderV3Expected();
          return;
        }
        if (!state.run) return;
        if (state.schemaKind === 'v2') {
          renderV2Expected();
          return;
        }
        renderSeries();
        renderArrivals();
        renderCostChartOnly();
      }, 180);
    });
  }
  async function init() {
    setDatasetButtons();
    renderEvidenceBadges();
    renderModeCards();
    wire();
    var preferred = preferredDataset();
    await loadDataset(preferred);
    var isEmpty = state.index && state.index.status === 'empty';
    if (isEmpty && preferred === 'v2') {
      await loadDataset('v1');
      if (state.index && state.index.status !== 'empty') {
        var banner = $('banner');
        banner.hidden = false;
        banner.className = 'banner warn';
        banner.textContent = 'v2 数据集尚未生成，已自动切换到 v1 数据集（观测重放与单世界运行）。v2 目录就绪后可点上方「v2 数据集」。';
        var note = $('dataset-note');
        if (note) note.textContent = '当前数据集：v1（自动回退；v2 数据尚未生成）。';
      } else if (state.index) {
        await loadDataset('v2');
      }
    }
    if (isEmpty && preferred === 'v3') {
      await loadDataset('v2');
      if (state.index && state.index.status !== 'empty') {
        var v3Banner = $('banner');
        v3Banner.hidden = false;
        v3Banner.className = 'banner warn';
        v3Banner.textContent = 'v3 数据集尚未生成，已自动切换到 v2 数据集。v3 目录就绪后可点上方「v3 数据集」。';
        var v3Note = $('dataset-note');
        if (v3Note) v3Note.textContent = '当前数据集：v2（自动回退；v3 数据尚未生成）。';
      } else if (state.index) {
        await loadDataset('v3');
      }
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
