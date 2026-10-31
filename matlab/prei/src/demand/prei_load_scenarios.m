function scenarios = prei_load_scenarios(cfg, base_dir)
%PREI_LOAD_SCENARIOS Read the fixed CSV fixture shared by all candidates.
%
%   scenarios = prei_load_scenarios(cfg, base_dir)
%
%   Required CSV columns:
%     scenario_id, hour, ev_share_target, total_arrivals, ev_share_actual,
%     ev_fuel_cost, ice_fuel_cost, ev_time_cost, ice_time_cost,
%     ev_complaint_cost, ice_complaint_cost
%
%   Each (scenario_id, ev_share_target) pair is one day. Rows are grouped by
%   that pair and ordered by hour. Every configured ev_share_target must be
%   present, and no unconfigured target is accepted. No sampling occurs here.

if nargin < 2 || isempty(base_dir)
    if isfield(cfg, 'config_dir')
        base_dir = cfg.config_dir;
    else
        base_dir = pwd;
    end
end
if ~ischar(base_dir) || isempty(base_dir)
    error('prei:scenarios:baseDir', 'base_dir must be a nonempty character path.');
end
if ~isstruct(cfg) || ~isfield(cfg, 'fixture_file')
    error('prei:scenarios:config', 'A validated configuration struct is required.');
end

path = fullfile(base_dir, cfg.fixture_file);
if exist(path, 'file') ~= 2
    error('prei:scenarios:missing', 'Scenario fixture not found: %s', path);
end

required = {'scenario_id', 'hour', 'ev_share_target', 'total_arrivals', ...
    'ev_share_actual', 'ev_fuel_cost', 'ice_fuel_cost', 'ev_time_cost', ...
    'ice_time_cost', 'ev_complaint_cost', 'ice_complaint_cost'};

fid = fopen(path, 'r', 'n', 'UTF-8');
if fid < 0
    error('prei:scenarios:open', 'Cannot open scenario fixture: %s', path);
end
file_cleanup = onCleanup(@() fclose(fid));
header_line = fgetl(fid);
if ~ischar(header_line)
    error('prei:scenarios:empty', 'Scenario fixture is empty: %s', path);
end
header_line = regexprep(header_line, '\r$', '');
header = prei_split_csv_line(header_line);
header = cellfun(@strtrim, header, 'UniformOutput', false);
if ~isempty(header) && ~isempty(header{1}) && double(header{1}(1)) == 65279
    header{1} = header{1}(2:end);
end
if numel(unique(header)) ~= numel(header)
    error('prei:scenarios:columns', 'Scenario CSV has duplicate column names.');
end

col = zeros(1, numel(required));
for k = 1:numel(required)
    hit = find(strcmp(header, required{k}), 1);
    if isempty(hit)
        error('prei:scenarios:columns', 'Scenario CSV is missing column: %s.', required{k});
    end
    col(k) = hit;
end

lines = {};
while true
    line = fgetl(fid);
    if ~ischar(line)
        break;
    end
    line = regexprep(line, '\r$', '');
    if ~isempty(strtrim(line))
        lines{end+1, 1} = line;
    end
end
n = numel(lines);
if n == 0
    error('prei:scenarios:rows', 'Scenario fixture contains no data rows.');
end

scenario_id = cell(n, 1);
hour = zeros(n, 1);
ev_share_target = zeros(n, 1);
total_arrivals = zeros(n, 1);
ev_share_actual = zeros(n, 1);
ev_fuel_cost = zeros(n, 1);
ice_fuel_cost = zeros(n, 1);
ev_time_cost = zeros(n, 1);
ice_time_cost = zeros(n, 1);
ev_complaint_cost = zeros(n, 1);
ice_complaint_cost = zeros(n, 1);

