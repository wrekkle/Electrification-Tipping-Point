# -*- coding: utf-8 -*-
"""T14 决策实验 E5-E7（从 run_validation_t14.py 机械拆分）。"""
import math
import random

from validation_common import (
    S, PREREG, STATIONS, LEVELS, mean, sd,
    visible_view, estimate, weights_for, cost_given_q, est_cost_per_day,
    true_cost_per_day,
)

def e5_ablation():
    sc = PREREG["scenarios"]["normal"]
    grid = PREREG["n_c_grid"]
    runs, hashes = {}, {}
    for st, scale in STATIONS:
        for s_ in PREREG["seeds"]:
            lg = S.make_demand_log(s_, PREREG["days"], params=sc, scale=scale)
            hashes[(st, s_)] = S.log_hash(lg)
            for n_c in grid:
                runs[(st, s_, n_c)] = S.simulate(s_, PREREG["days"], n_c, "R1", "first",
                                                 params=sc, scale=scale, log=lg)
    out = dict(levels={}, n_logs=len(set(hashes.values())),
               per_run_hash_equal=all(runs[k]["log_hash"] == hashes[(k[0], k[1])] for k in runs))
    est_cache, truth_cache = {}, {}
    for level in LEVELS:
        qs, qtrue, widths, cov = [], [], [], []
        for (st, s_), h in hashes.items():
            for n_c in grid:
                view = visible_view(runs[(st, s_, n_c)], level, PREREG["days"],
                                    PREREG["assumptions"])
                est_cache[(level, st, s_, n_c)] = estimate(view)
                a = S.aggregate(runs[(st, s_, n_c)]["per_day"], n_c)
                truth_cache[(st, s_, n_c)] = a
                if n_c == 4:
                    e = est_cache[(level, st, s_, n_c)]
                    qs.append(e["q_assumption_mid"])
                    qtrue.append(a["q_plug_true"])
                    widths.append(e["q_width"])
                    cov.append(e["q_bounds"][0] - 1e-12 <= a["q_plug_true"]
                               <= e["q_bounds"][1] + 1e-12)
        bias = mean(qs) - mean(qtrue)
        se = sd(qs) / math.sqrt(len(qs))
        out["levels"][level] = dict(
            q_assumption_mid_mean=mean(qs), q_true_mean=mean(qtrue), q_bias=bias,
            q_point_status="not_established", A_provenance=est_cache[(level, list(hashes)[0][0], list(hashes)[0][1], 4)]["A_provenance"],
            q_status=est_cache[(level, list(hashes)[0][0], list(hashes)[0][1], 4)]["q_status"],
            sessions_lo_mean=mean([est_cache[(level, st_, s_, 4)]["sessions_lo"] for (st_, s_) in hashes]),
            sessions_hi_mean=mean([est_cache[(level, st_, s_, 4)]["sessions_hi"] for (st_, s_) in hashes
                                   if est_cache[(level, st_, s_, 4)]["sessions_hi"] is not None]) if any(est_cache[(level, st_, s_, 4)]["sessions_hi"] is not None for (st_, s_) in hashes) else None,
            q_bias_ci95=[bias - 1.96 * se, bias + 1.96 * se],
            q_bounds_width_mean=mean(widths), bound_coverage=mean([1.0 if c else 0.0 for c in cov]),
            sessions_source=("session_keys" if level in ("L2", "L3") else "counting_transitions"),
            n_obs=len(qs))
    for cap in PREREG["cost"]["c_cap_range"]:
        key = "c_cap=%g" % cap
        out[key] = {}
        for level in LEVELS:
            est_by, true_by = {}, {}
            for n_c in grid:
                est_by[n_c] = mean([est_cost_per_day(
                    visible_view(runs[(st, s_, n_c)], level, PREREG["days"],
                                 PREREG["assumptions"]),
                    est_cache[(level, st, s_, n_c)], n_c, weights_for(cap))
                    for (st, s_) in hashes])
                true_by[n_c] = mean([true_cost_per_day(truth_cache[(st, s_, n_c)], n_c,
                                                       weights_for(cap))
                                     for (st, s_) in hashes])
            best_est = min(est_by.values())
            chosen = min(est_by, key=lambda k: est_by[k])
            best_true = min(true_by.values())
            est0 = est_cache[(level, list(hashes)[0][0], list(hashes)[0][1], 4)]
            if est0["q_status"] == "bounded":
                qlo, qhi = est0["q_bounds"]
                qgrid = [qlo + (qhi - qlo) * i / 4.0 for i in range(5)]
            else:
                qgrid = [0.0, 0.25, 0.5, 0.75, 1.0]
            picks = set()
            for q in qgrid:
                by_q = {}
                for n_c in grid:
                    by_q[n_c] = mean([cost_given_q(est_cache[(level, st, s_, n_c)], n_c,
                                                  weights_for(cap), PREREG["days"],
                                                  S.PARAMS["H"], PREREG["assumptions"], q)
                                      for (st, s_) in hashes])
                picks.add(min(by_q, key=lambda k: by_q[k]))
            d = dict(est=est_by, true_cost=true_by, chosen=chosen,
                     reco_set=[k for k in grid if est_by[k] <= best_est * 1.02],
                     regret_per_day=true_by[chosen] - best_true,
                     regret_pct=100.0 * (true_by[chosen] - best_true) / best_true,
                     reco_q_range=sorted(picks),
                     reco_status=("undetermined" if len(picks) == len(grid)
                                  else "range" if len(picks) > 1 else "single"),
                     boundary=(chosen in (min(grid), max(grid))),
                     boundary_side=("lower" if chosen == min(grid) else
                                    "upper" if chosen == max(grid) else "interior"),
                     true_optimal_set=[k for k in grid if abs(true_by[k] - best_true) <= 1e-9],
                     true_optimum_boundary=any(
                         k in (min(grid), max(grid))
                         for k in grid if abs(true_by[k] - best_true) <= 1e-9),
                     q_sensitivity_grid=qgrid,
                     reco_scope="finite_q_grid_sensitivity; no_all_q_guarantee",
                     q_used_provenance="scenario_assumption_not_estimate",
                     q_status=est0["q_status"],
                     A_provenance=est0["A_provenance"])
            out[key][level] = d
    # 追翻转：跨档是否出现不同选择（只报告，不追求）
    flips = {}
    for cap in PREREG["cost"]["c_cap_range"]:
        key = "c_cap=%g" % cap
        flips[key] = {lv: out[key][lv]["chosen"] for lv in LEVELS}
    out["chosen_by_level"] = flips
    out["any_flip"] = any(len({flips[k][lv] for lv in LEVELS}) > 1 for k in flips)
    return out


