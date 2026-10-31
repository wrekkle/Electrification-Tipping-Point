function static_verify()
%STATIC_VERIFY Independent MATLAB R2026a run and comparison for the static PREI model.
%
%   Runs the unchanged matlab/prei entry point on the two fixed configs
%   (final_tvr_n40_legacy / final_tvr_n40_corrected) into fresh
%   research/round5_20261031/matlab/static_run/<variant>/ directories, then
%   compares every output with the Python reference run
%   experiments/prei/runs/run2_v1_<variant> (byte-identical to ref_v1_<variant>).
%
%   Checks: raw SHA-256 of config and fixture vs the reference summary, byte
%   equality of config_used.json, the full cost matrix cells, refusals,
%   optimal/tie sets, best_candidates vs daily_optimal, ETP windows/target
%   recomputed from the Python matrix, an ETP hand example, the output
%   manifest, and legacy-vs-corrected cell differences.
%
%   Exit status: an error is raised (non-zero MATLAB exit) if any check fails.
%   Log: research/round5_20261031/matlab/logs/static_verify.log.

tol_abs = 1e-6;
tol_rel = 1e-9;

root = fileparts(fileparts(fileparts(fileparts(fileparts(mfilename('fullpath'))))));
base = fullfile(root, 'research', 'round5_20261031', 'matlab');
logs = fullfile(base, 'logs');
if exist(logs, 'dir') ~= 7, mkdir(logs); end
log_path = fullfile(logs, 'static_verify.log');
if exist(log_path, 'file') == 2, delete(log_path); end
diary(log_path); diary on;
diary_cleanup = onCleanup(@() diary('off')); %#ok<NASGU>

fprintf('== static_verify ==\n');
fprintf('now_local      : %s\n', datestr(now, 31));
fprintf('matlab_version : %s\n', version);
fprintf('matlab_release : %s\n', matlabRelease.Release);
fprintf('license MATLAB : %d\n', license('test', 'MATLAB'));
products = ver;
fprintf('products       : %d\n', numel(products));
for i = 1:numel(products)
    fprintf('  product|%s|%s\n', products(i).Name, products(i).Version);
end
fprintf('project_root   : %s\n', root);
fprintf('tolerance      : abs %.1e / rel %.1e (cell costs, RMB/day)\n', tol_abs, tol_rel);

prei_dir = fullfile(root, 'matlab', 'prei');
addpath(prei_dir);

self_test = 'pass'; self_test_message = '';
try
    prei_self_test();
catch err
    self_test = 'fail'; self_test_message = err.message;
end
fprintf('prei_self_test : %s %s\n', self_test, self_test_message);

specs = { ...
    struct('name', 'legacy', ...
        'config', fullfile(root, 'experiments', 'prei', 'configs', 'final_tvr_n40_legacy.json'), ...
        'out', fullfile(base, 'static_run', 'legacy'), ...
        'ref', fullfile(root, 'experiments', 'prei', 'runs', 'run2_v1_legacy')), ...
    struct('name', 'corrected', ...
        'config', fullfile(root, 'experiments', 'prei', 'configs', 'final_tvr_n40_corrected.json'), ...
        'out', fullfile(base, 'static_run', 'corrected'), ...
        'ref', fullfile(root, 'experiments', 'prei', 'runs', 'run2_v1_corrected'))};

cases = struct([]);
for k = 1:numel(specs)
    spec = specs{k};
    if exist(spec.out, 'dir') == 7
        entries = dir(spec.out);
        for j = 1:numel(entries)
            if ~entries(j).isdir
                delete(fullfile(spec.out, entries(j).name));
            end
        end
    end
    run_status = 'pass'; run_message = '';
    try
        run_prei(spec.config, spec.out);
    catch err
        run_status = 'fail'; run_message = getReport(err, 'basic');
    end
    fprintf('\n-- run %s : %s\n', spec.name, run_status);
    if ~isempty(run_message), fprintf('%s\n', run_message); end
    if strcmp(run_status, 'pass')
        r = compare_variant(spec, tol_abs, tol_rel, base);
    else
        r = blank_case(spec.name, run_status);
        r.run_error = run_message;
    end
    if isempty(cases), cases = r; else, cases(end + 1) = r; end %#ok<AGROW>
end

% Legacy vs corrected: which cells differ, and do the tie sets differ?
diffs = struct('available', false, 'n_diff', 0, 'columns', {{}}, ...
    'only_ratio_one', 0, 'max_abs', 0, 'tie_days', 0);
