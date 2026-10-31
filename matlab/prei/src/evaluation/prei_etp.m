function etp = prei_etp(targets, target_cost, full_index, atol, rtol)
%PREI_ETP Suffix-only equivalent full-installation threshold.
%
%   etp = prei_etp(targets, target_cost, full_index, atol, rtol)
%
%   targets are ordered ev_share_target values; target_cost is
%   n_candidates x n_targets. Full installation counts as best at a target
%   whenever it belongs to the full tie set at that target. An ETP exists only
%   when full installation is best at a target and at every later target. The
%   reported ETP is the first target of that suffix, or empty when no suffix
%   exists. All other contiguous full-optimal runs are reported as windows.
%   The value 0.70 receives no special treatment.

if nargin < 4 || isempty(atol)
    atol = 1e-8;
end
if nargin < 5 || isempty(rtol)
    rtol = 1e-10;
end
targets = targets(:);
n_targets = numel(targets);
if size(target_cost, 2) ~= n_targets
    error('prei:etp:shape', 'target_cost must have one column per target.');
end
if full_index < 1 || full_index > size(target_cost, 1)
    error('prei:etp:fullIndex', 'full_index is outside target_cost rows.');
end

full_best = false(n_targets, 1);
for k = 1:n_targets
    tied = prei_best_set(target_cost(:, k), atol, rtol);
    full_best(k) = any(tied == full_index);
end

window_start = [];
window_end = [];
k = 1;
while k <= n_targets
    if full_best(k)
        start = k;
        while k < n_targets && full_best(k + 1)
            k = k + 1;
        end
        window_start(end + 1, 1) = start;
        window_end(end + 1, 1) = k;
    end
    k = k + 1;
end

etp = struct();
etp.criterion = 'suffix_all_full_installation_best';
etp.has_etp = false;
etp.target = [];
etp.index = [];
etp.window_start_index = window_start;
etp.window_end_index = window_end;
if ~isempty(window_start)
    etp.window_start_target = targets(window_start);
    etp.window_end_target = targets(window_end);
else
    etp.window_start_target = [];
    etp.window_end_target = [];
end

if ~isempty(full_best) && full_best(end)
    start = n_targets;
    while start > 1 && full_best(start - 1)
        start = start - 1;
    end
    etp.has_etp = true;
    etp.target = targets(start);
    etp.index = start;
end
end
