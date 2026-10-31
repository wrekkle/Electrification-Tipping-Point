function result = run_prei(config_path, output_dir)
%RUN_PREI Static PREI entry point.
%
%   result = run_prei(config_path, output_dir)
%
%   output_dir must be explicit. An existing nonempty directory is refused;
%   an absent or empty directory is accepted. All numerical outputs are CSV;
%   summary.json and run_metadata.json carry hashes and environment facts.
%   This entry point is the only PREI function that writes files.

if nargin ~= 2
    error('prei:run:arguments', 'run_prei requires config_path and output_dir.');
end
if ~ischar(config_path) || isempty(config_path)
    error('prei:run:configPath', 'config_path must be a nonempty character path.');
end
if ~ischar(output_dir) || isempty(strtrim(output_dir))
    error('prei:run:outputDir', 'An explicit nonempty output directory is required.');
end

% The entry directory is the only caller-provided path. Initialise the src
% helpers before the first helper call so a clean Octave can find them.
path_cleanup = prei_path_init(); %#ok<NASGU>

output_dir = prei_abspath(strtrim(output_dir));
if exist(output_dir, 'file') == 2
    error('prei:run:outputFile', 'Output path is an existing file: %s', output_dir);
end
if exist(output_dir, 'dir') == 7
    entries = dir(output_dir);
    names = {entries.name};
    if any(~ismember(names, {'.', '..'}))
        error('prei:run:nonEmptyOutput', ...
            'Refusing to overwrite nonempty output directory: %s', output_dir);
    end
end

root = fileparts(mfilename('fullpath'));

[cfg, cfg_meta] = prei_load_config(config_path);
scenarios = prei_load_scenarios(cfg, cfg_meta.dir);
evaluation = prei_evaluate(cfg, scenarios);
env = prei_environment();
source_hash = prei_source_hash(root);

if exist(output_dir, 'dir') ~= 7
    [ok, message] = mkdir(output_dir);
    if ~ok
        error('prei:run:mkdir', 'Cannot create output directory: %s', message);
    end
end

prei_write_text(fullfile(output_dir, 'config_used.json'), fileread(cfg_meta.path));

written = {'config_used.json'};

% Wide matrix, retained for human inspection.
n_ratios = numel(evaluation.pile_ratios);
n_days = evaluation.n_days;
header = cell(1, 1 + n_days);
header{1} = 'pile_ratio';
for d = 1:n_days
    header{1 + d} = sprintf('day_%d', d);
end
rows = cell(n_ratios, 1 + n_days);
for i = 1:n_ratios
    rows{i, 1} = evaluation.pile_ratios(i);
    for d = 1:n_days
        rows{i, 1 + d} = evaluation.raw_cost_matrix(i, d);
    end
end
prei_write_csv(fullfile(output_dir, 'raw_cost_matrix_wide.csv'), header, rows);
written{end + 1} = 'raw_cost_matrix_wide.csv';

% Long raw matrix, column contract matching experiments/prei/reference.py.
% Values are one scenario-day per row, not means across EV targets.
header = {'scenario_id', 'ev_share_target', 'pile_ratio', 'total_arrivals', ...
    'ev_share_actual', 'capital_daily_cost', 'ev_rejected', 'ice_rejected', ...
    'ev_fuel_cost', 'ice_fuel_cost', 'ev_time_cost', 'ice_time_cost', ...
    'ev_complaint_cost', 'ice_complaint_cost', 'total_daily_cost', ...
    'is_optimal', 'g_full_minus_best_partial', 'delta_candidate_minus_full'};
rows = cell(n_ratios * n_days, numel(header));
cursor = 0;
for d = 1:n_days
    for i = 1:n_ratios
        cursor = cursor + 1;
        rows{cursor, 1} = evaluation.days.day_id{d};
        rows{cursor, 2} = evaluation.days.ev_share_target(d);
        rows{cursor, 3} = evaluation.pile_ratios(i);
        rows{cursor, 4} = evaluation.days.total_arrivals(d);
        rows{cursor, 5} = evaluation.days.ev_share_actual(d);
        rows{cursor, 6} = evaluation.daily_components.capital_daily_cost(i, d);
        rows{cursor, 7} = evaluation.daily_components.ev_rejected(i, d);
        rows{cursor, 8} = evaluation.daily_components.ice_rejected(i, d);
        rows{cursor, 9} = evaluation.daily_components.ev_fuel_cost(i, d);
        rows{cursor, 10} = evaluation.daily_components.ice_fuel_cost(i, d);
        rows{cursor, 11} = evaluation.daily_components.ev_time_cost(i, d);
        rows{cursor, 12} = evaluation.daily_components.ice_time_cost(i, d);
        rows{cursor, 13} = evaluation.daily_components.ev_complaint_cost(i, d);
        rows{cursor, 14} = evaluation.daily_components.ice_complaint_cost(i, d);
        rows{cursor, 15} = evaluation.daily_components.total_daily_cost(i, d);
        if any(evaluation.best_by_day{d} == i)
            rows{cursor, 16} = 'True';
        else
            rows{cursor, 16} = 'False';
        end
        rows{cursor, 17} = evaluation.g_full_minus_best_partial(d);
        rows{cursor, 18} = evaluation.delta_candidate_minus_full(i, d);
    end
