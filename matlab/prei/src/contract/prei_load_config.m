function [cfg, meta] = prei_load_config(config_path)
%PREI_LOAD_CONFIG Read and validate a PREI configuration JSON file.
%
%   [cfg, meta] = prei_load_config(path)
%
%   Contract fields (schema_version 1):
%     schema_version, model_variant, source_case, n_spaces,
%     installation_cost_rmb_per_pile, amortization_years,
%     partial_shared_fraction, full_install_open_to_all, pile_ratios,
%     ev_share_targets, fixture_file
%
%   model_variant is legacy_reference or corrected_baseline. The label
%   research_extension is explicitly rejected in this static stage.
%   fixture_file must be a relative path; the absolute fixture path is
%   resolved by prei_load_scenarios against meta.dir.

if ~ischar(config_path) || isempty(config_path)
    error('prei:config:path', 'A nonempty configuration path is required.');
end
if exist(config_path, 'file') ~= 2
    error('prei:config:missing', 'Configuration file not found: %s', config_path);
end

text = fileread(config_path);
try
    raw = jsondecode(text);
catch err
    error('prei:config:json', 'Cannot parse configuration JSON: %s', err.message);
end

cfg = prei_validate_config(raw);
meta = struct();
meta.path = prei_abspath(config_path);
meta.dir = fileparts(meta.path);
meta.sha256 = prei_hash_text(text);

cfg.config_path = meta.path;
cfg.config_dir = meta.dir;
cfg.config_sha256 = meta.sha256;
end

function cfg = prei_validate_config(raw)
if ~isstruct(raw) || ~isscalar(raw)
    error('prei:config:shape', 'Configuration must be one JSON object.');
end

cfg = struct();
cfg.schema_version = prei_scalar(raw, 'schema_version', 'prei:config:schema');
if cfg.schema_version ~= 1
    error('prei:config:schema', 'schema_version must equal 1; got %g.', cfg.schema_version);
end

cfg.model_variant = prei_text(raw, 'model_variant', 'prei:config:model');
if strcmp(cfg.model_variant, 'research_extension')
    error('prei:config:notImplemented', ...
        'model_variant research_extension is not implemented in this static stage.');
elseif ~any(strcmp(cfg.model_variant, {'legacy_reference', 'corrected_baseline'}))
    error('prei:config:model', ...
        'model_variant must be legacy_reference or corrected_baseline; got %s.', ...
        cfg.model_variant);
end

cfg.source_case = prei_text(raw, 'source_case', 'prei:config:source');

cfg.n_spaces = prei_scalar(raw, 'n_spaces', 'prei:config:nSpaces');
if cfg.n_spaces <= 0 || abs(cfg.n_spaces - round(cfg.n_spaces)) > 1e-12
    error('prei:config:nSpaces', 'n_spaces must be a positive integer.');
end

cfg.installation_cost_rmb_per_pile = ...
    prei_scalar(raw, 'installation_cost_rmb_per_pile', 'prei:config:installation');
if cfg.installation_cost_rmb_per_pile < 0
    error('prei:config:installation', 'installation_cost_rmb_per_pile must be nonnegative.');
end

cfg.amortization_years = prei_scalar(raw, 'amortization_years', 'prei:config:years');
if cfg.amortization_years <= 0
    error('prei:config:years', 'amortization_years must be positive.');
end

cfg.partial_shared_fraction = ...
    prei_scalar(raw, 'partial_shared_fraction', 'prei:config:sharedFraction');
if cfg.partial_shared_fraction < 0 || cfg.partial_shared_fraction > 1
    error('prei:config:sharedFraction', ...
        'partial_shared_fraction must lie in [0,1].');
end

cfg.full_install_open_to_all = ...
    prei_logical(raw, 'full_install_open_to_all', 'prei:config:openToAll');

cfg.pile_ratios = prei_vector(raw, 'pile_ratios', 'prei:config:pileRatios');
if any(cfg.pile_ratios < 0) || any(cfg.pile_ratios > 1)
    error('prei:config:pileRatios', 'pile_ratios must lie in [0,1].');
end
prei_require_strict_order(cfg.pile_ratios, 'pile_ratios', 'prei:config:pileRatiosOrder');

cfg.ev_share_targets = prei_vector(raw, 'ev_share_targets', 'prei:config:evTargets');
if any(cfg.ev_share_targets < 0) || any(cfg.ev_share_targets > 1)
    error('prei:config:evTargets', 'ev_share_targets must lie in [0,1].');
end
prei_require_strict_order(cfg.ev_share_targets, 'ev_share_targets', ...
    'prei:config:evTargetsOrder');

cfg.fixture_file = prei_text(raw, 'fixture_file', 'prei:config:fixture');
if ~isempty(regexp(cfg.fixture_file, '^([/\\]|[A-Za-z]:)', 'once'))
    error('prei:config:fixtureAbsolute', ...
        'fixture_file must be relative to the configuration directory.');
end

if strcmp(cfg.model_variant, 'legacy_reference')
    if cfg.partial_shared_fraction ~= 0
        error('prei:config:legacySharing', ...
            ['legacy_reference reproduces only the active h=0 branch; ' ...
             'a positive partial_shared_fraction is not implemented for that label.']);
    end
    if ~cfg.full_install_open_to_all
        error('prei:config:legacyClosedFull', ...
            ['legacy_reference requires full_install_open_to_all=true; ' ...
             'closed full-install policy belongs to corrected_baseline.']);
    end
end
end

function value = prei_scalar(s, name, id)
if ~isfield(s, name)
    error(id, 'Missing required field: %s.', name);
end
value = s.(name);
if islogical(value)
    value = double(value);
end
if ~isnumeric(value) || ~isscalar(value) || ~isfinite(value)
    error(id, 'Field %s must be a finite numeric scalar.', name);
end
value = double(value);
end

function value = prei_text(s, name, id)
if ~isfield(s, name)
    error(id, 'Missing required field: %s.', name);
end
value = s.(name);
if ~ischar(value) || isempty(value)
    error(id, 'Field %s must be a nonempty character value.', name);
end
value = strtrim(value);
if isempty(value)
    error(id, 'Field %s must be a nonempty character value.', name);
end
end

function value = prei_logical(s, name, id)
if ~isfield(s, name)
    error(id, 'Missing required field: %s.', name);
end
value = s.(name);
if islogical(value) && isscalar(value)
    return;
end
if isnumeric(value) && isscalar(value) && any(value == [0 1])
    value = logical(value);
    return;
end
error(id, 'Field %s must be a JSON boolean or 0/1.', name);
end

function value = prei_vector(s, name, id)
if ~isfield(s, name)
    error(id, 'Missing required field: %s.', name);
end
value = s.(name);
if ~isnumeric(value) || isempty(value) || ~isvector(value) || any(~isfinite(value))
    error(id, 'Field %s must be a nonempty finite numeric vector.', name);
end
value = value(:);
end

function prei_require_strict_order(value, name, id)
if numel(value) > 1 && any(diff(value) <= 0)
    error(id, '%s must be strictly increasing without duplicates.', name);
end
end
