function run_prei_tests()
fprintf('PREI static core tests (Octave only)\n');

% Allocation: zero demand, endpoints, no/full piles, overflow.
cfg = base_cfg();
a = prei_allocate(cfg, 0.5, 0, 0.4);
check(a.ev_refused == 0 && a.ice_refused == 0, 'zero demand must produce zero refusals');

a = prei_allocate(cfg, 0.5, 10, 1.0);
check(abs(a.ev_refused - 5) < 1e-12 && abs(a.ice_refused) < 1e-12, ...
    'EV share 1 endpoint');
a = prei_allocate(cfg, 0.5, 10, 0.0);
check(abs(a.ev_refused) < 1e-12 && abs(a.ice_refused - 5) < 1e-12, ...
    'ICE-only endpoint');
a = prei_allocate(cfg, 0.0, 10, 0.4);
check(abs(a.ev_refused - 4) < 1e-12 && abs(a.ice_refused) < 1e-12, ...
    'no charging piles rejects all EV demand');
a = prei_allocate(cfg, 1.0, 10, 0.4);
check(abs(a.ev_refused) < 1e-12 && abs(a.ice_refused - 6) < 1e-12, ...
    'closed full install leaves ICEV without a charging bay');
cfg_open = cfg;
cfg_open.full_install_open_to_all = true;
a = prei_allocate(cfg_open, 1.0, 14, 0.5);
check(abs(a.ev_refused - 2) < 1e-12 && abs(a.ice_refused - 2) < 1e-12, ...
    'open full install splits total overflow');

% Shared-capacity counterexample: N=100, T=105, EV share .4, r=.5, h=.4.
cfg_ref = cfg;
cfg_ref.n_spaces = 100;
cfg_ref.partial_shared_fraction = 0.4;
a = prei_allocate(cfg_ref, 0.5, 105, 0.4);
check(abs(a.ev_refused - 5) < 1e-12, 'shared counterexample EV refusal must be 5');
check(abs(a.ice_refused) < 1e-12, 'shared counterexample ICEV refusal must be 0');

% Cost decomposition: two rows, capital once per day.
s = make_scen([10; 0], [0.8; 0.4], 0.8, 10, 20, 2, 3, 5, 4);
c = prei_cost(cfg, s, prei_allocate(cfg, 0.5, s.total_arrivals, s.ev_share_actual), 0.5);
check(abs(c.capital_rmb_per_day - 50) < 1e-12, 'capital must be 50 RMB/day');
check(abs(c.ev_fuel_rmb_per_day - 30) < 1e-12, 'EV fuel component');
check(abs(c.ev_time_rmb_per_day - 6) < 1e-12, 'EV time component');
check(abs(c.ev_complaint_rmb_per_day - 15) < 1e-12, 'EV complaint component');
check(abs(c.total_rmb_per_day - 101) < 1e-12, 'total cost decomposition');

% Legacy full-install complaint omission differs by exactly the EV complaint.
s = make_scen(20, 0.5, 0.5, 1, 10, 2, 20, 5, 4);
cfg_legacy = cfg;
cfg_legacy.model_variant = 'legacy_reference';
cfg_legacy.full_install_open_to_all = true;
cfg_corrected = cfg;
cfg_corrected.full_install_open_to_all = true;
a = prei_allocate(cfg_legacy, 1, s.total_arrivals, s.ev_share_actual);
cl = prei_cost(cfg_legacy, s, a, 1);
cc = prei_cost(cfg_corrected, s, a, 1);
check(abs((cc.total_rmb_per_day - cl.total_rmb_per_day) - 25) < 1e-12, ...
    'legacy full branch omits only the EV complaint term');

% Tied optima and ETP suffix/multiple-window semantics.
idx = prei_best_set([2; 1; 1 + 1e-9], 1e-8, 1e-10);
check(numel(idx) == 2 && all(idx == [2; 3]), 'tie set must include near-equal candidates');
targets = [0.2; 0.4; 0.6; 0.8; 1.0];
tc = [1 5 5 5 5; 2 2 5 5 5; 5 5 1 1 1];
etp = prei_etp(targets, tc, 3, 1e-8, 1e-10);
check(etp.has_etp && abs(etp.target - 0.6) < 1e-12, 'suffix ETP must start at 0.6');
tc = [1 5 1 1 5; 2 2 2 2 2];
etp = prei_etp(targets, tc, 1, 1e-8, 1e-10);
check(~etp.has_etp, 'full installation not best at the last target means no ETP');
check(numel(etp.window_start_index) == 2, 'multiple full-optimal windows must be listed');
tc = [5 5 5 5 5; 1 1 1 1 1];
etp = prei_etp(targets, tc, 1, 1e-8, 1e-10);
check(~etp.has_etp, 'no full-optimal target means null ETP');