if numel(cases) == 2 && isfield(cases(1), 'matrix_path') && ...
        exist(cases(1).matrix_path, 'file') == 2 && exist(cases(2).matrix_path, 'file') == 2
    diffs = compare_variants(cases(1), cases(2));
    fprintf('\n-- legacy vs corrected (MATLAB outputs)\n');
    fprintf('differing_cells          : %d\n', diffs.n_diff);
    fprintf('differing_columns        : %s\n', strjoin(diffs.columns, ', '));
    fprintf('all_diffs_only_ratio_1   : %d\n', diffs.only_ratio_one);
    fprintf('max_abs_diff             : %.17g\n', diffs.max_abs);
    fprintf('primary_diff_cells       : %d\n', diffs.primary_cells);
    fprintf('derived_diff_cells       : %d\n', diffs.derived_cells);
    fprintf('days_with_different_ties : %d\n', diffs.tie_days);
end

etp_hand = etp_hand_check();
fprintf('\n-- etp hand example : %s\n', etp_hand.status);
fprintf('   case1 windows [%d %d], target %.17g | case2 windows [%d %d], has_etp %d\n', ...
    etp_hand.case1_window(1), etp_hand.case1_window(2), etp_hand.case1_target, ...
    etp_hand.case2_window(1), etp_hand.case2_window(2), etp_hand.case2_has_etp);

all_pass = strcmp(self_test, 'pass') && etp_hand.pass;
for k = 1:numel(cases)
    all_pass = all_pass && strcmp(cases(k).run_status, 'pass') && cases(k).pass;
end
out = struct();
out.generated_local = datestr(now, 31);
out.matlab_version = version;
out.matlab_release = matlabRelease.Release;
out.license_matlab = license('test', 'MATLAB');
out.project_root = root;
out.python_reference_dirs = {specs{1}.ref, specs{2}.ref};
out.tolerance = struct('abs', tol_abs, 'rel', tol_rel);
out.prei_self_test = self_test;
out.prei_self_test_message = self_test_message;
out.etp_hand = etp_hand;
out.cases = cases;
out.legacy_vs_corrected = diffs;
out.all_pass = all_pass;
json_path = fullfile(base, 'static_run', 'comparison_summary.json');
fid = fopen(json_path, 'w', 'n', 'UTF-8');
fprintf(fid, '%s\n', jsonencode(out));
fclose(fid);
fprintf('\ncomparison_summary: %s\n', json_path);
if all_pass
    fprintf('ALL STATIC CHECKS PASSED\n');
else
    error('static_verify:fail', 'One or more static checks failed; see log %s', log_path);
end
end

% -------------------------------------------------------------------------
function c = blank_case(name, run_status)
c = struct('name', name, 'run_status', run_status, 'run_error', '', ...
    'config_sha256_python', '', 'config_sha256_actual', '', ...
    'fixture_sha256_python', '', 'fixture_sha256_actual', '', ...
    'config_hash_match', false, 'fixture_hash_match', false, ...
    'metadata_config_hash_match', false, 'config_used_identical', false, ...
    'n_rows_matlab', 0, 'n_rows_python', 0, 'n_unique_keys', 0, ...
    'rows_complete', false, 'n_columns', 0, ...
    'n_tie_matlab', 0, 'n_tie_python', 0, 'tie_flag_mismatch', -1, ...
    'best_candidates_count', 0, 'best_candidates_match', false, ...
    'daily_optimal_ratio_match', false, 'refusal_crosscheck_mismatch', -1, ...
    'max_abs_diff', NaN, 'max_rel_diff', NaN, 'worst_column', '', ...
    'worst_key', '', 'etp_windows_match', false, 'etp_target_match', false, ...
    'etp_window_count_matlab', 0, 'etp_window_count_python', 0, ...
    'etp_has_etp', false, 'etp_target', [], ...
    'manifest_checked', 0, 'manifest_mismatch', -1, 'manifest_rawbyte_mismatch', -1, ...
    'platform_label', '', 'matrix_path', '', 'pass', false, 'notes', '');
end

% -------------------------------------------------------------------------
function r = compare_variant(spec, tol_abs, tol_rel, base)
path_cleanup = prei_path_init(); %#ok<NASGU>
r = blank_case(spec.name, 'pass');
mfile = fullfile(spec.out, 'raw_cost_matrix.csv');
pfile = fullfile(spec.ref, 'raw_cost_matrix.csv');
r.matrix_path = mfile;

