/* T64 三方案工作台前端 —— 原生 JS，无框架、无外部依赖。
   规则：所有数值来自当前响应；无数据显示“尚未运行”；缺参显示“无法完整计算”，不按 0 计。 */
'use strict';
(function () {
  var API = '/api/t64', CONTRACT = 'parking_lab_t64/1', DASH = '—', NOCOST = '无法完整计算', TL_LIMIT = 200;
  var COST_ROWS = [
    ['设施（固定桩）', ['facility_fixed', 'facility', 'facility_cost']],
    ['移动投资', ['facility_mobile', 'mobile_investment', 'mobile_capital']],
    ['停车被拒', ['rejection_I', 'parking_denied', 'denied_parking']],
    ['充电被拒（E0）', ['rejection_E0', 'charging_denied']],
    ['充电被拒（E1）', ['rejection_E1', 'charging_denied_e1']],
    ['未满足电量', ['unmet_energy', 'unmet_energy_cost']],
    ['资源成本', ['resource_energy', 'resource_cost', 'opportunity_cost']],
    ['移动运行', ['mobile_active', 'mobile_operation', 'mobile_operating']],
    ['移动能耗', ['mobile_energy']],
    ['换位', ['moves', 'repositioning', 'relocation']]
  ];
  var E1_LABEL = { delivered_kwh: '交付 kWh', unmet_kwh: '未满足 kWh', unmet_energy_kwh: '未满足 kWh', required_kwh: '需求 kWh',
    demand_kwh: '需求 kWh', vehicles_served: '服务车数', delivered_vehicles: '交付车数', vehicles_unmet: '未满足车数',
    unmet_ratio: '未满足比例', served_ratio: '满足比例', count: '记录数' };
  function $(id) { return document.getElementById(id); }
  function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined && text !== null) n.textContent = String(text); return n; }
  function td(text, cls) { return el('td', cls || null, (text === undefined || text === null || text === '') ? DASH : text); }
  function row(cells) { var tr = el('tr'); cells.forEach(function (c) { tr.appendChild(c); }); return tr; }
  function emptyRow(body, cols, msg) { var c = el('td', 'table-empty', msg); c.colSpan = cols; body.appendChild(row([c])); }
  function txt(node, v) { if (node) node.textContent = (v === undefined || v === null || v === '') ? DASH : String(v); }
  function show(node, on) { if (node) node.hidden = !on; }
  function clear(node) { while (node && node.firstChild) node.removeChild(node.firstChild); return node; }
  function notice(node, kind, msg) {
    if (!node) return;
    if (!msg) { node.hidden = true; node.textContent = ''; return; }
    node.className = 'notice' + (kind ? ' ' + kind : ''); node.textContent = msg; node.hidden = false;
  }
  function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function sval(v) { if (v === null || v === undefined) return ''; if (Array.isArray(v)) return v.map(sval).filter(Boolean).join('/'); if (isObj(v)) return ''; return String(v); }
  function numOf(v) { if (v === null || v === undefined || v === '') return null; var n = Number(v); return Number.isFinite(n) ? n : null; }
  function asArray(v) { if (v === undefined || v === null) return []; return Array.isArray(v) ? v : [v]; }
  function norm(k) { return String(k).toLowerCase().replace(/[\s_\-]/g, ''); }
  function findEntry(obj, names) {
    if (!isObj(obj)) return { rec: undefined, key: '' };
    var keys = Object.keys(obj), i, j;
    for (i = 0; i < names.length; i += 1) for (j = 0; j < keys.length; j += 1) if (keys[j] === names[i]) return { rec: obj[keys[j]], key: keys[j] };
    for (i = 0; i < names.length; i += 1) {
      var want = norm(names[i]);
      for (j = 0; j < keys.length; j += 1) if (norm(keys[j]) === want) return { rec: obj[keys[j]], key: keys[j] };
    }
    return { rec: undefined, key: '' };
  }
  function getKey(obj, names) { return findEntry(obj, names).rec; }
  function dig(root, names, maxDepth) {
    var want = names.map(norm), depth = maxDepth === undefined ? 3 : maxDepth, seen = [], queue = [[root, 0]];
    while (queue.length) {
      var cur = queue.shift(), obj = cur[0], d = cur[1];
      if (!isObj(obj) || seen.indexOf(obj) >= 0 || d > depth) continue;
      seen.push(obj);
      var keys = Object.keys(obj), i;
      for (i = 0; i < keys.length; i += 1) if (want.indexOf(norm(keys[i])) >= 0) return obj[keys[i]];
      for (i = 0; i < keys.length; i += 1) {
        var v = obj[keys[i]];
        if (isObj(v) || (Array.isArray(v) && v.length && isObj(v[0]))) queue.push([v, d + 1]);
      }
    }
    return undefined;
  }
  function unwrap(v) { if (isObj(v)) { var w = getKey(v, ['value', 'cost', 'amount', 'total']); return w === undefined ? null : w; } return v; }
  function fmt(v, digits) {
    if (v === null || v === undefined || v === '') return DASH;
    var n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    if (Number.isInteger(n) && Math.abs(n) < 1e12) return String(n);
    var d = digits === undefined ? 2 : digits;
    return n.toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function money(v) { var u = unwrap(v); if (u === null || u === undefined || u === '') return NOCOST; var n = Number(u); return Number.isFinite(n) ? fmt(n, 2) : NOCOST; }
  function fmtVal(v) {
    if (v === null || v === undefined || v === '') return DASH;
    if (Array.isArray(v)) return v.length ? v.map(fmtVal).join(', ') : DASH;
    if (isObj(v)) { var s = JSON.stringify(v); return s.length > 140 ? s.slice(0, 137) + '…' : s; }
    return fmt(v);
  }
  function appendFact(host, key, value, cls) { var r = el('div', 'fact'); r.appendChild(el('dt', null, key)); r.appendChild(el('dd', cls || null, value)); host.appendChild(r); return r; }
  function errText(res) { if (!res) return '未知错误'; var msg = res.error; if (isObj(msg)) msg = JSON.stringify(msg); return String(msg || '请求失败') + (res.status ? '（HTTP ' + res.status + '）' : ''); }
  /* 请求层：超时 / 非 JSON / HTTP 错误统一转成 {ok,status,error}，不抛异常 */
  function api(path, opts) {
    var o = opts || {}, ctl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, o.timeout || 45000);
    var init = { method: o.method || 'GET', cache: 'no-store' };
    if (ctl) init.signal = ctl.signal;
    if (o.body !== undefined && o.body !== null) { init.headers = { 'Content-Type': 'application/json' }; init.body = JSON.stringify(o.body); }
    return fetch(path, init).then(function (res) {
      return res.text().then(function (text) {
        var data = null, parseErr = null;
        if (text) { try { data = JSON.parse(text); } catch (e) { parseErr = e; } }
        if (!res.ok) {
          var raw = getKey(data, ['error', 'detail', 'message', 'reason']);
          var msg = typeof raw === 'string' ? raw : (raw ? JSON.stringify(raw).slice(0, 300) : '');
          if (!msg && parseErr) msg = text.slice(0, 200);
          return { ok: false, status: res.status, data: data, error: msg || ('接口返回 ' + res.status) };
        }
        if (parseErr) return { ok: false, status: res.status, data: null, error: '响应不是合法 JSON：' + text.slice(0, 160) };
        return { ok: true, status: res.status, data: data };
      });
    }).catch(function (e) {
      var aborted = e && e.name === 'AbortError';
      return { ok: false, status: 0, data: null, error: aborted ? ('请求超时（' + Math.round((o.timeout || 45000) / 1000) + 's）') : ('网络错误：' + ((e && e.message) || e)) };
    }).then(function (r) { clearTimeout(timer); return r; });
  }
  var state = { health: null, healthErr: '', streams: [], stream: null, limits: { n: null, m: null }, mobile: null, costs: null,
    scheme: 'S1', run: null, runId: '', compare: null, compareId: '', search: null, searchId: '', mathVersion: '', chartCompare: [], chartSearch: [], lastDecl: {}, crossAuto: false };
  /* ---------------------------------------------------------- 健康 / 版本标签 */
  function setMixing(msg) { notice($('mixingWarn'), 'err', msg); }
  function loadHealth() {
    var pill = $('pillHealth');
    pill.className = 'chip health checking';
    pill.textContent = '健康检查中…';
    return api(API + '/health', { timeout: 12000 }).then(function (res) {
      if (!res.ok) {
        state.health = null; state.healthErr = errText(res);
        pill.className = 'chip health bad'; pill.textContent = '后端不可达';
        setMixing('后端健康检查失败：' + state.healthErr + '。接口可能尚未实现；本页不用静态示例数字代替真实响应。');
        renderMobile(state.mobile); renderCosts(state.costs);
        return false;
      }
      state.health = isObj(res.data) ? res.data : {}; state.healthErr = ''; setMixing('');
      applyHealth();
      return true;
    });
  }
  function applyHealth() {
    var h = state.health || {}, pill = $('pillHealth');
    var st = String(sval(getKey(h, ['status', 'state', 'health'])) || '').toLowerCase(), okFlag = getKey(h, ['ok']);
    var good = st === 'ok' || st === 'healthy' || st === 'ready' || st === 'up' || okFlag === true;
    var bad = st === 'error' || st === 'degraded' || st === 'down' || st === 'failed' || okFlag === false;
    pill.className = 'chip health ' + (good ? 'ok' : (bad ? 'bad' : 'checking'));
    pill.textContent = '后端 ' + (st || '已响应');
    state.mathVersion = sval(dig(h, ['math_version', 'math_versions', 'math_model_version']));
    txt($('pillContract'), '契约 ' + (sval(dig(h, ['contract_version', 'contract'])) || DASH));
    txt($('pillEngine'), '引擎 ' + (sval(dig(h, ['engine_version', 'engine'])) || DASH));
    txt($('pillMath'), '数学 ' + (state.mathVersion || '未知'));
    updateModePill();
    var limits = dig(h, ['limits', 'bounds', 'domain']);
    var n1 = numOf(getKey(limits, ['n_max', 'max_n', 'max_slots'])), m1 = numOf(getKey(limits, ['m_max', 'max_m', 'max_mobile']));
    state.limits.n = n1 !== null ? n1 : numOf(dig(h, ['n_max', 'max_n'], 2));
    state.limits.m = m1 !== null ? m1 : numOf(dig(h, ['m_max', 'max_m'], 2));
    state.mobile = dig(h, ['mobile_defaults', 'mobile_params', 'mobile_device_defaults', 'device_defaults']);
    state.costs = dig(h, ['cost_defaults', 'cost_parameters', 'cost_params', 'costs']);
    renderMobile(state.mobile); renderCosts(state.costs); updateLimits();
    if (!state.crossAuto) { state.crossAuto = true; loadCrossSite(); }
  }
  function updateModePill() {
    var mode = state.stream ? sval(getKey(state.stream, ['mode', 'data_mode'])) : '';
    txt($('pillMode'), '数据模式 ' + (mode || '未选流'));
  }
  /* ---------------------------------------------------------- 默认参数（来源/status） */
  function renderMobile(src) {
    var host = clear($('mobileFacts')), note = $('mobileNote');
    if (!isObj(src) || !Object.keys(src).length) {
      appendFact(host, '状态', state.health ? '后端未返回移动设备默认参数' : '等待 /api/t64/health', 'muted');
      note.textContent = 'S3 的移动设备参数以后端 /api/t64/health 或 /api/t64/validate 返回的默认值为准；本页不硬编码假默认。';
      return;
    }
    Object.keys(src).slice(0, 24).forEach(function (k) { appendFact(host, k, fmtVal(src[k])); });
    note.textContent = '默认值来自后端响应；未列出的参数以 validate 返回为准。';
  }
  function normalizeRecords(src) {
    var out = [];
    function push(key, rec) {
      if (isObj(rec)) out.push({ key: key, value: unwrap(rec), source: sval(getKey(rec, ['source', 'source_class', 'source_ids', 'from'])) || sval(getKey(rec, ['sources'])), status: sval(getKey(rec, ['status', 'decision', 'provenance', 'is_scenario', 'kind'])) });
      else out.push({ key: key, value: rec, source: '', status: '' });
    }
    if (Array.isArray(src)) src.forEach(function (rec) { if (isObj(rec)) push(sval(getKey(rec, ['parameter_id', 'id', 'name', 'key'])) || '?', rec); });
    else if (isObj(src)) Object.keys(src).forEach(function (k) { push(k, src[k]); });
    return out;
  }
  function renderCosts(src) {
    var body = clear($('costBody')), note = $('costNote'), recs = normalizeRecords(src);
    if (!recs.length) {
      emptyRow(body, 4, state.health ? '后端未返回成本参数' : '等待 /api/t64/health');
      note.textContent = '无成本参数记录：结果里缺失的分项显示“无法完整计算”，不按 0 计。';
      return;
    }
    recs.slice(0, 80).forEach(function (r) {
      var v = money(r.value), s = el('span', 'chip', r.status || (r.value === null ? 'missing' : DASH)), sc = el('td');
      sc.appendChild(s);
      body.appendChild(row([td(r.key), td(v, v === NOCOST ? 'num missing' : 'num'), td(r.source || DASH), sc]));
    });
    note.textContent = 'source/status 原样取自后端；status 缺失时不推断。';
  }
  /* ---------------------------------------------------------- 冻结车辆流 */
  function streamField(s, names) { return getKey(s, names); }
  function extractStreams(d) {
    var arr = dig(d, ['streams', 'items', 'list'], 2);
    return (Array.isArray(arr) ? arr : (Array.isArray(d) ? d : [])).filter(isObj);
  }
  function loadStreams() {
    notice($('streamNotice'), '', '加载 /api/t64/streams …');
    return withBusy($('btnRefreshStreams'), '加载中…', function () {
      return api(API + '/streams', { timeout: 25000 }).then(function (res) {
        if (!res.ok) { notice($('streamNotice'), 'err', '加载车辆流失败：' + errText(res)); renderStreams([]); return; }
        var list = extractStreams(res.data);
        state.streams = list;
        renderStreams(list);
        notice($('streamNotice'), list.length ? 'ok' : 'warn', list.length ? ('已加载 ' + list.length + ' 条冻结车辆流') : '后端返回空列表：请创建或按路径载入。');
        if (state.stream) {
          var sid = sval(streamField(state.stream, ['stream_id', 'id']));
          var hit = list.filter(function (x) { return sval(streamField(x, ['stream_id', 'id'])) === sid; })[0];
          if (hit) state.stream = hit;
          renderSelected(); updateLimits();
        }
      });
    });
  }
  function renderStreams(list) {
    var body = clear($('streamBody'));
    txt($('streamCount'), list.length ? '共 ' + list.length + ' 条' : '0 条');
    if (!list.length) { emptyRow(body, 8, '当前没有冻结车辆流（响应为空）；请创建或按路径载入。'); return; }
    list.forEach(function (s) {
      var sid = sval(streamField(s, ['stream_id', 'id'])), hash = sval(streamField(s, ['hash', 'world_hash', 'sha256']));
      var hd = td(hash ? (hash.length > 14 ? hash.slice(0, 14) + '…' : hash) : DASH);
      hd.title = hash;
      var btn = el('button', null, '载入'), op = el('td');
      btn.type = 'button';
      btn.addEventListener('click', function () { selectStream(s); });
      op.appendChild(btn);
      body.appendChild(row([td(sid), td(sval(streamField(s, ['site', 'site_id']))), td(sval(streamField(s, ['mode', 'data_mode']))),
        td(sval(streamField(s, ['scenario', 'scenario_id']))), td(fmt(streamField(s, ['N', 'n', 'slots'])), 'num'),
        td(fmt(streamField(s, ['vehicles', 'vehicle_count', 'n_vehicles', 'count'])), 'num'), hd, op]));
    });
  }
  function selectStream(s) {
    state.stream = s;
    renderSelected(); updateLimits(); updateModePill();
    notice($('streamNotice'), 'ok', '已选中车流 ' + (sval(streamField(s, ['stream_id', 'id'])) || '(无 id)'));
  }
  function renderSelected() {
    var s = state.stream, box = $('selectedStream'), host = $('streamFacts'), exp = $('streamExport');
    clear(exp);
    if (!s) { show(box, false); return; }
    show(box, true); clear(host);
    appendFact(host, 'stream_id', sval(streamField(s, ['stream_id', 'id'])) || DASH);
    appendFact(host, 'site', sval(streamField(s, ['site', 'site_id'])) || DASH);
    appendFact(host, 'mode', sval(streamField(s, ['mode', 'data_mode'])) || DASH);
    appendFact(host, 'scenario', sval(streamField(s, ['scenario', 'scenario_id'])) || DASH);
    appendFact(host, 'N', fmt(streamField(s, ['N', 'n', 'slots'])));
    appendFact(host, '车数', fmt(streamField(s, ['vehicles', 'vehicle_count', 'n_vehicles'])));
    appendFact(host, 'world_hash', sval(streamField(s, ['world_hash', 'hash', 'sha256'])) || DASH);
    var ap = getKey(s, ['accept_power']);
    if (isObj(ap)) {
      appendFact(host, 'accept_power.declared', fmt(getKey(ap, ['declared', 'n_declared']), 0));
      appendFact(host, 'accept_power.missing', fmt(getKey(ap, ['missing', 'n_missing']), 0));
      appendFact(host, 'accept_power.source', sval(getKey(ap, ['source'])) || DASH);
    }
    var path = sval(streamField(s, ['path', 'file_path', 'file']));
    if (path) appendFact(host, 'path', path);
    ['created_at', 'seed', 'version', 'contract_version', 'engine_version'].forEach(function (k) {
      var v = getKey(s, [k]);
      if (v !== undefined && sval(v)) appendFact(host, k, sval(v));
    });
    var prov = getKey(s, ['provenance', 'prov']);
    if (isObj(prov)) Object.keys(prov).forEach(function (k) { appendFact(host, 'provenance.' + k, fmtVal(prov[k])); });
    var sid = sval(streamField(s, ['stream_id', 'id']));
    if (!sid) { exp.appendChild(el('span', 'muted', '响应未返回 stream_id，无法生成导出链接')); return; }
    ['json', 'csv'].forEach(function (f) {
      var a = el('a', 'export-btn', '导出 ' + f.toUpperCase());
      a.href = API + '/streams/' + encodeURIComponent(sid) + '/export?format=' + f;
      a.target = '_blank'; a.rel = 'noopener';
      exp.appendChild(a);
    });
  }
  function withBusy(btn, label, fn) {
    var p = Promise.resolve().then(fn);
    if (!btn) return p;
    var prev = btn.textContent;
    btn.disabled = true; btn.textContent = label;
    return p['finally'](function () { btn.disabled = false; btn.textContent = prev; });
  }
  function onCreate(ev) {
    ev.preventDefault();
    var body = { site_id: ($('inpSite').value || '').trim(), mode: $('inpMode').value, scenario_id: ($('inpScenario').value || '').trim(), seed: numOf($('inpSeed').value) };
    var miss = [];
    if (!body.site_id) miss.push('site_id');
    if (!body.scenario_id) miss.push('scenario_id');
    if (body.seed === null) miss.push('seed（整数）');
    if (miss.length) { notice($('createNotice'), 'err', '缺少必填：' + miss.join('、')); return; }
    notice($('createNotice'), '', '创建中…');
    withBusy($('btnCreateStream'), '创建中…', function () {
      return api(API + '/streams/create', { method: 'POST', body: body, timeout: 120000 }).then(function (res) {
        if (!res.ok) { notice($('createNotice'), 'err', '创建失败：' + errText(res)); return; }
        notice($('createNotice'), 'ok', '创建成功');
        var cand = getKey(res.data, ['stream', 'record', 'stream_meta']);
        var s = isObj(cand) ? cand : (isObj(res.data) && streamField(res.data, ['stream_id', 'id']) !== undefined ? res.data : null);
        if (s) selectStream(s);
        loadStreams();
      });
    });
  }
  function onLoad(ev) {
    ev.preventDefault();
    var p = ($('inpStreamPath').value || '').trim();
    if (!p) { notice($('loadNotice'), 'err', '需要 path'); return; }
    notice($('loadNotice'), '', '载入中…');
    withBusy($('btnLoadStream'), '载入中…', function () {
      return api(API + '/streams/load', { method: 'POST', body: { path: p }, timeout: 120000 }).then(function (res) {
        if (!res.ok) { notice($('loadNotice'), 'err', '载入失败：' + errText(res)); return; }
        notice($('loadNotice'), 'ok', '载入成功');
        var cand = getKey(res.data, ['stream', 'record']);
        var s = isObj(cand) ? cand : (isObj(res.data) && streamField(res.data, ['stream_id', 'id']) !== undefined ? res.data : null);
        if (s) selectStream(s);
        loadStreams();
      });
    });
  }
  /* ---------------------------------------------------------- 方案与参数 */
  function setScheme(v) {
    if (!v) return;
    state.scheme = v;
    $$('.seg-btn').forEach(function (b) {
      var on = b.getAttribute('data-scheme') === v;
      b.classList.toggle('active', on);
      b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    updateModePill(); updateParamVisibility(); updateLimits();
  }
  function updateParamVisibility() {
    var isS3 = state.scheme === 'S3', isS1 = state.scheme === 'S1';
    $('inpM').disabled = !isS3;
    $('mField').classList.toggle('inactive', !isS3);
    $('inpMGrid').disabled = !isS3;
    $('inpOpenRule').disabled = isS1;
    $('openRuleField').classList.toggle('inactive', isS1);
    var needOpen = !isS1 && $('inpOpenRule').value === 'opportunity';
    $('inpKappa').disabled = !needOpen;
    $('inpRecall').disabled = !needOpen;
    $('kappaField').classList.toggle('inactive', !needOpen);
    $('recallField').classList.toggle('inactive', !needOpen);
  }
  function updateLimits() {
    var s = state.stream, N = s ? numOf(streamField(s, ['N', 'n', 'slots'])) : null;
    var nMax = state.limits.n, mMax = state.limits.m, capN = N !== null ? N : nMax;
    if (capN !== null) $('inpN').max = String(capN); else $('inpN').removeAttribute('max');
    $('nHint').textContent = N !== null ? ('车流 N=' + N + (nMax !== null ? '，后端 n_max=' + nMax : '')) : (nMax !== null ? ('后端 n_max=' + nMax) : '上限取当前车流 N（未加载）');
    if (mMax !== null) $('inpM').max = String(mMax); else $('inpM').removeAttribute('max');
    $('mHint').textContent = mMax !== null ? ('后端 M_max=' + mMax) : '上限取后端 M_max（未返回）';
    var mode = s ? sval(streamField(s, ['mode', 'data_mode'])) : '';
    var extra = mode && mode !== state.scheme ? '（注意：车流 mode=' + mode + '，与所选方案 ' + state.scheme + ' 不一致）' : '';
    $('limitsNote').textContent = '上限与默认值来自后端响应，未返回则留空、不填假默认' + extra + '。';
  }
  function numField(id) { var raw = ($(id).value || '').trim(); if (!raw) return null; var n = Number(raw); return Number.isFinite(n) ? n : null; }
  function strField(id) { return ($(id).value || '').trim(); }
  function intList(id) {
    var raw = ($(id).value || '').trim();
    if (!raw) return null;
    var parts = raw.split(/[\\s,;，]+/).filter(Boolean), out = [];
    for (var i = 0; i < parts.length; i += 1) { var n = Number(parts[i]); if (!Number.isInteger(n) || n < 0) return false; out.push(n); }
    return out.length ? out : null;
  }
  function baseConfig() {
    var s = state.stream;
    var cfg = { contract_version: CONTRACT, scheme: state.scheme, n: numField('inpN'), admission: $('inpAdmission').value };
    if (s) {
      var sid = sval(streamField(s, ['stream_id', 'id']));
      if (sid) cfg.stream_id = sid;
      var p = sval(streamField(s, ['path', 'file_path'])) || strField('inpStreamPath');
      if (p) cfg.stream_path = p;
    } else if (strField('inpStreamPath')) cfg.stream_path = strField('inpStreamPath');
    if (state.scheme === 'S1') cfg.open_rule = 'never';
    else {
      cfg.open_rule = $('inpOpenRule').value;
      if (cfg.open_rule === 'opportunity') {
        var k = numField('inpKappa'), r = numField('inpRecall');
        if (k !== null) cfg.kappa = k;
        if (r !== null) cfg.recall_lead_min = r;
      }
    }
    if (state.scheme === 'S3') cfg.m = numField('inpM');
    if (state.mathVersion) cfg.math_version = state.mathVersion;
    return cfg;
  }
  function checkConfig(cfg) {
    var errs = [], s = state.stream, N = s ? numOf(streamField(s, ['N', 'n', 'slots'])) : null;
    if (!cfg.stream_id && !cfg.stream_path) errs.push('先选择或载入一条冻结车辆流');
    if (cfg.n === null || !Number.isInteger(cfg.n) || cfg.n < 0) errs.push('n 必须是 ≥0 的整数');
    if (N !== null && cfg.n !== null && cfg.n > N) errs.push('n=' + cfg.n + ' 超过车流 N=' + N);
    if (state.limits.n !== null && cfg.n !== null && cfg.n > state.limits.n) errs.push('n=' + cfg.n + ' 超过后端 n_max=' + state.limits.n);
    if (state.scheme === 'S3') {
      if (cfg.m === null) errs.push('S3 需要整数 m（移动设备数）');
      else if (!Number.isInteger(cfg.m) || cfg.m < 0) errs.push('m 必须是 ≥0 的整数');
      else if (state.limits.m !== null && cfg.m > state.limits.m) errs.push('m=' + cfg.m + ' 超过后端 M_max=' + state.limits.m);
    }
    if (state.scheme !== 'S1' && cfg.open_rule === 'opportunity') {
      if (cfg.kappa === undefined) errs.push('open_rule=opportunity 需要 kappa');
      if (cfg.recall_lead_min === undefined) errs.push('open_rule=opportunity 需要 recall_lead_min');
    }
    return errs;
  }
  /* ---------------------------------------------------------- 动作 / 作业轮询 */
  function postConfig(path, cfg, timeout) {
    return api(path, { method: 'POST', body: cfg, timeout: timeout }).then(function (res) {
      if (!res.ok && (res.status === 400 || res.status === 422) && /config|字段|field|body/i.test(String(res.error || ''))) {
        return api(path, { method: 'POST', body: { config: cfg }, timeout: timeout });
      }
      return res;
    });
  }
  function timeoutOf(kind) { return kind === 'validate' ? 40000 : (kind === 'run' ? 180000 : 300000); }
  function renderJob(j) {
    show($('jobBox'), true);
    var p = j.progress, pct = null, ptext = '', pv = numOf(p);
    if (pv !== null) { pct = pv <= 1 ? pv * 100 : pv; ptext = Math.round(pct) + '%'; }
    else if (isObj(p)) {
      var done = numOf(getKey(p, ['done', 'completed', 'current', 'finished'])), total = numOf(getKey(p, ['total', 'count', 'size']));
      var pp = numOf(getKey(p, ['pct', 'percent', 'progress', 'ratio']));
      if (pp !== null) pct = pp <= 1 ? pp * 100 : pp;
      else if (done !== null && total) pct = done / total * 100;
      if (pct !== null) { pct = Math.max(0, Math.min(100, pct)); ptext = Math.round(pct) + '%' + (done !== null && total ? '（' + done + '/' + total + '）' : ''); }
    }
    if (pct === null && (j.status === 'done' || j.status === 'succeeded' || j.status === 'completed')) pct = 100;
    $('jobBarFill').style.width = (pct === null ? 0 : pct) + '%';
    txt($('jobText'), '作业 ' + (j.status || '未知') + (ptext ? ' · ' + ptext : '') + (j.error ? ' · ' + sval(j.error) : ''));
    txt($('jobIdText'), j.id ? 'id ' + j.id : '');
  }
  function resetJob() { show($('jobBox'), false); $('jobBarFill').style.width = '0%'; txt($('jobText'), '等待作业…'); txt($('jobIdText'), ''); }
  function pollJob(id) {
    resetJob();
    renderJob({ status: 'queued', progress: null, id: id });
    var started = Date.now();
    function step(i) {
      if (i > 400) return Promise.resolve({ ok: false, status: 0, error: '作业轮询次数超限' });
      if (Date.now() - started > 600000) return Promise.resolve({ ok: false, status: 0, error: '作业轮询超时（10 分钟）' });
      return api(API + '/jobs/' + encodeURIComponent(id), { timeout: 25000 }).then(function (res) {
        if (!res.ok) {
          if (res.status === 404) return sleep(1500).then(function () { return step(i + 1); });
          return { ok: false, status: res.status, error: errText(res) };
        }
        var d = isObj(res.data) ? res.data : {}, st = String(sval(getKey(d, ['status', 'state'])) || '').toLowerCase();
        renderJob({ status: st || '未知', progress: getKey(d, ['progress', 'progress_info']), id: id, error: getKey(d, ['error', 'message']) });
        if (st === 'done' || st === 'succeeded' || st === 'completed') {
          var r = getKey(d, ['result', 'payload', 'data']);
          return { ok: true, data: isObj(r) ? r : d };
        }
        if (st === 'failed' || st === 'error' || st === 'cancelled') return { ok: false, status: 200, error: sval(getKey(d, ['error', 'message'])) || '作业失败' };
        return sleep(1200).then(function () { return step(i + 1); });
      });
    }
    return step(0);
  }
  function viaJob(kind, cfg) {
    return api(API + '/jobs', { method: 'POST', body: { kind: kind, payload: cfg, contract_version: CONTRACT }, timeout: 30000 }).then(function (res) {
      if (!res.ok) return res.status === 404 ? { fallback: true } : { ok: false, status: res.status, error: errText(res) };
      var jid = sval(getKey(res.data, ['job_id', 'id']));
      if (!jid) {
        var r = getKey(res.data, ['result']);
        return isObj(r) ? { ok: true, data: r } : { fallback: true };
      }
      return pollJob(jid).then(function (jr) { return jr.ok ? { ok: true, data: jr.data } : jr; });
    });
  }
  function runAction(kind) {
    var btns = { validate: $('btnValidate'), run: $('btnRun'), compare: $('btnCompare'), search: $('btnSearch') };
    var slot = $('actionNotice'), jn = $('jobNotice'), cfg = baseConfig(), errs = checkConfig(cfg);
    notice(jn, '', '');
    show($('validateOut'), false);
    if (kind === 'search') {
      var ng = intList('inpNGrid'), mg = intList('inpMGrid');
      if (ng === null) errs.push('搜索需要声明 n_grid（逗号分隔的 ≥0 整数）');
      else if (ng === false) errs.push('n_grid 只能包含 ≥0 整数');
      else cfg.n_grid = ng;
      if (state.scheme === 'S3') {
        if (mg === null) errs.push('S3 搜索需要声明 m_grid');
        else if (mg === false) errs.push('m_grid 只能包含 ≥0 整数');
        else cfg.m_grid = mg;
      } else if (Array.isArray(mg) && mg.length) cfg.m_grid = mg;
      state.lastDecl = { n: Array.isArray(ng) ? ng : null, m: Array.isArray(mg) ? mg : null };
    }
    if (errs.length) { notice(slot, 'err', '参数不完整，未发送请求：\n' + errs.map(function (e) { return '· ' + e; }).join('\n')); return; }
    resetJob();
    notice(slot, '', '');
    var busyLabel = { validate: '校验中…', run: '运行中…', compare: '对比中…', search: '搜索中…' }[kind];
    var doneLabel = { validate: '校验完成', run: '运行完成', compare: '对比完成', search: '搜索完成' }[kind];
    withBusy(btns[kind], busyLabel, function () {
      var useJob = $('chkAsync').checked && kind !== 'validate';
      var chain = useJob ? viaJob(kind, cfg).then(function (jr) {
        if (!jr.fallback) return jr;
        notice(jn, 'warn', '后端未实现 /api/t64/jobs（404），已回退同步接口。');
        return postConfig(API + '/' + kind, cfg, timeoutOf(kind));
      }) : postConfig(API + '/' + kind, cfg, timeoutOf(kind));
      return chain.then(function (res) {
        if (!res.ok) { notice(slot, 'err', busyLabel.replace('中…', '') + '失败：' + errText(res)); return; }
        dispatch(kind, res.data, slot, doneLabel);
      });
    }).catch(function (e) { notice(slot, 'err', '请求异常：' + ((e && e.message) || e)); });
  }
  function dispatch(kind, data, slot, doneLabel) {
    if (kind === 'validate') { applyValidate(data); notice(slot, 'ok', '校验响应已返回'); return; }
    var jid = sval(getKey(data, ['job_id']));
    var hasResult = getKey(data, ['result']) !== undefined || getKey(data, ['run_id', 'compare_id', 'search_id']) !== undefined;
    if (jid && !hasResult) {
      pollJob(jid).then(function (jr) {
        if (!jr.ok) { notice(slot, 'err', '作业失败：' + jr.error); return; }
        apply(kind, jr.data); notice(slot, 'ok', doneLabel + '（作业 ' + jid + '）');
      });
      return;
    }
    apply(kind, data);
    notice(slot, 'ok', doneLabel);
  }
  function applyValidate(data) {
    var host = clear($('validateOut'));
    show(host, true);
    var errors = asArray(getKey(data, ['errors', 'validation_errors', 'violations', 'problems']));
    var warnings = asArray(getKey(data, ['warnings', 'notes', 'soft_errors']));
    var okFlag = getKey(data, ['ok', 'valid']);
    host.appendChild(el('h3', null, '校验结果'));
    host.appendChild(el('div', 'notice ' + (errors.length || okFlag === false ? 'err' : 'ok'),
      errors.length ? ('校验未通过：' + errors.length + ' 项') : (okFlag === false ? '响应 ok=false（无 errors 列表）' : '校验通过')));
    if (errors.length) { var ul = el('ul'); errors.forEach(function (e) { ul.appendChild(el('li', null, typeof e === 'string' ? e : JSON.stringify(e))); }); host.appendChild(ul); }
    if (warnings.length) {
      host.appendChild(el('h3', null, '警告'));
      var uw = el('ul');
      warnings.forEach(function (e) { uw.appendChild(el('li', null, typeof e === 'string' ? e : JSON.stringify(e))); });
      host.appendChild(uw);
    }
    var feas = dig(data, ['feasible_region', 'feasible_domain', 'domain', 'feasible']);
    if (isObj(feas)) {
      host.appendChild(el('h3', null, '可行域'));
      var dl = el('dl', 'facts compact');
      Object.keys(feas).slice(0, 20).forEach(function (k) { appendFact(dl, k, fmtVal(feas[k])); });
      host.appendChild(dl);
    }
    var costs = dig(data, ['cost_parameters', 'cost_defaults', 'costs']);
    if (isObj(costs) && Object.keys(costs).length) { state.costs = costs; renderCosts(costs); }
    var mob = dig(data, ['mobile_defaults', 'mobile_params', 'mobile_device_defaults']);
    if (isObj(mob) && Object.keys(mob).length) { state.mobile = mob; renderMobile(mob); }
    var limits = dig(data, ['limits', 'bounds'], 2);
    if (isObj(limits)) {
      var mn = numOf(getKey(limits, ['n_max', 'max_n'])), mm = numOf(getKey(limits, ['m_max', 'max_m']));
      if (mn !== null) state.limits.n = mn;
      if (mm !== null) state.limits.m = mm;
      updateLimits();
    }
  }
  function exportHost(host, id, label) {
    clear(host);
    if (!id) { host.appendChild(el('span', 'muted', '无可导出 ' + label + '_id')); return; }
    ['json', 'csv'].forEach(function (f) {
      var a = el('a', 'export-btn', '导出 ' + f.toUpperCase());
      var base = label === 'search' ? '/searches/' : label === 'compare' ? '/compares/' : '/runs/';
      a.href = API + base + encodeURIComponent(id) + '/export?format=' + f;
      a.target = '_blank'; a.rel = 'noopener'; a.title = label + '_id=' + id;
      host.appendChild(a);
    });
  }
  function apply(kind, data) {
    var d = isObj(data) ? data : {}, inner = getKey(d, ['result']);
    if (isObj(inner)) d = inner;
    if (kind === 'run') { state.run = d; state.runId = sval(getKey(d, ['run_id', 'id'])); renderRun(); }
    else if (kind === 'compare') { state.compare = d; state.compareId = sval(getKey(d, ['compare_id', 'run_id', 'id'])); renderCompare(); }
    else { state.search = d; state.searchId = sval(getKey(d, ['search_id', 'run_id', 'id'])); renderSearch(); }
    txt($('footStamp'), (kind === 'run' ? '最近运行' : kind === 'compare' ? '最近对比' : '最近搜索') + ' · ' + new Date().toLocaleString('zh-CN'));
  }
  /* ---------------------------------------------------------- 单配置结果 */
  function renderRun() {
    var r = state.run;
    show($('resultEmpty'), !r);
    show($('resultBody'), !!r);
    exportHost($('runExport'), state.runId, 'run');
    if (!r) { txt($('footStamp'), '尚未运行'); return; }
    var facts = clear($('runFacts')), stream = state.stream;
    var sid = sval(getKey(r, ['stream_id'])) || (stream ? sval(streamField(stream, ['stream_id', 'id'])) : '');
    appendFact(facts, 'run_id', state.runId || DASH);
    appendFact(facts, 'scheme', sval(getKey(r, ['scheme', 'plan', 'variant'])) || state.scheme);
    appendFact(facts, 'stream_id', sid || DASH);
    appendFact(facts, 'world_hash', sval(getKey(r, ['world_hash', 'stream_hash'])) || DASH);
    appendFact(facts, 'math_version', sval(getKey(r, ['math_version'])) || DASH);
    appendFact(facts, 'engine_version', sval(getKey(r, ['engine_version', 'engine'])) || DASH);
    appendFact(facts, 'data_mode', sval(getKey(r, ['data_mode', 'mode'])) || DASH);
    appendFact(facts, 'n / m', fmt(getKey(r, ['n', 'chargers'])) + ' / ' + fmt(getKey(r, ['m', 'devices'])));
    var runMath = sval(getKey(r, ['math_version']));
    if (runMath && state.mathVersion && runMath !== state.mathVersion) setMixing('版本混用警告：结果数学版本 ' + runMath + ' 与后端健康版本 ' + state.mathVersion + ' 不一致，禁止与其他版本结果并列比较。');
    var total = dig(r, ['total_social_cost', 'social_cost', 'total_cost'], 2);
    txt($('kpiTotal'), money(total));
    txt($('kpiTotalNote'), total === undefined ? '响应未返回总社会成本' : 'total_social_cost');
    txt($('kpiScheme'), sval(getKey(r, ['scheme', 'plan'])) || state.scheme);
    txt($('kpiSchemeNote'), 'n=' + fmt(getKey(r, ['n'])) + '，m=' + fmt(getKey(r, ['m'])));
    txt($('kpiMath'), runMath || state.mathVersion || DASH);
    txt($('kpiMode'), sval(getKey(r, ['data_mode', 'mode'])) || DASH);
    renderCostTable(r); renderParking(r); renderE1(r); renderAccounting(r); renderMobileRun(r); renderTimeline(r);
  }
  function renderCostTable(r) {
    var body = clear($('costBodyRes')), note = $('costNoteRes');
    var bd = dig(r, ['cost_breakdown', 'breakdown', 'cost_items', 'cost_components'], 3);
    if (!isObj(bd)) { emptyRow(body, 4, '响应未返回 cost_breakdown：成本分项无法展示'); note.textContent = '无成本分项字段时显示“无法完整计算”，不填 0。'; return; }
    var missing = [], used = [];
    COST_ROWS.forEach(function (c) {
      var hit = findEntry(bd, c[1]), rec = hit.rec, rawKey = hit.key;
      if (rec === undefined) { rec = getKey(r, c[1]); rawKey = rec === undefined ? '' : '(响应顶层)'; }
      var val = rec === undefined ? null : unwrap(rec), m = money(val);
      if (val === null) missing.push(c[0]);
      var st = (isObj(rec) ? sval(getKey(rec, ['status', 'state', 'missing'])) : '') || (val === null ? 'missing' : DASH);
      body.appendChild(row([td(c[0]), td(m, m === NOCOST ? 'num missing' : 'num'), td(st), td(rawKey, 'muted')]));
      if (hit.key) used.push(norm(hit.key));
    });
    Object.keys(bd).forEach(function (k) {
      if (used.indexOf(norm(k)) >= 0) return;
      var v = unwrap(bd[k]);
      if (v === null || Number.isNaN(Number(v))) return;
      body.appendChild(row([td(k), td(fmt(Number(v), 2), 'num'), td(isObj(bd[k]) ? sval(getKey(bd[k], ['status'])) : ''), td(k, 'muted')]));
    });
    note.textContent = '成本分项取自响应 cost_breakdown；未匹配项以原始键列出。' + (missing.length ? ('缺失分项（显示“无法完整计算”）：' + missing.join('、')) : '');
  }
  function renderParking(r) {
    var body = clear($('parkingBody'));
    var src = dig(r, ['parking_outcomes', 'parking_results', 'parking_by_type', 'parking_stats', 'outcomes'], 3);
    var entries = [];
    if (Array.isArray(src)) entries = src.filter(isObj);
    else if (isObj(src)) entries = Object.keys(src).map(function (k) { return { __key: k, __val: src[k] }; });
    if (!entries.length) { emptyRow(body, 4, '响应未返回三类车停车结果'); return; }
    entries.forEach(function (e) {
      var o = isObj(e.__val) ? e.__val : e;
      var label = sval(getKey(o, ['vehicle_type', 'type', 'category', 'class', 'label'])) || sval(e.__key) || DASH;
      body.appendChild(row([td(label), td(fmt(getKey(o, ['attempted', 'attempts', 'tries', 'arrivals', 'demand'])), 'num'),
        td(fmt(getKey(o, ['admitted', 'accepted', 'served'])), 'num'), td(fmt(getKey(o, ['denied', 'rejected', 'refused', 'turned_away'])), 'num')]));
    });
  }
  function renderE1(r) {
    var host = clear($('e1Facts'));
    var e1 = dig(r, ['e1', 'e1_delivery', 'delivery', 'energy_delivery', 'delivery_summary'], 3);
    if (e1 === undefined) { appendFact(host, '状态', '响应未返回 E1 交付字段', 'muted'); return; }
    if (!isObj(e1)) { appendFact(host, 'E1', fmtVal(e1)); return; }
    Object.keys(e1).slice(0, 16).forEach(function (k) { appendFact(host, E1_LABEL[k] || k, fmtVal(e1[k])); });
  }
  function classCounts(o) {
    if (!isObj(o)) return DASH;
    return Object.keys(o).map(function (k) { return k + ' ' + fmt(o[k], 0); }).join(' / ');
  }
  function renderAccounting(r) {
    var host = clear($('accountingFacts'));
    var a = dig(r, ['accounting', 'accounting_window'], 2);
    if (!isObj(a)) { appendFact(host, '状态', '响应未返回 accounting 块', 'muted'); return; }
    appendFact(host, 'W / T / H', fmt(getKey(a, ['W']), 0) + ' / ' + fmt(getKey(a, ['T']), 0) + ' / ' + fmt(getKey(a, ['H']), 0));
    appendFact(host, 'window_days', fmt(getKey(a, ['window_days', 'days']), 0));
    appendFact(host, 'cohort_n', fmt(getKey(a, ['cohort_n', 'n_cohort']), 0));
    appendFact(host, 'cohort_by_class', classCounts(getKey(a, ['cohort_by_class'])));
    var ap = getKey(a, ['accept_power']);
    appendFact(host, 'accept_power.declared', fmt(getKey(ap, ['declared', 'n_declared']), 0));
    appendFact(host, 'accept_power.missing', fmt(getKey(ap, ['missing', 'n_missing']), 0));
    appendFact(host, 'accept_power.source', sval(getKey(ap, ['source'])) || DASH);
    var ma = getKey(a, ['mobile_assumption']);
    appendFact(host, 'mobile_assumption.assumed_accept_power_kw', fmt(getKey(ma, ['assumed_accept_power_kw']), 2));
    appendFact(host, 'mobile_assumption.source', sval(getKey(ma, ['source'])) || DASH);
    var cb = sval(getKey(a, ['cost_basis']));
    if (cb) appendFact(host, 'cost_basis', cb);
  }
  function renderMobileRun(r) {
    var host = clear($('mobileRunFacts'));
    var m = dig(r, ['mobile', 'mobile_summary'], 2);
    if (!isObj(m)) { appendFact(host, '状态', '响应未返回 mobile 摘要', 'muted'); return; }
    ['device_kind', 'devices', 'services', 'delivered_kwh', 'grid_kwh', 'loss_kwh', 'unserved_kwh', 'expired_jobs',
      'assumed_accept_power_kw', 'accept_power_missing_vehicles', 'accept_power_assumption_applied'].forEach(function (k) {
      var v = getKey(m, [k]);
      if (v !== undefined) appendFact(host, k, fmtVal(v));
    });
    var pd = sval(getKey(m, ['power_definition'])), dt = sval(getKey(m, ['delivery_time_definition']));
    if (pd) appendFact(host, 'power_definition', pd);
    if (dt) appendFact(host, 'delivery_time_definition', dt);
  }
  function creditText(v) {
    if (v === true || v === 'true' || v === 1) return '是';
    if (v === false || v === 'false' || v === 0) return '否';
    return DASH;
  }
  function renderTimeline(r) {
    var body = clear($('timelineBody')), note = $('timelineNote');
    var src = dig(r, ['timeline_sample', 'timeline', 'device_timeline', 'mobile_timeline', 'timeline_rows'], 3);
    var rows = Array.isArray(src) ? src.filter(isObj) : [];
    if (!rows.length) { emptyRow(body, 9, '响应未返回移动设备时间线（S1/S2 无移动设备时可能为空）'); note.textContent = 'S3 应返回 timeline_sample；缺失即视为后端未提供，不补造。'; return; }
    rows.slice(0, TL_LIMIT).forEach(function (o) {
      body.appendChild(row([td(sval(getKey(o, ['device_id', 'device', 'mobile_device_id']))), td(sval(getKey(o, ['vehicle', 'vehicle_id', 'vehicle_key']))),
        td(fmt(getKey(o, ['t_start', 'start', 'start_min', 't0'])), 'num'), td(fmt(getKey(o, ['t_end', 'end', 'end_min', 't1'])), 'num'),
        td(fmt(getKey(o, ['delivered_kwh', 'kwh', 'energy_kwh'])), 'num'), td(fmt(getKey(o, ['t_connect', 'connect', 'connect_min'])), 'num'),
        td(fmt(getKey(o, ['t_charge_end', 'charge_end', 'charge_end_min'])), 'num'), td(fmt(getKey(o, ['power_kw', 'p_eff_kw', 'power']), 2), 'num'),
        td(creditText(getKey(o, ['credited', 'is_credited'])))]));
    });
    note.textContent = 'timeline_sample 共 ' + rows.length + ' 条' + (rows.length > TL_LIMIT ? ('，展示前 ' + TL_LIMIT + ' 条') : '') + '。';
  }
  /* ---------------------------------------------------------- 同源对比 */
  function schemeColor(s) { return s === 'S1' ? '#7FB0D8' : s === 'S2' ? '#46B394' : s === 'S3' ? '#D8A54E' : '#8E9E97'; }
  function extractCompareRuns(d) {
    var arr = dig(d, ['rows', 'runs', 'results', 'schemes', 'compare', 'comparison'], 3);
    if (Array.isArray(arr)) return arr.filter(isObj);
    if (isObj(arr)) {
      return Object.keys(arr).map(function (k) {
        var v = arr[k], o = isObj(v) ? v : { total_social_cost: v };
        if (o.scheme === undefined) o.scheme = k;
        return o;
      });
    }
    return [];
  }
  function renderCompare() {
    var d = state.compare;
    show($('comparePanel'), !!d);
    exportHost($('compareExport'), state.compareId, 'compare');
    if (!d) return;
    var runs = extractCompareRuns(d), body = clear($('compareBody')), costs = [];
    if (!runs.length) emptyRow(body, 4, '响应未返回 runs/results；无法展示对比');
    runs.forEach(function (run) {
      var scheme = sval(getKey(run, ['scheme', 'plan', 'variant'])) || DASH;
      var cost = dig(run, ['total_social_cost', 'social_cost', 'total_cost'], 2), m = money(cost);
      var bd = dig(run, ['cost_breakdown', 'breakdown', 'cost_items'], 3), bits = [];
      if (isObj(bd)) COST_ROWS.slice(0, 3).forEach(function (c) {
        var v = unwrap(getKey(bd, c[1]));
        if (v !== null && Number.isFinite(Number(v))) bits.push(c[0] + ' ' + fmt(Number(v), 2));
      });
      body.appendChild(row([td(scheme), td(m, m === NOCOST ? 'num missing' : 'num'),
        td(sval(getKey(run, ['run_id', 'id']))), td(bits.length ? bits.join(' · ') : DASH, 'muted')]));
      var cv = numOf(unwrap(cost));
      if (cv !== null) costs.push({ label: scheme, value: cv, color: schemeColor(scheme) });
    });
    state.chartCompare = costs;
    drawCompareChart();
    var diffs = dig(d, ['diffs', 'differences', 'deltas', 'delta', 'decomposition'], 3), dbody = clear($('diffBody')), rows = [];
    if (Array.isArray(diffs)) rows = diffs.map(function (x) {
      return isObj(x) ? [sval(getKey(x, ['label', 'name', 'key', 'item'])) || DASH, fmtVal(getKey(x, ['value', 'delta', 'diff'])), sval(getKey(x, ['note', 'status']))] : ['#', fmtVal(x), ''];
    });
    else if (isObj(diffs)) rows = Object.keys(diffs).map(function (k) { return [k, fmtVal(diffs[k]), '']; });
    if (!rows.length) rows = runs.filter(function (x) { return isObj(getKey(x, ['delta_vs_s1'])); }).map(function (x) {
      var dv = getKey(x, ['delta_vs_s1']);
      return [(sval(getKey(x, ['scheme'])) || '?') + ' vs S1', fmtVal(dv), isObj(dv) && dv.total_social_cost !== undefined ? 'Δ总社会成本 ' + fmt(dv.total_social_cost, 2) : ''];
    });
    if (!rows.length) emptyRow(dbody, 3, '响应未返回差异字段（diffs）');
    else rows.forEach(function (r2) { dbody.appendChild(row([td(r2[0]), td(r2[1], 'num'), td(r2[2], 'muted')])); });
    $('compareNote').textContent = '对比项只按响应字段展示；某方案缺分项时不计算差值。' + (d.same_stream === true ? ' same_stream=true（同一冻结车流）。' : '') + (sval(d.layer) ? ' layer=' + sval(d.layer) + '。' : '') + (sval(d.evidence_label) ? ' evidence=' + sval(d.evidence_label) + '。' : '');
  }
  /* ---------------------------------------------------------- 配置曲线 / 近最优 */
  function extractPoints(d) {
    var arr = dig(d, ['points', 'grid_points', 'curve', 'configurations', 'evaluated_configs', 'results'], 3);
    var list = Array.isArray(arr) ? arr.filter(isObj) : [], out = [];
    list.forEach(function (o) {
      var n = numOf(getKey(o, ['n', 'chargers', 'fixed_chargers'])), m = numOf(getKey(o, ['m', 'devices', 'mobile_devices']));
      var cy = numOf(unwrap(dig(o, ['total_social_cost', 'cost', 'total_cost', 'objective'], 2)));
      if (n !== null && cy !== null) out.push({ x: n, y: cy, m: m === null ? 0 : m });
    });
    return out;
  }
  function renderSearch() {
    var d = state.search;
    show($('searchPanel'), !!d);
    exportHost($('searchExport'), state.searchId, 'search');
    if (!d) return;
    var meta = clear($('searchMeta'));
    appendFact(meta, 'n_grid', fmtVal(getKey(d, ['n_grid', 'n_values', 'n_grid_values'])));
    appendFact(meta, 'm_grid', fmtVal(getKey(d, ['m_grid', 'm_values', 'm_grid_values'])));
    appendFact(meta, '评估配置数', fmtVal(getKey(d, ['grid_points', 'evaluated', 'n_evaluated', 'configs', 'count'])));
    appendFact(meta, '最优配置', fmtVal(getKey(d, ['best', 'best_config', 'optimal'])));
    appendFact(meta, 'search_id', state.searchId || DASH);
    var decl = state.lastDecl || {};
    appendFact(meta, '本页声明网格', (decl.n ? 'n=' + decl.n.join(',') : 'n=—') + '；' + (decl.m ? 'm=' + decl.m.join(',') : 'm=—'));
    var pts = extractPoints(d);
    state.chartSearch = pts;
    drawSearchChart();
    var body = clear($('nearOptBody')), near = dig(d, ['near_optimal', 'near_optimal_set', 'shortlist', 'top'], 3);
    var nearList = Array.isArray(near) ? near.filter(isObj) : [], best = null;
    if (!nearList.length) emptyRow(body, 4, '响应未返回 near_optimal 集合');
    pts.forEach(function (p) { if (best === null || p.y < best) best = p.y; });
    nearList.slice(0, 120).forEach(function (o) {
      var cost = dig(o, ['total_social_cost', 'cost', 'objective', 'value'], 2), cnum = numOf(unwrap(cost)), cm = money(cost);
      var gap = (cnum !== null && best !== null && best !== 0) ? ((cnum - best) / best * 100) : null;
      body.appendChild(row([td(fmt(getKey(o, ['n', 'chargers'])), 'num'), td(fmt(getKey(o, ['m', 'devices'])), 'num'),
        td(cm, cm === NOCOST ? 'num missing' : 'num'), td(gap === null ? DASH : ('+' + gap.toFixed(2) + '%'), 'num')]));
    });
    $('searchNote').textContent = pts.length ? ('配置点 ' + pts.length + ' 个；曲线按 m 分组、以 n 为横轴，只绘制响应返回的点。') : '响应未返回可绘制的配置点（points/grid_points/curve）。';
  }
  /* ---------------------------------------------------------- canvas 手绘图表 */
  function prep(cv) {
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    var w = Math.max(240, Math.round(cv.clientWidth || (cv.parentNode && cv.parentNode.clientWidth) || 520));
    var h = Math.max(160, Math.round(cv.clientHeight || 240));
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
    var ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx: ctx, w: w, h: h };
  }
  function ticks(min, max, count) {
    if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
    if (min === max) return [min];
    var span = max - min, step = Math.pow(10, Math.floor(Math.log10(span / count))), err = span / (step * count);
    var mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1, s = step * mult;
    var lo = Math.floor(min / s) * s, hi = Math.ceil(max / s) * s, out = [];
    for (var v = lo; v <= hi + s / 2; v += s) out.push(Number(v.toFixed(6)));
    return out;
  }
  function fmtShort(v) {
    var a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(1) + 'G';
    if (a >= 1e6) return (v / 1e6).toFixed(1) + 'M';
    if (a >= 1e4) return (v / 1e3).toFixed(0) + 'k';
    if (a >= 1e3) return (v / 1e3).toFixed(1) + 'k';
    if (Number.isInteger(v)) return String(v);
    return v.toFixed(a < 1 ? 3 : 1);
  }
  function emptyCanvas(ctx, h) { ctx.fillStyle = '#7E8F88'; ctx.font = '12px "Segoe UI", sans-serif'; ctx.fillText('无可绘制的数据点', 58, h / 2); }
  function legendAdd(host, color, text) {
    var s = el('span', 'legend-item'), sw = el('span', 'swatch');
    sw.style.background = color;
    s.appendChild(sw); s.appendChild(el('span', null, text));
    host.appendChild(s);
  }
  function axisFrame(ctx, pad, w, h) {
    ctx.strokeStyle = '#30453B';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, h - pad.b); ctx.lineTo(w - pad.r, h - pad.b);
    ctx.stroke();
  }
  function drawCompareChart() {
    var cv = $('compareCanvas');
    if (!cv) return;
    var items = state.chartCompare || [], p = prep(cv), ctx = p.ctx, w = p.w, h = p.h;
    var pad = { l: 58, r: 14, t: 16, b: 40 };
    clear($('compareLegend'));
    if (!items.length) { emptyCanvas(ctx, h); return; }
    var vmax = 0;
    items.forEach(function (it) { if (it.value > vmax) vmax = it.value; });
    vmax = vmax * 1.15 || 1;
    var bw = (w - pad.l - pad.r) / items.length;
    ctx.font = '10px Consolas, monospace';
    ticks(0, vmax, 4).forEach(function (v) {
      var y = h - pad.b - (v / vmax) * (h - pad.t - pad.b);
      ctx.strokeStyle = '#223029';
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillStyle = '#7E8F88';
      ctx.fillText(fmtShort(v), 6, y + 3);
    });
    items.forEach(function (it, i) {
      var x = pad.l + bw * i + bw * 0.18, bwid = bw * 0.64, bh = (it.value / vmax) * (h - pad.t - pad.b);
      ctx.fillStyle = it.color || '#46B394';
      ctx.fillRect(x, h - pad.b - bh, bwid, bh);
      ctx.fillStyle = '#B4C4BD';
      ctx.fillText(fmtShort(it.value), x, h - pad.b - bh - 4);
      ctx.fillStyle = '#7E8F88';
      ctx.fillText(it.label, x, h - pad.b + 14);
      legendAdd($('compareLegend'), it.color || '#46B394', it.label + ' · ' + fmt(it.value, 2));
    });
    axisFrame(ctx, pad, w, h);
  }
  function drawSearchChart() {
    var cv = $('curveCanvas');
    if (!cv) return;
    var pts = state.chartSearch || [], p = prep(cv), ctx = p.ctx, w = p.w, h = p.h;
    var pad = { l: 62, r: 14, t: 16, b: 38 }, legend = clear($('curveLegend'));
    if (!pts.length) { emptyCanvas(ctx, h); return; }
    var ms = [];
    pts.forEach(function (q) { if (ms.indexOf(q.m) < 0) ms.push(q.m); });
    ms.sort(function (a, b) { return a - b; });
    var palette = ['#46B394', '#7FB0D8', '#D8A54E', '#C98BD8', '#E1727A', '#8ED86F'];
    var series = ms.map(function (m, i) {
      return { m: m, color: palette[i % palette.length], pts: pts.filter(function (q) { return q.m === m; }).sort(function (a, b) { return a.x - b.x; }) };
    });
    var xmin = Infinity, xmax = -Infinity, ymin = Infinity, ymax = -Infinity;
    pts.forEach(function (q) { xmin = Math.min(xmin, q.x); xmax = Math.max(xmax, q.x); ymin = Math.min(ymin, q.y); ymax = Math.max(ymax, q.y); });
    if (xmin === xmax) { xmin -= 1; xmax += 1; }
    var ypad = (ymax - ymin) * 0.1 || Math.abs(ymax || 1) * 0.1 || 1;
    ymin -= ypad; ymax += ypad;
    function X(v) { return pad.l + (v - xmin) / (xmax - xmin) * (w - pad.l - pad.r); }
    function Y(v) { return h - pad.b - (v - ymin) / (ymax - ymin) * (h - pad.t - pad.b); }
    ctx.font = '10px Consolas, monospace';
    ticks(ymin, ymax, 5).forEach(function (v) {      var y = Y(v);
      ctx.strokeStyle = '#223029';
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(w - pad.r, y); ctx.stroke();
      ctx.fillStyle = '#7E8F88';
      ctx.fillText(fmtShort(v), 6, y + 3);
    });
    ticks(xmin, xmax, 6).forEach(function (v) {
      var x = X(v);
      ctx.strokeStyle = '#182420';
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, h - pad.b); ctx.stroke();
      ctx.fillStyle = '#7E8F88';
      ctx.fillText(fmtShort(v), x - 6, h - pad.b + 14);
    });
    axisFrame(ctx, pad, w, h);
    series.forEach(function (s) {
      ctx.strokeStyle = s.color;
      ctx.fillStyle = s.color;
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      s.pts.forEach(function (q, i) { if (i) ctx.lineTo(X(q.x), Y(q.y)); else ctx.moveTo(X(q.x), Y(q.y)); });
      ctx.stroke();
      s.pts.forEach(function (q) { ctx.beginPath(); ctx.arc(X(q.x), Y(q.y), 2.3, 0, Math.PI * 2); ctx.fill(); });
      legendAdd(legend, s.color, 'm=' + s.m);
    });
    ctx.fillStyle = '#B4C4BD';
    ctx.font = '11px "Segoe UI", sans-serif';
    ctx.fillText('n（固定桩数）', (w - pad.r + pad.l) / 2 - 30, h - 6);
  }

  /* ---------------------------------------------------------- 跨站点独立评价 */
  function crossExportUrl(fmt) {
    return API + '/cross-site/export?format=' + encodeURIComponent(fmt || 'csv');
  }
  function openCrossExport() {
    var sel = $('crossExportFmt');
    var url = crossExportUrl(sel && sel.value ? sel.value : 'csv');
    if (typeof window.open === 'function') { window.open(url, '_blank'); return; }
    notice($('crossNotice'), 'warn', '当前环境不支持窗口打开，导出地址：' + url);
  }
  function deltaCell(d) {
    if (!isObj(d)) return td(DASH, 'num');
    var mean = numOf(getKey(d, ['mean', 'delta', 'value']));
    var se = numOf(getKey(d, ['se', 'stderr', 'std_err']));
    if (mean === null) return td(DASH, 'num');
    var s = (mean >= 0 ? '+' : '') + fmt(mean, 2);
    if (se !== null) s += ' (se ' + fmt(se, 2) + ')';
    var cell = td(s, 'num');
    var pos = numOf(getKey(d, ['positive']));
    if (pos !== null) cell.title = '逐世界 Δ>0 的个数：' + fmt(pos, 0);
    return cell;
  }
  function crossSelectionRow(r) {
    var j = getKey(r, ['J', 'J_mean', 'J_sel', 'select_J', 'total_social_cost']);
    return row([
      td(sval(getKey(r, ['site_id', 'site']))),
      td(sval(getKey(r, ['mechanism', 'mech']))),
      td(sval(getKey(r, ['scenario_id', 'scenario']))),
      td(sval(getKey(r, ['scheme', 'plan']))),
      td(fmt(getKey(r, ['n', 'selected_n', 'n_sel']), 0), 'num'),
      td(fmt(getKey(r, ['m', 'selected_m', 'm_sel']), 0), 'num'),
      td(fmt(j, 2), 'num'),
      td(fmt(getKey(r, ['candidates', 'candidate_count', 'n_candidates', 'worlds', 'selection_worlds', 'replicates']), 0), 'num')
    ]);
  }
  function crossEvalRow(s) {
    var s1 = getKey(s, ['S1']), s2 = getKey(s, ['S2']), s3 = getKey(s, ['S3']);
    return row([
      td(sval(getKey(s, ['site_id', 'site']))),
      td(sval(getKey(s, ['mechanism', 'mech']))),
      td(sval(getKey(s, ['scenario_id', 'scenario']))),
      td(fmt(getKey(s1, ['J_mean', 'J']), 2), 'num'),
      td(fmt(getKey(s2, ['J_mean', 'J']), 2), 'num'),
      td(fmt(getKey(s3, ['J_mean', 'J']), 2), 'num'),
      deltaCell(getKey(s, ['delta_S2_S1', 'delta_S2S1', 'delta_s2_s1'])),
      deltaCell(getKey(s, ['delta_S3_S2', 'delta_S3S2', 'delta_s3_s2'])),
      td(fmt(getKey(s, ['worlds', 'evaluation_worlds', 'replicates']), 0), 'num')
    ]);
  }
  function renderCrossSite(d, err) {
    var nHost = $('crossNotice');
    var fHost = clear($('crossFacts'));
    var sBody = clear($('crossSelectBody')), eBody = clear($('crossEvalBody'));
    show($('crossPanel'), true);
    if (err) {
      notice(nHost, 'err', '跨站点评价加载失败：' + err);
      appendFact(fHost, '状态', '加载失败', 'muted');
      emptyRow(sBody, 8, '尚未取得选择集数据');
      emptyRow(eBody, 9, '尚未取得评价集数据');
      return;
    }
    if (getKey(d, ['available']) === false) {
      var dir = sval(getKey(d, ['dir']));
      appendFact(fHost, '状态', sval(getKey(d, ['status'])) || 'missing', 'muted');
      if (dir) appendFact(fHost, '结果目录', dir, 'mono');
      notice(nHost, 'warn', sval(getKey(d, ['message'])) || '跨站点评价结果尚未生成');
      emptyRow(sBody, 8, '尚未生成（available=false）');
      emptyRow(eBody, 9, '尚未生成（available=false）');
      return;
    }
    state.cross = d;
    var summary = getKey(d, ['summary', 'results']);
    var pickNum = function (names) {
      var v = getKey(summary, names);
      return v === undefined ? dig(d, names, 2) : v;
    };
    appendFact(fHost, 'select_worlds', fmt(pickNum(['select_worlds']), 0));
    appendFact(fHost, 'evaluation_worlds', fmt(pickNum(['evaluation_worlds']), 0));
    appendFact(fHost, 'runtime_sec', fmt(pickNum(['runtime_sec']), 2));
    appendFact(fHost, 'data_mode', sval(getKey(d, ['data_mode'])) || DASH);
    var proto = getKey(d, ['protocol']);
    var math = sval(getKey(proto, ['math_version'])), eng = sval(getKey(proto, ['engine_version']));
    if (math) appendFact(fHost, 'math_version', math, 'mono');
    if (eng) appendFact(fHost, 'engine_version', eng, 'mono');
    var notes = getKey(d, ['notes']);
    if (Array.isArray(notes) && notes.length) notice(nHost, 'ok', notes.join('\n'));
    else { nHost.textContent = ''; show(nHost, false); }
    var sel = getKey(d, ['selection', 'selection_best']);
    if (Array.isArray(sel) && sel.length) sel.forEach(function (r) { sBody.appendChild(crossSelectionRow(r)); });
    else emptyRow(sBody, 8, '后端未返回 selection 行');
    var strata = getKey(d, ['evaluation_strata', 'strata']);
    if (Array.isArray(strata) && strata.length) strata.forEach(function (s) { eBody.appendChild(crossEvalRow(s)); });
    else emptyRow(eBody, 9, '后端未返回 evaluation_strata 行');
  }
  function loadCrossSite() {
    var btn = $('btnCrossSite');
    if (btn) btn.disabled = true;
    notice($('crossNotice'), 'muted', '加载 /api/t64/cross-site …');
    return api(API + '/cross-site', { timeout: 30000 }).then(function (res) {
      if (btn) btn.disabled = false;
      if (!res.ok) { renderCrossSite(null, errText(res)); return; }
      renderCrossSite(isObj(res.data) ? res.data : {}, '');
    })['catch'](function (e) {
      if (btn) btn.disabled = false;
      renderCrossSite(null, (e && e.message) || String(e));
    });
  }
  /* ---------------------------------------------------------- 初始化 */
  function init() {
    $('btnHealth').addEventListener('click', function () { loadHealth(); });
    $('btnRefreshStreams').addEventListener('click', function () { loadStreams(); });
    $('formCreate').addEventListener('submit', onCreate);
    $('formLoad').addEventListener('submit', onLoad);
    $$('.seg-btn').forEach(function (b) { b.addEventListener('click', function () { setScheme(b.getAttribute('data-scheme')); }); });
    $('inpOpenRule').addEventListener('change', updateParamVisibility);
    $('inpAdmission').addEventListener('change', updateParamVisibility);
    $('btnValidate').addEventListener('click', function () { runAction('validate'); });
    $('btnRun').addEventListener('click', function () { runAction('run'); });
    $('btnCompare').addEventListener('click', function () { runAction('compare'); });
    $('btnSearch').addEventListener('click', function () { runAction('search'); });
    var rt = null;
    window.addEventListener('resize', function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (state.compare) drawCompareChart();
        if (state.search) drawSearchChart();
      }, 180);
    });
    $('btnCrossSite').addEventListener('click', function () { loadCrossSite(); });
    $('btnCrossExport').addEventListener('click', openCrossExport);
    appendFact(clear($('mobileFacts')), '状态', '等待 /api/t64/health', 'muted');
    setScheme('S1');
    renderSelected();
    renderCosts(null);
    loadHealth();
    loadStreams();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
