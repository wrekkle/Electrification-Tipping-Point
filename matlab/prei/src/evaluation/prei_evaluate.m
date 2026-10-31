function result = prei_evaluate(cfg, scenarios)
%PREI_EVALUATE Enumerate every configured pile ratio on one fixed scenario set.
%
%   No sampling happens here. Every candidate reads the same rows from
%   scenarios. The raw cost matrix is n_candidates x n_days. Ties are formed
%   with atol=1e-8 RMB and rtol=1e-10 using only the cost values (no display
%   mask). g_full_minus_best_partial = C_full - min(C_partial) and
%   delta_candidate_minus_full = C_candidate - C_full.

atol = 1e-8;
rtol = 1e-10;

if ~isstruct(cfg) || ~isfield(cfg, 'pile_ratios')
    error('prei:evaluate:config', 'A validated configuration struct is required.');
end
if ~isstruct(scenarios) || ~isfield(scenarios, 'n_days')
    error('prei:evaluate:scenarios', 'A loaded scenario struct is required.');
end
ratios = cfg.pile_ratios(:);
n_ratios = numel(ratios);
full_index = find(ratios == 1, 1);
if isempty(full_index)
    error('prei:evaluate:noFull', 'pile_ratios must include 1.0 for the full-installation comparison.');
end
partial_index = find(ratios < 1);

n_days = scenarios.n_days;
raw = zeros(n_ratios, n_days);
ev_refused_daily = zeros(n_ratios, n_days);
ice_refused_daily = zeros(n_ratios, n_days);
capital = zeros(n_ratios, 1);
ev_fuel = zeros(n_ratios, 1);
ice_fuel = zeros(n_ratios, 1);
ev_time = zeros(n_ratios, 1);
ice_time = zeros(n_ratios, 1);
ev_complaint = zeros(n_ratios, 1);
ice_complaint = zeros(n_ratios, 1);
fuel = zeros(n_ratios, 1);
time = zeros(n_ratios, 1);
complaint = zeros(n_ratios, 1);
total = zeros(n_ratios, 1);
branch = cell(n_ratios, 1);
allocation = cell(n_ratios, 1);
daily_capital = zeros(n_ratios, n_days);
daily_ev_fuel = zeros(n_ratios, n_days);
daily_ice_fuel = zeros(n_ratios, n_days);
daily_ev_time = zeros(n_ratios, n_days);
daily_ice_time = zeros(n_ratios, n_days);
daily_ev_complaint = zeros(n_ratios, n_days);
daily_ice_complaint = zeros(n_ratios, n_days);
daily_total = zeros(n_ratios, n_days);

for i = 1:n_ratios
    alloc = prei_allocate(cfg, ratios(i), scenarios.total_arrivals, ...
        scenarios.ev_share_actual);
    cost = prei_cost(cfg, scenarios, alloc, ratios(i));
    allocation{i} = alloc;
    branch{i} = alloc.branch;
    raw(i, :) = cost.daily_total(:)';
    capital(i) = cost.capital_rmb_per_day;
    ev_fuel(i) = cost.ev_fuel_rmb_per_day;
    ice_fuel(i) = cost.ice_fuel_rmb_per_day;
    ev_time(i) = cost.ev_time_rmb_per_day;
    ice_time(i) = cost.ice_time_rmb_per_day;
    ev_complaint(i) = cost.ev_complaint_rmb_per_day;
    ice_complaint(i) = cost.ice_complaint_rmb_per_day;
    fuel(i) = cost.fuel_rmb_per_day;
    time(i) = cost.time_rmb_per_day;
    complaint(i) = cost.complaint_rmb_per_day;
    total(i) = cost.total_rmb_per_day;
    daily_capital(i, :) = cost.daily.capital_daily_cost(:)';
    daily_ev_fuel(i, :) = cost.daily.ev_fuel_cost(:)';
    daily_ice_fuel(i, :) = cost.daily.ice_fuel_cost(:)';
    daily_ev_time(i, :) = cost.daily.ev_time_cost(:)';
    daily_ice_time(i, :) = cost.daily.ice_time_cost(:)';
    daily_ev_complaint(i, :) = cost.daily.ev_complaint_cost(:)';
    daily_ice_complaint(i, :) = cost.daily.ice_complaint_cost(:)';
    daily_total(i, :) = cost.daily.total_daily_cost(:)';
    for d = 1:n_days
        rows = (scenarios.day_index == d);
        ev_refused_daily(i, d) = sum(alloc.ev_refused(rows));
        ice_refused_daily(i, d) = sum(alloc.ice_refused(rows));
    end
