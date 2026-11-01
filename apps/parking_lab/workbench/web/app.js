'use strict';
/* 停车场研究可视化实验台 —— 前端入口
   原则：所有数字来自后端快照（同一仿真时钟）；点阵/图表/指标同帧渲染；
   1Hz 更新只做差量 DOM 更新（不重建点阵、不重建图表骨架、不丢 hover/焦点）。 */
const $ = function (id) { return document.getElementById(id); };

/* ------------------------------------------------------------ 参数标签与分组 */
const LABELS = {
  n_spaces: '总车位 / 个', charging_bays: '充电车位 / 个', chargers: '带枪车位 / 个',
  charger_kw: '单枪功率 / kW', feeder_kw: '场站总功率 / kW', policy: '共享策略',
  reserve_fixed: '固定保留带枪位', scenario: '到达情景', duration_hours: '仿真时长 / 小时',
  start_hour: '开始时刻 / 小时', seed: '随机种子', arrival_rate_hour: '基准到达 / 辆每小时',
  ev_share: '电车比例 / 0-1', charge_probability: '电车需充电概率', ice_dwell_min: '油车平均停车 / 分钟',
  ev_dwell_min: '电车平均停车 / 分钟', energy_mean_kwh: '平均充电需求 / kWh',
  dwell_cv: '停车时长变异系数', peak_multiplier: '高峰强度倍数', burst_multiplier: '突发强度倍数',
  drift_at_fraction: '变化发生 / 时长比例', drift_rate_multiplier: '变化后强度倍数', drift_ev_share: '变化后电车比例',
  forecast_window_min: '保护预测窗口 / 分钟', reserve_safety: '保护安全系数',
  interval_level: '预测区间水平', learning_half_life_min: '学习半衰期 / 分钟', prior_rate_hour: '先验到达 / 辆每小时',
  prior_strength_min: '先验暴露 / 分钟', prior_ev_share: '先验电车比例', prior_charge_probability: '先验需充电概率',
  prior_type_strength: '先验类型等效样本', cost: '成本参数（无来源一律留空 = 未知）'
};
const SECTIONS = [
  ['停车资源', ['n_spaces', 'charging_bays', 'chargers', 'charger_kw', 'feeder_kw', 'policy', 'reserve_fixed'],
    '充电车位包含带枪车位。固定与自适应策略保留带枪空位；车充满后继续占位到离场。'],
  ['车流与运行', ['scenario', 'duration_hours', 'start_hour', 'seed', 'arrival_rate_hour', 'ev_share', 'charge_probability', 'ice_dwell_min', 'ev_dwell_min', 'energy_mean_kwh'],
    '到达强度按 1 分钟分段恒定。模型在入口观察所有到访，包括最终被拒的车辆。'],
  ['变化与共享细节', ['dwell_cv', 'peak_multiplier', 'burst_multiplier', 'drift_at_fraction', 'drift_rate_multiplier', 'drift_ev_share', 'forecast_window_min', 'reserve_safety'],
    '自适应保留数 = 向上取整(预计需充电到达数 + 安全系数 x 其平方根)，最多保留全部带枪位。'],
  ['在线学习与独立先验', ['interval_level', 'learning_half_life_min', 'prior_rate_hour', 'prior_strength_min', 'prior_ev_share', 'prior_charge_probability', 'prior_type_strength'],
    '先验与模拟车流独立。较短半衰期更快适应变化，同时增加估计波动。区间按当前估计的恒定强度推算。'],
  ['成本参数（无来源一律留空 = 未知）', ['cost'],
    '成本参数没有可靠来源时留空（null），界面显示未知／待校准；禁止填 0 或演示默认值。']
];
const COST_LABELS = {
  currency: '币种', price_year: '价格年份（留空 = 未核实）', accounting_period: '核算周期',
  rejected_disposition: '被拒车辆去向', vot_per_hour: '时间价值 / TWD每小时',
  search_min: '搜索时间 / 分钟', detour_min: '绕行时间 / 分钟', walking_min: '步行时间 / 分钟',
  detour_km_per_failure: '每次失败绕行 / km', ev_kwh_per_km: '电车能耗 / kWh每km',
  ev_energy_price_per_kwh: '电车补能价 / TWD每kWh', alternative_charging_delta_per_kwh: '替代桩价差 / TWD每kWh',
  residual_trip_loss_per_kwh: '剩余行程损失 / TWD每kWh', emission_cost_per_km: '排放外部性 / TWD每km',
  fuel_l_per_km: '油耗 / L每km', fuel_price_per_l: '油价 / TWD每L', activity_loss_per_failure: '活动损失 / TWD每次',
  electricity_price_per_kwh: '购电价 / TWD每kWh', maintenance_per_kwh: '维护 / TWD每kWh',
  maintenance_per_bay_day: '维护 / TWD每带枪车位（设备位）每日', depreciation_annual: '年折旧 / TWD',
  depreciation_capex: '设备投入 / TWD', depreciation_life_years: '折旧年限 / 年（必须 > 0）',
  relocation_cost_per_move: '挪车成本 / TWD每次', relocation_km_per_move: '挪车 / km每次',
  parking_fee_per_hour: '停车费 / TWD每小时', charging_fee_per_kwh: '充电费 / TWD每kWh',
  fine_per_event: '罚金 / TWD每次', subsidy_per_session: '补贴 / TWD每次'
};
const COST_ENUMS = { accounting_period: ['per_day', 'per_hour'], rejected_disposition: ['detour_exit', 'alternate_bay', 'give_up'] };
const COST_PRESERVE = new Set(['sources', 'metadata', 'provenance']);

/* ------------------------------------------------------------ 模块状态 */
let metadata = null, sessionId = null, state = null, busy = false, liveTimer = null;
let dirty = false, comparison = null, nestedLoaded = {};
let selectedBay = null, filterState = null, hoverBay = null;
let activeTab = 'runtime';
let compareMetric = 'rejection_rate';
let matrix = { n: -1, key: '', layout: null, dots: [], prev: [], bodyWidth: 0, emptyNode: null };
let charts = { key: '', occupancy: null, power: null, energy: null, heatmap: null, bars: null };
let heat = { rowOffset: 0, rows: 90 };
let replayState = { total: 0, index: 0, positions: [], payload: null };
let lastSeen = { time: -1, events: -1, mode: '' };
const STATE_LABEL = { 0: '空闲', 1: '油车占用', 2: '电车停车（未充电）', 3: '充电中', 4: '充满仍占位' };
const STATE_FILL = { 0: '#E6EDEA', 1: '#39464B', 2: '#5C88AC', 3: '#1F6F5C', 4: '#C98A16' };
const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ------------------------------------------------------------ 小工具 */
function message(text, kind) { const node = $('message'); if (!node) return; node.textContent = text; node.className = 'message ' + (kind || ''); }
function number(x, digits) { return x === null || x === undefined ? '—' : Number(x).toLocaleString('zh-CN', { maximumFractionDigits: digits === undefined ? 1 : digits, minimumFractionDigits: digits === undefined ? 1 : digits }); }
function percent(x, digits) { return x === null || x === undefined ? '—' : number(x * 100, digits === undefined ? 1 : digits) + '%'; }
function utcShort(text) { return text ? String(text).replace('T', ' ').slice(0, 19) + 'Z' : '—'; }
function clock(minute, c) {
  const config = c || (state && state.config) || {};
  const total = Math.floor((config.start_hour || 0) * 60 + minute), day = Math.floor(total / 1440);
  return (day ? '第' + (day + 1) + '天 ' : '') + String(Math.floor(total / 60) % 24).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
function shortClock(minute, c) {
  const config = c || (state && state.config) || {};
  const total = Math.floor((config.start_hour || 0) * 60 + minute), day = Math.floor(total / 1440);
  return (day ? 'D' + (day + 1) + ' ' : '') + String(Math.floor(total / 60) % 24).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  let data;
  try { data = await response.json(); } catch (error) { throw new Error('服务返回了无法解析的结果 (' + response.status + ')'); }
  if (!response.ok) throw new Error(data.error || '请求失败 (' + response.status + ')');
  return data;
}
const tooltipNode = function () { return $('tooltip'); };
function showTooltip(payload) {
  const node = tooltipNode(); if (!node || !payload) return;
  const parts = [];
  if (payload.title) parts.push('<strong>' + payload.title + '</strong>');
  for (const row of payload.rows || []) {
    parts.push('<div class="row"><span>' + (row.color ? '<i style="background:' + row.color + '"></i>' : '') + row.label + '</span><b>' + row.value + '</b></div>');
  }
  node.innerHTML = parts.join('');
  node.hidden = false;
  const pad = 14;
  const width = node.offsetWidth, height = node.offsetHeight;
  let x = (payload.x || 0) + pad, y = (payload.y || 0) + pad;
  if (x + width > window.innerWidth - 8) x = (payload.x || 0) - width - pad;
  if (y + height > window.innerHeight - 8) y = (payload.y || 0) - height - pad;
  node.style.left = Math.max(6, x) + 'px';
  node.style.top = Math.max(6, y) + 'px';
}
function hideTooltip() { const node = tooltipNode(); if (node) node.hidden = true; }
function isPlainObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function flash(dot) {
  if (REDUCED || !dot || typeof dot.animate !== 'function') return;
  dot.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.28)' }, { transform: 'scale(1)' }], { duration: 340, easing: 'ease-out' });
}

