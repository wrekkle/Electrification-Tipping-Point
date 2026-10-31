function indices = prei_best_set(cost, atol, rtol)
%PREI_BEST_SET All candidates tied with the minimum cost.
%   A candidate c is in the set when
%     abs(c - min(cost)) <= atol + rtol*abs(min(cost)).
%   Display masks are not accepted here: only the supplied cost vector
%   participates in the comparison.

if nargin < 2 || isempty(atol)
    atol = 1e-8;
end
if nargin < 3 || isempty(rtol)
    rtol = 1e-10;
end
cost = cost(:);
if isempty(cost) || any(~isfinite(cost))
    error('prei:bestSet:cost', 'Cost vector must be nonempty and finite.');
end
best = min(cost);
indices = find(abs(cost - best) <= atol + rtol * abs(best));
indices = indices(:);
end