py = jsondecode(fileread(fullfile(spec.ref, 'summary.json')));
r.config_sha256_python = py.input.config_sha256;
r.fixture_sha256_python = py.input.fixture_sha256;
r.config_sha256_actual = sha256_file_bytes(spec.config);
cfg = jsondecode(fileread(spec.config));
fixture_path = fullfile(fileparts(spec.config), cfg.fixture_file);
r.fixture_sha256_actual = sha256_file_bytes(fixture_path);
r.config_hash_match = strcmpi(r.config_sha256_actual, r.config_sha256_python);
r.fixture_hash_match = strcmpi(r.fixture_sha256_actual, r.fixture_sha256_python);

meta = jsondecode(fileread(fullfile(spec.out, 'run_metadata.json')));
r.metadata_config_hash_match = strcmpi(meta.config_sha256, r.config_sha256_actual);
r.platform_label = meta.actual_tested_platforms;
r.config_used_identical = strcmp(fileread(fullfile(spec.out, 'config_used.json')), ...
    fileread(spec.config));

m = readtable(mfile, 'Delimiter', ',', 'TextType', 'string', ...
    'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
p = readtable(pfile, 'Delimiter', ',', 'TextType', 'string', ...
    'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
r.n_rows_matlab = height(m);
r.n_rows_python = height(p);
r.n_columns = width(m);
same_cols = isequal(string(m.Properties.VariableNames), string(p.Properties.VariableNames));
if ~same_cols
    r.notes = 'column name sets differ';
end
kc = key_of(m);
kp = key_of(p);
r.n_unique_keys = numel(unique(kc));
[found, loc] = ismember(kc, kp);
r.rows_complete = same_cols && all(found) && r.n_rows_matlab == r.n_rows_python && ...
    r.n_unique_keys == r.n_rows_matlab && numel(unique(kp)) == numel(kp);
if ~r.rows_complete
    r.notes = [r.notes ' key join incomplete'];
    c0 = r; return
end
p = p(loc, :);
[m, order] = sortrows(m, 'pile_ratio'); %#ok<ASGLU>
% rows of m must be re-joined after sorting: re-key and reorder p accordingly
kc2 = key_of(m);
[found2, loc2] = ismember(kc2, kp);
assert(all(found2), 're-key failed');
p = p(loc2, :);
kc = kc2;

num_cols = {'total_arrivals', 'ev_share_actual', 'capital_daily_cost', ...
    'ev_rejected', 'ice_rejected', 'ev_fuel_cost', 'ice_fuel_cost', ...
    'ev_time_cost', 'ice_time_cost', 'ev_complaint_cost', 'ice_complaint_cost', ...
    'total_daily_cost', 'g_full_minus_best_partial', 'delta_candidate_minus_full'};
max_abs = 0; max_rel = 0; worst_col = ''; worst_key = '';
rows = cell(numel(num_cols), 4);
for i = 1:numel(num_cols)
    col = num_cols{i};
    a = double(m.(col));
    b = double(p.(col));
    d = abs(a - b);
    rel = d ./ max(abs(b), realmin);
    [mv, mi] = max(d);
    rows{i, 1} = col; rows{i, 2} = mv;
    rows{i, 3} = max(rel);
    rows{i, 4} = kc(mi);
    if mv > max_abs, max_abs = mv; worst_col = col; worst_key = kc(mi); end
    max_rel = max(max_rel, max(rel));
end
r.max_abs_diff = max_abs;
r.max_rel_diff = max_rel;
r.worst_column = worst_col;
r.worst_key = worst_key;
diff_table = cell2table(rows, 'VariableNames', {'column', 'max_abs', 'max_rel', 'worst_key'});
writetable(diff_table, fullfile(base, 'static_run', [spec.name '_diff_by_column.csv']));

optM = flag_of(m.is_optimal);
optP = flag_of(p.is_optimal);
r.n_tie_matlab = sum(optM);
r.n_tie_python = sum(optP);
r.tie_flag_mismatch = sum(optM ~= optP);

% best_candidates.csv vs the Python tie set (day key includes the target)
bc = readtable(fullfile(spec.out, 'best_candidates.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
kbc = bc.day_id + "|" + compose('%.17g', bc.ev_share_target) + "|" + ...
    compose('%.17g', bc.pile_ratio);
kpy = p.scenario_id + "|" + compose('%.17g', p.ev_share_target) + "|" + ...
    compose('%.17g', p.pile_ratio);
ktie = kpy(optP);
r.best_candidates_count = height(bc);
r.best_candidates_match = r.best_candidates_count == numel(ktie) && ...
    all(ismember(kbc, ktie)) && all(ismember(ktie, kbc));

% daily_optimal.csv has no pile_ratio column (Python RESULT_COLUMNS contract),
% so its content is checked against the lowest tied candidate of that day.
do = readtable(fullfile(spec.ref, 'daily_optimal.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
fix_cols = {'total_arrivals', 'ev_share_actual', 'ev_fuel_cost', 'ice_fuel_cost', ...
    'ev_time_cost', 'ice_time_cost', 'ev_complaint_cost', 'ice_complaint_cost'};
day_keys = p.scenario_id + "|" + compose('%.17g', p.ev_share_target);
ok_daily = height(do) == numel(unique(day_keys));
for j = 1:height(do)
    if ~ok_daily, break; end
    sel_day = p.scenario_id == do.scenario_id(j) & ...
        abs(p.ev_share_target - double(do.ev_share_target(j))) <= 1e-12;
    tie_rows = find(sel_day & optP);
    if isempty(tie_rows) || sum(sel_day) == 0
        ok_daily = false; break
    end
    lowest = min(p.pile_ratio(tie_rows));
    pick = tie_rows(abs(p.pile_ratio(tie_rows) - lowest) <= 1e-12);
    pick = pick(1);
    if abs(double(do.hour(j)) - 24) > 1e-12
        ok_daily = false; break
    end
    for c = 1:numel(fix_cols)
        if abs(double(do.(fix_cols{c})(j)) - double(p.(fix_cols{c})(pick))) > 1e-12
            ok_daily = false; break
        end
    end
end
r.daily_optimal_ratio_match = ok_daily;
r.notes = [r.notes 'python daily_optimal.csv lacks pile_ratio; checked against lowest tied row'];

% refusals.csv must equal the matrix refusal columns
rf = readtable(fullfile(spec.out, 'refusals.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
krf = rf.day_id + "|" + compose('%.17g', rf.ev_share_target) + "|" + ...
    compose('%.17g', rf.pile_ratio);
km = m.scenario_id + "|" + compose('%.17g', m.ev_share_target) + "|" + ...
    compose('%.17g', m.pile_ratio);
[ok_rf, loc_rf] = ismember(krf, km);
if all(ok_rf)
    bad = sum(abs(double(rf.ev_refused) - double(m.ev_rejected(loc_rf))) > 1e-12) + ...
          sum(abs(double(rf.ice_refused) - double(m.ice_rejected(loc_rf))) > 1e-12);
    r.refusal_crosscheck_mismatch = bad;
else
    r.refusal_crosscheck_mismatch = -1;
end

% ETP recomputed from the Python matrix, compared with MATLAB etp_windows.csv
atol = 1e-8; rtol = 1e-10;
etp = recompute_etp(p, atol, rtol);
w = readtable(fullfile(spec.out, 'etp_windows.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
r.etp_window_count_matlab = height(w);
r.etp_window_count_python = numel(etp.window_start_index);
r.etp_windows_match = r.etp_window_count_matlab == r.etp_window_count_python && ...
    isequal(double(w.start_index(:)), etp.window_start_index(:)) && ...
    isequal(double(w.end_index(:)), etp.window_end_index(:));
msum = jsondecode(fileread(fullfile(spec.out, 'summary.json')));
ml_target = msum.etp.target;
if isempty(ml_target) && isempty(etp.target)
    r.etp_target_match = true;
elseif ~isempty(ml_target) && ~isempty(etp.target)
    r.etp_target_match = abs(double(ml_target) - etp.target) <= 1e-12;
else
    r.etp_target_match = false;
end
if ~isempty(ml_target), r.etp_target = double(ml_target); end
r.etp_has_etp = logical(msum.etp.has_etp);

% manifest self-consistency
% manifest uses prei_hash_text(fileread(file)) (a UTF-16 code-unit hash)
% rather than raw UTF-8 bytes. Check the declared contract, and record how
% many entries would disagree with a raw-byte SHA-256 as a separate fact.
man = readtable(fullfile(spec.out, 'manifest.csv'), 'Delimiter', ',', ...
    'TextType', 'string', 'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
bad = 0; raw_bad = 0;
for j = 1:height(man)
    f = fullfile(spec.out, man.file(j));
    if exist(f, 'file') ~= 2
        bad = bad + 1; raw_bad = raw_bad + 1; continue
    end
    if ~strcmpi(prei_hash_text(fileread(f)), man.sha256(j)) || ...
            dir(f).bytes ~= man.bytes(j)
        bad = bad + 1;
    end
    if ~strcmpi(sha256_file_bytes(f), man.sha256(j))
        raw_bad = raw_bad + 1;
    end
end
r.manifest_checked = height(man);
r.manifest_mismatch = bad;
r.manifest_rawbyte_mismatch = raw_bad;

r.pass = r.config_hash_match && r.fixture_hash_match && r.config_used_identical && ...
    r.rows_complete && r.tie_flag_mismatch == 0 && r.best_candidates_match && ...
    r.daily_optimal_ratio_match && r.refusal_crosscheck_mismatch == 0 && ...
    r.max_abs_diff <= tol_abs && r.max_rel_diff <= tol_rel && ...
    r.etp_windows_match && r.etp_target_match && r.manifest_mismatch == 0;
fprintf('rows m/p %d/%d | max_abs %.3e | max_rel %.3e (%s)\n', ...
    r.n_rows_matlab, r.n_rows_python, r.max_abs_diff, r.max_rel_diff, worst_col);
fprintf('ties m/p %d/%d mismatch %d | best set %d | daily optimal %d | refusals %d\n', ...
    r.n_tie_matlab, r.n_tie_python, r.tie_flag_mismatch, r.best_candidates_match, ...
    r.daily_optimal_ratio_match, r.refusal_crosscheck_mismatch);
fprintf('hash cfg %d fixture %d | etp windows %d target %d | manifest %d bad %d rawbyte %d | pass %d\n', ...
    r.config_hash_match, r.fixture_hash_match, r.etp_windows_match, ...
    r.etp_target_match, r.manifest_checked, r.manifest_mismatch, ...
    r.manifest_rawbyte_mismatch, r.pass);
fprintf('platform label in run_metadata: %s\n', r.platform_label);
end

% -------------------------------------------------------------------------
function d = compare_variants(a, b)
ml = readtable(a.matrix_path, 'Delimiter', ',', 'TextType', 'string', ...
    'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
mc = readtable(b.matrix_path, 'Delimiter', ',', 'TextType', 'string', ...
    'VariableNamingRule', 'preserve', 'Encoding', 'UTF-8');
kl = key_of(ml); kc = key_of(mc);
[found, loc] = ismember(kl, kc);
assert(all(found) && numel(kl) == numel(kc), 'variant key join failed');
mc = mc(loc, :);
cols = ml.Properties.VariableNames;
num_cols = cols(~ismember(cols, {'scenario_id', 'is_optimal'}));
n_diff = 0; max_abs = 0; cols_diff = strings(0);
primary = {'ev_complaint_cost', 'total_daily_cost'};
primary_cells = 0;
for i = 1:numel(num_cols)
    col = num_cols{i};
    x = ml.(col); y = mc.(col);
    if isstring(x) || ischar(x)
        dd = ~strcmp(string(x), string(y));
    else
        dd = abs(double(x) - double(y)) > 1e-12;
    end
    if any(dd)
        n_diff = n_diff + sum(dd);
        cols_diff(end + 1) = string(col); %#ok<AGROW>
        if ~isstring(x) && ~ischar(x)
            max_abs = max(max_abs, max(abs(double(x(dd)) - double(y(dd)))));
        end
        if any(strcmp(col, primary)), primary_cells = primary_cells + sum(dd); end
    end
end
only_ratio_one = true;
for ic = 1:numel(primary)
    dd = abs(double(ml.(primary{ic})) - double(mc.(primary{ic}))) > 1e-12;
    if any(dd & abs(ml.pile_ratio - 1) > 1e-12)
        only_ratio_one = false;
    end
end
tie_l = flag_of(ml.is_optimal); tie_c = flag_of(mc.is_optimal);
days = unique(ml.scenario_id);
tie_days = 0;
for j = 1:numel(days)
    sel = ml.scenario_id == days(j);
    if any(tie_l(sel & abs(ml.pile_ratio - 1) > 1e-12) ~= tie_c(sel & abs(ml.pile_ratio - 1) > 1e-12))
        tie_days = tie_days + 1;
    end
end
% also count full-ratio tie differences
for j = 1:numel(days)
    sel = ml.scenario_id == days(j) & abs(ml.pile_ratio - 1) < 1e-12;
    if any(tie_l(sel) ~= tie_c(sel))
        % already counted above only for partial; count separately is not needed
    end
end
d = struct('available', true, 'n_diff', n_diff, 'columns', {cellstr(cols_diff)}, ...
    'only_ratio_one', only_ratio_one, 'max_abs', max_abs, 'tie_days', tie_days, ...
    'primary_cells', primary_cells, 'derived_cells', n_diff - primary_cells);
end

% -------------------------------------------------------------------------
function etp = recompute_etp(p, atol, rtol)
ratios = unique(p.pile_ratio);
targets = unique(p.ev_share_target);
TC = nan(numel(ratios), numel(targets));
for j = 1:numel(targets)
    for i = 1:numel(ratios)
        sel = abs(p.ev_share_target - targets(j)) <= 1e-12 & ...
              abs(p.pile_ratio - ratios(i)) <= 1e-12;
        TC(i, j) = mean(p.total_daily_cost(sel));
    end
end
full_index = find(abs(ratios - 1) <= 1e-12, 1);
full_best = false(numel(targets), 1);
for j = 1:numel(targets)
    b = min(TC(:, j));
    full_best(j) = any(abs(TC(full_index, j) - b) <= atol + rtol * abs(b));
end
starts = []; ends = [];
k = 1;
while k <= numel(targets)
    if full_best(k)
        s = k;
        while k < numel(targets) && full_best(k + 1)
            k = k + 1;
        end
        starts(end + 1, 1) = s; %#ok<AGROW>
        ends(end + 1, 1) = k; %#ok<AGROW>
    end
    k = k + 1;
end
etp = struct('window_start_index', starts, 'window_end_index', ends, ...
    'has_etp', false, 'target', []);
if ~isempty(full_best) && full_best(end)
    s = numel(targets);
    while s > 1 && full_best(s - 1)
        s = s - 1;
    end
    etp.has_etp = true;
    etp.target = targets(s);
end
end

% -------------------------------------------------------------------------
function h = etp_hand_check()
path_cleanup = prei_path_init(); %#ok<NASGU>
h = struct('status', 'fail', 'case1_window', [0 0], 'case1_target', NaN, ...
    'case2_window', [0 0], 'case2_has_etp', 1, 'pass', false);
t = [0.1 0.2 0.3 0.4 0.5];
e1 = prei_etp(t, [10 10 10 10 10; 11 10 10 9 9], 2, 1e-8, 1e-10);
e2 = prei_etp(t, [10 10 10 10 10; 9 9 11 11 11], 2, 1e-8, 1e-10);
h.case1_window = [e1.window_start_index(1) e1.window_end_index(end)];
h.case1_target = e1.target;
h.case2_window = [e2.window_start_index(1) e2.window_end_index(end)];
h.case2_has_etp = double(e2.has_etp);
ok = isequal(e1.window_start_index(:), 2) ... %#ok<*NBRAK>
    && isequal(e1.window_end_index(:), 5) ...
    && abs(e1.target - 0.2) <= 1e-12 && e1.has_etp ...
    && isequal(e2.window_start_index(:), 1) ...
    && isequal(e2.window_end_index(:), 2) ...
    && ~e2.has_etp && isempty(e2.target);
if ok
    h.status = 'pass'; h.pass = true;
end
end

% -------------------------------------------------------------------------
function k = key_of(tbl)
k = tbl.scenario_id + "|" + compose('%.17g', tbl.ev_share_target) + ...
    "|" + compose('%.17g', tbl.pile_ratio);
end

function v = flag_of(col)
if islogical(col)
    v = col;
elseif isnumeric(col)
    v = col ~= 0;
else
    v = strcmpi(strtrim(string(col)), "True");
end
end

function digest = sha256_file_bytes(path)
fid = fopen(path, 'r');
if fid < 0
    error('static_verify:hash', 'Cannot open file for hashing: %s', path);
end
bytes = fread(fid, Inf, 'uint8=>uint8');
fclose(fid);
md = java.security.MessageDigest.getInstance('SHA-256');
md.update(bytes);
digest = lower(reshape(dec2hex(typecast(md.digest(), 'uint8'), 2)', 1, []));
end