/* ------------------------------------------------------------ 配置表单（语义沿用原实现） */
function makeField(key, def) {
  if (def !== null && typeof def === 'object' && !Array.isArray(def)) return makeNested(key, def);
  const wrapper = document.createElement('div'); wrapper.className = 'field';
  const label = document.createElement('label'); label.htmlFor = 'field-' + key; label.textContent = LABELS[key] || key;
  let input;
  if (typeof def === 'boolean') {
    input = document.createElement('select'); input.dataset.kind = 'bool';
    for (const value of ['true', 'false']) { const option = document.createElement('option'); option.value = value; option.textContent = value === 'true' ? '是' : '否'; input.append(option); }
  } else if (typeof def === 'string') {
    input = document.createElement('select');
    const choices = key === 'policy' ? metadata.policies : key === 'scenario' ? metadata.scenarios : null;
    if (choices) { for (const value of Object.keys(choices)) { const option = document.createElement('option'); option.value = value; option.textContent = choices[value]; input.append(option); } }
    else { input = document.createElement('input'); input.type = 'text'; input.dataset.kind = 'text'; }
  } else {
    input = document.createElement('input'); input.type = 'number'; input.min = 0; input.step = Number.isInteger(def) ? '1' : 'any'; input.required = true;
  }
  input.id = 'field-' + key; input.name = key;
  input.addEventListener('change', markDirty); input.addEventListener('input', markDirty);
  wrapper.append(label, input); return wrapper;
}
function makeNested(key, def) {
  const details = document.createElement('details'); details.open = false; details.className = 'nested';
  const summary = document.createElement('summary'); summary.textContent = LABELS[key] || key; details.append(summary);
  for (const sub of Object.keys(def)) {
    if (COST_PRESERVE.has(sub)) continue;
    const wrapper = document.createElement('div'); wrapper.className = 'field';
    const label = document.createElement('label'); label.htmlFor = 'field-' + key + '-' + sub; label.textContent = COST_LABELS[sub] || sub;
    let input;
    if (COST_ENUMS[sub]) {
      input = document.createElement('select');
      for (const value of COST_ENUMS[sub]) { const option = document.createElement('option'); option.value = value; option.textContent = value; input.append(option); }
      input.dataset.kind = 'enum';
    } else if (sub === 'currency') {
      input = document.createElement('input'); input.type = 'text'; input.dataset.kind = 'text';
    } else {
      input = document.createElement('input'); input.type = 'number'; input.min = 0; input.step = 'any';
      input.placeholder = '未知／待校准（留空 = null）'; input.dataset.kind = 'number';
    }
    if (sub === 'depreciation_life_years' && input.type === 'number') { input.min = '0.0001'; input.step = 'any'; }
    input.id = 'field-' + key + '-' + sub; input.name = key + '-' + sub;
    input.addEventListener('change', markDirty); input.addEventListener('input', markDirty);
    wrapper.append(label, input); details.append(wrapper);
  }
  const help = document.createElement('p'); help.className = 'field-help';
  help.textContent = '数值留空即 null（未知／待校准）；sources/metadata 保持原样，不手填来源。';
  details.append(help);
  return details;
}
function makeFields() {
  const container = $('fields');
  container.replaceChildren();
  const placed = new Set();
  for (const [title, keys, help] of SECTIONS) {
    // 首屏只展开常用设置（停车资源、车流与运行）；高级参数默认折叠，避免侧栏淹没演示。
    const details = document.createElement('details');
    details.open = title === '停车资源' || title === '车流与运行';
    const summary = document.createElement('summary'); summary.textContent = title; details.append(summary);
    for (const key of keys) { if (Object.prototype.hasOwnProperty.call(metadata.defaults, key)) { placed.add(key); details.append(makeField(key, metadata.defaults[key])); } }
    const paragraph = document.createElement('p'); paragraph.className = 'field-help'; paragraph.textContent = help; details.append(paragraph);
    container.append(details);
  }
  const rest = Object.keys(metadata.defaults).filter(function (key) { return !placed.has(key); });
  if (rest.length) {
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = '其他参数'; details.append(summary);
    for (const key of rest) details.append(makeField(key, metadata.defaults[key]));
    container.append(details);
  }
}
function writeForm(config) {
  const merged = Object.assign({}, metadata.defaults, config || {});
  for (const key of Object.keys(metadata.defaults)) {
    const def = metadata.defaults[key];
    if (isPlainObject(def)) {
      writeNested(key, Object.assign({}, def, isPlainObject(config && config[key]) ? config[key] : {}));
    } else {
      const input = $('field-' + key);
      if (!input) continue;
      const value = merged[key];
      if (input.dataset.kind === 'bool') input.value = value ? 'true' : 'false';
      else input.value = value === null || value === undefined ? '' : String(value);
    }
  }
  updateProvenanceBanner();
  updateConfigSummary();
}
function writeNested(key, values) {
  const preserved = {};
  for (const sub of COST_PRESERVE) if (Object.prototype.hasOwnProperty.call(values, sub)) preserved[sub] = values[sub];
  for (const sub of Object.keys(values)) {
    const input = $('field-' + key + '-' + sub);
    if (!input) continue;
    const value = values[sub];
    input.value = value === null || value === undefined ? '' : String(value);
  }
  nestedLoaded[key] = { preserved: preserved, baseline: readNested(key) };
  updateProvenanceBanner();
}
function readNested(key) {
  const def = (metadata && metadata.defaults[key]) || {}, out = {};
  for (const sub of Object.keys(def)) {
    if (COST_PRESERVE.has(sub)) continue;
    const input = $('field-' + key + '-' + sub);
    if (!input) continue;
    const raw = input.value.trim();
    out[sub] = input.dataset.kind === 'number' ? (raw === '' ? null : Number(raw)) : input.value;
  }
  return out;
}
function changedNested(key) {
  const loaded = nestedLoaded[key];
  if (!loaded) return [];
  const current = readNested(key);
  return Object.keys(current).filter(function (sub) { return !Object.is(current[sub], loaded.baseline[sub]); });
}
function filterPreservedBlock(name, block, changed, values) {
  const out = {};
  if (!isPlainObject(block)) return out;
  for (const param of Object.keys(block)) {
    if (changed.indexOf(param) >= 0) continue;
    const entry = block[param];
    if (name === 'metadata' && isPlainObject(entry)) {
      if (entry.currency !== undefined && entry.currency !== values.currency) continue;
      if (entry.year !== undefined && (values.price_year === null || values.price_year === undefined || entry.year !== values.price_year)) continue;
    }
    out[param] = entry;
  }
  return out;
}
function collectNested(key) {
  const out = readNested(key);
  const loaded = nestedLoaded[key] || { preserved: {}, baseline: {} };
  const changed = changedNested(key);
  for (const name of COST_PRESERVE) {
    if (name === 'provenance') continue;
    out[name] = filterPreservedBlock(name, loaded.preserved[name], changed, out);
  }
  out.provenance = changed.length ? 'unknown_not_calibrated' : (loaded.preserved.provenance || 'unknown_not_calibrated');
  return out;
}
function collect() {
  if (!$('config-form').reportValidity()) throw new Error('请先修正左侧标记的参数');
  const config = {};
  for (const key of Object.keys(metadata.defaults)) {
    const def = metadata.defaults[key];
    if (isPlainObject(def)) config[key] = collectNested(key);
    else {
      const input = $('field-' + key), raw = input.value.trim();
      if (input.dataset.kind === 'bool') config[key] = input.value === 'true';
      else if (input.dataset.kind === 'text') config[key] = input.value;
      else config[key] = input.tagName === 'SELECT' ? input.value : (raw === '' ? null : Number(raw));
    }
  }
  return config;
}
function updateProvenanceBanner() {
  const banner = $('provenance-banner');
  if (!banner || !metadata) return;
  const cost = collectNested('cost');
  const filled = Object.keys(cost).filter(function (key) { return !COST_PRESERVE.has(key) && typeof cost[key] === 'number'; });
  let text = '';
  if (cost.provenance === 'illustrative_not_calibrated') {
    text = '合成示例（非现实成本，仅演示算术）：参数只用于演示算术，不代表现实成本或已校准估计。';
  } else if (cost.provenance === 'official_verified') {
    text = '官方已核实参数（来源见 cost.sources）：仍须核对币种与价格年份，不代表本场地实测。';
  } else if (filled.length) {
    text = '成本参数未核实／未校准：无可靠来源，或数值已修改、原来源标记不再适用；结果只用于演示算术。';
  }
  banner.hidden = !text;
  banner.textContent = text;
  banner.classList.toggle('verified', cost.provenance === 'official_verified');
}
function countDiff() {
  if (!state || !state.config || !metadata) return 0;
  let changes = 0;
  let current;
  try { current = collect(); } catch (error) { return 1; }
  const compare = function (a, b, path) {
    if (isPlainObject(a) && isPlainObject(b)) {
      const keys = new Set(Object.keys(a).concat(Object.keys(b)));
      for (const key of keys) { if (COST_PRESERVE.has(key)) continue; compare(a[key], b[key], path + '.' + key); }
      return;
    }
    if (isPlainObject(a) || isPlainObject(b)) return;
    if (!Object.is(a, b)) changes += 1;
  };
  compare(current, state.config, '');
  return changes;
}
function updateConfigSummary() {
  const node = $('config-summary');
  if (!node) return;
  if (!state || !state.config) { node.textContent = '尚未创建实验。'; return; }
  const c = state.config;
  const parts = [
    c.n_spaces + ' 车位', c.charging_bays + ' 充电位', c.chargers + ' 带枪',
    c.charger_kw + ' kW', c.feeder_kw + ' kW 限额',
    (state.policy_name || c.policy), c.duration_hours + ' 小时'
  ];
  const diff = dirty ? countDiff() : 0;
  node.innerHTML = '<strong>当前运行配置</strong><br>' + parts.join(' · ') +
    (diff ? '<br><span style="color:var(--amber);font-weight:600">待应用：' + diff + ' 项参数已修改</span>' : '<br>表单与运行配置一致');
}
function markDirty() {
  dirty = true;
  $('dirty-note').textContent = '参数已修改，应用后生效。正在观看的运行保留原配置。';
  $('dirty-note').classList.add('dirty');
  updateProvenanceBanner(); updateConfigSummary(); controls();
}

