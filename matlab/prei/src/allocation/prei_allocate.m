function alloc = prei_allocate(cfg, pile_ratio, total_arrivals, ev_share_actual)
%PREI_ALLOCATE Static parking/charging capacity allocation for one candidate.
%
%   alloc = prei_allocate(cfg, pile_ratio, total_arrivals, ev_share_actual)
%
%   Partial installation (pile_ratio < 1):
%     normal spaces = N*(1-pile_ratio)
%     charging spaces = N*pile_ratio
%     shareable charging spaces = N*pile_ratio*partial_shared_fraction
%   ICEV use normal spaces first, then shareable charging spaces. EV use
%   dedicated charging spaces plus shareable spaces not taken by ICEV. Normal
%   spaces are never opened to EV. h=0 is the strict original partition.
%
%   Full installation (pile_ratio == 1) with full_install_open_to_all=true:
%     total overflow is split between EV and ICEV in proportion to demand.
%   Full installation with the flag false: the partial-installation priority
%   rule is retained with zero normal spaces.
%
%   legacy_reference at pile_ratio == 1 reproduces the supplied script's
%   overflow split and supplies no EV complaint adjustment here; prei_cost
%   omits that complaint term for the legacy full branch.

if ~isstruct(cfg) || ~isfield(cfg, 'n_spaces')
    error('prei:allocate:config', 'A validated configuration struct is required.');
end
if ~isnumeric(pile_ratio) || ~isscalar(pile_ratio) || ~isfinite(pile_ratio) || ...
        pile_ratio < 0 || pile_ratio > 1
    error('prei:allocate:pileRatio', 'pile_ratio must be one finite scalar in [0,1].');
end

total = total_arrivals(:);
share = ev_share_actual(:);
if isempty(total) || ~isnumeric(total) || ~isnumeric(share)
    error('prei:allocate:demand', 'Arrivals and EV shares must be numeric vectors.');
end
if numel(total) == 1 && numel(share) > 1
    total = repmat(total, numel(share), 1);
elseif numel(share) == 1 && numel(total) > 1
    share = repmat(share, numel(total), 1);
end
if numel(total) ~= numel(share)
    error('prei:allocate:length', 'Arrivals and EV shares must have equal lengths.');
end
if any(~isfinite(total)) || any(total < 0)
    error('prei:allocate:demand', 'Arrivals must be finite and nonnegative.');
end
if any(~isfinite(share)) || any(share < 0) || any(share > 1)
    error('prei:allocate:share', 'EV shares must be finite and lie in [0,1].');
end

n_spaces = cfg.n_spaces;
h = cfg.partial_shared_fraction;
ev_demand = total .* share;
ice_demand = total .* (1 - share);

ev_refused = zeros(numel(total), 1);
ice_refused = zeros(numel(total), 1);
normal_capacity = zeros(numel(total), 1);
charging_capacity = zeros(numel(total), 1);
shared_capacity = zeros(numel(total), 1);
ev_capacity = zeros(numel(total), 1);
ice_capacity = zeros(numel(total), 1);

legacy = strcmp(cfg.model_variant, 'legacy_reference');

if pile_ratio == 1 && cfg.full_install_open_to_all
    overflow = max(total - n_spaces, 0);
    ev_share_of_total = zeros(numel(total), 1);
    positive = total > 0;
    ev_share_of_total(positive) = ev_demand(positive) ./ total(positive);
    ev_refused = overflow .* ev_share_of_total;
    ice_refused = overflow .* (1 - ev_share_of_total);
    normal_capacity(:) = 0;
    charging_capacity(:) = n_spaces;
    shared_capacity(:) = n_spaces;
    ev_capacity = n_spaces * ev_share_of_total;
    ice_capacity = n_spaces * (1 - ev_share_of_total);
    if legacy
        branch = 'legacy_full_open_overflow_split';
    else
        branch = 'corrected_full_open_overflow_split';
    end
elseif pile_ratio == 1
    normal = 0;
    charging = n_spaces;
    shared = charging * h;
    [ice_refused, ice_shared_used] = prei_ice_priority(ice_demand, normal, shared);
    ev_capacity = charging - ice_shared_used;
    ev_refused = max(ev_demand - ev_capacity, 0);
    normal_capacity(:) = normal;
    charging_capacity(:) = charging;
    shared_capacity(:) = shared;
    ice_capacity = normal + shared;
    branch = 'corrected_full_closed_shared_priority';
else
    normal = n_spaces * (1 - pile_ratio);
    charging = n_spaces * pile_ratio;
    shared = charging * h;
    [ice_refused, ice_shared_used] = prei_ice_priority(ice_demand, normal, shared);
    ev_capacity = charging - ice_shared_used;
    ev_refused = max(ev_demand - ev_capacity, 0);
    normal_capacity(:) = normal;
    charging_capacity(:) = charging;
    shared_capacity(:) = shared;
    ice_capacity = normal + shared;
    if h == 0
        if legacy
            branch = 'legacy_partial_strict_partition';
        else
            branch = 'corrected_partial_strict_partition';
        end
    else
        branch = 'corrected_partial_shared_priority';
    end
end

alloc = struct();
alloc.pile_ratio = pile_ratio;
alloc.branch = branch;
alloc.total_arrivals = total;
alloc.ev_share_actual = share;
alloc.ev_demand = ev_demand;
alloc.ice_demand = ice_demand;
alloc.ev_refused = ev_refused;
alloc.ice_refused = ice_refused;
alloc.ev_served = max(ev_demand - ev_refused, 0);
alloc.ice_served = max(ice_demand - ice_refused, 0);
alloc.normal_capacity = normal_capacity;
alloc.charging_capacity = charging_capacity;
alloc.shared_capacity = shared_capacity;
alloc.ev_capacity = ev_capacity;
alloc.ice_capacity = ice_capacity;
end

function [ice_refused, ice_shared_used] = prei_ice_priority(ice_demand, normal, shared)
ice_after_normal = max(ice_demand - normal, 0);
ice_shared_used = min(ice_after_normal, shared);
ice_refused = max(ice_after_normal - shared, 0);
end
