# -*- coding: utf-8 -*-
"""stats

Statistics: block bootstrap confidence sets, g(r) intervals, the three-region
rule, empirical CVaR and the equation (12) path decomposition.

Scope and limits (2026-10-29 revision)
-------------------------------------
* Every routine here is an *independent re-implementation* calibrated on the
  simulated sample.  None of it is Martinoli et al. 2026 (M03) theorem code and
  it does not inherit their set-coverage guarantee; the confidence set is a
  single-step max-t (or Holm) approximation with a block bootstrap, valid only
  conditionally on the simulated day sample.
* Selection of the best partial design inside g(r) is a minimum over candidate
  means; the paired bootstrap keeps the day index aligned between the full and
  partial arms but the minimum itself carries winner's-curse selection bias.
  A synthetic experiment accompanies this revision (tools/stat_experiment.py).
* All monetary quantities are RMB over the same horizon; g is RMB.

No time units are used in this module.

拆分后仅保留 _finite_number, g_structure, three_region, empirical_cvar, decompose, etp_from_g；其余实现由下列模块提供并在此重新导出（公共导入面不变）。
"""
from __future__ import annotations
import math
import numpy as np

from .stats_bootstrap import block_indices, bootstrap_means, normal_cdf, confidence_set, _interval_meta, g_interval

def _finite_number(value):
    if value is None:
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def g_structure(rows):
    """Separate dominant windows, negative islands and the sustained suffix.

    rows: per-r statistics with r, g_hat, g_lo, g_hi (as produced by
    evaluate.v2_cell_stats).  Windows are reported on the DISCRETE grid, as
    [first_r, last_r] pairs; no interpolation between grid points is implied.

    Definitions are kept explicit because they are not the same claim:
      * full_dominant_windows: runs with a FINITE g_hi < 0 (interval upper
        bound excludes zero, pointwise);
      * partial_dominant_windows: runs with a FINITE g_lo > 0;
      * etp_sustained_suffix: smallest r whose g_hat is < 0 for that r and
        for every later grid point (strict, point-estimate sign pattern; the
        same primitive as etp_from_g);
      * negative_islands: runs with FINITE g_hat < 0 that end before that
        suffix, i.e. a transient sign change is not an ETP.

    Missing and non-finite values are MISSING, never negative: they are
    excluded from every window/island flag, they break a run and they break
    the suffix (absence of a value is not evidence that g stays negative).
    The suffix therefore never contains a non-finite row.
    """
    ordered = sorted(rows, key=lambda x: float(x["r"]))
    finite_rows = [(_finite_number(row.get("g_hat"))
                   and _finite_number(row.get("g_lo"))
                   and _finite_number(row.get("g_hi"))) for row in ordered]
    non_finite_r = [float(row["r"]) for row, ok in zip(ordered, finite_rows)
                    if not ok]
    base = {"suffix_basis": ("g_hat<0 strictly at r and every later grid point "
                             "(point estimate, discrete grid)"),
            "full_dominant_basis": "finite g_hi<0 (pointwise interval bound)",
            "partial_dominant_basis": "finite g_lo>0 (pointwise interval bound)",
            "interval_scope": "per_r_pointwise", "joint_across_r": False,
            "n_non_finite": len(non_finite_r), "non_finite_r": non_finite_r}
    if not ordered:
        return dict(base, etp_sustained_suffix=None,
                    full_dominant_windows=[], partial_dominant_windows=[],
                    negative_islands=[], n_grid_points=0, r_grid=[])

    def runs(flags):
        out, start, prev_r = [], None, None
        for row, flag in zip(ordered, flags):
            r = float(row["r"])
            if flag and start is None:
                start = r
            if not flag and start is not None:
                out.append([start, prev_r])
                start = None
            prev_r = r
        if start is not None:
            out.append([start, prev_r])
        return out

    # A row with any non-finite field is MISSING, so it cannot support a
    # window/island flag even when the other two fields happen to be finite.
    neg_hat = [ok and float(row["g_hat"]) < 0.0
               for row, ok in zip(ordered, finite_rows)]
    full_windows = runs([ok and float(row["g_hi"]) < 0.0
                         for row, ok in zip(ordered, finite_rows)])
    partial_windows = runs([ok and float(row["g_lo"]) > 0.0
                            for row, ok in zip(ordered, finite_rows)])
    etp = None
    if neg_hat[-1]:
        i = len(neg_hat) - 1
        while i > 0 and neg_hat[i - 1]:
            i -= 1
        etp = float(ordered[i]["r"])
    neg_blocks = runs(neg_hat)
    if etp is None:
        islands = [list(b) for b in neg_blocks]
    else:
        islands = [list(b) for b in neg_blocks if b[1] < etp - 1e-12]
    inconsistent = []
    for row in ordered:
        if (_finite_number(row.get("g_hi")) and float(row["g_hi"]) < 0.0
                and not (_finite_number(row.get("g_hat"))
                         and float(row["g_hat"]) < 0.0)):
            inconsistent.append([float(row["r"]), "g_hi<0 but g_hat not <0"])
        if (_finite_number(row.get("g_lo")) and float(row["g_lo"]) > 0.0
                and not (_finite_number(row.get("g_hat"))
                         and float(row["g_hat"]) > 0.0)):
            inconsistent.append([float(row["r"]), "g_lo>0 but g_hat not >0"])
    return dict(base, etp_sustained_suffix=etp,
                full_dominant_windows=full_windows,
                partial_dominant_windows=partial_windows,
                negative_islands=islands,
                n_inconsistent_sign_rows=len(inconsistent),
                inconsistent_sign_rows=inconsistent,
                n_grid_points=len(ordered),
                r_grid=[float(ordered[0]["r"]), float(ordered[-1]["r"])])