for i = 1:n
    fields = prei_split_csv_line(lines{i});
    if numel(fields) ~= numel(header)
        error('prei:scenarios:rowWidth', ...
            'Row %d has %d fields; header has %d.', i + 1, numel(fields), numel(header));
    end
    scenario_id{i} = strtrim(fields{col(1)});
    if isempty(scenario_id{i})
        error('prei:scenarios:id', 'Row %d has an empty scenario_id.', i + 1);
    end
    values = zeros(10, 1);
    for k = 2:11
        token = strtrim(fields{col(k)});
        value = str2double(token);
        if isempty(token) || ~isfinite(value)
            error('prei:scenarios:numeric', ...
                'Row %d column %s is not a finite number.', i + 1, required{k});
        end
        values(k - 1) = value;
    end
    hour(i) = values(1);
    ev_share_target(i) = values(2);
    total_arrivals(i) = values(3);
    ev_share_actual(i) = values(4);
    ev_fuel_cost(i) = values(5);
    ice_fuel_cost(i) = values(6);
    ev_time_cost(i) = values(7);
    ice_time_cost(i) = values(8);
    ev_complaint_cost(i) = values(9);
    ice_complaint_cost(i) = values(10);

    if abs(hour(i) - round(hour(i))) > 1e-12 || hour(i) < 0 || hour(i) > 23
        error('prei:scenarios:hour', ...
            'Row %d has a non-integer hour outside 0..23.', i + 1);
    end
    if ev_share_target(i) < 0 || ev_share_target(i) > 1
        error('prei:scenarios:target', 'Row %d ev_share_target is outside [0,1].', i + 1);
    end
    if total_arrivals(i) < 0
        error('prei:scenarios:demand', 'Row %d total_arrivals is negative.', i + 1);
    end
    if ev_share_actual(i) < 0 || ev_share_actual(i) > 1
        error('prei:scenarios:actualShare', 'Row %d ev_share_actual is outside [0,1].', i + 1);
    end
    costs = values(5:10);
    if any(costs < 0)
        error('prei:scenarios:cost', 'Row %d has a negative cost.', i + 1);
    end
end

day_index = zeros(n, 1);
day_ids = {};
day_targets = [];
for i = 1:n
    found = 0;
    for d = 1:numel(day_ids)
        if strcmp(day_ids{d}, scenario_id{i}) && ...
                abs(day_targets(d) - ev_share_target(i)) <= 1e-12
            found = d;
            break;
        end
    end
    if found == 0
        day_ids{end+1, 1} = scenario_id{i};
        day_targets(end+1, 1) = ev_share_target(i);
        found = numel(day_ids);
    end
    day_index(i) = found;
end
n_days = numel(day_ids);

rows_per_day = zeros(n_days, 1);
day_total_arrivals = zeros(n_days, 1);
day_ev_share_actual = zeros(n_days, 1);
rate_names = {'ev_fuel_cost', 'ice_fuel_cost', 'ev_time_cost', ...
    'ice_time_cost', 'ev_complaint_cost', 'ice_complaint_cost'};
rate_values = [ev_fuel_cost, ice_fuel_cost, ev_time_cost, ...
    ice_time_cost, ev_complaint_cost, ice_complaint_cost];