end
prei_write_csv(fullfile(output_dir, 'raw_cost_matrix.csv'), header, rows);
written{end + 1} = 'raw_cost_matrix.csv';

% Cost components in RMB/day.
header = {'pile_ratio', 'branch', 'capital_rmb_per_day', ...
    'ev_fuel_rmb_per_day', 'ice_fuel_rmb_per_day', 'fuel_rmb_per_day', ...
    'ev_time_rmb_per_day', 'ice_time_rmb_per_day', 'time_rmb_per_day', ...
    'ev_complaint_rmb_per_day', 'ice_complaint_rmb_per_day', ...
    'complaint_rmb_per_day', 'total_rmb_per_day'};
rows = cell(n_ratios, numel(header));
for i = 1:n_ratios
    rows{i, 1} = evaluation.pile_ratios(i);
    rows{i, 2} = evaluation.branch{i};
    rows{i, 3} = evaluation.components.capital(i);
    rows{i, 4} = evaluation.components.ev_fuel(i);
    rows{i, 5} = evaluation.components.ice_fuel(i);
    rows{i, 6} = evaluation.components.fuel(i);
    rows{i, 7} = evaluation.components.ev_time(i);
    rows{i, 8} = evaluation.components.ice_time(i);
    rows{i, 9} = evaluation.components.time(i);
    rows{i, 10} = evaluation.components.ev_complaint(i);
    rows{i, 11} = evaluation.components.ice_complaint(i);
    rows{i, 12} = evaluation.components.complaint(i);
    rows{i, 13} = evaluation.components.total(i);
end
prei_write_csv(fullfile(output_dir, 'cost_components.csv'), header, rows);
written{end + 1} = 'cost_components.csv';

% Refused vehicles by candidate and scenario-day.
header = {'pile_ratio', 'day_index', 'day_id', 'ev_share_target', ...
    'ev_refused', 'ice_refused'};
rows = cell(n_ratios * n_days, numel(header));
cursor = 0;
for i = 1:n_ratios
    for d = 1:n_days
        cursor = cursor + 1;
        rows{cursor, 1} = evaluation.pile_ratios(i);
        rows{cursor, 2} = d;
        rows{cursor, 3} = evaluation.days.day_id{d};
        rows{cursor, 4} = evaluation.days.ev_share_target(d);
        rows{cursor, 5} = evaluation.ev_refused_daily(i, d);
        rows{cursor, 6} = evaluation.ice_refused_daily(i, d);
    end
end
prei_write_csv(fullfile(output_dir, 'refusals.csv'), header, rows);
written{end + 1} = 'refusals.csv';

% One row per tied optimum.
header = {'day_index', 'day_id', 'ev_share_target', 'candidate_index', ...
    'pile_ratio', 'cost_rmb_per_day', 'is_full'};
n_best = numel(evaluation.best.day_index);
rows = cell(n_best, numel(header));
for k = 1:n_best
    d = evaluation.best.day_index(k);
    rows{k, 1} = d;
    rows{k, 2} = evaluation.days.day_id{d};
    rows{k, 3} = evaluation.days.ev_share_target(d);
    rows{k, 4} = evaluation.best.candidate_index(k);
    rows{k, 5} = evaluation.best.pile_ratio(k);
    rows{k, 6} = evaluation.best.cost(k);
    rows{k, 7} = evaluation.best.is_full(k);
end
prei_write_csv(fullfile(output_dir, 'best_candidates.csv'), header, rows);
written{end + 1} = 'best_candidates.csv';

