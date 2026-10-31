# -*- coding: utf-8 -*-
"""Synthetic experiments behind the 2026-10-29 statistics fixes (R2/R3/R5/R6).

These are small, reproducible Monte-Carlo checks of the *implementation*
properties, not evidence about the paper's empirical claims:

  A. paired g(r) interval: exactness for a fixed offset and winner's-curse bias
     of the min-over-partials functional (discrete candidate set).
  B. confidence set: coverage of the true best design, family-wise false
     inclusion rate, set size, and the near-tie / exact-tie behaviour
     (max-t vs Holm).
  C. CVaR: fractional tail weight agrees with the auxiliary programme and with
     the analytic normal CVaR at a large sample size.
  D. etp_from_g: agrees with the brute-force suffix definition on every sign
     pattern of a 4-point grid (discrete grid only).

Deterministic seeds; run from the revision directory:

    python tools/stat_experiment.py --out reports/stat_experiment.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from prei import stats  # noqa: E402


def _synthetic_means(reps, M, S, true_means, noise_sd, seed, n_boot=300,
                     method="max-t"):
    """Coverage of the true best and inclusion rate per candidate.

    A confidence *set* is not a per-candidate test: including a non-best
    candidate is not a Type-I error by itself.  What can be assessed is
    (i) whether the true best is retained (mis-exclusion rate) and
    (ii) whether a candidate that is worse by many standard errors still gets
    included (it should not).
    """
    truth_best = int(np.argmin(true_means))
    se_gap = noise_sd * math.sqrt(2.0 / S)
    included_count = np.zeros(len(true_means))
    miss, sizes = 0, []
    for rep in range(reps):
        rng = np.random.default_rng(seed + rep)
        common = rng.normal(0.0, noise_sd, size=(S, 1))
        mat = true_means[None, :] + common + rng.normal(
            0.0, noise_sd, size=(S, len(true_means)))
        cs = stats.confidence_set(mat, n_boot=n_boot, alpha=0.05,
                                  rng=np.random.default_rng(seed + 100000 + rep),
                                  method=method)
        included = set(cs["included"])
        for j in included:
            included_count[j] += 1
        miss += int(truth_best not in included)
        sizes.append(len(included))
    rate = included_count / reps
    dominated = [j for j in range(len(true_means))
                 if true_means[j] - true_means[truth_best] >= 6.0 * se_gap]
    return {"reps": reps, "method": method, "S": S, "noise_sd": noise_sd,
            "se_of_gap": float(se_gap),
            "coverage_best": 1.0 - miss / reps,
            "mis_exclusion_rate": miss / reps,
            "mean_set_size": float(np.mean(sizes)),
            "inclusion_rate_by_candidate": [float(x) for x in rate],
            "clearly_worse_inclusion_rate": (
                float(np.mean([rate[j] for j in dominated])) if dominated else None),
            "clearly_worse_count": len(dominated)}


def experiment_a(seed=20261029):
    """Paired g interval: exact offset, then winner's-curse bias of min()."""
    rng = np.random.default_rng(seed)
    S = 120
    part = rng.normal(100.0, 10.0, size=(S, 1))
    full = part[:, 0] + 10.0
    gi = stats.g_interval(full, part, n_boot=2000,
                          rng=np.random.default_rng(seed + 1))
    exact = {"g_hat": gi["g_hat"], "g_lo": gi["g_lo"], "g_hi": gi["g_hi"],
             "width": gi["g_hi"] - gi["g_lo"]}

    # winner's curse: K partial designs with the SAME true mean, full cheaper by
    # a fixed true offset; the max over paired differences (= min over partial
    # means) is biased up, so g_hat is biased up.  The old percentile interval
    # inherits that shift; the simultaneous max-t interval does not (T14/F09).
    true_g = -5.0
    K, reps = 6, 200
    g_min, g_fixed = [], []
    sim_lo, sim_hi, pct_lo, pct_hi, sim_crit = [], [], [], [], []
    for rep in range(reps):
        r = np.random.default_rng(seed + 500 + rep)
        common = r.normal(0.0, 4.0, size=(S, 1))
        p = common + r.normal(0.0, 2.0, size=(S, K))
        f = common + true_g + r.normal(0.0, 2.0, size=(S, 1))
        boot_seed = seed + 900 + rep
        sm = stats.g_interval(f, p, n_boot=400,
                              rng=np.random.default_rng(boot_seed),
                              method="simultaneous-max-t")
        pm = stats.g_interval(f, p, n_boot=400,
                              rng=np.random.default_rng(boot_seed),
                              method="percentile")
        g_min.append(sm["g_hat"])
        g_fixed.append(float(f.mean() - p[:, 0].mean()))
        sim_lo.append(sm["g_lo"])
        sim_hi.append(sm["g_hi"])
        sim_crit.append(sm["critical_value"])
        pct_lo.append(pm["g_lo"])
        pct_hi.append(pm["g_hi"])
    g_min = np.asarray(g_min)
    g_fixed = np.asarray(g_fixed)
    sim_lo, sim_hi = np.asarray(sim_lo), np.asarray(sim_hi)
    pct_lo, pct_hi = np.asarray(pct_lo), np.asarray(pct_hi)

    def _cov(lo, hi):
        return float(np.mean((lo <= true_g) & (true_g <= hi)))

    return {"fixed_offset_K1": exact,
            "min_over_partials": {
                "reps": reps, "K": K, "true_g": true_g,
                "mean_g_hat_min": float(g_min.mean()),
                "mean_g_hat_fixed_partial": float(g_fixed.mean()),
                "selection_bias_min_vs_fixed": float((g_min - g_fixed).mean()),
                "bias_vs_true_g": float(g_min.mean() - true_g),
                "coverage_of_true_g": _cov(sim_lo, sim_hi),
                "mean_width": float(np.mean(sim_hi - sim_lo)),
                "mean_critical_value": float(np.mean(sim_crit)),
                "method": "simultaneous-max-t",
                "note": ("g = max_k E[d_k]; the point estimate is biased up by "
                         "the max, the simultaneous max-t interval keeps "
                         "nominal coverage because the same bounds are used "
                         "for every candidate")},
            "percentile_diagnostic": {
                "coverage_of_true_g": _cov(pct_lo, pct_hi),
                "mean_width": float(np.mean(pct_hi - pct_lo)),
                "method": "paired_block_bootstrap_percentile",
                "note": ("diagnostic only (pre-T14 default); inherits the max "
                         "selection shift and under-covers near-ties, so it is "
                         "not reported as a nominal 95% interval")}}