end

targets = cfg.ev_share_targets(:);
n_targets = numel(targets);
target_mean = zeros(n_ratios, n_targets);
for k = 1:n_targets
    cols = find(abs(scenarios.day_targets(:) - targets(k)) <= 1e-12);
    if isempty(cols)
        error('prei:evaluate:targetMissing', ...
            'No scenario day exists for target %.17g.', targets(k));
    end
    target_mean(:, k) = mean(raw(:, cols), 2);
end

g = nan(n_days, 1);
if ~isempty(partial_index)
    g = raw(full_index, :)' - min(raw(partial_index, :), [], 1)';
end
delta = raw - repmat(raw(full_index, :), n_ratios, 1);

best_day = [];
best_candidate = [];
best_pile_ratio = [];
best_cost = [];
best_is_full = [];
best_by_day = cell(n_days, 1);
for d = 1:n_days
    tied = prei_best_set(raw(:, d), atol, rtol);
    best_by_day{d} = tied;
    for k = 1:numel(tied)
        best_day(end + 1, 1) = d;
        best_candidate(end + 1, 1) = tied(k);
        best_pile_ratio(end + 1, 1) = ratios(tied(k));
        best_cost(end + 1, 1) = raw(tied(k), d);
        best_is_full(end + 1, 1) = (tied(k) == full_index);
    end
end

best = struct();
best.day_index = best_day;
best.candidate_index = best_candidate;
best.pile_ratio = best_pile_ratio;
best.cost = best_cost;
best.is_full = logical(best_is_full);
best.by_day = best_by_day;

days = struct();
days.day_id = scenarios.day_ids;
days.ev_share_target = scenarios.day_targets;
days.n_rows = scenarios.rows_per_day;
days.total_arrivals = scenarios.day_total_arrivals;
days.ev_share_actual = scenarios.day_ev_share_actual;

daily_components = struct();
daily_components.capital_daily_cost = daily_capital;
daily_components.ev_rejected = ev_refused_daily;
daily_components.ice_rejected = ice_refused_daily;
daily_components.ev_fuel_cost = daily_ev_fuel;
daily_components.ice_fuel_cost = daily_ice_fuel;
daily_components.ev_time_cost = daily_ev_time;
daily_components.ice_time_cost = daily_ice_time;
daily_components.ev_complaint_cost = daily_ev_complaint;
daily_components.ice_complaint_cost = daily_ice_complaint;
daily_components.total_daily_cost = daily_total;

components = struct();
components.capital = capital;
components.ev_fuel = ev_fuel;
components.ice_fuel = ice_fuel;
components.fuel = fuel;
components.ev_time = ev_time;
components.ice_time = ice_time;
components.time = time;
components.ev_complaint = ev_complaint;
components.ice_complaint = ice_complaint;
components.complaint = complaint;
components.total = total;

result = struct();
result.model_variant = cfg.model_variant;
result.diagnostic_only = strcmp(cfg.model_variant, 'legacy_reference');
result.pile_ratios = ratios;
result.full_index = full_index;
result.partial_index = partial_index;
result.branch = branch;
result.allocation = allocation;
result.raw_cost_matrix = raw;
result.mean_cost_by_candidate = mean(raw, 2);
result.target_mean_cost = target_mean;
result.components = components;
result.daily_components = daily_components;
result.ev_refused_daily = ev_refused_daily;
result.ice_refused_daily = ice_refused_daily;
result.g_full_minus_best_partial = g;
result.delta_candidate_minus_full = delta;
result.best = best;
result.best_by_day = best_by_day;
result.days = days;
result.etp = prei_etp(targets, target_mean, full_index, atol, rtol);
result.tolerance = struct('atol', atol, 'rtol', rtol);
result.targets = targets;
result.n_days = n_days;
result.n_rows = scenarios.n_rows;
end
