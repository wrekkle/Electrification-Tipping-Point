function indep_verify()
%INDEP_VERIFY Independent MATLAB R2026a checks of the parking_lab contracts.
%
%   No Python summary or output is read here. Every expected number in
%   indep/inputs/*_expected.csv is a hand-computed benchmark; the formulas
%   are reimplemented in this file from the source contracts:
%     apps/parking_lab/workbench/costs.py          facility_cost
%     apps/parking_lab/workbench/traffic_gen.py    demand_ledger
%     apps/parking_lab/workbench/allocation.py     erlang_b, service_level_k,
%                                                  integer_recommendation
%     apps/parking_lab/workbench/rules.py          dedicated_by_type (A),
%                                                  full_open_ice_first (B),
%                                                  predictive_shared_ice_first (D)
%     apps/parking_lab/workbench/service_metrics.py summarise
%
%   Outputs: indep/out/indep_checks.csv, indep/out/trajectory_visits.csv,
%   indep/out/indep_summary.json and logs/indep_verify.log.
%   Tolerances: money abs 1e-4 / rel 1e-6; probability abs 1e-12;
%   energy abs 1e-9 / rel 1e-12; counts and statuses exact.

root = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
base = fullfile(root, 'research', 'round5_20261031', 'matlab', 'indep');
inp = fullfile(base, 'inputs');
out = fullfile(base, 'out');
logs = fullfile(root, 'research', 'round5_20261031', 'matlab', 'logs');
if exist(out, 'dir') ~= 7, mkdir(out); end
if exist(logs, 'dir') ~= 7, mkdir(logs); end
log_path = fullfile(logs, 'indep_verify.log');
if exist(log_path, 'file') == 2, delete(log_path); end
diary(log_path); diary on;
diary_cleanup = onCleanup(@() diary('off')); %#ok<NASGU>

fprintf('== indep_verify ==\n');
fprintf('now_local      : %s\n', datestr(now, 31));
fprintf('matlab_version : %s\n', version);
fprintf('matlab_release : %s\n', matlabRelease.Release);
fprintf('license MATLAB : %d\n', license('test', 'MATLAB'));
fprintf('project_root   : %s\n', root);

checks = struct('check_id', {}, 'expected', {}, 'actual', {}, 'abs_diff', {}, ...
    'tolerance', {}, 'unit', {}, 'pass', {});

% ---------------- 1. facility cost, k=0/1/2 x half/full day ----------------
fp = readtable(fullfile(inp, 'facility_params.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
P = containers.Map(cellstr(fp.key), num2cell(double(fp.value)));
fc = readtable(fullfile(inp, 'facility_cases.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
money_tol = 'money(1e-4/1e-6)';
for i = 1:height(fc)
    k = double(fc.k(i)); days = double(fc.days(i));
    branch = string(fc.branch(i));
    if branch == "annual"
        daily = P('depreciation_annual') / 365;
    else
        daily = P('depreciation_capex') / P('depreciation_life_years') / 365;
    end
    capital = k * daily * days;
    maintenance = k * P('maintenance_per_bay_day') * days;
    fixed = P('facility_fixed_cost_per_day') * days;
    value = capital + maintenance + fixed;
    checks = add_check(checks, char(fc.case_id(i)), double(fc.expected(i)), value, ...
        money_tol, 'TWD', root);
    if k == 0
        checks = add_check(checks, [char(fc.case_id(i)) '_capital_zero'], 0, capital, ...
            money_tol, 'TWD', root);
        checks = add_check(checks, [char(fc.case_id(i)) '_maintenance_zero'], 0, maintenance, ...
            money_tol, 'TWD', root);
    end
end

% ---------------- 2. energy ledger: 14 kWh, 7 kW, 60 min -------------------
en = readtable(fullfile(inp, 'energy_params.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
EP = containers.Map(cellstr(en.key), num2cell(double(en.value)));
ev = readtable(fullfile(inp, 'energy_cases.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
ee = readtable(fullfile(inp, 'energy_expected.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
led1 = energy_ledger(ev, EP('charger_kw'), EP('efficiency'), EP('horizon_min'), ...
    EP('initial_occupancy_n'));
led09 = energy_ledger(ev, EP('charger_kw'), 0.9, EP('horizon_min'), ...
    EP('initial_occupancy_n'));
for i = 1:height(ee)
    id = char(ee.check_id(i));
    expected = double(ee.expected(i));
    unit = char(ee.unit(i));
    switch unit
        case 'count'
            tol = 'count(exact)';
        case 'min'
            tol = 'minutes(1e-9/1e-12)';
        otherwise
            tol = 'energy(1e-9/1e-12)';
    end
    pref = 'eff09_';
    if startsWith(id, pref)
        led = led09; key = extractAfter(id, pref);
    else
        led = led1; key = id;
    end
    switch key
        case 'v1_required_min', actual = led.vehicles(1).required_min;
        case 'v1_deliverable_kwh', actual = led.vehicles(1).deliverable_kwh;
        case 'v1_departed_shortfall_kwh', actual = led.vehicles(1).departed_shortfall_kwh;
        case 'v1_pending_kwh', actual = led.vehicles(1).pending_kwh;
        case 'v2_censored', actual = double(led.vehicles(2).censored);
        case 'v2_deliverable_kwh', actual = led.vehicles(2).deliverable_kwh;
        case 'v2_departed_shortfall_kwh', actual = led.vehicles(2).departed_shortfall_kwh;
        case 'v2_pending_kwh', actual = led.vehicles(2).pending_kwh;
        case 'v4_deliverable_kwh', actual = led.vehicles(4).deliverable_kwh;
        case 'v4_pending_kwh', actual = led.vehicles(4).pending_kwh;
        case 'total_demand_kwh', actual = led.totals.demand_kwh;
        case 'total_required_min', actual = led.totals.required_min;
        case 'total_deliverable_kwh', actual = led.totals.deliverable_kwh;
        case 'total_departed_shortfall_kwh', actual = led.totals.departed_shortfall_kwh;
        case 'total_pending_kwh', actual = led.totals.pending_kwh;
        case 'n_charge_sessions', actual = led.totals.n_charge;
        case 'censored_sessions', actual = led.totals.n_censored;
        case 'charge_shortfall_sessions', actual = led.totals.n_short;
        otherwise, error('indep_verify:key', 'Unknown energy key %s', key);
    end
    checks = add_check(checks, id, expected, actual, tol, unit, root);
end

% ---------------- 3. Erlang-B, including zero load -------------------------
er = readtable(fullfile(inp, 'erlang_expected.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
prob_tol = 'probability(1e-12)';
for i = 1:height(er)
    a = double(er.offered_load(i)); c = double(er.servers(i));
    b = erlang_b(a, c);
    checks = add_check(checks, char(er.case_id(i)), double(er.expected(i)), b, ...
        prob_tol, 'probability', root);
    bc = erlang_b_closed(a, c);
    checks = add_check(checks, [char(er.case_id(i)) '_closed_form'], b, bc, ...
        prob_tol, 'probability', root);
end
ms = readtable(fullfile(inp, 'min_servers_expected.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
for i = 1:height(ms)
    kk = min_servers_for_blocking(double(ms.offered_load(i)), ...
        double(ms.target_blocking(i)), double(ms.k_max(i)));
    if isnan(kk), kk = NaN; end
    checks = add_check(checks, char(ms.case_id(i)), double(ms.expected_k(i)), kk, ...
        'count(exact)', 'connectors', root);
end

% ---------------- 4. small service table and integer search ----------------
sc = readtable(fullfile(inp, 'service_cases.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
for i = 1:height(sc)
    byk = parse_byk(char(sc.by_k(i)));
    search_max = double(sc.search_max(i));
    if isnan(search_max), search_max = []; end
    budget = double(sc.budget_max(i));
    if isnan(budget), budget = []; end
    res = service_level_search(byk, double(sc.alpha(i)), search_max, budget);
    actual_k = NaN; if ~isempty(res.k), actual_k = res.k; end
    checks = add_check(checks, [char(sc.scenario_id(i)) '_k'], ...
        double(sc.expected_k(i)), actual_k, 'count(exact)', 'connectors', root);
    checks = add_check(checks, [char(sc.scenario_id(i)) '_status'], ...
        char(sc.expected_status(i)), res.status, 'status(exact)', 'status', root);
    checks = add_check(checks, [char(sc.scenario_id(i)) '_boundary'], ...
        double(sc.expected_boundary(i)), double(res.boundary), 'count(exact)', 'bool', root);
end
rc = readtable(fullfile(inp, 'recommendation_cases.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
for i = 1:height(rc)
    seed_text = rc.per_seed(i);
    if ismissing(seed_text), seed_text = ""; end
    seeds = parse_seeds(char(seed_text));
    res = integer_recommendation(seeds, double(rc.cap(i)));
    id = char(rc.scenario_id(i));
    checks = add_check(checks, [id '_median'], double(rc.expected_median(i)), ...
        num_or_nan(res.median), 'count(exact)', 'k', root);
    checks = add_check(checks, [id '_q90'], double(rc.expected_q90(i)), ...
        num_or_nan(res.q90), 'count(exact)', 'k', root);
    checks = add_check(checks, [id '_k'], double(rc.expected_k(i)), ...
        num_or_nan(res.recommended_k), 'count(exact)', 'k', root);
    checks = add_check(checks, [id '_status'], char(rc.expected_status(i)), ...
        res.status, 'status(exact)', 'status', root);
end

% ---------------- 5-6. A/B/D deterministic trajectory ----------------------
tp = readtable(fullfile(inp, 'trajectory_params.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
TP = containers.Map(cellstr(tp.key), num2cell(double(tp.value)));
tr = readtable(fullfile(inp, 'trajectory.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
te = readtable(fullfile(inp, 'trajectory_expected.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
tb = readtable(fullfile(inp, 'trajectory_expected_bay.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
rule_names = {'A', 'B', 'D'};
visits_all = {};
for r = 1:numel(rule_names)
    rule = rule_names{r};
    sim = simulate_trajectory(tr, TP, rule);
    visits_all{r} = sim; %#ok<NASGU>
    for i = 1:height(te)
        if string(te.rule(i)) ~= string(rule), continue; end
        metric = char(te.metric(i));
        expected = double(te.expected(i));
        unit = char(te.unit(i));
        actual = sim.metrics.(metric);
        tol = metric_tolerance(unit);
        checks = add_check(checks, sprintf('%s_%s', rule, metric), expected, actual, ...
            tol, unit, root);
    end
    for i = 1:height(tb)
        if string(tb.rule(i)) ~= string(rule), continue; end
        id = double(tb.vehicle_id(i));
        j = find(double(tr.vehicle_id) == id, 1);
        checks = add_check(checks, sprintf('%s_v%d_admitted', rule, id), ...
            double(tb.expected_admitted(i)), double(sim.admitted(j)), 'count(exact)', 'bool', root);
        checks = add_check(checks, sprintf('%s_v%d_bay', rule, id), ...
            double(tb.expected_bay(i)), double(sim.bay(j)), 'count(exact)', 'bay', root);
    end
end
% same-instant batch at t=0 and immediate occupancy
checks = add_check(checks, 't0_batch_occupancy', 3, ...
    sum(double(tr.time_min) == 0), 'count(exact)', 'vehicles', root);
checks = add_check(checks, 't0_batch_order_unique', 3, ...
    numel(unique(double(tr.vehicle_id(tr.time_min == 0)))), 'count(exact)', 'vehicles', root);

% ---------------- output ---------------------------------------------------
n = numel(checks);
table_rows = cell(n, 7);
for i = 1:n
    table_rows(i, :) = {checks(i).check_id, checks(i).expected, checks(i).actual, ...
        checks(i).abs_diff, checks(i).tolerance, checks(i).unit, checks(i).pass};
end
tbl = cell2table(table_rows, 'VariableNames', {'check_id', 'expected', 'actual', ...
    'abs_diff', 'tolerance', 'unit', 'pass'});
writetable(tbl, fullfile(out, 'indep_checks.csv'));
fprintf('\n%-34s %-16s %-16s %-10s %s\n', 'check_id', 'expected', 'actual', 'abs_diff', 'pass');
for i = 1:n
    if ischar(checks(i).actual)
        fprintf('%-34s %-16s %-16s %-10s %d\n', checks(i).check_id, checks(i).expected, ...
            checks(i).actual, '-', checks(i).pass);
    else
        fprintf('%-34s %-16.10g %-16.10g %-10.3e %d\n', checks(i).check_id, ...
            checks(i).expected, checks(i).actual, checks(i).abs_diff, checks(i).pass);
    end
end
% trajectory visits for audit
vrows = cell(0, 9);
for r = 1:numel(rule_names)
    sim = simulate_trajectory(tr, TP, rule_names{r});
    for j = 1:numel(sim.visits)
        v = sim.visits(j);
        vrows(end + 1, :) = {rule_names{r}, v.vehicle_id, v.time_min, ...
            double(v.is_ev), double(v.needs_charge), double(v.admitted), v.bay, ...
            v.departure_min, v.delivered_kwh}; %#ok<AGROW>
    end
end
vtbl = cell2table(vrows, 'VariableNames', {'rule', 'vehicle_id', 'time_min', ...
    'is_ev', 'needs_charge', 'admitted', 'bay', 'departure_min', 'delivered_kwh'});
writetable(vtbl, fullfile(out, 'trajectory_visits.csv'));

n_pass = sum([checks.pass]);
summary = struct();
summary.generated_local = datestr(now, 31);
summary.matlab_version = version;
summary.matlab_release = matlabRelease.Release;
summary.license_matlab = license('test', 'MATLAB');
summary.n_checks = n;
summary.n_pass = n_pass;
summary.n_fail = n - n_pass;
summary.failed = {checks(~[checks.pass]).check_id};
summary.all_pass = n_pass == n;
json_path = fullfile(out, 'indep_summary.json');
fid = fopen(json_path, 'w', 'n', 'UTF-8');
fprintf(fid, '%s\n', jsonencode(summary));
fclose(fid);
fprintf('\nchecks: %d pass, %d fail  -> %s\n', n_pass, n - n_pass, json_path);
if n_pass ~= n
    error('indep_verify:fail', '%d of %d independent checks failed; see %s', ...
        n - n_pass, n, log_path);
end
fprintf('ALL INDEPENDENT CHECKS PASSED\n');
end

% =========================================================================
function checks = add_check(checks, id, expected, actual, tol, unit, root) %#ok<INUSD>
entry = struct('check_id', id, 'expected', expected, 'actual', actual, ...
    'abs_diff', NaN, 'tolerance', tol, 'unit', unit, 'pass', false);
if ischar(actual)
    entry.abs_diff = NaN;
    entry.pass = strcmp(expected, actual);
else
    if ~isfinite(expected) || ~isfinite(actual)
        entry.pass = isequaln(expected, actual);
        entry.abs_diff = 0;
    else
        entry.abs_diff = abs(expected - actual);
        switch tol
            case 'money(1e-4/1e-6)'
                entry.pass = entry.abs_diff <= 1e-4 || ...
                    entry.abs_diff <= 1e-6 * max(abs(expected), abs(actual));
            case 'probability(1e-12)'
                entry.pass = entry.abs_diff <= 1e-12;
            case 'energy(1e-9/1e-12)'
                entry.pass = entry.abs_diff <= 1e-9 || ...
                    entry.abs_diff <= 1e-12 * max(abs(expected), abs(actual));
            case 'minutes(1e-9/1e-12)'
                entry.pass = entry.abs_diff <= 1e-9 || ...
                    entry.abs_diff <= 1e-12 * max(abs(expected), abs(actual));
            otherwise % count(exact)
                entry.pass = entry.abs_diff <= 1e-12;
        end
    end
end
checks(end + 1) = entry;
end

function tol = metric_tolerance(unit)
switch unit
    case 'count', tol = 'count(exact)';
    case 'probability', tol = 'probability(1e-12)';
    case 'kwh', tol = 'energy(1e-9/1e-12)';
    otherwise, tol = 'minutes(1e-9/1e-12)';
end
end

% =========================================================================
function led = energy_ledger(rows, charger_kw, efficiency, horizon, initial_n)
cap_per_hour = charger_kw * efficiency;
cap_per_min = cap_per_hour / 60;
n = height(rows);
vehicles = struct('vehicle_id', {}, 'demand_kwh', {}, 'required_min', {}, ...
    'deliverable_kwh', {}, 'departed_shortfall_kwh', {}, 'pending_kwh', {}, ...
    'censored', {}, 'short', {});
tot = struct('demand_kwh', 0, 'required_min', 0, 'deliverable_kwh', 0, ...
    'departed_shortfall_kwh', 0, 'pending_kwh', 0, 'n_charge', 0, ...
    'n_censored', 0, 'n_short', 0, 'initial_demand_kwh', 0);
for i = 1:n
    needs = double(rows.needs_charge(i)) ~= 0;
    demand = 0; if needs, demand = double(rows.energy_kwh(i)); end
    required = 0; if demand > 0, required = demand / cap_per_hour * 60; end
    t = double(rows.time_min(i)); dwell = double(rows.dwell_min(i));
    departure = t + dwell;
    censored = departure > horizon + 1e-9;
    stay = dwell;
    if censored, stay = max(0, min(dwell, horizon - t)); end
    deliverable = min(demand, cap_per_min * stay);
    if censored
        gap = 0; pending = demand - deliverable;
    else
        gap = demand - deliverable; pending = 0;
    end
    short = ~censored && gap > 1e-9;
    v = struct('vehicle_id', double(rows.vehicle_id(i)), 'demand_kwh', demand, ...
        'required_min', required, 'deliverable_kwh', deliverable, ...
        'departed_shortfall_kwh', gap, 'pending_kwh', pending, ...
        'censored', logical(censored), 'short', logical(short));
    if i <= initial_n, tot.initial_demand_kwh = tot.initial_demand_kwh + demand; end
    if demand > 0
        tot.n_charge = tot.n_charge + 1;
        tot.n_censored = tot.n_censored + double(censored);
    end
    tot.n_short = tot.n_short + double(short);
    tot.demand_kwh = tot.demand_kwh + demand;
    tot.required_min = tot.required_min + required;
    tot.deliverable_kwh = tot.deliverable_kwh + deliverable;
    tot.departed_shortfall_kwh = tot.departed_shortfall_kwh + gap;
    tot.pending_kwh = tot.pending_kwh + pending;
    vehicles(end + 1) = v; %#ok<AGROW>
end
led = struct('vehicles', vehicles, 'totals', tot);
end

% =========================================================================
function b = erlang_b(a, c)
b = 1.0;
for i = 1:c
    b = (a * b) / (i + a * b);
end
end

function b = erlang_b_closed(a, c)
if a == 0
    b = 0.0; return
end
la = log(a);
terms = zeros(1, c + 1);
for n = 0:c
    terms(n + 1) = n * la - gammaln(n + 1);
end
top = max(terms);
total = sum(exp(terms - top));
b = exp(terms(end) - top) / total;
end

function k = min_servers_for_blocking(a, target, kmax)
if a == 0
    k = 0; return
end
k = NaN;
for c = 1:kmax
    if erlang_b(a, c) <= target
        k = c; return
    end
end
end

% =========================================================================
function values = parse_byk(text)
parts = strsplit(text, ';', 'CollapseDelimiters', false);
values = containers.Map('KeyType', 'double', 'ValueType', 'double');
for k = 0:numel(parts) - 1
    token = strtrim(parts{k + 1});
    if ~isempty(token)
        values(double(k)) = str2double(token);
    end
end
end

function res = service_level_search(values, alpha, search_max, budget)
data_max = [];
if values.Count > 0, data_max = max(cell2mat(keys(values))); end
limits = [];
if ~isempty(data_max), limits(end + 1) = data_max; end
if ~isempty(search_max), limits(end + 1) = search_max; end
if ~isempty(budget), limits(end + 1) = budget; end
evaluated_max = [];
if ~isempty(limits) && ~isempty(data_max), evaluated_max = min(limits); end
res = struct('status', '', 'k', [], 'evaluated_max', evaluated_max, ...
    'baseline', [], 'boundary', false);
if ~isKey(values, 0)
    res.status = 'missing_data'; return
end
baseline = values(0);
if baseline == 0
    res.status = 'no_demand'; res.k = 0; return
end
if isempty(search_max)
    target_bound = data_max;
else
    target_bound = search_max;
end
threshold = alpha * baseline;
tolerance = 1e-9 * max(1, abs(threshold));
for count = 1:evaluated_max
    if ~isKey(values, count)
        res.status = 'missing_data'; return
    end
    value = values(count);
    if value <= threshold + tolerance
        res.status = 'achieved';
        res.k = count;
        res.boundary = count == target_bound;
        return
    end
end
if ~isempty(evaluated_max) && ~isempty(target_bound) && evaluated_max >= target_bound
    res.status = 'infeasible_upper_bound'; return
end
res.status = 'budget_exhausted';
end

function seeds = parse_seeds(text)
if isempty(strtrim(text))
    seeds = [];
    return
end
parts = strsplit(text, ';', 'CollapseDelimiters', false);
seeds = cell(1, numel(parts));
for i = 1:numel(parts)
    token = strtrim(parts{i});
    if isempty(token)
        seeds{i} = [];
    else
        seeds{i} = str2double(token);
    end
end
end

function res = integer_recommendation(seeds, cap) %#ok<INUSD>
res = struct('median', [], 'q90', [], 'recommended_k', [], 'status', '');
if isempty(seeds)
    res.status = 'missing_data'; return
end
known = [];
missing = 0;
for i = 1:numel(seeds)
    if isempty(seeds{i}), missing = missing + 1; else, known(end + 1) = seeds{i}; end %#ok<AGROW>
end
known = sort(known);
if isempty(known)
    res.status = 'lower_bound'; return
end
count = numel(known);
if mod(count, 2) == 1
    median = known((count + 1) / 2);
else
    lo = known(count / 2); hi = known(count / 2 + 1);
    if lo == hi, median = lo; else, median = (lo + hi) / 2; end
end
rank = max(1, ceil(0.9 * count));
q90 = known(rank);
res.median = median; res.q90 = q90;
if missing > 0
    res.status = 'lower_bound'; return
end
if median ~= fix(median)
    res.recommended_k = ceil(median);
    res.status = 'statistical_summary_not_installable'; return
end
res.recommended_k = median;
res.status = 'ok';
end

function v = num_or_nan(x)
if isempty(x), v = NaN; else, v = x; end
end

% =========================================================================
function sim = simulate_trajectory(rows, P, rule)
n = P('n_spaces'); chargers = P('chargers'); charging_bays = P('charging_bays');
horizon = P('horizon_min'); power = P('power_kw'); eff = P('efficiency');
cap_per_min = power * eff / 60;
[~, ord] = sortrows([double(rows.time_min), double(rows.vehicle_id)]);
rows = rows(ord, :);
m = height(rows);
occ = zeros(1, n);
bay = -ones(m, 1);
admitted = false(m, 1);
released = false(m, 1);
departure = double(rows.time_min) + double(rows.dwell_min);
peak = 0;
for i = 1:m
    t = double(rows.time_min(i));
    % end events strictly before this arrival: free bays
    for j = 1:i - 1
        if admitted(j) && ~released(j) && departure(j) <= t + 1e-12
            occ(bay(j) + 1) = 0;
            released(j) = true;
        end
    end
    free = find(occ == 0) - 1;
    equipped = free(free < chargers);
    designated = free(free >= chargers & free < charging_bays);
    ordinary = free(free >= charging_bays);
    is_ev = double(rows.is_ev(i)) ~= 0;
    candidate = [];
    if is_ev
        candidate = [equipped, designated, ordinary];
    else
        switch rule
            case 'A'
                candidate = ordinary;
            case 'B'
                candidate = [ordinary, equipped, designated];
            case 'D'
                if ~isempty(ordinary)
                    candidate = [ordinary, equipped, designated];
                else
                    free_charging = numel(equipped) + numel(designated);
                    usable = free_charging - 1;
                    expected = P('arrival_rate_per_hour') / 60 * P('p_ev') * ...
                        P('p_charge_given_ev') * P('prediction_window_min');
                    slack = usable - expected;
                    if free_charging > 0 && slack >= P('safety_margin') - 1e-9
                        candidate = [equipped, designated];
                    end
                end
        end
    end
    if ~isempty(candidate)
        bay(i) = candidate(1);
        admitted(i) = true;
        occ(bay(i) + 1) = 1;
    end
    peak = max(peak, sum(occ));
end
for j = 1:m
    if admitted(j) && ~released(j) && departure(j) <= horizon + 1e-12
        released(j) = true;
    end
end
visits = struct('vehicle_id', {}, 'time_min', {}, 'is_ev', {}, 'needs_charge', {}, ...
    'admitted', {}, 'bay', {}, 'departure_min', {}, 'delivered_kwh', {});
delivered = zeros(m, 1);
for i = 1:m
    if admitted(i) && double(rows.needs_charge(i)) ~= 0
        end_min = min(departure(i), horizon);
        delivered(i) = min(double(rows.energy_kwh(i)), cap_per_min * (end_min - double(rows.time_min(i))));
    end
    visits(end + 1) = struct('vehicle_id', double(rows.vehicle_id(i)), ...
        'time_min', double(rows.time_min(i)), 'is_ev', logical(rows.is_ev(i)), ...
        'needs_charge', logical(rows.needs_charge(i)), 'admitted', admitted(i), ...
        'bay', bay(i), 'departure_min', departure(i), 'delivered_kwh', delivered(i)); %#ok<AGROW>
end
metrics = trajectory_metrics(rows, admitted, bay, departure, delivered, peak, P, chargers);
sim = struct('admitted', admitted, 'bay', bay, 'visits', visits, 'metrics', metrics);
end

function s = trajectory_metrics(rows, admitted, bay, departure, delivered, peak, P, chargers)
m = numel(admitted);
horizon = P('horizon_min');
n_spaces = P('n_spaces');
rejected = sum(~admitted);
in_window = double(rows.time_min) >= 0 & double(rows.time_min) < horizon;
is_initial = double(rows.initial) ~= 0;
departed = admitted & departure <= horizon + 1e-12;
censored = admitted & ~departed & (in_window | is_initial);
total_bay_minutes = 0; charging_bay_minutes = 0; ice_blocking = 0; delivered_kwh = 0;
n_released = sum(admitted & departure <= horizon + 1e-12);
num_unmet = 0; num_ev_fail = 0; num_ice_fail = 0; num_short = 0;
den_ev = 0; den_ice = 0; den_req = 0; req_kwh = 0;
pending_count = 0; pending_energy = 0;
for i = 1:m
    stay = 0;
    if admitted(i)
        stay = min(departure(i), horizon) - double(rows.time_min(i));
    end
    total_bay_minutes = total_bay_minutes + stay;
    if admitted(i) && bay(i) >= 0 && bay(i) < chargers
        charging_bay_minutes = charging_bay_minutes + stay;
        if double(rows.is_ev(i)) == 0
            ice_blocking = ice_blocking + stay;
        end
    end
    if censored(i) && double(rows.is_ev(i)) ~= 0 && double(rows.needs_charge(i)) ~= 0
        pending_count = pending_count + 1;
        pending_energy = pending_energy + max(0, double(rows.energy_kwh(i)) - delivered(i));
    end
    if is_initial(i) || ~in_window(i)
        continue
    end
    if double(rows.is_ev(i)) ~= 0
        den_ev = den_ev + 1;
        if ~admitted(i), num_ev_fail = num_ev_fail + 1; end
    else
        den_ice = den_ice + 1;
        if ~admitted(i), num_ice_fail = num_ice_fail + 1; end
    end
    if ~(double(rows.is_ev(i)) ~= 0 && double(rows.needs_charge(i)) ~= 0)
        continue
    end
    den_req = den_req + 1;
    if ~admitted(i)
        num_unmet = num_unmet + 1;
        continue
    end
    if ~departed(i)
        continue
    end
    requested = double(rows.energy_kwh(i));
    shortfall = max(0, requested - delivered(i));
    req_kwh = req_kwh + requested;
    num_short = num_short + shortfall;
    if shortfall > 1e-9
        num_unmet = num_unmet + 1;
    end
    delivered_kwh = delivered_kwh + delivered(i);
end
% delivered_kwh for censored sessions is also part of delivered energy
for i = 1:m
    if admitted(i) && ~departed(i)
        delivered_kwh = delivered_kwh + delivered(i);
    end
end
s = struct();
s.rejected = rejected;
s.peak_occupancy = peak;
s.released = n_released;
s.total_bay_minutes = total_bay_minutes;
s.charging_bay_minutes = charging_bay_minutes;
s.ice_blocking_minutes = ice_blocking;
s.delivered_kwh = delivered_kwh;
s.ev_parking_failure_rate = ratio(num_ev_fail, den_ev);
s.ice_parking_failure_rate = ratio(num_ice_fail, den_ice);
s.capacity_unmet_rate = ratio(num_unmet, den_req);
s.departed_shortfall_energy_rate = ratio(num_short, req_kwh);
s.pending_count = pending_count;
s.pending_energy_kwh = pending_energy;
s.n_spaces = n_spaces;
end

function r = ratio(a, b)
if b == 0, r = NaN; else, r = a / b; end
end