for d = 1:n_days
    idx = find(day_index == d);
    h = hour(idx);
    if numel(idx) ~= 24 || any(sort(h) ~= (0:23)')
        error('prei:scenarios:hours', ...
            'Day %s at target %.17g must contain hours 0..23 exactly once.', ...
            day_ids{d}, day_targets(d));
    end
    reference_rates = rate_values(idx(1), :);
    rate_delta = abs(rate_values(idx, :) - repmat(reference_rates, numel(idx), 1));
    if any(rate_delta(:) > 1e-12)
        [~, bad_col] = find(rate_delta > 1e-12, 1);
        error('prei:scenarios:variableRate', ...
            'Day %s at target %.17g changes unit rate %s inside the day.', ...
            day_ids{d}, day_targets(d), rate_names{bad_col});
    end
    rows_per_day(d) = numel(idx);
    day_total_arrivals(d) = sum(total_arrivals(idx));
    if day_total_arrivals(d) > 0
        day_ev_share_actual(d) = sum(total_arrivals(idx) .* ev_share_actual(idx)) / ...
            day_total_arrivals(d);
    else
        day_ev_share_actual(d) = day_targets(d);
    end
end

% Canonical order: days in first-appearance order, hours ascending inside each.
order = zeros(n, 1);
cursor = 0;
for d = 1:n_days
    idx = find(day_index == d);
    [~, ord] = sort(hour(idx));
    order(cursor + (1:numel(idx))) = idx(ord);
    cursor = cursor + numel(idx);
end

scenario_id = scenario_id(order);
hour = hour(order);
ev_share_target = ev_share_target(order);
total_arrivals = total_arrivals(order);
ev_share_actual = ev_share_actual(order);
ev_fuel_cost = ev_fuel_cost(order);
ice_fuel_cost = ice_fuel_cost(order);
ev_time_cost = ev_time_cost(order);
ice_time_cost = ice_time_cost(order);
ev_complaint_cost = ev_complaint_cost(order);
ice_complaint_cost = ice_complaint_cost(order);
day_index = day_index(order);

% Targets in the fixture and in the configuration must be the same set.
for d = 1:n_days
    if ~any(abs(cfg.ev_share_targets - day_targets(d)) <= 1e-12)
        error('prei:scenarios:targetUnconfigured', ...
            'Fixture target %.17g is not listed in ev_share_targets.', day_targets(d));
    end
end
for k = 1:numel(cfg.ev_share_targets)
    if ~any(abs(day_targets - cfg.ev_share_targets(k)) <= 1e-12)
        error('prei:scenarios:targetMissing', ...
            'Configured ev_share_target %.17g has no fixture day.', cfg.ev_share_targets(k));
    end
end

scenarios = struct();
scenarios.scenario_id = scenario_id;
scenarios.hour = hour;
scenarios.ev_share_target = ev_share_target;
scenarios.total_arrivals = total_arrivals;
scenarios.ev_share_actual = ev_share_actual;
scenarios.ev_fuel_cost = ev_fuel_cost;
scenarios.ice_fuel_cost = ice_fuel_cost;
scenarios.ev_time_cost = ev_time_cost;
scenarios.ice_time_cost = ice_time_cost;
scenarios.ev_complaint_cost = ev_complaint_cost;
scenarios.ice_complaint_cost = ice_complaint_cost;
scenarios.day_index = day_index;
scenarios.day_ids = day_ids;
scenarios.day_targets = day_targets;
scenarios.rows_per_day = rows_per_day;
scenarios.day_total_arrivals = day_total_arrivals;
scenarios.day_ev_share_actual = day_ev_share_actual;
scenarios.n_rows = n;
scenarios.n_days = n_days;
scenarios.column_names = header;
scenarios.source_path = prei_abspath(path);
scenarios.source_sha256 = prei_hash_file(path);
end

function fields = prei_split_csv_line(line)
% Minimal CSV splitter with doubled-quote support; commas inside quotes are
% kept as data. The fixture schema has no multiline fields.
fields = {};
current = '';
in_quotes = false;
i = 1;
while i <= numel(line)
    ch = line(i);
    if in_quotes
        if ch == '"'
            if i < numel(line) && line(i + 1) == '"'
                current(end + 1) = '"';
                i = i + 2;
                continue;
            end
            in_quotes = false;
            i = i + 1;
            continue;
        end
        current(end + 1) = ch;
        i = i + 1;
    else
        if ch == '"'
            in_quotes = true;
            i = i + 1;
        elseif ch == ','
            fields{end + 1} = current;
            current = '';
            i = i + 1;
        else
            current(end + 1) = ch;
            i = i + 1;
        end
    end
end
fields{end + 1} = current;
end