% Signed differences.
header = {'day_index', 'day_id', 'ev_share_target', 'candidate_index', ...
    'pile_ratio', 'cost_rmb_per_day', 'delta_candidate_minus_full', ...
    'g_full_minus_best_partial'};
rows = cell(n_ratios * n_days, numel(header));
cursor = 0;
for d = 1:n_days
    for i = 1:n_ratios
        cursor = cursor + 1;
        rows{cursor, 1} = d;
        rows{cursor, 2} = evaluation.days.day_id{d};
        rows{cursor, 3} = evaluation.days.ev_share_target(d);
        rows{cursor, 4} = i;
        rows{cursor, 5} = evaluation.pile_ratios(i);
        rows{cursor, 6} = evaluation.raw_cost_matrix(i, d);
        rows{cursor, 7} = evaluation.delta_candidate_minus_full(i, d);
        rows{cursor, 8} = evaluation.g_full_minus_best_partial(d);
    end
end
prei_write_csv(fullfile(output_dir, 'deltas.csv'), header, rows);
written{end + 1} = 'deltas.csv';

% Day map.
header = {'day_index', 'scenario_id', 'ev_share_target', 'n_hours'};
rows = cell(n_days, numel(header));
for d = 1:n_days
    rows{d, 1} = d;
    rows{d, 2} = evaluation.days.day_id{d};
    rows{d, 3} = evaluation.days.ev_share_target(d);
    rows{d, 4} = evaluation.days.n_rows(d);
end
prei_write_csv(fullfile(output_dir, 'days.csv'), header, rows);
written{end + 1} = 'days.csv';

% ETP windows.
header = {'window_index', 'start_index', 'end_index', 'start_target', 'end_target'};
n_windows = numel(evaluation.etp.window_start_index);
rows = cell(n_windows, numel(header));
for k = 1:n_windows
    rows{k, 1} = k;
    rows{k, 2} = evaluation.etp.window_start_index(k);
    rows{k, 3} = evaluation.etp.window_end_index(k);
    rows{k, 4} = evaluation.etp.window_start_target(k);
    rows{k, 5} = evaluation.etp.window_end_target(k);
end
prei_write_csv(fullfile(output_dir, 'etp_windows.csv'), header, rows);
written{end + 1} = 'etp_windows.csv';

meta = struct();
meta.config_sha256 = cfg_meta.sha256;
meta.input_sha256 = scenarios.source_sha256;
meta.source_sha256 = source_hash;
meta.environment = env;
meta.actual_tested_platforms = 'octave';
meta.verification_scope = 'static_core_and_entrypoint_smoke_tests_octave_only';

summary = prei_summarize(evaluation, cfg, scenarios, meta);
prei_write_json(fullfile(output_dir, 'summary.json'), summary);
written{end + 1} = 'summary.json';

run_metadata = struct();
run_metadata.schema_version = 1;
run_metadata.created_local = env.timestamp_local;
run_metadata.config_path = cfg_meta.path;
run_metadata.config_sha256 = cfg_meta.sha256;
run_metadata.input_path = scenarios.source_path;
run_metadata.input_sha256 = scenarios.source_sha256;
run_metadata.fixture_sha256 = scenarios.source_sha256;
run_metadata.source_root = root;
run_metadata.source_sha256 = source_hash;
run_metadata.hashes = struct('config_sha256', cfg_meta.sha256, ...
    'fixture_sha256', scenarios.source_sha256, ...
    'source_sha256', source_hash);
run_metadata.command = sprintf('run_prei(''%s'', ''%s'')', cfg_meta.path, output_dir);
run_metadata.environment = env;
run_metadata.actual_tested_platforms = 'octave';
run_metadata.matlab_tested = false;
run_metadata.verification_scope = 'static_core_and_entrypoint_smoke_tests_octave_only';
run_metadata.output_dir = output_dir;
run_metadata.output_files = written;
prei_write_json(fullfile(output_dir, 'run_metadata.json'), run_metadata);
written{end + 1} = 'run_metadata.json';

% Manifest excludes itself because its own hash cannot be embedded.
header = {'file', 'sha256', 'bytes'};
rows = cell(numel(written), numel(header));
for k = 1:numel(written)
    path = fullfile(output_dir, written{k});
    info = dir(path);
    rows{k, 1} = written{k};
    rows{k, 2} = prei_hash_file(path);
    rows{k, 3} = info.bytes;
end
prei_write_csv(fullfile(output_dir, 'manifest.csv'), header, rows);

result = summary;
result.output_dir = output_dir;
result.output_files = written;
end