def e6_holdout():
    sc = PREREG["scenarios"]["normal"]
    days, tune, grid = PREREG["days"], PREREG["tune_days"], PREREG["n_c_grid"]
    key_pairs = [(a, b) for a, _ in STATIONS for b in PREREG["seeds"]]
    views, eval_truth = {}, {}
    partition_max_t = -1.0
    for st, scale in STATIONS:
        for s_ in PREREG["seeds"]:
            lg = S.make_demand_log(s_, days, params=sc, scale=scale)
            for n_c in grid:
                run = S.simulate(s_, days, n_c, "R1", "first", params=sc, scale=scale, log=lg)
                view = visible_view(run, "L3", days, PREREG["assumptions"])
                cut = tune * run["params"]["H"]
                tv = dict(view, rows=[r for r in view["rows"] if r["t"] < cut])
                views[(st, s_, n_c)] = dict(all=view, tune=tv)
                partition_max_t = max(partition_max_t,
                                      max(r["t"] for r in tv["rows"]) if tv["rows"] else -1.0)
                eval_truth[(st, s_, n_c)] = true_cost_per_day(
                    S.aggregate(run["per_day"][tune:], n_c), n_c, weights_for(300.0))

    def choose(key):
        est = {}
        for n_c in grid:
            est[n_c] = mean([est_cost_per_day(views[(st, s_, n_c)][key],
                                              estimate(views[(st, s_, n_c)][key]),
                                              n_c, weights_for(300.0)) for st, s_ in key_pairs])
        return min(est, key=lambda k: est[k])

    def regret(n_c):
        best = min(mean([eval_truth[(st, s_, k)] for st, s_ in key_pairs]) for k in grid)
        return mean([eval_truth[(st, s_, n_c)] for st, s_ in key_pairs]) - best

    clean, leaky = choose("tune"), choose("all")
    return dict(tune_days=tune, days=days,
                partition_max_t=partition_max_t,
                partition_ok=partition_max_t < tune * 840,
                chosen_clean=clean, chosen_leaky=leaky,
                regret_clean=regret(clean), regret_leaky=regret(leaky),
                optimism=regret(clean) - regret(leaky),
                note="泄漏判据=数据划分追踪，不是后悔是否为 0；leaky 仅量化乐观偏差")