def experiment_b(seed=20261029):
    M, S, reps = 8, 100, 300
    spread = np.array([0.00, 0.10, 0.20, 0.35, 0.50, 0.70, 0.90, 1.20])
    near = np.array([0.00, 0.005, 0.01, 0.02, 0.05, 0.10, 0.20, 1.20])
    out = {
        "separated_max_t": _synthetic_means(reps, M, S, spread, 0.6, seed),
        "separated_holm": _synthetic_means(reps, M, S, spread, 0.6, seed,
                                           method="holm"),
        "near_tie_max_t": _synthetic_means(reps, M, S, near, 0.6, seed + 7),
    }
    # exact tie between the two best candidates
    tie_mat = np.column_stack([np.full(50, 100.0), np.full(50, 100.0),
                               np.full(50, 140.0)])
    cs = stats.confidence_set(tie_mat, n_boot=200, alpha=0.05,
                              rng=np.random.default_rng(seed + 3))
    out["exact_tie"] = {"included": cs["included"],
                        "pvalues": [float(x) for x in cs["pvalues"]],
                        "family_size": cs["family_size"]}
    # zero-variance dominated column
    dom = np.column_stack([np.linspace(0, 1, 60), np.linspace(50, 51, 60)])
    cs2 = stats.confidence_set(dom, n_boot=200, alpha=0.05,
                               rng=np.random.default_rng(seed + 4))
    out["zero_variance_dominated"] = {"included": cs2["included"],
                                      "pvalue": float(cs2["pvalues"][1])}
    return out


def experiment_c(seed=20261029):
    rng = np.random.default_rng(seed)
    rows = []
    for n in (25, 100, 257, 1000):
        for alpha in (0.90, 0.95, 0.99):
            losses = rng.lognormal(2.0, 0.8, size=n)
            out = stats.empirical_cvar(losses, alpha)
            rows.append({"n": n, "alpha": alpha,
                         "cvar": out["cvar"], "cvar_aux": out["cvar_aux"],
                         "gap": abs(out["cvar"] - out["cvar_aux"]),
                         "tail_weight": out["tail_weight"],
                         "tail_weight_integer": abs(
                             out["tail_weight"] - round(out["tail_weight"])) < 1e-9})
    example = stats.empirical_cvar(list(range(0, 24)) + [100.0], 0.95)
    z = 1.959963984540054  # placeholder replaced below
    zq = 1.6448536269514722  # normal 95% quantile
    normal_cvar = math.exp(-0.5 * zq * zq) / (math.sqrt(2 * math.pi) * 0.05)
    big = rng.normal(0.0, 1.0, size=500_000)
    big_cvar = stats.empirical_cvar(big, 0.95)["cvar"]
    return {"fractional_example_84_6": example["cvar"],
            "aux_agreement_max_gap": max(r["gap"] for r in rows),
            "rows": rows,
            "normal_check": {"analytic_cvar": normal_cvar,
                             "monte_carlo_n500k": big_cvar,
                             "relative_gap": abs(big_cvar - normal_cvar) / normal_cvar},
            "note": ("exactness is with respect to the empirical distribution; the "
                     "normal check is a large-sample sanity check only")}


def experiment_d(seed=20261029):
    r_values = (0.2, 0.4, 0.6, 0.8)
    checked, mismatches = 0, []
    for pattern in itertools.product((-1.0, 0.0, 1.0), repeat=4):
        rows = [{"r": r, "g_hat": float(g)} for r, g in zip(r_values, pattern)]
        got = stats.etp_from_g(rows)
        want = brute_force_etp(pattern, r_values)
        checked += 1
        if (got is None) != (want is None) or (
                got is not None and abs(got - want) > 1e-12):
            mismatches.append({"pattern": pattern, "got": got, "want": want})
    return {"grid_points": len(r_values), "patterns_checked": checked,
            "mismatches": mismatches,
            "note": ("discrete grid only; g_hat == 0 is not cheaper and breaks "
                     "the suffix")}


def brute_force_etp(pattern, r_values):
    for i in range(len(pattern)):
        if all(g < 0.0 for g in pattern[i:]):
            return float(r_values[i])
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "reports",
                                                  "stat_experiment.json"))
    args = ap.parse_args(argv)
    payload = {"generated_by": "tools/stat_experiment.py",
               "a_paired_g_interval": experiment_a(),
               "b_confidence_set": experiment_b(),
               "c_cvar": experiment_c(),
               "d_etp_grid": experiment_d()}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True,
                  default=lambda o: float(o))
        fh.write("\n")
    print(json.dumps({k: payload[k] for k in ("a_paired_g_interval",
                                              "b_confidence_set",
                                              "d_etp_grid")},
                     ensure_ascii=False, indent=2)[:4000])
    print("wrote", args.out)


if __name__ == "__main__":
    main()
