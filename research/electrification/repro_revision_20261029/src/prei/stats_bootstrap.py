# -*- coding: utf-8 -*-
"""stats_bootstrap

拆分自 stats.py，内容逐字节搬移以保持行为不变；公共入口仍由 stats 提供。
"""
from __future__ import annotations
import math
import numpy as np


def block_indices(rng, n, block_len, n_boot):
    """Circular block bootstrap index matrix (B x n)."""
    block_len = max(1, int(block_len))
    n_blocks = int(math.ceil(n / block_len))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    offsets = np.arange(block_len)
    idx = (starts[:, :, None] + offsets[None, None, :]).reshape(n_boot, -1) % n
    return idx[:, :n]


def bootstrap_means(matrix, n_boot, block_len, rng):
    """Bootstrap distribution of the column means (B x M)."""
    n = matrix.shape[0]
    idx = block_indices(rng, n, block_len, n_boot)
    return matrix[idx].mean(axis=1)


def normal_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def confidence_set(cost_matrix, n_boot=1000, alpha=0.05, block_len=1,
                   rng=None, method="max-t"):
    """Candidates that cannot be excluded as best, paired against the best.

    The comparison family is the full candidate list of the cell (M columns):
    every candidate j is contrasted with the point-estimate best column via
    the mean daily-cost difference.  The bootstrap keeps the same replayed day
    index for all M columns (common random numbers), so the contrasts are
    paired.

    method="max-t": single-step simultaneous p-values
        p_j = (1 + #{b : max_k T_bk >= T_j}) / (B + 1)
    with T_j the studentised paired difference and T_bk its bootstrap
    counterpart.  Equality is counted, which is conservative (it keeps exact
    ties) and avoids the degenerate all-tied case.

    method="holm": Bonferroni-Holm adjustment of normal-approximation marginal
    p-values; a different (also valid, but marginal-model) family, reported as
    such.

    Zero standard error is handled explicitly: a column whose paired
    difference has zero variance is either an exact duplicate of the best
    column (p = 1, kept) or deterministically dominated (p = 0, excluded).

    Returns the best index, included/excluded indices, the max-t critical
    value, the simultaneous p-values, the family size and the zero-se columns.
    This is *not* a theorem-level set: it is conditional on the simulated
    sample.
    """
    cost_matrix = np.asarray(cost_matrix, dtype=float)
    if cost_matrix.ndim != 2:
        raise ValueError("cost_matrix must be S x M")
    n, M = cost_matrix.shape
    if n < 2 or M < 1:
        raise ValueError("need at least two scenarios and one candidate")
    if rng is None:
        rng = np.random.default_rng(20261029)
    means = cost_matrix.mean(axis=0)
    best = int(np.argmin(means))
    diffs = cost_matrix - cost_matrix[:, [best]]
    d_mean = diffs.mean(axis=0)
    se = diffs.std(axis=0, ddof=1) / math.sqrt(n)
    zero_se = se <= 1e-15
    t_stat = np.zeros(M, dtype=float)
    t_stat[~zero_se] = d_mean[~zero_se] / se[~zero_se]
    boot = bootstrap_means(diffs, n_boot, block_len, rng)
    boot_center = boot - d_mean[None, :]
    t_boot = np.zeros_like(boot_center)
    t_boot[:, ~zero_se] = boot_center[:, ~zero_se] / se[None, ~zero_se]
    max_t = np.max(t_boot, axis=1)
    crit = float(np.quantile(max_t, 1.0 - alpha))

    if method == "max-t":
        pvals = (1.0 + np.sum(max_t[:, None] >= t_stat[None, :], axis=0)) \
            / (n_boot + 1.0)
        pvals = np.clip(pvals, 0.0, 1.0)
    elif method == "holm":
        pvals = 1.0 - np.array([normal_cdf(x) for x in t_stat])
        order = np.argsort(pvals)
        adjusted = np.empty(M)
        running = 0.0
        for rank, j in enumerate(order):
            running = max(running, (M - rank) * pvals[j])
            adjusted[j] = min(1.0, running)
        pvals = adjusted
    else:
        raise ValueError("unknown multiplicity method %r" % method)

    # explicit zero-variance semantics, applied after the bootstrap p-values
    for j in range(M):
        if zero_se[j]:
            pvals[j] = 1.0 if d_mean[j] <= 1e-12 else 0.0
    pvals[best] = 1.0
    included = [j for j in range(M) if j == best or pvals[j] > alpha]
    return {
        "best": best,
        "included": sorted(included),
        "excluded": sorted(set(range(M)) - set(included)),
        "critical_value": crit,
        "pvalues": pvals,
        "t_statistics": t_stat,
        "means": means,
        "n_scenarios": n,
        "n_boot": n_boot,
        "block_len": block_len,
        "alpha": alpha,
        "method": method,
        "family_size": M,
        "zero_se": [int(j) for j in np.nonzero(zero_se)[0]],
    }