/* ------------------------------------------------------------ 控件状态 */
function runningMode(c) { return !!c && !c.paused && !c.replay.active && (c.mode === 'realtime' || c.mode === 'accelerated'); }
function replayActive() { const c = state && state.continuous; return !!(c && c.replay && c.replay.active); }
function applyLink(path) { const a = document.createElement('a'); a.href = path; a.download = 'parking-result'; a.click(); }
function controls() {
  const c = state && state.continuous, replay = replayActive();
  const finished = !!(state && state.finished);
  const disabled = busy || !sessionId;
  const play = $('transport-play');
  const paused = !!(c && c.paused);
  play.disabled = disabled || replay || finished;
  play.setAttribute('aria-pressed', String(!!c && !paused && !finished));
  play.querySelector('use').setAttribute('href', (!c || paused || finished) ? '#icon-play' : '#icon-pause');
  $('transport-play-label').textContent = (!c || paused || finished) ? '播放' : '暂停';
  $('transport-step').disabled = disabled || replay || finished || dirty;
  $('transport-finish').disabled = disabled || replay || finished || dirty;
  $('transport-reset').disabled = disabled;
  $('step-minutes').disabled = disabled || replay;
  const speedButtons = document.querySelectorAll('[data-speed]');
  const effective = c ? (c.effective_speed || c.speed) : null;
  for (const button of speedButtons) {
    const value = Number(button.dataset.speed);
    button.classList.toggle('active', !!c && Number(effective) === value);
    button.setAttribute('aria-pressed', String(!!c && Number(effective) === value));
    button.disabled = disabled || replay;
  }
  $('replay-start').disabled = disabled || replay || dirty;
  $('replay-step').disabled = disabled || !replay || busy;
  $('replay-exit').disabled = disabled || !replay;
  $('replay-range').disabled = disabled || !replay;
  $('apply').disabled = busy;
  $('compare').disabled = busy;
  $('download').disabled = disabled;
  $('preset').disabled = busy;
  $('heatmap-prev').disabled = !(state && heat.rowOffset > 0);
  const nSpaces = state && state.config ? state.config.n_spaces : 0;
  $('heatmap-next').disabled = !(nSpaces > heat.rowOffset + heat.rows);
  const lamp = $('run-indicator');
  lamp.className = 'run-lamp' + (runningMode(c) ? ' running' : '');
  const modeText = busy ? '计算中…' : (finished ? '已完成' : (c ? c.mode_label : '尚未创建'));
  $('run-status').textContent = modeText;
  const badge = $('mode-badge');
  if (c) {
    badge.textContent = finished ? '窗口结束' : c.mode_label;
    badge.className = 'badge ' + (finished ? 'finished' : c.mode);
  } else { badge.textContent = '尚未创建'; badge.className = 'badge'; }
  document.body.classList.toggle('busy', busy);
}
function act(label, fn) {
  if (busy) return;
  busy = true; controls(); message(label, 'pending');
  Promise.resolve().then(fn).catch(function (error) { message(error.message, 'error'); hideTooltip(); }).finally(function () { busy = false; controls(); });
}

/* ------------------------------------------------------------ 视图（回放取同一历史快照） */
// 回放视图只读取后端 /api/replay/snapshot 返回的真实状态快照；时间、点阵、KPI、图表、
// 事件都来自这一份快照，不把实时 state 按时间裁剪来拼，避免“时钟 08:57、点阵 08:54”。
function currentView(s) {
  const replay = replayActive();
  const snapshot = replay ? replayState.payload : null;
  const t = replay ? (snapshot ? snapshot.time_min : 0) : s.time_min;
  const row = liveRowAt(s, t);
  return { replay: replay, t: t, row: row, horizon: Math.max(1, s.horizon_min || 1), snapshot: snapshot };
}
function liveRowAt(s, t) {
  const rows = s.history || [];
  let row = null;
  for (const item of rows) { if (item.time_min <= t + 1e-9) row = item; else break; }
  if (row) return row;
  return { time_min: 0, occupancy: 0, charging: 0, arrivals: 0, rejected: 0, power_kw: 0, energy_kwh: 0, charged: 0, p_ev: 0.5, reserve: 0 };
}
function viewHistory(s, t) {
  const rows = [];
  for (const item of s.history || []) { if (item.time_min <= t + 1e-9) rows.push(item); else break; }
  return rows;
}
function viewFrames(s, t) {
  const frames = [];
  for (const frame of s.bay_frames || []) { if (frame.t <= t + 1e-9) frames.push(frame); else break; }
  return frames;
}
function bayStateArray(s, t) {
  const n = (s.config && s.config.n_spaces) || 0;
  const frames = s.bay_frames || [];
  let text = '';
  // 点阵必须和当前/快照状态逐位一致。热力图帧是降采样（可能落后当前时刻最多一个帧间隔），
  // 不能用来画“当前”点阵；实时的 s.bay_state 与 metrics.occupancy/charging 同源。
  if (replayActive() && replayState.payload) text = replayState.payload.bay_state || '';
  else text = s.bay_state || '';
  if (!text) { for (const frame of frames) { if (frame.t <= t + 1e-9) text = frame.s || ''; else break; } }
  if (!text) text = s.bay_state || '';
  const out = new Array(n);
  for (let i = 0; i < n; i++) out[i] = text.charAt(i) || '0';
  return out;
}

