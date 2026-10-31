'use strict';
const $ = id => document.getElementById(id);
let metadata, sessionId = null, state = null, busy = false, liveTimer = null;
let dirty = false, comparison = null;
let nestedLoaded = {};   // 嵌套块（cost）已加载的保留字段与基线值，用于配置往返与来源标记一致性

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
   '到达强度按1分钟分段恒定。模型在入口观察所有到访，包括最终被拒的车辆。'],
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
const MODE_TEXT = { fresh: '新鲜 fresh', stale: '过期 stale', expired: '已过期 expired', unknown: '未知', missing: '缺失' };

function message(text, kind) { $('message').textContent = text; $('message').className = 'message ' + (kind || ''); }
function number(x, digits) { return x === null || x === undefined ? '—' : Number(x).toLocaleString('zh-CN', { maximumFractionDigits: digits === undefined ? 1 : digits, minimumFractionDigits: digits === undefined ? 1 : digits }); }
function percent(x, digits) { return x === null || x === undefined ? '—' : number(x * 100, digits === undefined ? 1 : digits) + '%'; }
function utcShort(text) { return text ? String(text).replace('T', ' ').slice(0, 19) + 'Z' : '—'; }
function clock(minute, c) {
  const config = c || (state && state.config) || {};
  const total = Math.floor((config.start_hour || 0) * 60 + minute), day = Math.floor(total / 1440);
  return (day ? '第' + (day + 1) + '天 ' : '') + String(Math.floor(total / 60) % 24).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
}
async function api(path, payload) {
  const response = await fetch(path, payload === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  let data;
  try { data = await response.json(); } catch (error) { throw new Error('服务返回了无法解析的结果 (' + response.status + ')'); }
  if (!response.ok) throw new Error(data.error || '请求失败 (' + response.status + ')');
  return data;
}

// ---------------------------------------------------------------- config form
function makeField(key, def) {
  if (def !== null && typeof def === 'object' && !Array.isArray(def)) return makeNested(key, def);
  const wrapper = document.createElement('div'); wrapper.className = 'field';
  const label = document.createElement('label'); label.htmlFor = 'field-' + key; label.textContent = LABELS[key] || key;
  let input;
  if (typeof def === 'string') {
    input = document.createElement('select');
    const choices = key === 'policy' ? metadata.policies : key === 'scenario' ? metadata.scenarios : null;
    if (choices) { for (const value of Object.keys(choices)) { const option = document.createElement('option'); option.value = value; option.textContent = choices[value]; input.append(option); } }
    else { input = document.createElement('input'); input.type = 'text'; }
  } else {
    input = document.createElement('input'); input.type = 'number'; input.min = 0; input.step = Number.isInteger(def) ? '1' : 'any'; input.required = true;
  }
  input.id = 'field-' + key; input.name = key;
  input.addEventListener('change', markDirty); input.addEventListener('input', markDirty);
  wrapper.append(label, input); return wrapper;
}
function makeNested(key, def) {
  const details = document.createElement('details'); details.open = true; details.className = 'nested';
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
    if (sub === 'depreciation_life_years' && input.type === 'number') { input.min = '0.0001'; input.step = 'any'; }  // 0 会被 Config.parse 拒绝
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
  const placed = new Set();
  for (const [title, keys, help] of SECTIONS) {
    const details = document.createElement('details'); details.open = title !== '成本参数（无来源一律留空 = 未知）';
    const summary = document.createElement('summary'); summary.textContent = title; details.append(summary);
    for (const key of keys) { if (Object.prototype.hasOwnProperty.call(metadata.defaults, key)) { placed.add(key); details.append(makeField(key, metadata.defaults[key])); } }
    const paragraph = document.createElement('p'); paragraph.className = 'field-help'; paragraph.textContent = help; details.append(paragraph);
    container.append(details);
  }
  const rest = Object.keys(metadata.defaults).filter(key => !placed.has(key));
  if (rest.length) {
    const details = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = '其他参数'; details.append(summary);
    for (const key of rest) details.append(makeField(key, metadata.defaults[key]));
    container.append(details);
  }
}
function isPlainObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function writeForm(config) {
  // 导入/预设/服务端配置按“覆盖默认值”处理：缺失字段保留默认，不被清空成空串或 0。
  const merged = Object.assign({}, metadata.defaults, config || {});
  for (const key of Object.keys(metadata.defaults)) {
    const def = metadata.defaults[key];
    if (isPlainObject(def)) {
      writeNested(key, Object.assign({}, def, isPlainObject(config && config[key]) ? config[key] : {}));
    } else {
      const input = $('field-' + key);
      if (!input) continue;
      const value = merged[key];
      input.value = value === null || value === undefined ? '' : String(value);
    }
  }
  updateProvenanceBanner();
}
function writeNested(key, values) {
  // sources/metadata/provenance 没有输入框，但必须原样留住，供 collectNested 回填。
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
  const def = metadata.defaults[key] || {}, out = {};
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
  return Object.keys(current).filter(sub => !Object.is(current[sub], loaded.baseline[sub]));
}
function filterPreservedBlock(name, block, changed, values) {
  const out = {};
  if (!isPlainObject(block)) return out;
  for (const param of Object.keys(block)) {
    if (changed.indexOf(param) >= 0) continue;   // 数值已改：原来源标记不再匹配该参数
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
  // 来源标记必须与当前参数一致：只要改过任何参数，旧的“合成示例/官方已核实”就不再成立。
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
      config[key] = input.tagName === 'SELECT' ? input.value : (raw === '' ? null : Number(raw));
    }
  }
  return config;
}
function updateProvenanceBanner() {
  const banner = $('provenance-banner');
  if (!banner || !metadata) return;
  const cost = collectNested('cost');
  const filled = Object.keys(cost).filter(key => !COST_PRESERVE.has(key) && typeof cost[key] === 'number');  // 只有真正的数值参数才算“已填”
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
function markDirty() { dirty = true; $('dirty-note').textContent = '参数已修改，应用后生效。正在观看的运行保留原配置。'; updateProvenanceBanner(); controls(); }

// ---------------------------------------------------------------- controls
function runningMode(c) { return !!c && !c.paused && !c.replay.active && (c.mode === 'realtime' || c.mode === 'accelerated'); }
function controls() {
  const c = state && state.continuous, replay = !!(c && c.replay && c.replay.active), finished = !!(state && state.finished);
  const disabled = busy || !sessionId;
  $('mode-realtime').disabled = disabled || dirty || replay || (c && c.mode === 'realtime' && !c.paused);
  $('mode-accelerated').disabled = disabled || dirty || replay || (c && c.mode === 'accelerated');
  $('speed').disabled = disabled || replay;
  $('pause').disabled = disabled || replay || !c || c.paused || finished;
  $('resume').disabled = disabled || replay || !c || !c.paused;
  $('step').disabled = disabled || dirty || replay || finished;
  $('finish').disabled = disabled || dirty || replay || finished;
  $('reset').disabled = disabled;
  $('replay-synthetic').disabled = disabled || dirty;
  $('replay-step').disabled = disabled || !replay;
  $('replay-exit').disabled = disabled || !replay;
  $('apply').disabled = busy;
  $('compare').disabled = busy;
  $('download').disabled = disabled;
  $('download-comparison').disabled = busy || !comparison;
  $('preset').disabled = busy;
  $('run-indicator').classList.toggle('running', runningMode(c));
  const modeText = c ? c.mode_label : '尚未创建';
  $('run-status').textContent = busy ? '计算中…' : (finished ? '已完成' : modeText);
  $('mode-badge').textContent = c ? c.mode_label : '—';
  $('mode-badge').className = 'badge ' + (c ? c.mode : '');
  $('runtime-label').textContent = c ? c.mode_label : '—';
  document.body.classList.toggle('busy', busy);
}
function act(label, fn) {
  if (busy) return;
  busy = true; controls(); message(label, 'pending');
  Promise.resolve().then(fn).catch(error => message(error.message, 'error')).finally(() => { busy = false; controls(); });
}

// ---------------------------------------------------------------- rendering
function render(s) {
  state = s;
  const m = s.metrics || {}, f = s.forecast || {}, c = s.config || {};
  updateProvenanceBanner();
  $('clock').textContent = clock(s.time_min, c);
  $('progress-fill').style.width = (100 * s.time_min / Math.max(s.horizon_min, 1)) + '%';
  $('stat-occupancy').textContent = (m.occupancy === undefined ? '—' : m.occupancy) + ' / ' + c.n_spaces;
  $('stat-utilization').textContent = '时间平均占用率 ' + percent(m.mean_occupancy_rate);
  $('stat-arrivals').textContent = (m.arrivals === undefined ? '—' : m.arrivals) + ' / ' + (m.rejected === undefined ? '—' : m.rejected);
  $('stat-rejections').textContent = '被拒：油车 ' + (m.rejected_ice === undefined ? '—' : m.rejected_ice) + ' · 电车 ' + (m.rejected_ev === undefined ? '—' : m.rejected_ev);
  $('stat-energy').textContent = number(m.energy_delivered_kwh);
  $('stat-power').textContent = '当前 ' + number(m.current_power_kw) + ' / 限额 ' + number(c.feeder_kw) + ' kW';
  $('lot-summary').textContent = c.charging_bays + ' 个充电车位 · ' + c.chargers + ' 个带枪位 · 当前 ' + (m.charging_now === undefined ? '—' : m.charging_now) + ' 辆充电';
  $('policy-label').textContent = s.policy_name || '';
  renderRuntime(s.continuous);
  renderCost(s);
  const grid = $('bay-grid'); grid.replaceChildren();
  for (const bay of s.bays || []) {
    const v = bay.vehicle, item = document.createElement('div');
    item.className = 'bay ' + (bay.equipped ? 'equipped ' : '') + (bay.charging_bay && !bay.equipped ? 'designated ' : '') + (v ? 'occupied ' + (bay.power_kw > 0 ? 'charging' : v.is_ev ? 'ev' : 'ice') : '');
    const title = document.createElement('strong'); title.textContent = (bay.equipped ? '⚡ ' : '') + String(bay.bay + 1).padStart(2, '0');
    const detail = document.createElement('small'); detail.textContent = !v ? '空闲' : (v.is_ev ? '电车' : '油车') + (bay.power_kw > 0 ? ' 充电' : v.completed ? ' 已满' : '');
    item.append(title, detail);
    item.title = '车位' + (bay.bay + 1) + '：' + (bay.equipped ? '带枪' : bay.charging_bay ? '充电预留位（无枪）' : '普通位') + (v ? '\n车辆' + (v.vehicle_id + 1) + '，预计' + clock(v.departure_min, c) + '离场\n需求' + number(v.energy_kwh) + ' / 已交付' + number(v.delivered_kwh) + ' kWh' : '');
    grid.append(item);
  }
  if (!(s.bays || []).length) { const empty = document.createElement('div'); empty.className = 'empty-state'; empty.textContent = '总车位为0：所有到达将被拒绝，在线学习仍继续。'; grid.append(empty); }
  $('bay-note').textContent = s.bays_total > s.bays_shown ? '显示前' + s.bays_shown + '个车位；指标及导出包含全部' + s.bays_total + '个车位。' : '带枪位边框为实线，无枪充电预留位为虚线。充满后车辆仍停留。';
  $('completed').textContent = (m.charge_completed === undefined ? '—' : m.charge_completed) + ' / ' + (m.charge_requests === undefined ? '—' : m.charge_requests);
  $('departed-gap').textContent = number(m.departed_shortfall_kwh) + ' kWh';
  $('pending-energy').textContent = number(m.pending_energy_kwh) + ' kWh';
  $('p-ev').textContent = number(100 * f.p_ev) + '%'; $('p-ev-fill').style.width = (100 * (f.p_ev || 0)) + '%';
  $('interval-label').textContent = number(f.interval_level * 100, 0) + '% 到达等待时间预测区间';
  $('wait-interval').textContent = number(f.wait_lower_min) + ' – ' + number(f.wait_upper_min) + ' 分钟';
  $('observed').textContent = f.observed_arrivals + ' 辆'; $('rate').textContent = number(f.arrival_rate_hour) + ' 辆/小时';
  $('need-forecast').textContent = number(f.expected_charge_arrivals) + ' 辆 / ' + f.window_min + '分钟';
  $('reserve').textContent = s.reserve + ' 个'; $('cold-start').textContent = f.cold_start ? '冷启动 / <20辆' : '持续更新';
  $('brier').textContent = number(m.brier, 3); $('coverage').textContent = percent(m.interval_coverage);
  $('width').textContent = number(m.interval_width_min) + ' 分钟'; $('score-n').textContent = m.prediction_samples;
  $('score-description').textContent = '按上一到达时刻发布的预测评分。' + (s.finished ? '最后一个尚未观察到下一辆的预测按右删失保留，不计分。' : '当前时刻预测已计入无车到达期间的暴露时间。');
  drawChart('occupancy-chart', s.history || [], [['occupancy', '#217461'], ['charging', '#c08b2e']], Math.max(c.n_spaces || 1, 1), s.horizon_min, false);
  drawChart('learning-chart', s.history || [], [['p_ev', '#527baf']], 1, s.horizon_min, true);
  renderEvents(s);
  controls();
}
function renderEvents(s) {
  const body = $('event-body'); body.replaceChildren();
  const rows = (s.ledger_tail && s.ledger_tail.length ? s.ledger_tail : s.events || []).slice().reverse();
  const names = { arrival: '到达并停车', rejected: '停车被拒', charged: '充电完成', departure: '离场' };
  for (const event of rows) {
    const row = document.createElement('tr');
    const info = event.kind === 'arrival' || event.kind === 'rejected' ? (event.is_ev ? '电车' : '油车') + (event.needs_charge ? ' · 有充电需求' : ' · 仅停车') : event.delivered_kwh !== undefined ? '交付 ' + number(event.delivered_kwh) + ' kWh' : '';
    const cells = [event.seq === undefined ? '—' : '#' + event.seq, clock(event.time_min, s.config), '#' + (event.vehicle_id + 1), names[event.kind] || event.kind, event.bay === null || event.bay === undefined ? '—' : event.bay + 1, info];
    for (const text of cells) { const cell = document.createElement('td'); cell.textContent = text; row.append(cell); }
    body.append(row);
  }
  if (!rows.length) { const row = document.createElement('tr'), cell = document.createElement('td'); cell.colSpan = 6; cell.textContent = '尚无已入账事件。点击实时/加速推进，或单步。'; row.append(cell); body.append(row); }
}
function renderRuntime(c) {
  if (!c) return;
  const ledger = c.ledger || {}, replay = c.replay || {};
  const speed = c.effective_speed || c.speed;
  $('run-mode').textContent = c.mode_label + (c.paused ? '（已暂停）' : '');
  $('run-speed').textContent = (c.mode === 'realtime' ? '有效 1x（realtime 固定，所选倍速 ' + c.speed + 'x 不生效）' : '有效 ' + speed + 'x') + ' · ' + c.speed_note;
  $('run-time').textContent = number(c.time_min, 1) + ' / ' + number(c.horizon_min, 0) + ' 分钟';
  $('run-elapsed').textContent = number(c.real_elapsed_s, 1) + ' 秒';
  $('run-ticks').textContent = c.ticks + ' 次';
  $('run-events').textContent = c.events_total + ' 事件 / ' + ledger.entries + ' 已入账';
  $('run-ledger').textContent = '水位 ' + ledger.watermark + ' · seq ' + (ledger.first_seq || '—') + '–' + (ledger.last_seq || '—');
  $('run-clock-source').textContent = c.clock_source === 'injected' ? '注入时钟（测试）' : '后端单调时钟';
  const windowInfo = c.window || {};
  $('run-window').textContent = windowInfo.finite
    ? ('有限窗口：仿真时长 ' + number(c.horizon_min, 0) + ' 分钟到期后 tick 自动停止（finished），不是无限持续运行')
    : '—';
  const expected = c.time_min * 60 / (speed || 1);
  $('run-lag').textContent = '实时 ' + number(c.real_elapsed_s, 1) + ' 秒 / 期望 ' + number(expected, 1) + ' 秒（偏差 ' + number(c.real_elapsed_s - expected, 1) + ' 秒）';
  $('run-replay').textContent = replay.active ? ('回放 replay · ' + replay.source + ' · 游标 ' + replay.cursor + '/' + replay.total) : '未在回放';
  $('run-guard').textContent = ledger.double_accounting_guard || '—';
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
  $('stat-cost').textContent = total === null || total === undefined ? '无法完整计算' : number(total, 0);
  $('stat-cost-note').textContent = complete ? '口径 ' + version + ' · 完整' : '口径 ' + version + ' · 缺 ' + missing.length + ' 个参数（未知／待校准）';
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
  const show = value => value === null || value === undefined ? '未知／待校准' : (typeof value === 'object' ? JSON.stringify(value) : String(value));
  const flatten = group => group ? Object.keys(group).map(key => key + '=' + show(group[key])).join('；') : '不可用／未知';
  // 实时口径（只累计到 sim.time）与“预计最终值”必须分开显示：预计值不得当成已发生。
  const projected = (block && block.projected) || null;
  const projectedText = projected && Object.keys(projected).length
    ? ('占桩归因 ' + flatten(projected.occupancy_minutes_by_reason) + ' · 收费/转移 ' + flatten(projected.transfers))
    : '不可用';
  const relocation = block ? (block.relocation_count === undefined ? '—' : block.relocation_count) + ' 次（无普通位被阻止 ' + (block.relocation_blocked === undefined ? '—' : block.relocation_blocked) + ' 次）' : '—';
  $('cost-notes').textContent = '占桩影响归因（实时口径：只累计到当前 sim.time，不进 total）：' + flatten(attribution)
    + ' · 收费/转移支付（实时，不进 total）：' + flatten(transfers)
    + ' · 预计最终值（单列，不是已发生）：' + projectedText
    + ' · 挪车 ' + relocation;
}
function drawChart(id, history, series, maxY, horizon, isPercent) {
  const svg = $(id), left = 40, right = 625, top = 12, bottom = 153;
  const x = t => left + t / Math.max(horizon, 1) * (right - left);
  const y = v => bottom - v / maxY * (bottom - top);
  let html = '';
  for (let i = 0; i <= 4; i++) { const value = maxY * i / 4, yy = y(value); html += '<line x1="' + left + '" x2="' + right + '" y1="' + yy + '" y2="' + yy + '" stroke="#e9efeb"/><text x="31" y="' + (yy + 4) + '" text-anchor="end" fill="#83918a" font-size="10">' + (isPercent ? Math.round(value * 100) + '%' : number(value, 0)) + '</text>'; }
  for (let i = 0; i <= 4; i++) html += '<text x="' + x(horizon * i / 4) + '" y="177" text-anchor="middle" fill="#83918a" font-size="10">' + clock(horizon * i / 4) + '</text>';
  for (const entry of series) {
    const points = history.map(row => x(row.time_min).toFixed(2) + ',' + y(row[entry[0]]).toFixed(2)).join(' ');
    html += '<polyline points="' + points + '" fill="none" stroke="' + entry[1] + '" stroke-width="2.2" stroke-linejoin="round"/>';
  }
  svg.innerHTML = html;
}

// ---------------------------------------------------------------- live clock
async function livePoll() {
  if (!sessionId || busy || dirty) return;
  const c = state && state.continuous;
  if (!runningMode(c) || (state && state.finished)) return;
  try { render(await api('/api/advance', { id: sessionId })); }
  catch (error) { message(error.message, 'error'); }
}

// ---------------------------------------------------------------- actions
async function apply() {
  const config = collect();
  const result = sessionId ? await api('/api/reset', { id: sessionId, config: config }) : await api('/api/create', { config: config, speed: Number($('speed').value) });
  sessionId = result.id; dirty = false; comparison = null;
  $('compare-results').hidden = true; $('compare-empty').hidden = false;
  $('dirty-note').textContent = '参数已应用。可实时推进、单步，或运行至结束。';
  render(result); message('实验已创建。后端时钟由服务器推进，界面每秒轮询一次。');
}
function wire() {
  $('toggle-settings').addEventListener('click', () => {
    const open = document.querySelector('.sidebar').classList.toggle('settings-open');
    $('toggle-settings').textContent = open ? '收起参数设置' : '展开参数设置';
    $('toggle-settings').setAttribute('aria-expanded', String(open));
  });
  $('config-form').addEventListener('submit', event => event.preventDefault());
  $('apply').addEventListener('click', () => act('正在应用参数…', apply));
  $('reset').addEventListener('click', () => act('正在重置当前实验…', async () => { render(await api('/api/reset', { id: sessionId })); message('已按当前运行配置重置；随机种子不变。'); }));
  $('mode-realtime').addEventListener('click', () => act('切换到实时模式…', async () => { render(await api('/api/mode', { id: sessionId, mode: 'realtime' })); message('实时 1x：1 仿真分钟 = 60 实时秒。'); }));
  $('mode-accelerated').addEventListener('click', () => act('切换到加速模式…', async () => { render(await api('/api/mode', { id: sessionId, mode: 'accelerated', speed: Number($('speed').value) })); message('加速模式已启用。'); }));
  $('speed').addEventListener('change', () => act('正在调整倍速…', async () => { render(await api('/api/speed', { id: sessionId, speed: Number($('speed').value) })); message('倍速已调整。'); }));
  $('pause').addEventListener('click', () => act('正在暂停…', async () => { render(await api('/api/pause', { id: sessionId })); message('已暂停：时钟不推进，已入账水位不变。'); }));
  $('resume').addEventListener('click', () => act('正在恢复…', async () => { render(await api('/api/resume', { id: sessionId })); message('已恢复：从当前时刻继续，不补推进暂停区间。'); }));
  $('step').addEventListener('click', () => act('正在推进…', async () => { render(await api('/api/step', { id: sessionId, minutes: Number($('step-minutes').value) })); message(state.finished ? '仿真已完成。' : '已手动推进一个步长。'); }));
  $('finish').addEventListener('click', () => act('正在运行至结束…', async () => { render(await api('/api/run', { id: sessionId })); message('仿真已完成；仍在场的请求作为待交付单列。'); }));
  $('replay-synthetic').addEventListener('click', () => act('正在进入合成账本回放…', async () => { render(await api('/api/replay/start', { id: sessionId, source: 'synthetic' })); message('回放 replay：只按账本顺序暴露已入账事件，不再推进仿真。'); }));
  $('replay-step').addEventListener('click', () => act('回放单步…', async () => {
    const result = await api('/api/replay/step', { id: sessionId, count: 1 });
    render(result);
    const step = result.replay_step || {};
    message('回放 replay：游标 ' + (step.cursor === undefined ? '—' : step.cursor) + '/' + (step.total === undefined ? '—' : step.total) + (step.batches ? '（批次 ' + step.batches.map(batch => utcShort(batch.slot_utc)).join('、') + '）' : step.events ? '（事件 ' + step.events.length + ' 条）' : ''));
  }));
  $('replay-exit').addEventListener('click', () => act('正在退出回放…', async () => { render(await api('/api/replay/exit', { id: sessionId })); message('已退出回放，回到实时/加速模式。'); }));
  $('preset').addEventListener('change', () => { const preset = metadata.presets.find(item => item.id === $('preset').value); writeForm(preset.config); markDirty(); message('预设已填入表单，点击“应用参数并重置”生效。'); });
  $('compare').addEventListener('click', () => act('正在重放四种策略与多个种子…', async () => {
    const parts = $('seeds').value.split(',').map(item => item.trim());
    if (parts.some(item => !/^\d+$/.test(item))) throw new Error('种子请使用逗号分隔的非负整数');
    const result = await api('/api/compare', { config: collect(), seeds: parts.map(Number) });
    renderComparison(result); message('策略对比完成；成本为 v2 口径，null 显示未知。');
  }));
  $('download-comparison').addEventListener('click', () => downloadBlob(comparison, 'parking-comparison.json'));
  $('export-config').addEventListener('click', () => { try { downloadBlob(collect(), 'parking-config.json'); message('配置已导出（null 保持 null）。'); } catch (error) { message(error.message, 'error'); } });
  $('import-config').addEventListener('click', () => $('config-file').click());
  $('config-file').addEventListener('change', () => act('正在读取并校验配置…', async () => {
    const file = $('config-file').files[0]; if (!file) return;
    if (file.size > 131072) throw new Error('配置文件超过128KB');
    const raw = JSON.parse(await file.text());
    const result = await api('/api/validate', { config: raw });
    writeForm(result.config); markDirty(); message('配置已导入并校验，点击应用生效。'); $('config-file').value = '';
  }));
  $('download').addEventListener('click', () => {
    const format = $('export-format').value;
    const link = document.createElement('a');
    link.href = '/api/export?id=' + encodeURIComponent(sessionId) + '&format=' + format;
    link.download = 'parking-result'; link.click();
    message('导出已发起；完整 JSON 含连续运行状态、账本、数据源与 cost_model_version。');
  });
}
function downloadBlob(payload, name) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function renderComparison(result) {
  comparison = result; $('compare-empty').hidden = true; $('compare-results').hidden = false;
  const c = result.config;
  $('compare-description').textContent = c.n_spaces + '车位 / ' + c.chargers + '枪 · ' + c.duration_hours + '小时 · ' + result.seeds.length + '个独立种子 · 每种子车流一致';
  const body = $('compare-body'); body.replaceChildren(); const bars = $('cost-bars'); bars.replaceChildren();
  const costs = result.rows.map(row => row.total_cost).filter(value => value !== null && value !== undefined);
  const maxCost = Math.max(1, ...costs);
  for (const row of result.rows) {
    const tr = document.createElement('tr');
    const uncertainty = (key, pct) => pct ? percent(row[key]) + ' ± ' + percent(row[key + '_std']) : number(row[key], 1) + ' ± ' + number(row[key + '_std'], 1);
    const costText = row.total_cost === null || row.total_cost === undefined ? '未知／待校准' : 'TWD ' + number(row.total_cost, 0);
    for (const text of [row.name, uncertainty('rejection_rate', true), uncertainty('charge_completion_rate_all', true), uncertainty('energy_delivered_kwh'), costText, number(row.paired_cost_delta_vs_open, 1)]) {
      const td = document.createElement('td'); td.textContent = text; tr.append(td);
    }
    body.append(tr);
    const item = document.createElement('div'), head = document.createElement('div'), label = document.createElement('span'), value = document.createElement('strong'), track = document.createElement('div'), fill = document.createElement('span');
    head.className = 'cost-bar-head'; label.textContent = row.name;
    value.textContent = row.total_cost === null || row.total_cost === undefined ? '未知' : 'TWD ' + number(row.total_cost, 0);
    head.append(label, value); track.className = 'cost-bar-track';
    fill.style.width = (100 * ((row.total_cost || 0) / maxCost)) + '%'; track.append(fill); item.append(head, track); bars.append(item);
  }
}
async function init() {
  metadata = await api('/api/presets');
  makeFields();
  for (const preset of metadata.presets) { const option = document.createElement('option'); option.value = preset.id; option.textContent = preset.name; $('preset').append(option); }
  $('preset').value = 'peaks';
  writeForm(metadata.defaults);
  wire();
  liveTimer = setInterval(livePoll, 1000);
  await act('正在创建示范实验…', apply);
}
init().catch(error => { message('初始化失败：' + error.message, 'error'); controls(); });