def _interval_meta(method, independent, block_len, alpha):
    """Machine-readable scope flags for one g(r) interval.

    The flags must follow applicability, not the method name: a block
    bootstrap with block_len>1 (or scenarios explicitly declared dependent)
    only produces a diagnostic, and the string says so.  The interval is
    per-r pointwise in every case; no joint statement across the r grid is
    implied (see g_structure and the three-region labels).
    """
    nominal = bool(method == "simultaneous-max-t" and independent)
    if nominal:
        scope = ("simultaneous over all K paired contrasts, max-propagation to "
                 "g = max_k mu_k; requires iid scenarios (block_len=1), paired/"
                 "CRN designs and a candidate set fixed a priori; per-r "
                 "pointwise, not joint across the r grid")
    elif method == "percentile":
        scope = ("diagnostic only: percentile of the selected maximum; no "
                 "nominal coverage")
    elif int(block_len) > 1:
        scope = ("diagnostic only: block_len=%d>1, so the iid "
                 "studentisation does not establish nominal coverage; do not "
                 "quote as a %d%% interval"
                 % (int(block_len), int(round((1.0 - alpha) * 100.0))))
    else:
        scope = ("diagnostic only: scenarios declared dependent, so the iid "
                 "studentisation does not establish nominal coverage; do not "
                 "quote as a %d%% interval"
                 % int(round((1.0 - alpha) * 100.0)))
    return {"coverage_scope": scope, "nominal_coverage": nominal,
            "diagnostic_only": not nominal,
            "interval_scope": "per_r_pointwise", "joint_across_r": False}