% Loader, long output, and refusal to overwrite a nonempty directory.
tmp = tempname();
mkdir(tmp);
cleanup = onCleanup(@() rmdir(tmp, 's')); %#ok<NASGU>
cfg = base_cfg();
cfg.pile_ratios = [0; 0.5; 1];
cfg.ev_share_targets = [0.2; 0.8];
cfg.fixture_file = 'fixture.csv';
config_path = fullfile(tmp, 'config.json');
write_json(config_path, cfg);
write_fixture(fullfile(tmp, 'fixture.csv'));
[loaded, meta] = prei_load_config(config_path);
check(loaded.n_spaces == 10 && ~isempty(meta.sha256), 'config loader and hash');
scen = prei_load_scenarios(loaded, meta.dir);
check(scen.n_days == 2 && scen.n_rows == 48, 'scenario grouping by day');
check(abs(scen.day_total_arrivals(1) - 10) < 1e-12, 'day arrivals must sum rows');
ev = prei_evaluate(loaded, scen);
check(isequal(size(ev.raw_cost_matrix), [3 2]), 'raw matrix is candidates by days');
check(abs(ev.delta_candidate_minus_full(ev.full_index, 1)) < 1e-12, ...
    'delta at full installation must be zero');

out = fullfile(tmp, 'run1');
run_prei(config_path, out);
check(exist(fullfile(out, 'raw_cost_matrix.csv'), 'file') == 2, 'long matrix written');
check(exist(fullfile(out, 'raw_cost_matrix_wide.csv'), 'file') == 2, 'wide matrix written');
check(exist(fullfile(out, 'summary.json'), 'file') == 2, 'summary written');
fid = fopen(fullfile(out, 'raw_cost_matrix.csv'), 'r');
line = fgetl(fid);
fclose(fid);
check(~isempty(strfind(line, 'delta_candidate_minus_full')), 'long matrix header contract');
text = fileread(fullfile(out, 'raw_cost_matrix.csv'));
check(numel(strsplit(text, sprintf('\n'))) - 2 == 6, 'long matrix has day x ratio rows');
expect_error(@() run_prei(config_path, out), 'prei:run:nonEmptyOutput');

% Fixture contract regressions: every day needs 0..23 exactly once and six
% unit rates constant within the day.
fixture_modes = {'missing_hour', 'out_of_day_hour', 'variable_daily_unit_rate'};
fixture_ids = {'prei:scenarios:hours', 'prei:scenarios:hour', ...
    'prei:scenarios:variableRate'};
for k = 1:numel(fixture_modes)
    name = ['bad_' fixture_modes{k} '.csv'];
    write_fixture(fullfile(tmp, name), fixture_modes{k});
    bad_fixture = cfg;
    bad_fixture.fixture_file = name;
    expect_error(@() prei_load_scenarios(bad_fixture, tmp), fixture_ids{k});
end

% Invalid parameters.
bad = cfg; bad.schema_version = 2;
expect_config_error(tmp, 'bad_schema.json', bad, 'prei:config:schema');
bad = cfg; bad.model_variant = 'research_extension';
expect_config_error(tmp, 'bad_model.json', bad, 'prei:config:notImplemented');
bad = cfg; bad.n_spaces = 10.5;
expect_config_error(tmp, 'bad_n.json', bad, 'prei:config:nSpaces');
bad = cfg; bad.pile_ratios = [0.5; 0.4; 1];
expect_config_error(tmp, 'bad_order.json', bad, 'prei:config:pileRatiosOrder');
bad = cfg; bad.fixture_file = 'C:\absolute.csv';
expect_config_error(tmp, 'bad_path.json', bad, 'prei:config:fixtureAbsolute');
bad = cfg; bad.model_variant = 'legacy_reference'; bad.partial_shared_fraction = 0.2;
expect_config_error(tmp, 'bad_legacy_h.json', bad, 'prei:config:legacySharing');
bad = cfg; bad.model_variant = 'legacy_reference'; bad.full_install_open_to_all = false;
expect_config_error(tmp, 'bad_legacy_closed.json', bad, 'prei:config:legacyClosedFull');
bad = rmfield(cfg, 'amortization_years');
expect_config_error(tmp, 'bad_missing.json', bad, 'prei:config:years');
expect_error(@() run_prei(config_path, ''), 'prei:run:outputDir');

