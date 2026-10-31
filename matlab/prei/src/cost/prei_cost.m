function out = prei_cost(cfg, scenarios, alloc, pile_ratio)
%PREI_COST Daily cost components in RMB/day for one candidate.
%
%   Capital cost is charged once per scenario-day:
%     N_spaces * pile_ratio * installation_cost_rmb_per_pile / (365*years)
%   Refusal costs are summed over hourly rows and then averaged across
%   scenario-days. Each refused vehicle is charged one fuel, one time and one
%   complaint cost.
%
%   legacy_reference at pile_ratio == 1 drops the EV complaint term, matching
%   the supplied full-installation branch. Every other branch counts both
%   user classes once.

if ~isstruct(cfg) || ~isstruct(scenarios) || ~isstruct(alloc)
    error('prei:cost:input', 'cfg, scenarios and alloc must be structs.');
end
n = scenarios.n_rows;
if numel(alloc.ev_refused) ~= n
    error('prei:cost:length', 'Allocation and scenario row counts differ.');
end
if ~isfield(scenarios, 'day_index') || numel(scenarios.day_index) ~= n
    error('prei:cost:dayIndex', 'scenarios.day_index is missing or has the wrong length.');
end

capital = cfg.n_spaces * pile_ratio * cfg.installation_cost_rmb_per_pile / ...
    (365 * cfg.amortization_years);

ev_fuel_row = alloc.ev_refused .* scenarios.ev_fuel_cost;
ice_fuel_row = alloc.ice_refused .* scenarios.ice_fuel_cost;
ev_time_row = alloc.ev_refused .* scenarios.ev_time_cost;
ice_time_row = alloc.ice_refused .* scenarios.ice_time_cost;
ev_complaint_row = alloc.ev_refused .* scenarios.ev_complaint_cost;
ice_complaint_row = alloc.ice_refused .* scenarios.ice_complaint_cost;

% The received full-installation branch omitted EV complaints. This is kept
% only under the diagnostic legacy label.
if strcmp(cfg.model_variant, 'legacy_reference') && pile_ratio == 1
    ev_complaint_row(:) = 0;
end

n_days = scenarios.n_days;
day_total = capital * ones(n_days, 1);
day_fuel = zeros(n_days, 1);
day_time = zeros(n_days, 1);
day_complaint = zeros(n_days, 1);
day_ev_fuel = zeros(n_days, 1);
day_ice_fuel = zeros(n_days, 1);
day_ev_time = zeros(n_days, 1);
day_ice_time = zeros(n_days, 1);
day_ev_complaint = zeros(n_days, 1);
day_ice_complaint = zeros(n_days, 1);
day_ev_refused = zeros(n_days, 1);
day_ice_refused = zeros(n_days, 1);

for i = 1:n
    d = scenarios.day_index(i);
    refusal = ev_fuel_row(i) + ice_fuel_row(i) + ev_time_row(i) + ...
        ice_time_row(i) + ev_complaint_row(i) + ice_complaint_row(i);
    day_total(d) = day_total(d) + refusal;
    day_fuel(d) = day_fuel(d) + ev_fuel_row(i) + ice_fuel_row(i);
    day_time(d) = day_time(d) + ev_time_row(i) + ice_time_row(i);
    day_complaint(d) = day_complaint(d) + ev_complaint_row(i) + ice_complaint_row(i);
    day_ev_fuel(d) = day_ev_fuel(d) + ev_fuel_row(i);
    day_ice_fuel(d) = day_ice_fuel(d) + ice_fuel_row(i);
    day_ev_time(d) = day_ev_time(d) + ev_time_row(i);
    day_ice_time(d) = day_ice_time(d) + ice_time_row(i);
    day_ev_complaint(d) = day_ev_complaint(d) + ev_complaint_row(i);
    day_ice_complaint(d) = day_ice_complaint(d) + ice_complaint_row(i);
    day_ev_refused(d) = day_ev_refused(d) + alloc.ev_refused(i);
    day_ice_refused(d) = day_ice_refused(d) + alloc.ice_refused(i);
end

out = struct();
out.pile_ratio = pile_ratio;
out.capital_rmb_per_day = capital;
out.ev_fuel_rmb_per_day = mean(day_ev_fuel);
out.ice_fuel_rmb_per_day = mean(day_ice_fuel);
out.fuel_rmb_per_day = mean(day_fuel);
out.ev_time_rmb_per_day = mean(day_ev_time);
out.ice_time_rmb_per_day = mean(day_ice_time);
out.time_rmb_per_day = mean(day_time);
out.ev_complaint_rmb_per_day = mean(day_ev_complaint);
out.ice_complaint_rmb_per_day = mean(day_ice_complaint);
out.complaint_rmb_per_day = mean(day_complaint);
out.total_rmb_per_day = mean(day_total);
out.daily_total = day_total;
out.daily = struct();
out.daily.capital_daily_cost = capital * ones(n_days, 1);
out.daily.ev_rejected = day_ev_refused;
out.daily.ice_rejected = day_ice_refused;
out.daily.ev_fuel_cost = day_ev_fuel;
out.daily.ice_fuel_cost = day_ice_fuel;
out.daily.ev_time_cost = day_ev_time;
out.daily.ice_time_cost = day_ice_time;
out.daily.ev_complaint_cost = day_ev_complaint;
out.daily.ice_complaint_cost = day_ice_complaint;
out.daily.total_daily_cost = day_total;
end