/* ------------------------------------------------------------ 点阵 */
function matrixHeuristics(n) {
  // 首屏优先：点阵高度控制在一屏内（案例 40–160 车位约 180–240px），宽度仍自适应。
  if (n <= 16) return { maxSize: 40, maxHeight: 180, minSize: 18, gapRatio: 0.42, targetAspect: 2.4 };
  if (n <= 40) return { maxSize: 34, maxHeight: 200, minSize: 14, gapRatio: 0.42, targetAspect: 2.5 };
  if (n <= 100) return { maxSize: 28, maxHeight: 220, minSize: 12, gapRatio: 0.44, targetAspect: 2.6 };
  if (n <= 300) return { maxSize: 20, maxHeight: 260, minSize: 9, gapRatio: 0.46, targetAspect: 2.6 };
  return { maxSize: 14, maxHeight: 320, minSize: 6, gapRatio: 0.48, targetAspect: 2.6 };
}
function resourceClass(bay, c) {
  if (bay < c.chargers) return 't-equipped';
  if (bay < c.charging_bays) return 't-charge-bay';
  return 't-ordinary';
}
function matrixAvailableWidth() {
  const body = document.querySelector('.matrix-body');
  const detail = $('bay-detail');
  const width = body ? body.clientWidth : 600;
  const detailWidth = detail && !detail.hidden ? 318 : 0;
  return Math.max(160, width - detailWidth - 2);
}
function layoutMatrix(force) {
  const s = state;
  if (!s || !s.config) return;
  const n = s.config.n_spaces || 0;
  const host = $('bay-matrix');
  const width = matrixAvailableWidth();
  if (n <= 0) {
    matrix = { n: 0, key: 'empty', layout: null, dots: [], prev: [], bodyWidth: width, emptyNode: null };
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.textContent = '总车位为 0：所有到达都会被拒绝，充电与共享指标不可用；在线学习与事件账本仍继续。';
    host.replaceChildren(empty);
    host.style.width = '100%';
    host.style.height = 'auto';
    $('bay-range').textContent = '0 个车位';
    return;
  }
  const heuristics = matrixHeuristics(n);
  if (typeof DotGrid === 'undefined') { host.textContent = '布局模块未加载'; return; }
  const layout = DotGrid.computeLayout({ count: n, width: width, maxHeight: heuristics.maxHeight, minSize: heuristics.minSize, maxSize: heuristics.maxSize, gapRatio: heuristics.gapRatio, targetAspect: heuristics.targetAspect });
  const key = n + '|' + layout.cols + '|' + layout.rows + '|' + Math.round(layout.size * 100) + '|' + Math.round(layout.gap * 100);
  const compact = layout.size < 15;
  host.style.width = Math.ceil(layout.gridWidth) + 'px';
  host.style.height = Math.ceil(layout.gridHeight) + 'px';
  host.style.position = 'relative';
  if (!force && matrix.key === key && matrix.dots.length === n) return;
  const dots = [];
  const fragment = document.createDocumentFragment();
  for (let bay = 0; bay < n; bay++) {
    const dot = document.createElement('button');
    dot.type = 'button';
    dot.className = 'bay-dot ' + resourceClass(bay, s.config) + (compact ? ' compact' : '');
    dot.dataset.bay = String(bay);
    dot.style.width = layout.size + 'px';
    dot.style.height = layout.size + 'px';
    dot.style.left = '0px';
    dot.style.top = '0px';
    dot.setAttribute('aria-label', '车位 ' + (bay + 1));
    fragment.append(dot);
    dots.push(dot);
  }
  host.replaceChildren(fragment);
  const positions = [];
  for (let bay = 0; bay < n; bay++) {
    const row = Math.floor(bay / layout.cols);
    const col = bay % layout.cols;
    const inRow = Math.min(layout.cols, n - row * layout.cols);
    const rowWidth = inRow * layout.size + (inRow - 1) * layout.gap;
    const offset = (layout.gridWidth - rowWidth) / 2;
    const x = offset + col * (layout.size + layout.gap);
    const y = row * (layout.size + layout.gap);
    positions.push([x, y]);
    dots[bay].style.left = x.toFixed(2) + 'px';
    dots[bay].style.top = y.toFixed(2) + 'px';
  }
  matrix = { n: n, key: key, layout: layout, dots: dots, prev: new Array(n).fill(''), bodyWidth: width, emptyNode: null, label: n + ' 个车位 · ' + layout.cols + ' 列 × ' + layout.rows + ' 行' };
  $('bay-range').textContent = matrix.label;
  $('matrix-count').textContent = '圆点直径 ' + layout.size.toFixed(1) + 'px';
  applyFilterClass();
  applySelectionClass();
  updateMatrixStates(s, currentView(s), true);
}
function applyFilterClass() {
  if (!matrix.dots.length) return;
  for (let bay = 0; bay < matrix.dots.length; bay++) {
    const dot = matrix.dots[bay];
    const stateCode = matrix.prev[bay] || '0';
    dot.classList.toggle('dimmed', filterState !== null && stateCode !== filterState);
  }
}
function applySelectionClass() {
  for (const dot of matrix.dots) dot.classList.toggle('selected', selectedBay !== null && Number(dot.dataset.bay) === selectedBay);
}
function bayDetailMap(s) {
  const map = new Map();
  for (const item of s.occupied || []) if (item && item.bay !== undefined) map.set(item.bay, item);
  for (const item of s.bays || []) if (item && item.vehicle && !map.has(item.bay)) map.set(item.bay, item);
  return map;
}
function updateMatrixStates(s, view, silent) {
  if (!matrix.dots.length) return;
  const states = bayStateArray(s, view.t);
  const c = s.config;
  const details = bayDetailMap(s);
  for (let bay = 0; bay < matrix.dots.length; bay++) {
    const dot = matrix.dots[bay];
    const code = states[bay] || '0';
    if (matrix.prev[bay] !== code) {
      const base = 'bay-dot ' + resourceClass(bay, c) + (matrix.layout && matrix.layout.size < 15 ? ' compact' : '');
      dot.className = base + ' s' + code + (filterState !== null && code !== filterState ? ' dimmed' : '') + (selectedBay === bay ? ' selected' : '') + (hoverBay === bay ? ' linked' : '');
      matrix.prev[bay] = code;
      if (!silent && !view.replay) flash(dot);
      const detail = details.get(bay);
      dot.setAttribute('aria-label', '车位 ' + (bay + 1) + '，' + STATE_LABEL[code] + (detail && detail.vehicle ? '，车辆 ' + (detail.vehicle.vehicle_id + 1) : ''));
    }
  }
}
function updateLinkedDot() {
  if (!matrix.dots.length) return;
  for (const dot of matrix.dots) dot.classList.toggle('linked', hoverBay !== null && Number(dot.dataset.bay) === hoverBay);
}
function dotTooltip(bay, s, view) {
  const c = s.config;
  const type = bay < c.chargers ? '带枪位' : bay < c.charging_bays ? '充电车位（无枪）' : '普通位';
  const states = bayStateArray(s, view.t);
  const code = states[bay] || '0';
  const rows = [{ label: '资源类型', value: type }, { label: '当前状态', value: STATE_LABEL[code], color: STATE_FILL[code] }];
  const detail = bayDetailMap(s).get(bay);
  const vehicle = detail && detail.vehicle;
  if (view.replay) {
    rows.push({ label: '回放快照', value: '实际时刻 ' + shortClock(view.t, c) + (vehicle ? '（车辆明细来自快照）' : '（该时刻无车辆记录）') });
    if (vehicle && vehicle.needs_charge) {
      rows.push({ label: '已交付', value: number(vehicle.delivered_kwh) + ' / ' + number(vehicle.energy_kwh) + ' kWh' });
    }
  } else if (vehicle) {
    rows.push({ label: '车辆', value: '#' + (vehicle.vehicle_id + 1) + ' · ' + (vehicle.is_ev ? '电车' : '油车') });
    if (vehicle.needs_charge) {
      rows.push({ label: '充电需求', value: number(vehicle.energy_kwh) + ' kWh' });
      rows.push({ label: '已交付', value: number(vehicle.delivered_kwh) + ' kWh' });
      if (detail.power_kw > 0) rows.push({ label: '当前功率', value: number(detail.power_kw, 1) + ' kW' });
      if (vehicle.completed) rows.push({ label: '充满时刻', value: vehicle.completion_min === undefined || vehicle.completion_min === null ? '—' : clock(vehicle.completion_min, c) });
    }
    rows.push({ label: '预计离场', value: clock(vehicle.departure_min, c) });
  } else {
    rows.push({ label: '车位', value: '空闲' });
  }
  return { title: '车位 ' + (bay + 1) + ' · ' + type, rows: rows };
}
function selectBay(bay) {
  selectedBay = bay;
  applySelectionClass();
  updateLinkedDot();
  renderBayDetail();
  const n = state && state.config ? state.config.n_spaces : 0;
  if (n > heat.rows) {
    const nextOffset = Math.floor(bay / heat.rows) * heat.rows;
    if (nextOffset !== heat.rowOffset) { heat.rowOffset = nextOffset; renderCharts(state, currentView(state)); }
  }
  if (charts.heatmap) charts.heatmap.setGeometry({ selectedBay: bay });
}
function renderBayDetail() {
  const panel = $('bay-detail');
  if (!panel) return;
  if (selectedBay === null || !state) { panel.hidden = true; layoutMatrix(true); return; }
  panel.hidden = false;
  const s = state, c = s.config, view = currentView(s);
  const bay = selectedBay;
  const type = bay < c.chargers ? '带枪位' : bay < c.charging_bays ? '充电车位（无枪）' : '普通位';
  $('bay-detail-title').textContent = '车位 ' + (bay + 1) + ' · ' + type;
  const states = bayStateArray(s, view.t);
  const code = states[bay] || '0';
  const detail = bayDetailMap(s).get(bay);
  const vehicle = detail && detail.vehicle;
  const facts = [];
  facts.push(['当前状态', STATE_LABEL[code]]);
  if (vehicle) {
    facts.push(['车辆', '#' + (vehicle.vehicle_id + 1) + ' · ' + (vehicle.is_ev ? '电车' : '油车')]);
    if (vehicle.needs_charge) {
      facts.push(['充电需求', number(vehicle.energy_kwh) + ' kWh']);
      facts.push(['已交付', number(vehicle.delivered_kwh) + ' kWh']);
      facts.push(['当前功率', number(detail.power_kw || 0, 1) + ' kW']);
      facts.push(['充满时刻', vehicle.completion_min === undefined || vehicle.completion_min === null ? '未完成' : clock(vehicle.completion_min, c)]);
    } else {
      facts.push(['充电需求', '无（仅停车）']);
    }
    facts.push(['预计离场', clock(vehicle.departure_min, c)]);
    if (view.replay) facts.push(['数据来源', '回放快照（该历史时刻的真实状态）']);
  } else if (view.replay) {
    facts.push(['车辆明细', s.occupied_available === false ? '该历史时刻未记录（快照不保存车辆级明细）' : '该历史时刻该车位无车辆记录']);
  }
  const list = $('bay-facts');
  list.replaceChildren();
  for (const pair of facts) {
    const row = document.createElement('div');
    const term = document.createElement('dt'); term.textContent = pair[0];
    const value = document.createElement('dd'); value.textContent = pair[1];
    row.append(term, value); list.append(row);
  }
  updateBayTimeline(s, bay, view);
}
function updateBayTimeline(s, bay, view) {
  const host = $('bay-timeline');
  host.replaceChildren();
  const frames = viewFrames(s, view.t);
  const horizon = Math.max(1, s.horizon_min || 1);
  $('bay-timeline-end').textContent = shortClock(view.t, s.config) + '（已运行 ' + Math.round(view.t) + ' / ' + Math.round(horizon) + ' 分钟）';
  if (!frames.length) {
    const empty = document.createElement('span');
    empty.className = 'seg-empty'; empty.style.flex = '1 1 auto';
    host.append(empty);
    return;
  }
  const segments = [];
  for (let i = 0; i < frames.length; i++) {
    const start = frames[i].t;
    const end = i + 1 < frames.length ? frames[i + 1].t
      : (view.replay ? start + 1e-6 : Math.max(start + 1e-6, view.t));
    const code = (frames[i].s || '').charAt(bay) || '0';
    if (segments.length && segments[segments.length - 1].code === code) segments[segments.length - 1].end = end;
    else segments.push({ code: code, start: start, end: end });
  }
  if (view.replay && view.snapshot && frames.length && view.t > frames[frames.length - 1].t + 1e-9) {
    const tailCode = (view.snapshot.bay_state || '').charAt(bay) || '0';
    const tailStart = frames[frames.length - 1].t;
    if (segments.length && segments[segments.length - 1].code === tailCode) segments[segments.length - 1].end = view.t;
    else segments.push({ code: tailCode, start: tailStart, end: view.t });
  }
  for (const segment of segments) {
    const span = document.createElement('span');
    span.className = 'seg-' + segment.code;
    span.style.flex = String(Math.max(0.001, segment.end - segment.start)) + ' 1 0';
    span.title = shortClock(segment.start, s.config) + ' – ' + shortClock(segment.end, s.config) + ' · ' + STATE_LABEL[segment.code];
    host.append(span);
  }
}