fprintf('ALL PREI STATIC TESTS PASSED\n');
end

function cfg = base_cfg()
cfg = struct();
cfg.schema_version = 1;
cfg.model_variant = 'corrected_baseline';
cfg.source_case = 'unit_test';
cfg.n_spaces = 10;
cfg.installation_cost_rmb_per_pile = 3650;
cfg.amortization_years = 1;
cfg.partial_shared_fraction = 0;
cfg.full_install_open_to_all = false;
cfg.pile_ratios = [0; 0.5; 1];
cfg.ev_share_targets = [0; 0.2; 0.4; 0.6; 0.8; 1];
cfg.fixture_file = 'fixture.csv';
end

function s = make_scen(total, share, target, evf, icf, evt, ict, evc, icc)
n = numel(total);
s = struct();
s.scenario_id = repmat({'d1'}, n, 1);
s.hour = (0:n-1)';
s.ev_share_target = target * ones(n, 1);
s.total_arrivals = total(:);
s.ev_share_actual = share(:);
s.ev_fuel_cost = evf * ones(n, 1);
s.ice_fuel_cost = icf * ones(n, 1);
s.ev_time_cost = evt * ones(n, 1);
s.ice_time_cost = ict * ones(n, 1);
s.ev_complaint_cost = evc * ones(n, 1);
s.ice_complaint_cost = icc * ones(n, 1);
s.day_index = ones(n, 1);
s.n_days = 1;
s.n_rows = n;
end

function check(condition, message)
if ~condition
    error('prei:test:failed', '%s', message);
end
end

function expect_error(fn, identifier)
try
    fn();
catch err
    if ~strcmp(err.identifier, identifier)
        error('prei:test:wrongError', 'Expected %s, got %s: %s', ...
            identifier, err.identifier, err.message);
    end
    return;
end
error('prei:test:noError', 'Expected error %s was not raised.', identifier);
end

function expect_config_error(tmp, name, cfg, identifier)
path = fullfile(tmp, name);
write_json(path, cfg);
expect_error(@() prei_load_config(path), identifier);
end

function write_json(path, value)
fid = fopen(path, 'w');
fprintf(fid, '%s', jsonencode(value));
fclose(fid);
end

function write_fixture(path, mode)
if nargin < 2
    mode = 'valid';
end
fid = fopen(path, 'w');
fprintf(fid, ['scenario_id,hour,ev_share_target,total_arrivals,' ...
    'ev_share_actual,ev_fuel_cost,ice_fuel_cost,ev_time_cost,' ...
    'ice_time_cost,ev_complaint_cost,ice_complaint_cost\n']);
for d = 1:2
    if d == 1
        id = 'd1'; target = 0.2;
    else
        id = 'd2'; target = 0.8;
    end
    for h = 0:23
        if strcmp(mode, 'missing_hour') && d == 1 && h == 5
            continue;
        end
        out_hour = h;
        if strcmp(mode, 'out_of_day_hour') && d == 1 && h == 23
            out_hour = 24;
        end
        total = 0;
        share = target;
        if d == 1 && h == 0
            total = 10; share = 0.2;
        elseif d == 1 && h == 1
            total = 0; share = 0.2;
        elseif d == 2 && h == 0
            total = 12; share = 0.8;
        elseif d == 2 && h == 1
            total = 8; share = 0.8;
        end
        ev_fuel = 1;
        if strcmp(mode, 'variable_daily_unit_rate') && d == 1 && h == 5
            ev_fuel = 2;
        end
        fprintf(fid, '%s,%d,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f,%.1f\n', ...
            id, out_hour, target, total, share, ev_fuel, 2, 3, 4, 5, 6);
    end
end
fclose(fid);
end