def _binom_pmf(n, p, k):
    return math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                    + k * math.log(p) + (n - k) * math.log(1 - p))


def e7_bc_etp():
    e1, q1, e2, q2 = 240, 0.6, 360, 0.4
    ks = list(range(0, max(e1, e2) + 1))
    pa = [_binom_pmf(e1, q1, k) if k <= e1 else 0.0 for k in ks]
    pb = [_binom_pmf(e2, q2, k) if k <= e2 else 0.0 for k in ks]
    tv = 0.5 * sum(abs(x - y) for x, y in zip(pa, pb))
    C_obs, E_lo, E_hi, U_lo, U_hi = 144.0, 300.0, 480.0, 0.0, 48.0
    b_lo = max(0.0, (C_obs + U_lo) / E_hi)
    b_hi = min(1.0, (C_obs + U_hi) / E_lo)
    sc = PREREG["scenarios"]["normal"]
    grid = PREREG["n_c_grid"]
    nmax = max(grid)
    per_seed_cost = {}
    for n_c in grid:
        per_seed_cost[n_c] = []
        for st, scale in STATIONS:
            for s_ in PREREG["seeds"]:
                lg = S.make_demand_log(s_, PREREG["days"], params=sc, scale=scale)
                a = S.aggregate(S.simulate(s_, PREREG["days"], n_c, "R1", "first",
                                           params=sc, scale=scale, log=lg)["per_day"], n_c)
                per_seed_cost[n_c].append(true_cost_per_day(a, n_c, weights_for(300.0)))
    g = {n_c: mean(per_seed_cost[nmax]) - mean(per_seed_cost[n_c]) for n_c in grid}

    def regions(gvals):
        dom, tail = [], []
        cur = None
        for n_c in sorted(grid):
            if gvals[n_c] > 0:
                if cur is None:
                    cur = [n_c, n_c]
                else:
                    cur[1] = n_c
            else:
                if cur is not None:
                    dom.append(cur)
                    cur = None
        if cur is not None:
            dom.append(cur)
        cur = None
        for n_c in sorted(grid):
            if gvals[n_c] < 0:
                if cur is None:
                    cur = [n_c, n_c]
                else:
                    cur[1] = n_c
            else:
                cur = None
        if cur is not None:
            tail.append(cur)
        return dict(dominant=dom, sustained_negative_suffix=tail)

    rng = random.Random(20261029)
    n = len(per_seed_cost[nmax])
    inc = {n_c: 0 for n_c in grid}
    nboot = 300
    for _ in range(nboot):
        idx = [rng.randrange(n) for _ in range(n)]
        base = mean([per_seed_cost[nmax][i] for i in idx])
        for n_c in grid:
            if base - mean([per_seed_cost[n_c][i] for i in idx]) > 0:
                inc[n_c] += 1
    return dict(observation_equivalence=dict(
                    pairs=[dict(E=e1, q=q1, mean=e1 * q1), dict(E=e2, q=q2, mean=e2 * q2)],
                    equal_means=abs(e1 * q1 - e2 * q2) < 1e-12,
                    total_variation_distance=tv,
                    distributions_identical=(tv < 1e-6),
                    conclusion="期望相同但分布不同；观察等价必须由分布等价证明。"),
                B=dict(interval=[b_lo, b_hi], C_obs=C_obs, E=[E_lo, E_hi], U=[U_lo, U_hi]),
                etp=dict(sign_convention="g(r)=C_full-C_partial(r); g>0 部分更便宜, g<0 全安装更便宜",
                         r_grid={str(round(n_c / nmax, 4)): g[n_c] for n_c in grid},
                         regions=regions(g),
                         inclusion_prob={str(n_c): inc[n_c] / nboot for n_c in grid},
                         note="占优窗口= g>0 极大网格段；持续负后缀=末尾连续 g<0 段；不外推网格间"))