/* ------------------------------------------------------------ 图表 */
function configKey(s) {
  const c = s.config || {};
  return [c.n_spaces, c.horizon_min || s.horizon_min, c.feeder_kw, c.charger_kw, c.chargers].join('|');
}
function resetCharts() {
  for (const key of ['occupancy', 'power', 'energy', 'bars', 'heatmap']) {
    const chart = charts[key];
    if (chart && typeof chart.destroy === 'function') chart.destroy();
  }
  for (const id of ['chart-occupancy', 'chart-power', 'chart-energy-cum', 'chart-heatmap', 'compare-bars']) {
    const host = $(id);
    if (host) host.replaceChildren();
  }
  charts = { key: '', occupancy: null, power: null, energy: null, heatmap: null, bars: null };
}
function ensureCharts(s) {
  const key = configKey(s);
  if (charts.key === key && charts.occupancy) return;
  resetCharts();
  charts.key = key;
  const c = s.config;
  charts.occupancy = new LabCharts.TimeChart($('chart-occupancy'), {
    height: 236, stacked: false, yTicks: 4, xDomain: [0, Math.max(1, s.horizon_min)], ariaLabel: '空闲、在场与充电中车位数随时间变化',
    yLabel: '车位', yFormat: function (v) { return LabCharts.fmt(v, 0); }, xFormat: function (t) { return shortClock(t); },
    series: [
      { key: 'occupancy', label: '在场车辆', color: '#5F7F96', fill: 'rgba(95,127,150,.30)', width: 2 },
      { key: 'charging', label: '充电中', color: '#1F6F5C', fill: 'rgba(31,111,92,.34)', width: 2 },
      { key: 'idle', label: '空闲车位', color: '#9DB0A8', width: 1.6, dash: '4 3' }
    ],
    tooltip: function (payload) { showTooltip(payload); }, onHoverEnd: hideTooltip,
    yDomain: function () { return Math.max(1, (state && state.config ? state.config.n_spaces : 1)); }
  });
  charts.power = new LabCharts.TimeChart($('chart-power'), {
    height: 132, yTicks: 3, xDomain: [0, Math.max(1, s.horizon_min)], ariaLabel: '当前充电功率随时间变化',
    yLabel: 'kW', yFormat: function (v) { return LabCharts.fmt(v, 0); }, xFormat: function (t) { return shortClock(t); }, hideXLabels: true,
    series: [{ key: 'power_kw', label: '当前功率', color: '#B4761F', fill: 'rgba(180,118,31,.16)' }],
    reference: { value: c.feeder_kw, label: '场站限额 ' + c.feeder_kw + ' kW', color: '#8A9A94' },
    yDomain: function () { return Math.max(1, (c.feeder_kw || 1), (state && state.metrics ? state.metrics.peak_power_kw || 0 : 0)); },
    tooltip: function (payload) { showTooltip(payload); }, onHoverEnd: hideTooltip
  });
  charts.energy = new LabCharts.TimeChart($('chart-energy-cum'), {
    height: 148, yTicks: 4, xDomain: [0, Math.max(1, s.horizon_min)], ariaLabel: '累计交付电量随时间变化',
    yLabel: 'kWh', yFormat: function (v) { return LabCharts.fmt(v, 0); }, xFormat: function (t) { return shortClock(t); },
    series: [{ key: 'energy_kwh', label: '累计交付电量', color: '#1F5FA8', fill: 'rgba(31,95,168,.12)', endLabel: true, endDigits: 1, unit: ' kWh' }],
    yDomain: function (rows) { const last = rows.length ? Number(rows[rows.length - 1].energy_kwh) || 0 : 0; return LabCharts.niceCeil(Math.max(1, last * 1.06 + 1)); },
    tooltip: function (payload) { showTooltip(payload); }, onHoverEnd: hideTooltip
  });
  charts.heatmap = new LabCharts.Heatmap($('chart-heatmap'), {
    height: 380, maxRows: heat.rows, stateColors: STATE_FILL, clock: function (t) { return shortClock(t); },
    tooltip: function (payload) { showTooltip(payload); },
    onHoverBay: function (bay) { hoverBay = bay; updateLinkedDot(); },
    onHoverEnd: function () { hoverBay = null; updateLinkedDot(); },
    onClickBay: function (bay) { selectBay(bay); }
  });
  updateOccupancyLegend();
  updateHeatmapLegend();
}
function updateOccupancyLegend() {
  const host = $('occupancy-legend');
  if (!host || !charts.occupancy) return;
  host.replaceChildren();
  const entries = [
    { key: 'occupancy', label: '在场车辆', color: '#5F7F96' },
    { key: 'charging', label: '充电中', color: '#1F6F5C' },
    { key: 'idle', label: '空闲车位', color: '#9DB0A8' }
  ];
  for (const entry of entries) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'chip';
    button.setAttribute('aria-pressed', 'true');
    button.innerHTML = '<i class="legend-dot" style="background:' + entry.color + '"></i>' + entry.label;
    button.addEventListener('click', function () {
      const on = button.getAttribute('aria-pressed') !== 'true';
      button.setAttribute('aria-pressed', String(on));
      charts.occupancy.setVisible(entry.key, on);
    });
    host.append(button);
  }
}
function updateHeatmapLegend() {
  const host = $('heatmap-legend');
  if (!host) return;
  host.replaceChildren();
  for (const code of ['0', '1', '2', '3', '4']) {
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.style.cursor = 'default';
    chip.innerHTML = '<i class="swatch s' + code + '"></i>' + STATE_LABEL[code];
    host.append(chip);
  }
}
function chartRows(history, n) {
  return history.map(function (row) {
    const occupancy = Number(row.occupancy) || 0;
    const charging = Number(row.charging) || 0;
    return { time_min: row.time_min, idle: Math.max(0, n - occupancy), occupancy: occupancy, parked: Math.max(0, occupancy - charging), charging: charging, power_kw: Number(row.power_kw) || 0, energy_kwh: Number(row.energy_kwh) || 0 };
  });
}
function renderCharts(s, view) {
  ensureCharts(s);
  const n = (s.config && s.config.n_spaces) || 0;
  const history = viewHistory(s, view.t);
  const rows = chartRows(history, n);
  charts.occupancy.update(rows, {});
  charts.power.update(rows, {});
  charts.energy.update(rows, {});
  const frames = viewFrames(s, view.t);
  const rowOffset = Math.min(heat.rowOffset, Math.max(0, n - 1));
  const rowCount = Math.max(0, Math.min(heat.rows, n - rowOffset));
  const heatMeta = { nSpaces: n, horizon: Math.max(1, s.horizon_min), currentT: view.t, rowOffset: rowOffset, rowCount: rowCount, selectedBay: selectedBay, highlightBay: hoverBay };
  // 快照帧是热力图的采样；快照时刻可能晚于最后一帧。用快照 bay_state 补齐最后一列，
  // 保证热力图右边界与回放时钟、点阵、KPI 截止到同一时刻。
  // 快照/实时 state 的离散车位状态都精确到当前时刻，用其补齐热力图最后一列。
  if (view.replay && view.snapshot) heatMeta.tailState = view.snapshot.bay_state;
  else if (s.bay_state) heatMeta.tailState = s.bay_state;
  charts.heatmap.setGeometry(heatMeta);
  charts.heatmap.update(frames, heatMeta);
  const rangeStart = n > 0 ? rowOffset + 1 : 0, rangeEnd = rowOffset + rowCount;
  $('heatmap-range').textContent = n > heat.rows ? '车位 ' + rangeStart + '–' + rangeEnd + ' / 共 ' + n : '全部 ' + n + ' 个车位';
  const energyNote = s.metrics ? ('峰值 ' + number(s.metrics.peak_power_kw, 1) + ' kW') : '—';
  $('energy-chart-note').textContent = energyNote;
  if (selectedBay !== null) renderBayDetail();
}

/* ------------------------------------------------------------ 指标与文本 */
function renderKpis(s, view) {
  const c = s.config, m = s.metrics || {}, row = view.row;
  const n = c.n_spaces || 0;
  const occupancy = view.replay ? row.occupancy : m.occupancy;
  const charging = view.replay ? row.charging : m.charging_now;
  const energy = view.replay ? row.energy_kwh : m.energy_delivered_kwh;
  const power = view.replay ? row.power_kw : m.current_power_kw;
  const arrivals = view.replay ? row.arrivals : m.arrivals;
  const rejected = view.replay ? row.rejected : m.rejected;
  const completed = view.replay ? row.charged : m.charge_completed;
  $('kpi-occupancy').textContent = number(occupancy, 0) + ' / ' + n;
  $('kpi-occupancy-sub').textContent = '空位 ' + number(Math.max(0, n - occupancy), 0) + ' · 时间平均占用率 ' + (view.replay ? '该历史时刻未记录' : percent(m.mean_occupancy_rate));
  $('kpi-charging').textContent = number(charging, 0) + ' 辆';
  $('kpi-charging-sub').textContent = '充电车位 ' + c.charging_bays + ' · 带枪位 ' + c.chargers + ' · 已充满 ' + number(completed, 0) + ' 辆';
  $('kpi-energy').textContent = number(energy, 1);
  $('kpi-energy-sub').textContent = '当前功率 ' + number(power, 1) + ' kW · 场站限额 ' + number(c.feeder_kw, 0) + ' kW';
  $('kpi-arrivals').textContent = number(arrivals, 0) + ' / ' + number(rejected, 0);
  const rate = view.replay ? m.rejection_rate : (arrivals ? rejected / arrivals : null);
  const rejIce = m.rejected_ice === undefined ? null : m.rejected_ice;
  const rejEv = m.rejected_ev === undefined ? null : m.rejected_ev;
  $('kpi-arrivals-sub').textContent = '拒绝率 ' + percent(rate) + ' · 油车 ' + number(rejIce, 0) + ' · 电车 ' + number(rejEv, 0);
}