def g_interval(full_matrix, partial_matrix, n_boot=1000, alpha=0.05,
               block_len=1, rng=None, method="simultaneous-max-t",
               independent_scenarios=None):
    """g = V(full) - min_partial V, with a coverage-valid paired interval.

    full_matrix: S vector or S x 1 full-installation costs.
    partial_matrix: S vector or S x K candidate partial-design costs.

    Definition: g = mean(full) - min_k mean(partial_k).  With the paired
    differences d_k(s) = full(s) - partial_k(s) this is g = max_k E[d_k], i.e.
    the best partial design is the one with the largest mean saving.

    Why not the plain percentile bootstrap of the min (T14/F09)
    -----------------------------------------------------------
    Resampling and then taking min_k inside every replicate reproduces the
    sampling distribution of the selected maximum, which is biased: for K
    near-tied partial designs the point estimate sits about E[max Z]*se away
    from the truth and the percentile interval inherits that shift while its
    width does not grow with K.  Measured coverage of the true g was 65% at a
    nominal 95% (fixed-seed experiment, seed 20261030 family).

    Simultaneous-interval construction (default)
    --------------------------------------------
    1. studentise every paired contrast: T_k = (dbar_k - mu_k)/se_k;
    2. one bootstrap (same day index for all K columns) gives the max-t
       critical value c = q_{1-alpha}( max_k |T*_k| );
    3. per-contrast simultaneous bounds L_k = dbar_k - c*se_k, U_k = dbar_k + c*se_k;
    4. propagate the maximum: g in [max_k L_k, max_k U_k].

    Because g = max_k mu_k, the event {all mu_k in [L_k,U_k]} implies both
    inequalities, so coverage of g is at least the simultaneous level 1-alpha.
    No selection claim is involved: the same bounds are used for every k, so
    the winner's curse shifts the point estimate but not the coverage.
    Zero-variance contrasts (se_k = 0) are exact: L_k = U_k = dbar_k.

    Applicability conditions (do not overclaim)
    -------------------------------------------
    * paired scenarios (common random numbers): the S rows are the same days
      for full and partial arms;
    * scenarios must be independent for the studentisation used here: with
      block_len > 1 the standard errors are still iid-based, so the nominal
      level is NOT established for serially dependent days - the CI is
      reported but the coverage guarantee is claimed only for block_len == 1;
    * the candidate set is declared before seeing the data (no data-dependent
      addition of candidates), otherwise the family changes after selection;
    * coverage is asymptotic in S (bootstrap max-t calibration), finite-sample
      behaviour is checked by the fixed-seed experiment, not assumed;
    * this is not the Martinoli et al. (2026) theorem: no set-coverage
      statement about the argmin design is inherited, only the interval for
      g = max_k mu_k above.

    method="percentile" is kept as a labelled diagnostic only (old behaviour);
    it does not have the coverage property above and must not be reported as a
    nominal 95% interval.
    """
    full = np.asarray(full_matrix, dtype=float)
    if full.ndim == 1:
        full = full[:, None]
    if full.ndim != 2 or full.shape[1] != 1:
        raise ValueError("full_matrix must be S x 1 or a length-S vector")
    part = np.asarray(partial_matrix, dtype=float)
    if part.ndim == 1:
        part = part[:, None]
    if part.ndim != 2:
        raise ValueError("partial_matrix must be S x K or a length-S vector")
    n = full.shape[0]
    if part.shape[0] != n:
        raise ValueError("full and partial matrices must share the scenario axis")
    if n < 2:
        raise ValueError("at least two scenarios are required for a bootstrap")
    if rng is None:
        rng = np.random.default_rng(20261029)
    part_means = part.mean(axis=0)
    best_partial = int(np.argmin(part_means))
    g_hat = float(full.mean() - part_means[best_partial])
    diffs = full.reshape(-1)[:, None] - part          # S x K, paired
    d_mean = diffs.mean(axis=0)
    se = diffs.std(axis=0, ddof=1) / math.sqrt(n) if n > 1 else np.zeros(part.shape[1])
    zero_se = se <= 1e-15

    if independent_scenarios is None:
        independent = int(block_len) <= 1
    else:
        independent = bool(independent_scenarios)
    meta = _interval_meta(method, independent, block_len, alpha)
    if method == "percentile":
        idx = block_indices(rng, n, block_len, n_boot)
        boot_full = full.reshape(-1)[idx].mean(axis=1).ravel()
        boot_part = part[idx].mean(axis=1).min(axis=1).ravel()
        boot = boot_full - boot_part
        lo = float(np.quantile(boot, alpha / 2.0))
        hi = float(np.quantile(boot, 1.0 - alpha / 2.0))
        return {"g_hat": g_hat, "g_lo": lo, "g_hi": hi,
                "n_scenarios": n, "n_boot": n_boot, "alpha": alpha,
                "block_len": int(block_len), "best_partial_index": best_partial,
                "best_partial_mean": float(part_means[best_partial]),
                "n_partial": int(part.shape[1]), "paired": True,
                "critical_value": float("nan"), "se_best": float("nan"),
                "n_zero_se": int(np.sum(zero_se)), "max_t": True,
                "method": "paired_block_bootstrap_percentile",
                "independent_scenarios": independent,
                "unit": "RMB", **meta}
    if method != "simultaneous-max-t":
        raise ValueError("unknown g interval method %r" % (method,))

    idx = block_indices(rng, n, block_len, n_boot)
    boot = diffs[idx].mean(axis=1)                    # B x K, paired
    center = boot - d_mean[None, :]
    t_boot = np.zeros_like(center)
    t_boot[:, ~zero_se] = center[:, ~zero_se] / se[None, ~zero_se]
    max_abs_t = np.max(np.abs(t_boot), axis=1)
    crit = float(np.quantile(max_abs_t, 1.0 - alpha))
    lower = d_mean - crit * se
    upper = d_mean + crit * se
    lower[zero_se] = d_mean[zero_se]
    upper[zero_se] = d_mean[zero_se]
    g_lo = float(np.max(lower))
    g_hi = float(np.max(upper))
    return {"g_hat": g_hat, "g_lo": g_lo, "g_hi": g_hi,
            "n_scenarios": n, "n_boot": n_boot, "alpha": alpha,
            "block_len": int(block_len), "best_partial_index": best_partial,
            "best_partial_mean": float(part_means[best_partial]),
            "n_partial": int(part.shape[1]), "paired": True,
            "critical_value": crit,
            "se_best": float(se[best_partial]),
            "n_zero_se": int(np.sum(zero_se)),
            "method": "simultaneous-max-t",
            "independent_scenarios": independent,
            "unit": "RMB", **meta}
