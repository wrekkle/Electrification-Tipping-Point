# -*- coding: utf-8 -*-
"""Statistics: block bootstrap confidence sets (an approximation of the
Martinoli et al. 2026 SAA confidence set), g(r) intervals, the three-region
rule, CVaR_0.95 and the equation (12) path decomposition.

The confidence set is an approximation, not their theorem: it is conditional
on the simulated sample.  Pairing uses the same replayed day trajectories
(common random numbers).
"""
from __future__ import annotations

import math

import numpy as np


# --------------------------------------------------------------------------
# Bootstrap
# --------------------------------------------------------------------------
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

    Returns best index, included indices, critical value and test statistics.
    method may be max-t or holm.
    """
    cost_matrix = np.asarray(cost_matrix, dtype=float)
    n, M = cost_matrix.shape
    if rng is None:
        rng = np.random.default_rng(20261029)
    means = cost_matrix.mean(axis=0)
    best = int(np.argmin(means))
    diffs = cost_matrix - cost_matrix[:, [best]]
    se = diffs.std(axis=0, ddof=1) / math.sqrt(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        t_stat = np.where(se > 0, diffs.mean(axis=0) / se, 0.0)
    boot = bootstrap_means(diffs, n_boot, block_len, rng)
    boot_center = boot - diffs.mean(axis=0)[None, :]
    with np.errstate(divide="ignore", invalid="ignore"):
        t_boot = np.where(se[None, :] > 0, boot_center / se[None, :], 0.0)
    max_t = np.max(t_boot, axis=1)
    crit = float(np.quantile(max_t, 1.0 - alpha))
    if method == "max-t":
        pvals = (1.0 + np.sum(t_boot > t_stat[None, :], axis=0)) / (n_boot + 1.0)
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
    }


def g_interval(full_matrix, partial_matrix, n_boot=1000, alpha=0.05,
               block_len=1, rng=None):
    """g = V(full) - min_partial V, with a paired bootstrap interval.

    full_matrix: S vector or S x 1 full-installation costs.
    partial_matrix: S x K costs of candidate partial designs.
    """
    full = np.asarray(full_matrix, dtype=float)
    if full.ndim == 1:
        full = full[:, None]
    part = np.asarray(partial_matrix, dtype=float)
    n = full.shape[0]
    if rng is None:
        rng = np.random.default_rng(20261029)
    g_hat = float(full.mean() - part.mean(axis=0).min())
    idx = block_indices(rng, n, block_len, n_boot)
    boot = full[idx].mean(axis=1) - part[idx].mean(axis=1).min(axis=1)
    lo = float(np.quantile(boot, alpha / 2.0))
    hi = float(np.quantile(boot, 1.0 - alpha / 2.0))
    return {"g_hat": g_hat, "g_lo": lo, "g_hi": hi,
            "n_scenarios": n, "n_boot": n_boot}


def three_region(g_hat, g_lo, g_hi):
    """Fixed three-region rule (documented in README)."""
    if g_hi < 0.0:
        return "full_dominant"
    if g_lo > 0.0:
        return "partial_dominant"
    return "undetermined"


# --------------------------------------------------------------------------
# CVaR
# --------------------------------------------------------------------------
def empirical_cvar(losses, alpha=0.95):
    """CVaR at level alpha with explicit tie handling and sample counts."""
    arr = np.sort(np.asarray(losses, dtype=float))
    n = arr.size
    if n == 0:
        raise ValueError("empty loss sample")
    # subtract a tiny epsilon so an exact integer tail is not rounded up
    tail_n = int(math.ceil((1.0 - alpha) * n - 1e-9))
    tail_n = max(1, min(tail_n, n))
    var = float(arr[n - tail_n])
    cvar = float(arr[n - tail_n:].mean())
    candidates = np.unique(arr)
    vals = [eta + np.maximum(arr - eta, 0.0).mean() / (1.0 - alpha)
            for eta in candidates]
    k = int(np.argmin(vals))
    return {
        "n": n, "tail_n": tail_n, "alpha": alpha,
        "var": var, "cvar": cvar,
        "cvar_aux": float(vals[k]), "eta_star": float(candidates[k]),
    }


# --------------------------------------------------------------------------
# Equation (12) decomposition
# --------------------------------------------------------------------------
def decompose(v_full_flex, v_full_strict, v_m0_flex, v_m0_strict):
    """V(N,pi_F) - V(m0,pi_S) split along both change orders.

    path A (capacity first):  [V(N,F)-V(m0,F)] + [V(m0,F)-V(m0,S)]
    path B (rule first):      [V(N,F)-V(N,S)] + [V(N,S)-V(m0,S)]
    """
    total = v_full_flex - v_m0_strict
    cap_a = v_full_flex - v_m0_flex          # capacity change under pi_F
    rule_a = v_m0_flex - v_m0_strict         # rule change at m0
    cap_b = v_full_flex - v_full_strict      # rule change at N
    rule_b = v_full_strict - v_m0_strict     # capacity change under pi_S
    return {
        "total": total,
        "capacity_effect_pathA": cap_a,
        "rule_effect_pathA": rule_a,
        "capacity_effect_pathB": v_full_strict - v_m0_strict,
        "rule_effect_pathB": cap_b,
        "path_dependence_capacity": cap_a - (v_full_strict - v_m0_strict),
        "path_dependence_rule": rule_a - cap_b,
        "identity_gap": total - (cap_a + rule_a),
    }


def etp_from_g(rows):
    """First r where full installation is cheaper and stays cheaper."""
    ordered = sorted(rows, key=lambda x: x["r"])
    threshold = None
    for row in ordered:
        if row["g_hat"] < 0.0:
            threshold = row["r"]
            break
    if threshold is None:
        return None
    for row in ordered:
        if row["r"] >= threshold and row["g_hat"] >= 0.0:
            return None
    return threshold