/* ------------------------------------------------------------ 运行明细 / 成本 / 预测 / 事件 */
function renderRuntime(s) {
  const c = s.continuous;
  if (!c) { $('run-mode').textContent = '—'; return; }
  const ledger = c.ledger || {}, replayInfo = c.replay || {};
  const speed = c.effective_speed || c.speed;
  $('run-mode').textContent = c.mode_label + (c.paused ? '（已暂停）' : '');
  $('run-speed').textContent = (c.mode === 'realtime' ? '有效 1x（realtime 固定）' : '有效 ' + speed + 'x') + ' · ' + c.speed_note;
  $('run-time').textContent = number(c.time_min, 1) + ' / ' + number(c.horizon_min, 0) + ' 分钟';
  $('run-elapsed').textContent = number(c.real_elapsed_s, 1) + ' 秒';
  $('run-ticks').textContent = c.ticks + ' 次';
  $('run-events').textContent = c.events_total + ' 事件 / ' + ledger.entries + ' 已入账';
  $('run-ledger').textContent = '水位 ' + ledger.watermark + ' · seq ' + (ledger.first_seq || '—') + '–' + (ledger.last_seq || '—');
  $('run-clock-source').textContent = c.clock_source === 'injected' ? '注入时钟（测试）' : '后端单调时钟';
  const windowInfo = c.window || {};
  $('run-window').textContent = windowInfo.finite ? '有限窗口：到期后自动停止（finished）' : '—';
  const expected = c.time_min * 60 / (speed || 1);
  $('run-lag').textContent = '实时 ' + number(c.real_elapsed_s, 1) + ' 秒 / 期望 ' + number(expected, 1) + ' 秒（偏差 ' + number(c.real_elapsed_s - expected, 1) + ' 秒）';
  $('run-replay').textContent = replayInfo.active
    ? ('回放 replay · ' + (replayInfo.basis || 'state_snapshot') + ' · 快照 ' + ((replayInfo.cursor || 0) + 1) + '/' + replayInfo.total)
    : '未在回放';
  $('run-guard').textContent = ledger.double_accounting_guard || '—';
  const note = $('run-note');
  if (note) {
    if (replayActive() && s.replay_diagnostics) {
      note.hidden = false;
      note.textContent = '以下“仿真时间 / tick / 账本 / 成本”是当前后端运行诊断（' + clock(s.replay_diagnostics.diagnostics_time_min, s.config) + '），不是回放快照时刻；回放视图只用快照数据。';
    } else { note.hidden = true; note.textContent = ''; }
  }
}
function renderCost(s) {
  const m = s.metrics || {}, block = m.cost || null, version = (block && block.cost_model_version) || s.cost_model_version || '—';
  $('cost-version').textContent = version;
  const total = m.total_cost !== undefined ? m.total_cost : block ? block.total : null;
  const complete = m.cost_complete !== undefined ? m.cost_complete : block ? block.complete : false;
  const missing = m.cost_missing_parameters || (block && block.missing_parameters) || [];
  $('cost-total').textContent = total === null || total === undefined ? '无法完整计算（未知／待校准）' : number(total, 2) + ' ' + ((block && block.currency) || '');
  $('cost-complete').textContent = complete ? '完整' : '不完整（存在 null 参数）';
  $('cost-currency').textContent = ((block && block.currency) || '—') + ' / ' + ((block && block.price_year) === null || (block && block.price_year) === undefined ? '未核实' : block.price_year);
  $('cost-period').textContent = (block && block.accounting_period) || '—';
  $('cost-missing').textContent = missing.length ? missing.join('、') : '无';
  const body = $('cost-items'); body.replaceChildren();
  const items = (block && block.items) || m.cost_items || {};
  const unit = (block && block.unit) || m.cost_unit || 'TWD / 窗口';
  for (const key of Object.keys(items)) {
    const row = document.createElement('tr');
    const cells = [key, items[key] === null ? '未知／待校准' : number(items[key], 2), unit];
    for (const text of cells) { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }
    body.append(row);
  }
  if (!Object.keys(items).length) { const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 3; cell.textContent = '成本分项不可用（未知／待校准）'; row.append(cell); body.append(row); }
  const attribution = m.cost_attribution || (block && block.attribution) || null;
  const transfers = m.cost_transfers || (block && block.transfers) || null;
  const show = function (value) { return value === null || value === undefined ? '未知／待校准' : (typeof value === 'object' ? JSON.stringify(value) : String(value)); };
  const flatten = function (group) { return group ? Object.keys(group).map(function (key) { return key + '=' + show(group[key]); }).join('；') : '不可用／未知'; };
  const projected = (block && block.projected) || null;
  const projectedText = projected && Object.keys(projected).length ? ('占桩归因 ' + flatten(projected.occupancy_minutes_by_reason) + ' · 收费/转移 ' + flatten(projected.transfers)) : '不可用';
  const relocation = block ? (block.relocation_count === undefined ? '—' : block.relocation_count) + ' 次（无普通位被阻止 ' + (block.relocation_blocked === undefined ? '—' : block.relocation_blocked) + ' 次）' : '—';
  const replayPrefix = replayActive() ? '【当前运行累计（非回放时刻）】回放快照未记录历史成本；' : '';
  $('cost-notes').textContent = replayPrefix + '占桩影响归因（实时口径：只累计到当前 sim.time，不进 total）：' + flatten(attribution)
    + ' · 收费/转移支付（实时，不进 total）：' + flatten(transfers)
    + ' · 预计最终值（单列，不是已发生）：' + projectedText + ' · 挪车 ' + relocation;
}
function renderPrediction(s, view) {
  const f = s.forecast || {}, m = s.metrics || {};
  $('p-ev').textContent = number(100 * f.p_ev) + '%';
  $('p-ev-fill').style.width = (100 * (f.p_ev || 0)) + '%';
  $('interval-label').textContent = number(f.interval_level * 100, 0) + '% 到达等待时间预测区间';
  $('wait-interval').textContent = number(f.wait_lower_min) + ' – ' + number(f.wait_upper_min) + ' 分钟';
  $('observed').textContent = f.observed_arrivals + ' 辆';
  $('rate').textContent = number(f.arrival_rate_hour) + ' 辆/小时';
  $('need-forecast').textContent = number(f.expected_charge_arrivals) + ' 辆 / ' + f.window_min + '分钟';
  $('reserve').textContent = s.reserve + ' 个';
  $('brier').textContent = number(m.brier, 3);
  $('coverage').textContent = percent(m.interval_coverage);
  $('width').textContent = number(m.interval_width_min) + ' 分钟';
  $('score-n').textContent = m.prediction_samples;
  $('score-description').textContent = '按上一到达时刻发布的预测评分。' + (s.finished ? '最后一个尚未观察到下一辆的预测按右删失保留，不计分。' : '当前时刻预测已计入无车到达期间的暴露时间。') + (view.replay && view.snapshot ? '（回放快照：预测与评分是该历史时点的值。）' : '');
  const history = viewHistory(s, view.t);
  const values = history.map(function (row) { return Number(row.p_ev); }).filter(function (v) { return isFinite(v); });
  LabCharts.sparkline($('learning-spark'), values, { color: '#1F5FA8', fill: 'rgba(31,95,168,.12)' });
}
function renderEvents(s, view) {
  const body = $('event-body'); body.replaceChildren();
  let rows;
  if (view.replay) rows = (s.events || []).slice().reverse();
  else rows = (s.ledger_tail && s.ledger_tail.length ? s.ledger_tail : s.events || []).slice().reverse();
  const names = { arrival: '到达并停车', rejected: '停车被拒', charged: '充电完成', charging_start: '开始充电', departure: '离场', relocated: '挪车释放', release_blocked: '无法释放' };
  for (const event of rows) {
    const row = document.createElement('tr');
    const info = event.kind === 'arrival' || event.kind === 'rejected' ? (event.is_ev ? '电车' : '油车') + (event.needs_charge ? ' · 有充电需求' : ' · 仅停车') : event.delivered_kwh !== undefined ? '交付 ' + number(event.delivered_kwh) + ' kWh' : '';
    const cells = [event.seq === undefined ? '—' : '#' + event.seq, clock(event.time_min, s.config), '#' + (event.vehicle_id + 1), names[event.kind] || event.kind, event.bay === null || event.bay === undefined ? '—' : event.bay + 1, info];
    for (const text of cells) { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }
    body.append(row);
  }
  if (!rows.length) { const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 6; cell.textContent = '尚无已入账事件。点击「播放」推进、或用「单步」逐段观察。'; row.append(cell); body.append(row); }
  $('ledger-meta').textContent = view.replay
    ? ('回放快照：截至实际时刻 ' + shortClock(view.t, s.config) + ' 已入账 ' + number(s.events_total, 0) + ' 条（最近 60 条，最新在上）')
    : ('显示最近 60 条已入账事件；完整账本与事件可分别导出。' + (s.continuous && s.continuous.ledger ? '账本共 ' + s.continuous.ledger.entries + ' 条。' : ''));
}

/* ------------------------------------------------------------ 顶部时钟 / 进度 / 回放 */
function renderChrome(s, view) {
  const c = s.config || {}, cont = s.continuous || {};
  const horizon = Math.max(1, s.horizon_min || 1);
  $('clock').textContent = clock(view.t, c);
  const fill = $('progress-fill');
  fill.style.width = (100 * view.t / horizon) + '%';
  $('progress-bar') && 0;
  document.querySelector('.progress').classList.toggle('mode-replay', view.replay);
  $('progress-text').textContent = shortClock(view.t, c) + ' / 结束 ' + shortClock(horizon, c) + ' · ' + Math.round(view.t) + ' / ' + Math.round(horizon) + ' 分钟';
  if (view.replay) {
    const snap = view.snapshot || {};
    const ledger = snap.replay ? ' · 账本 #' + snap.replay.event_seq : '';
    $('replay-status').textContent = '快照 ' + (replayState.index + 1) + ' / ' + replayState.total
      + ' · 实际时刻 ' + clock(view.t, c) + ledger;
    $('replay-range').max = String(Math.max(0, replayState.total - 1));
    $('replay-range').value = String(replayState.index);
  } else {
    $('replay-status').textContent = '未在回放';
    $('replay-range').max = String(cont.replay ? Math.max(0, cont.replay.total - 1) : 0);
    $('replay-range').value = '0';
  }
}

