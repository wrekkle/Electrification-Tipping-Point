function summary = prei_summarize(evaluation, cfg, scenarios, meta)
%PREI_SUMMARIZE Assemble the machine-readable static result summary.
%
%   Does not write files, draw figures, or change random state. Hashes and
%   environment facts come from the caller; missing values are marked as
%   not_available rather than guessed.

if nargin < 4 || isempty(meta)
    meta = struct();
end
if ~isstruct(evaluation) || ~isstruct(cfg) || ~isstruct(scenarios)
    error('prei:summarize:input', 'evaluation, cfg and scenarios must be structs.');
end

env = prei_meta_or(meta, 'environment', prei_environment());
config_hash = prei_meta_or(meta, 'config_sha256', ...
    prei_struct_or(cfg, 'config_sha256', 'not_available'));
input_hash = prei_meta_or(meta, 'input_sha256', ...
    prei_struct_or(scenarios, 'source_sha256', 'not_available'));
source_hash = prei_meta_or(meta, 'source_sha256', 'not_available');

summary = struct();
summary.schema_version = 1;
summary.model_variant = evaluation.model_variant;
summary.source_case = cfg.source_case;
summary.diagnostic_only = evaluation.diagnostic_only;
if summary.diagnostic_only
    summary.recommendation_status = 'diagnostic_only_not_a_recommendation';
else
    summary.recommendation_status = 'corrected_baseline_static_no_recommendation_claim';
end
summary.units = 'RMB per day';

summary.config = struct();
summary.config.n_spaces = cfg.n_spaces;
summary.config.installation_cost_rmb_per_pile = cfg.installation_cost_rmb_per_pile;
summary.config.amortization_years = cfg.amortization_years;
summary.config.partial_shared_fraction = cfg.partial_shared_fraction;
summary.config.full_install_open_to_all = cfg.full_install_open_to_all;
summary.config.pile_ratios = cfg.pile_ratios;
summary.config.ev_share_targets = cfg.ev_share_targets;

summary.results = struct();
summary.results.mean_cost_by_candidate = evaluation.mean_cost_by_candidate;
summary.results.target_mean_cost = evaluation.target_mean_cost;
summary.results.best_day_index = evaluation.best.day_index;
summary.results.best_candidate_index = evaluation.best.candidate_index;
summary.results.best_pile_ratio = evaluation.best.pile_ratio;
summary.results.best_cost = evaluation.best.cost;
summary.results.best_is_full = evaluation.best.is_full;
summary.results.g_full_minus_best_partial = evaluation.g_full_minus_best_partial;
summary.results.g_full_minus_best_partial_sign = 'C_full_minus_min_C_partial';
summary.results.delta_candidate_minus_full = evaluation.delta_candidate_minus_full;
summary.results.delta_candidate_minus_full_sign = 'C_candidate_minus_C_full';
summary.results.tolerance_atol = evaluation.tolerance.atol;
summary.results.tolerance_rtol = evaluation.tolerance.rtol;
summary.results.branch = evaluation.branch;

finite_g = evaluation.g_full_minus_best_partial(isfinite(evaluation.g_full_minus_best_partial));
if isempty(finite_g)
    summary.results.g_mean = [];
    summary.results.g_min = [];
    summary.results.g_max = [];
    summary.results.g_negative_days = [];
else
    summary.results.g_mean = mean(finite_g);
    summary.results.g_min = min(finite_g);
    summary.results.g_max = max(finite_g);
    summary.results.g_negative_days = sum(finite_g < 0);
end
summary.results.delta_min = min(evaluation.delta_candidate_minus_full(:));
summary.results.delta_max = max(evaluation.delta_candidate_minus_full(:));

summary.etp = evaluation.etp;
summary.days = struct();
summary.days.day_id = scenarios.day_ids;
summary.days.ev_share_target = scenarios.day_targets;
summary.days.n_rows = scenarios.rows_per_day;
summary.n_rows = scenarios.n_rows;
summary.n_days = scenarios.n_days;

summary.hashes = struct();
summary.hashes.config_sha256 = config_hash;
summary.hashes.input_sha256 = input_hash;
summary.hashes.source_sha256 = source_hash;

summary.environment = env;
summary.verification = struct();
if isfield(meta, 'actual_tested_platforms') && ~isempty(meta.actual_tested_platforms)
    summary.verification.actual_tested_platforms = meta.actual_tested_platforms;
elseif env.is_octave
    summary.verification.actual_tested_platforms = 'octave';
else
    summary.verification.actual_tested_platforms = 'unverified';
end
summary.verification.octave_tested = env.is_octave;
summary.verification.matlab_tested = false;
summary.verification.scope = prei_meta_or(meta, 'verification_scope', ...
    'static_core_and_entrypoint_smoke_tests');
summary.verification.note = ['Only Octave static-core and entry-point smoke tests ' ...
    'were executed for this delivery; MATLAB was not run.'];

caveats = {};
if summary.diagnostic_only
    caveats{end + 1} = ['legacy_reference is diagnostic_only: its known full-installation ' ...
        'EV complaint omission is preserved and must not be called a recommendation.'];
else
    caveats{end + 1} = ['corrected_baseline is a static reference calculation, not a ' ...
        'policy recommendation.'];
end
if cfg.partial_shared_fraction > 0
    caveats{end + 1} = ['partial_shared_fraction > 0 is an explicit conditional benchmark; ' ...
        'it does not claim to reproduce every sharing mode of the original scripts.'];
end
caveats{end + 1} = 'full_install_open_to_all is applied only when pile_ratio equals 1.';
caveats{end + 1} = 'ETP is a suffix criterion and is not targeted at 0.70.';
caveats{end + 1} = ['Capital cost is charged once per scenario-day; refusal costs are ' ...
    'summed over hourly rows and averaged across scenario-days.'];
caveats{end + 1} = ['The event layer, complex sampling and cross-language numerical ' ...
    'comparison are outside this first static stage.'];
summary.caveats = caveats;
end

function value = prei_meta_or(s, field, default)
if isfield(s, field) && ~isempty(s.(field))
    value = s.(field);
else
    value = default;
end
end

function value = prei_struct_or(s, field, default)
if isfield(s, field) && ~isempty(s.(field))
    value = s.(field);
else
    value = default;
end
end