def three_region(g_hat, g_lo, g_hi):
    """Fixed three-region rule (documented in README)."""
    if g_hi < 0.0:
        return "full_dominant"
    if g_lo > 0.0:
        return "partial_dominant"
    return "undetermined"


def empirical_cvar(losses, alpha=0.95):
    """Empirical CVaR at level alpha with the exact fractional tail weight.

    With n observations the tail carries mass w = (1 - alpha) * n, generally
    fractional.  The exact empirical CVaR is

        CVaR = (1 / w) * ( sum of the full tail values
                           + fraction of the boundary value )

    and equals the Rockafellar-Uryasev auxiliary value
    eta + E[(X - eta)^+] / (1 - alpha) at eta = VaR.  Both are returned and
    must agree.  The integer-tail shortcut (average of the ceil(w) largest
    values) is only valid when w is an integer and is not the CVaR definition
    otherwise: 25 losses 0..23 and 100 at alpha=.95 give 84.6, not 61.5.

    tail_n is the number of sample points touched by the tail, reported for
    traceability; tail_weight is the mass actually used.
    """
    arr = np.sort(np.asarray(losses, dtype=float))
    n = arr.size
    if n == 0:
        raise ValueError("empty loss sample")
    if not np.all(np.isfinite(arr)):
        raise ValueError("loss sample must be finite")
    if not (0.0 < alpha < 1.0):
        raise ValueError("alpha must be in (0,1)")
    tail_weight = (1.0 - alpha) * n
    tail_n = max(1, min(int(math.ceil(tail_weight - 1e-12)), n))
    var = float(arr[n - tail_n])
    k = int(math.floor(tail_weight + 1e-12))
    frac = tail_weight - k
    total = float(arr[n - k:].sum()) if k > 0 else 0.0
    if frac > 1e-12:
        total += frac * float(arr[n - k - 1])
    cvar = total / tail_weight
    # The Rockafellar-Uryasev auxiliary function is convex in eta and is
    # minimised at the alpha-quantile, so evaluating it on the (at most 500)
    # order statistics that bracket the tail is exact and keeps the cost linear
    # in the tail size instead of quadratic in n.
    candidates = np.unique(arr[max(0, n - tail_n - 2):])
    if candidates.size > 500:
        keep = np.linspace(0, candidates.size - 1, 500).astype(int)
        candidates = candidates[keep]
    aux = [eta + np.maximum(arr - eta, 0.0).mean() / (1.0 - alpha)
           for eta in candidates]
    kk = int(np.argmin(aux))
    return {
        "n": n, "tail_n": tail_n, "tail_weight": float(tail_weight),
        "alpha": alpha, "var": var, "cvar": float(cvar),
        "cvar_aux": float(aux[kk]), "eta_star": float(candidates[kk]),
        "exact": True,
    }


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
    """Smallest grid r whose g(r) is negative for that r and every later r.

    Discrete-grid only: no continuous monotonicity, interpolation or
    extrapolation is implied.  Conventions:
      * "full installation is cheaper" means g_hat < 0 strictly; g_hat == 0 is
        not cheaper and does not open a sustainment window;
      * NaN / non-finite g_hat is treated as "not cheaper";
      * an earlier negative island that turns non-negative again does not
        count: the search only accepts a suffix that stays negative;
      * duplicate r values are an input error (the grid must be a function).

    Returns the r value (float) or None when no sustained suffix exists.
    """
    if rows is None:
        return None
    pairs = []
    for row in rows:
        r = row.get("r")
        g = row.get("g_hat")
        if r is None:
            raise ValueError("row without r")
        if g is None:
            raise ValueError("row without g_hat at r=%r" % (r,))
        pairs.append((float(r), float(g)))
    if not pairs:
        return None
    pairs.sort(key=lambda x: x[0])
    for (r0, _), (r1, _) in zip(pairs, pairs[1:]):
        if r1 <= r0:
            raise ValueError("duplicate r values on the grid: %r" % (r1,))
    last_cheaper = -1
    for i, (_, g) in enumerate(pairs):
        if g < 0.0:                     # NaN compares False -> not cheaper
            last_cheaper = i
            continue
        last_cheaper = -1               # suffix broken
    if last_cheaper < 0:
        return None
    start = last_cheaper
    while start > 0 and pairs[start - 1][1] < 0.0:
        start -= 1
    return pairs[start][0]