/* ------------------------------------------------------------ 策略对比 */
function renderCompareMeta(result) {
  const box = $('compare-meta');
  if (!box) return;
  box.replaceChildren();
  box.hidden = false;
  const model = result.comparison_model || {};
  const dl = document.createElement('dl');
  dl.className = 'facts compact compare-facts';
  const add = function (term, value) {
    const row = document.createElement('div');
    const dt = document.createElement('dt'); dt.textContent = term;
    const dd = document.createElement('dd'); dd.textContent = value === null || value === undefined || value === '' ? '—' : String(value);
    row.append(dt, dd); dl.append(row);
  };
  add('模型版本 / 策略集合', (model.model_version || '—') + ' · ' + (model.label || result.policy_set || '—'));
  add('适用模型', model.applicable_model);
  add('信息合同', model.info_contract);
  add('外生车辆流', model.demand_stream);
  add('仿真与指标合同', model.simulation_contract);
  add('基线策略', model.baseline_policy);
  add('样本范围', result.config.n_spaces + ' 车位 / ' + result.config.duration_hours + ' 小时 / 情景 '
    + result.config.scenario + ' / 种子 ' + (result.seeds || []).join(', '));
  add('不确定性', model.uncertainty);
  add('配对成本', model.paired_cost_rule);
  box.append(dl);
  const defs = model.metric_definitions || {};
  if (Object.keys(defs).length) {
    const details = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = '指标定义（本次对比口径）';
    const list = document.createElement('dl'); list.className = 'facts compact compare-facts';
    details.append(summary);
    for (const key of Object.keys(defs)) {
      const row = document.createElement('div');
      const dt = document.createElement('dt'); dt.textContent = key;
      const dd = document.createElement('dd'); dd.textContent = defs[key];
      row.append(dt, dd); list.append(row);
    }
    details.append(list);
    box.append(details);
  }
  const warning = $('compare-warning');
  if (warning) {
    const notice = model.legacy_notice;
    warning.hidden = !notice;
    warning.textContent = notice ? (notice + ' 适用模型：' + (model.applicable_model || '历史实现')) : '';
  }
}
function renderComparison(result) {
  comparison = result;
  $('compare-empty').hidden = true; $('compare-results').hidden = false;
  const c = result.config, model = result.comparison_model || {};
  $('compare-description').textContent = c.n_spaces + ' 车位 / ' + c.chargers + ' 枪 · ' + c.duration_hours + ' 小时 · '
    + result.seeds.length + ' 个独立种子 · 每种子各策略重放同一外生车流 · ' + (model.label || result.policy_set || '');
  renderCompareMeta(result);
  const body = $('compare-body'); body.replaceChildren();
  const deltaKey = result.rows.length && result.rows[0].paired_cost_delta_vs_baseline !== undefined
    ? 'paired_cost_delta_vs_baseline' : 'paired_cost_delta_vs_open';
  for (const row of result.rows) {
    const tr = document.createElement('tr');
    const uncertainty = function (key, pct) { return pct ? percent(row[key]) + ' ± ' + percent(row[key + '_std']) : number(row[key], 1) + ' ± ' + number(row[key + '_std'], 1); };
    const costText = row.total_cost === null || row.total_cost === undefined ? '未知／待校准' : 'TWD ' + number(row.total_cost, 0);
    const name = row.name + (row.baseline ? '（基线）' : '');
    for (const text of [name, uncertainty('rejection_rate', true), uncertainty('charge_completion_rate_all', true), uncertainty('energy_delivered_kwh'), costText, number(row[deltaKey], 1)]) {
      const td = document.createElement('td'); td.textContent = text; tr.append(td);
    }
    body.append(tr);
  }
  ensureBars();
  updateCompareMetric();
  $('download-comparison').disabled = false;
}
function ensureBars() {
  if (!charts.bars) charts.bars = new LabCharts.PolicyBars($('compare-bars'), {});
}
function metricInfo(key) {
  if (key === 'rejection_rate') return { key: 'rejection_rate', color: '#1F5FA8', format: function (v, s) { return percent(v) + (s ? ' ± ' + percent(s) : ''); } };
  if (key === 'charge_completion_rate_all') return { key: 'charge_completion_rate_all', color: '#1F6F5C', format: function (v, s) { return percent(v) + (s ? ' ± ' + percent(s) : ''); } };
  return { key: 'energy_delivered_kwh', color: '#B4761F', format: function (v, s) { return number(v, 1) + (s ? ' ± ' + number(s, 1) : '') + ' kWh'; } };
}
function updateCompareMetric() {
  if (!comparison) return;
  ensureBars();
  charts.bars.update(comparison.rows, metricInfo(compareMetric));
  for (const button of document.querySelectorAll('#compare-metric-tabs button')) button.setAttribute('aria-pressed', String(button.dataset.metric === compareMetric));
}

/* ------------------------------------------------------------ 主渲染 */
function render(s) {
  state = s;
  const view = currentView(s);
  ensureCharts(s);
  layoutMatrix(false);
  renderChrome(s, view);
  if (view.replay) {
    $('bay-range').textContent = '回放快照 ' + (replayState.index + 1) + ' / ' + replayState.total
      + ' · 实际时刻 ' + shortClock(view.t, s.config);
  } else if (matrix.label) { $('bay-range').textContent = matrix.label; }
  renderKpis(s, view);
  updateMatrixStates(s, view, false);
  applyFilterClass();
  applySelectionClass();
  renderCharts(s, view);
  renderRuntime(s);
  renderCost(s);
  renderPrediction(s, view);
  renderEvents(s, view);
  updateConfigSummary();
  controls();
  lastSeen = { time: s.time_min, events: (s.events || []).length, mode: s.continuous ? s.continuous.mode : '' };
}

/* ------------------------------------------------------------ 动作 */
async function apply() {
  const config = collect();
  const result = sessionId ? await api('/api/reset', { id: sessionId, config: config }) : await api('/api/create', { config: config, speed: selectedSpeed() });
  sessionId = result.id; dirty = false;
  $('dirty-note').textContent = '参数已应用。可播放推进、单步，或运行至结束。';
  $('dirty-note').classList.remove('dirty');
  comparison = null; $('compare-results').hidden = true; $('compare-empty').hidden = false;
  replayResetState();
  heat.rowOffset = 0; matrix.key = '';
  render(result); message('实验已创建。仿真时钟由后端推进，界面每秒轮询一次。', 'ok');
}
async function resetRun() {
  const result = await api('/api/reset', { id: sessionId });
  replayResetState();
  heat.rowOffset = 0; matrix.key = '';
  render(result); message('已按当前运行配置重置；随机种子不变。', 'ok');
}
async function playPause() {
  const c = state && state.continuous;
  if (!c) return;
  if (c.paused) { render(await api('/api/resume', { id: sessionId })); message('已恢复：从当前时刻继续，不补推进暂停区间。', 'ok'); }
  else { render(await api('/api/pause', { id: sessionId })); message('已暂停：时钟不推进，已入账水位不变。', 'ok'); }
}
function selectedSpeed() {
  const active = document.querySelector('[data-speed].active');
  return active ? Number(active.dataset.speed) : 60;
}
async function setSpeed(speed) {
  const result = speed === 1
    ? await api('/api/mode', { id: sessionId, mode: 'realtime' })
    : await api('/api/mode', { id: sessionId, mode: 'accelerated', speed: speed });
  render(result);
  message(speed === 1 ? '已切换到实时 1x（1 仿真分钟 = 60 实时秒）。' : '倍速已调整为 ' + speed + 'x；各视图使用同一仿真时钟。', 'ok');
}
async function stepOnce() {
  const minutes = Number($('step-minutes').value);
  const before = state && state.continuous ? state.continuous.ledger.entries : 0;
  const result = await api('/api/step', { id: sessionId, minutes: minutes });
  render(result);
  const after = result.continuous ? result.continuous.ledger.entries : 0;
  const added = Math.max(0, after - before);
  message(result.finished ? '仿真已完成。' : ('已单步推进 ' + minutes + ' 分钟，新增入账 ' + added + ' 条事件；本步状态变化已在点阵与图表中高亮。'), 'ok');
}
async function finishRun() {
  const before = state && state.continuous ? state.continuous.ledger.entries : 0;
  const result = await api('/api/run', { id: sessionId });
  render(result);
  const after = result.continuous ? result.continuous.ledger.entries : 0;
  message('仿真运行至窗口结束，共新增入账 ' + Math.max(0, after - before) + ' 条；仍场请求作为待交付单列。', 'ok');
}
function replayResetState() {
  replayState = { total: 0, index: 0, positions: [], payload: null };
  heat.rowOffset = 0; selectedBay = null; $('bay-detail').hidden = true;
}
function mergeSnapshot(live, payload) {
  const base = live || {};
  const merged = Object.assign({}, base, payload);
  merged.continuous = Object.assign({}, base.continuous || {}, payload.continuous || {});
  merged.continuous.replay = Object.assign({}, (base.continuous || {}).replay || {}, (payload.continuous || {}).replay || {});
  merged.config = payload.config || base.config;
  return merged;
}
async function loadReplaySnapshot(index) {
  const payload = await api('/api/replay/snapshot', { id: sessionId, index: index });
  replayState.payload = payload;
  replayState.total = payload.replay.total;
  replayState.index = payload.replay.index;
  replayState.positions = payload.replay.positions || [];
  return payload;
}
async function replayStart() {
  replayResetState();
  const live = await api('/api/replay/start', { id: sessionId, source: 'synthetic' });
  const payload = await loadReplaySnapshot(0);
  render(mergeSnapshot(live, payload));
  message('已进入回放：回放位置=后端真实状态快照，实际时刻 ' + shortClock(payload.time_min, payload.config)
    + '；点阵、KPI、图表、事件均来自该快照（同一时刻的多个事件合为一个快照）。', 'ok');
}
async function replayStep(count) {
  const live = await api('/api/replay/step', { id: sessionId, count: count });
  const step = live.replay_step || {};
  const cursor = step.cursor === undefined ? replayState.index + 1 : step.cursor;
  const payload = await loadReplaySnapshot(cursor);
  render(mergeSnapshot(live, payload));
  message('回放快照 ' + (replayState.index + 1) + '/' + replayState.total + ' · 实际时刻 '
    + shortClock(payload.time_min, payload.config) + ' · 账本 #' + payload.replay.event_seq, 'ok');
}
async function jumpReplay(target) {
  const clamped = Math.max(0, Math.min(Number(target) || 0, Math.max(0, replayState.total - 1)));
  if (clamped === replayState.index && replayState.payload) { render(state); return; }
  const live = await api('/api/replay/jump', { id: sessionId, index: clamped });
  const step = live.replay_jump || {};
  const payload = await loadReplaySnapshot(step.cursor === undefined ? clamped : step.cursor);
  render(mergeSnapshot(live, payload));
  message('回放定位到快照 ' + (replayState.index + 1) + ' / ' + replayState.total + ' · 实际时刻 '
    + shortClock(payload.time_min, payload.config) + '；视图已同步到该快照。', 'ok');
}
async function replayExit() {
  const live = await api('/api/replay/exit', { id: sessionId });
  replayResetState();
  render(live);
  message('已退出回放，回到实时/加速模式；回放快照与当前运行状态已分开。', 'ok');
}

/* ------------------------------------------------------------ 事件绑定 */
function wire() {
  $('toggle-settings').addEventListener('click', function () {
    const open = $('sidebar').classList.toggle('settings-open');
    $('toggle-settings').textContent = open ? '收起参数设置' : '展开参数设置';
    $('toggle-settings').setAttribute('aria-expanded', String(open));
  });
  $('config-form').addEventListener('submit', function (event) { event.preventDefault(); });
  $('apply').addEventListener('click', function () { act('正在应用参数…', apply); });
  $('transport-play').addEventListener('click', function () { act('正在切换运行状态…', playPause); });
  $('transport-step').addEventListener('click', function () { act('正在推进一个步长…', stepOnce); });
  $('transport-finish').addEventListener('click', function () { act('正在运行至结束…', finishRun); });
  $('transport-reset').addEventListener('click', function () { act('正在重置当前实验…', resetRun); });
  for (const button of document.querySelectorAll('[data-speed]')) {
    button.addEventListener('click', function () { act('正在调整倍速…', function () { return setSpeed(Number(button.dataset.speed)); }); });
  }
  $('replay-start').addEventListener('click', function () { act('正在进入合成账本回放…', replayStart); });
  $('replay-step').addEventListener('click', function () { act('回放单步…', function () { return replayStep(1); }); });
  $('replay-exit').addEventListener('click', function () { act('正在退出回放…', replayExit); });
  $('replay-range').addEventListener('change', function () {
    const target = Number($('replay-range').value);
    if (!replayActive()) return;
    act('正在定位回放进度…', function () { return jumpReplay(target); });
  });
  $('preset').addEventListener('change', function () {
    const preset = metadata.presets.find(function (item) { return item.id === $('preset').value; });
    if (!preset) return;
    writeForm(preset.config); markDirty(); message('预设已填入表单，点击「应用参数并重置」生效。');
  });
  $('export-config').addEventListener('click', function () {
    try { downloadBlob(collect(), 'parking-config.json'); message('配置已导出（null 保持 null）。', 'ok'); }
    catch (error) { message(error.message, 'error'); }
  });
  $('import-config').addEventListener('click', function () { $('config-file').click(); });
  $('config-file').addEventListener('change', function () {
    act('正在读取并校验配置…', async function () {
      const file = $('config-file').files[0]; if (!file) return;
      if (file.size > 131072) throw new Error('配置文件超过128KB');
      const raw = JSON.parse(await file.text());
      const result = await api('/api/validate', { config: raw });
      writeForm(result.config); markDirty(); message('配置已导入并校验，点击「应用参数并重置」生效。', 'ok'); $('config-file').value = '';
    });
  });
  $('download').addEventListener('click', function () {
    const format = $('export-format').value;
    applyLink('/api/export?id=' + encodeURIComponent(sessionId) + '&format=' + format);
    message('导出已发起；完整 JSON 含连续运行状态、账本、数据源与 cost_model_version。');
  });
  $('compare').addEventListener('click', function () {
    act('正在重放四种策略与多个种子…', async function () {
      const parts = $('seeds').value.split(',').map(function (item) { return item.trim(); });
      if (parts.some(function (item) { return !/^\d+$/.test(item); })) throw new Error('种子请使用逗号分隔的非负整数');
      const policySet = $('policy-set') ? $('policy-set').value : 'formal';
      const result = await api('/api/compare', { config: collect(), seeds: parts.map(Number), policy_set: policySet });
      renderComparison(result);
      message(policySet === 'legacy'
        ? '历史策略演示对比完成：结果不代表当前研究模型，不得作为 π0/π1/π2 结论引用。'
        : '正式规则对比完成：同一外生车辆流重放，成本为 v2 口径，null 显示未知。', 'ok');
    });
  });
  $('download-comparison').addEventListener('click', function () { downloadBlob(comparison, 'parking-comparison.json'); });
  for (const button of document.querySelectorAll('#compare-metric-tabs button')) {
    button.addEventListener('click', function () { compareMetric = button.dataset.metric; updateCompareMetric(); });
  }
  for (const button of document.querySelectorAll('[data-filter-state]')) {
    button.addEventListener('click', function () {
      const value = Number(button.dataset.filterState);
      const pressed = button.getAttribute('aria-pressed') === 'true';
      for (const other of document.querySelectorAll('[data-filter-state]')) other.setAttribute('aria-pressed', 'false');
      if (pressed) { filterState = null; } else { filterState = value; button.setAttribute('aria-pressed', 'true'); }
      applyFilterClass();
    });
  }
  for (const button of document.querySelectorAll('[data-tab]')) {
    button.addEventListener('click', function () {
      activeTab = button.dataset.tab;
      for (const tab of document.querySelectorAll('[data-tab]')) tab.setAttribute('aria-selected', String(tab.dataset.tab === activeTab));
      for (const panel of document.querySelectorAll('[data-panel]')) panel.hidden = panel.dataset.panel !== activeTab;
      if (activeTab === 'prediction' && state) renderPrediction(state, currentView(state));
    });
  }
  $('bay-detail-close').addEventListener('click', function () { selectedBay = null; $('bay-detail').hidden = true; applySelectionClass(); layoutMatrix(true); if (charts.heatmap) charts.heatmap.setGeometry({ selectedBay: null }); });
  $('heatmap-prev').addEventListener('click', function () { heat.rowOffset = Math.max(0, heat.rowOffset - heat.rows); renderCharts(state, currentView(state)); controls(); });
  $('heatmap-next').addEventListener('click', function () { heat.rowOffset += heat.rows; renderCharts(state, currentView(state)); controls(); });
  const body = document.querySelector('.matrix-body');
  if (body) {
    let timer = null;
    new ResizeObserver(function () { clearTimeout(timer); timer = setTimeout(function () { layoutMatrix(true); }, 160); }).observe(body);
  }
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && selectedBay !== null) { selectedBay = null; $('bay-detail').hidden = true; applySelectionClass(); layoutMatrix(true); }
    if (event.key === ' ' && event.target === document.body) { event.preventDefault(); act('正在切换运行状态…', playPause); }
  });
  window.addEventListener('resize', hideTooltip);
  $('bay-matrix').addEventListener('pointerover', function (event) {
    const dot = event.target.closest ? event.target.closest('.bay-dot') : null;
    if (!dot || !state) return;
    const bay = Number(dot.dataset.bay);
    showTooltip(Object.assign(dotTooltip(bay, state, currentView(state)), { x: event.clientX, y: event.clientY }));
  });
  $('bay-matrix').addEventListener('pointerout', function (event) {
    const dot = event.target.closest ? event.target.closest('.bay-dot') : null;
    if (dot) hideTooltip();
  });
  $('bay-matrix').addEventListener('click', function (event) {
    const dot = event.target.closest ? event.target.closest('.bay-dot') : null;
    if (!dot || !state) return;
    selectBay(Number(dot.dataset.bay));
  });
}
function downloadBlob(payload, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const a = document.createElement('a'); a.href = url; a.download = name; a.click();
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

/* ------------------------------------------------------------ 实时轮询与初始化 */
async function livePoll() {
  if (!sessionId || busy || dirty || replayActive()) return;
  const c = state && state.continuous;
  if (!runningMode(c) || (state && state.finished)) return;
  try {
    const result = await api('/api/advance', { id: sessionId });
    const changed = !state || Math.abs(result.time_min - (state.time_min || 0)) > 1e-9 || (result.events || []).length !== (state.events || []).length;
    if (changed) render(result);
  } catch (error) { message('轮询失败：' + error.message, 'error'); }
}
async function init() {
  metadata = await api('/api/presets');
  makeFields();
  for (const preset of metadata.presets) { const option = document.createElement('option'); option.value = preset.id; option.textContent = preset.name; $('preset').append(option); }
  const policySelect = $('policy-set');
  if (policySelect && metadata.policy_sets) {
    policySelect.replaceChildren();
    for (const key of Object.keys(metadata.policy_sets)) {
      const info = metadata.policy_sets[key];
      const option = document.createElement('option');
      option.value = key;
      option.textContent = info.label + (info.kind === 'legacy' ? '（非当前研究）' : '');
      policySelect.append(option);
    }
    policySelect.value = metadata.default_policy_set || 'formal';
  }
  $('preset').value = 'peaks';
  writeForm(metadata.defaults);
  wire();
  liveTimer = setInterval(livePoll, 1000);
  const created = await api('/api/create', { config: collect(), speed: 60 });
  sessionId = created.id;
  dirty = false;
  render(created);
  message('示范实验已创建：60x 加速运行（1 秒轮询）。暂停后所有视图停止推进。', 'ok');
}
window.__lab = { get sessionId() { return sessionId; }, get state() { return state; } };
init().catch(function (error) {
  message('初始化失败：' + error.message + '（若后端未启动，请运行 python -m apps.parking_lab.workbench serve）', 'error');
  const node = $('version-line'); if (node) node.textContent = '未连接后端';
  controls();
});
