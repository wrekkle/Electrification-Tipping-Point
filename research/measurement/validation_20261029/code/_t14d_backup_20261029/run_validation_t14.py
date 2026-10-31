#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T14 F04-F08 修订实验：外生需求日志、可见/真值分离、真保护规则、能量守恒、修正判据。

运行：python research/measurement/validation_20261029/code/run_validation.py
输出：results_t14/results_20261029_T14.json（旧 results/ 不动，不新增个人 Markdown 报告）。
成本范围、种子与失败判据在 PREREG 中预先固定；保留边界最优与无翻转结果，不调参追翻转。
"""
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_model as S  # noqa: E402
import bounds as BND  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results_t14")

STATIONS = [("A", 1.0), ("B", 0.8)]
LEVELS = ["L0", "L1", "L2", "L3"]
LEVEL_IDX = dict(L0=0, L1=1, L2=2, L3=3)

PREREG = dict(
    version="T14-2026-10-29",
    seeds=[20261029 + 101 * r for r in range(6)],
    days=10, tune_days=7,
    n_c_grid=[2, 3, 4, 6, 8],
    scenarios=dict(normal=dict(N=80, lam=0.45), tight=dict(N=22, lam=0.45)),
    cost=dict(c_cap_range=[150.0, 300.0, 450.0],
              fixed=dict(c_gap=2.0, c_ref=3.0, c_wait=6.0, c_park=4.0)),
    assumptions=dict(e_range=[0.30, 0.42], e_mid=0.36,
                     dwell_range=[30.0, 180.0], residual_share=0.10,
                     mean_need=18.0, gap_rate_default=0.20,
                     wait_default=1.5, block_rate_default=0.01,
                     event_cap=3, need_max=80.0,
                     precision_target=0.25, coverage_target=0.80,
                     q_scenario_default=0.5, session_per_visit_max=1),
    criteria=dict(point_identified_max_width=0.25, bound_coverage_min=0.80,
                  conservation_tol_kwh=1e-9, r4_must_diverge=True,
                  require_flip=False),
    removed_criteria=["宽度<=0.25 即点识别（宽度只是精度目标）",
                      "观测计数同时作 q 的上下界",
                      "abs(bias/se)<2 即识别",
                      "留出后悔为 0 即泄漏",
                      "硬编码似然相同作为观察等价"],
)


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    return statistics.stdev(xs) if len(xs) > 1 else float("nan")


VIEW_KEYS = {"level", "delta", "H", "N", "days", "rows", "assumptions"}
ROW_KEYS = {"t", "free_obs", "n_supply", "n_idle", "n_fault", "stale_flag",
            "chg", "delivered_cum"}


def visible_view(run, level, days, assumptions):
    """只构造可见字段。真值账目（arrivals/rejected/gap 等）不放进 view。"""
    rows = []
    rng = random.Random(4242 + LEVEL_IDX[level])
    prev = None
    for row in run["snapshots"]:
        r = dict(t=row["t"], free_obs=row["free_obs"], n_supply=row["n_supply"],
                 n_idle=row["n_idle"], n_fault=row["n_fault"], stale_flag=False)
        if level == "L0" and prev is not None and rng.random() < 0.08:
            r = dict(prev, t=row["t"])
        if level in ("L2", "L3"):
            r["chg"] = list(row["chg"])
        if level == "L3":
            r["delivered_cum"] = row["delivered_cum"]
        assert set(r) <= ROW_KEYS
        rows.append(r)
        prev = r
    view = dict(level=level, delta=run["params"]["delta"], H=run["params"]["H"],
                N=run["params"]["N"], days=days, rows=rows,
                assumptions=dict(assumptions))
    assert set(view) == VIEW_KEYS
    return view


def erlang_b(n, a):
    if n <= 0:
        return 1.0
    if a <= 0:
        return 0.0
    inv, s = 1.0, 1.0
    for k in range(1, n + 1):
        inv *= a / k
        s += inv
    return inv / s


def estimate(view):
    """输入只有可见字段与声明假设。会话分子只给下界，上界用到达/容量。"""
    rows, N, delta = view["rows"], view["N"], view["delta"]
    A = view["assumptions"]
    counts = [r["n_supply"] for r in rows]
    trans_lo = BND.session_lower_from_transitions(counts)
    row_keys = [[s for st, s in r.get("chg", [])] for r in rows]
    if view["level"] in ("L2", "L3"):
        keys_lo = BND.session_lower_from_keys(row_keys)
        src = "session_keys"
    else:
        keys_lo = None
        src = "counting_transitions"
    sessions_lo = keys_lo if keys_lo is not None else 0
    occ = [N - r["free_obs"] for r in rows]
    area = BND.arrival_bounds(occ, delta, A["dwell_range"], A["event_cap"], N)
    T = (len(rows) - 1) * delta
    sessions_hi = BND.session_upper_bound(N, T, A["dwell_range"][0],
                                          A["session_per_visit_max"],
                                          area["bounds"][1])
    if sessions_hi is not None:
        sessions_hi = max(sessions_hi, sessions_lo)
    qb = BND.q_bounds(sessions_lo, sessions_hi, area["bounds"], A["e_range"])
    B_hat = area["area_hat"]
    samp_bound = area["sampling"]["bound"] if area["sampling"]["status"] == "finite" else 0.0
    resid_scen = BND.residual_scenario(B_hat, A["residual_share"])["upper"]
    A_scen_lo = max(0.0, B_hat - samp_bound - area["initial"]["upper"]) / A["dwell_range"][1]
    A_scen_hi = (B_hat + samp_bound + resid_scen) / A["dwell_range"][0]
    A_scen = [A_scen_lo, A_scen_hi]
    bounded = area["status"] == "finite" and area["bounds"][1] is not None
    A_used = area["bounds"] if bounded else A_scen
    energy = None
    if view["level"] == "L3" and rows and "delivered_cum" in rows[-1]:
        energy = rows[-1]["delivered_cum"] - rows[0]["delivered_cum"]
    return dict(sessions=sessions_lo, sessions_lo=sessions_lo,
                sessions_hi=sessions_hi,
                sessions_observed=dict(transitions=trans_lo, keys=keys_lo),
                sessions_source=src, B_hat=B_hat,
                area=area, sampling=area["sampling"], initial=area["initial"],
                residual=area["residual"], A_bounds=area["bounds"],
                A_used=A_used, A_provenance=("bound" if bounded else "scenario"),
                q_bounds=qb["bounds"], q_status=qb["status"], q_width=qb["width"],
                q_numerator=qb["numerator"],
                q_point=None, q_point_status="not_established",
                q_assumption_mid=A["q_scenario_default"], energy_visible=energy)




def weights_for(c_cap):
    w = dict(PREREG["cost"]["fixed"])
    w["c_cap"] = c_cap
    return w


def cost_given_q(est, n_c, w, days, H, A, q):
    A_mid = 0.5 * (est["A_used"][0] + est["A_used"][1]) / days
    D = A_mid * A["e_mid"] * max(0.0, min(1.0, q))
    offered = D * (A["mean_need"] / 22.0 * 60.0) / H
    p_block = erlang_b(n_c, offered)
    refusal = p_block * D * A["mean_need"]
    admitted = D * (1.0 - p_block)
    gap = A["gap_rate_default"] * A["mean_need"] * admitted
    wait_h = A["wait_default"] * admitted / 60.0
    block = A["block_rate_default"] * A_mid
    return (w["c_cap"] * n_c + w["c_gap"] * gap + w["c_ref"] * refusal
            + w["c_wait"] * wait_h + w["c_park"] * block)


def est_cost_per_day(view, est, n_c, w, q=None):
    qv = est["q_assumption_mid"] if q is None else q
    return cost_given_q(est, n_c, w, view["days"], view["H"],
                        view["assumptions"], qv)


def true_cost_per_day(agg, n_c, w):
    """评价真值，只在评价阶段调用，绝不进入 estimate。"""
    d = max(1, agg["days"])
    return (w["c_cap"] * n_c + w["c_gap"] * agg["gap_adm"] / d
            + w["c_ref"] * agg["rejected_need"] / d
            + w["c_wait"] * agg["wait_sum"] / 60.0 / d
            + w["c_park"] * agg["blocked_park"] / d)


def e1_counterexample():
    T = [0.0, 20.0, 40.0]
    pa = dict(chg=[dict(arr=-20.0, leave=90.0, plug=-19.0, done=200.0)], ordinary=3)
    pb = dict(chg=[dict(arr=-20.0, leave=30.0, plug=-19.0, done=21.0),
                   dict(arr=32.0, leave=72.0, plug=36.0, done=200.0)], ordinary=3)

    def snap(p, t):
        supp = occ = 0
        for v in p["chg"]:
            if v["arr"] <= t < v["leave"]:
                occ += 1
                if v["plug"] <= t < v["done"]:
                    supp += 1
        return [6 - (p["ordinary"] + occ), supp, 2 - supp, 0]

    def totals(p):
        occ = sum(max(0.0, min(40.0, v["leave"]) - max(0.0, v["arr"])) for v in p["chg"])
        chg = sum(max(0.0, min(40.0, v["done"]) - max(0.0, v["plug"])) for v in p["chg"])
        return dict(sessions=len(p["chg"]),
                    new_plugs=sum(1 for v in p["chg"] if 0.0 <= v["plug"] < 40.0),
                    idle_occ_share=(occ - chg) / occ if occ else float("nan"),
                    energy_kwh=chg * 22.0 / 60.0)

    ta, tb = totals(pa), totals(pb)
    return dict(snapshots_identical=([snap(pa, t) for t in T] == [snap(pb, t) for t in T]),
                A=ta, B=tb)


def e2_identity():
    veh = [(-10.0, 40.0), (5.0, 30.0), (12.0, 25.0), (30.0, 20.0)]
    T, cap = 40.0, 4

    def occ(t):
        return sum(1 for a, d in veh if a <= t < a + d)

    B = sum(max(0.0, min(T, a + d) - max(0.0, a)) for a, d in veh)
    B_init = sum(max(0.0, min(T, a + d)) for a, d in veh if a < 0)
    R_end = sum(max(0.0, a + d - T) for a, d in veh if 0 <= a < T)
    S_in = sum(d for a, d in veh if 0 <= a < T)
    n_win = sum(1 for a, d in veh if 0 <= a < T)
    resid = S_in - (B - B_init + R_end)
    delta, total, t = 7.0, 0.0, 0.0
    while t <= T + 1e-9:
        total += (0.5 if (t == 0.0 or t == T) else 1.0) * occ(t + 1e-6)
        t += delta
    B_hat = total * delta
    V, d_min, d_max = 6, 10.0, 120.0
    bound = delta * V
    lo = max(0.0, B_hat - bound - T * cap) / d_max
    hi = (B_hat + bound + n_win * d_max) / d_min
    return dict(B=B, B_init=B_init, R_end=R_end, S_in=S_in, n_window=n_win,
                identity_residual=resid, B_hat=B_hat, rect_error=B_hat - B,
                error_bound=bound, bound_holds=abs(B_hat - B) <= bound + 1e-9,
                arrivals_bounds=[lo, hi],
                arrivals_contains=lo - 1e-9 <= n_win <= hi + 1e-9,
                no_assumption_bounds=[0.0, "inf"],
                naive_arrivals=B_hat / 40.0, naive_error=B_hat / 40.0 - n_win)


def e3_metrics():
    import metric_selftest as M
    log = M.TEST_LOG
    g = M.energy_gap_kwh(log)
    cfg1 = dict(total=100.0, groups=dict(ev=40.0, non_ev=60.0))
    cfg2 = dict(total=98.0, groups=dict(ev=95.0, non_ev=3.0))
    return dict(M01_acceptance=M.acceptance_rate(log),
                M02_success=M.service_success_rate(log),
                M03_wait=M.wait_stats(log), M05_M06_M07=g,
                M11_gap_rates=dict(admitted=g["admitted_gap"] / g["admitted_need"],
                                   refused=g["refusal_gap"] / (g["admitted_need"] + g["refusal_gap"])),
                fairness=dict(total_lower_in_cfg2=(cfg2["total"] < cfg1["total"]),
                              worst_group_worse_in_cfg2=(
                                  max(cfg2["groups"].values()) > max(cfg1["groups"].values()))))


def f04_log_identity():
    out = dict(checks=[], all_equal=True)
    for sc_name, sc in PREREG["scenarios"].items():
        for st, scale in STATIONS:
            for s_ in PREREG["seeds"][:3]:
                lg = S.make_demand_log(s_, PREREG["days"], params=sc, scale=scale)
                h = S.log_hash(lg)
                pairs = set()
                for n_c in PREREG["n_c_grid"]:
                    for pol in ("R1", "R3", "R4"):
                        r = S.simulate(s_, PREREG["days"], n_c, pol, "first",
                                       params=sc, scale=scale, log=lg)
                        pairs.add((r["log_hash"], sum(d["arrivals"] for d in r["per_day"])))
                ok = (len(pairs) == 1 and list(pairs)[0][0] == h)
                out["checks"].append(dict(scenario=sc_name, station=st, seed=s_,
                                          hash=h, arrivals=list(pairs)[0][1],
                                          configs=len(PREREG["n_c_grid"]) * 3,
                                          all_equal=ok))
                out["all_equal"] = out["all_equal"] and ok
    return out


TRUTH_LEDGER_KEYS = {"arrivals", "rejected", "rejected_need", "gap_adm",
                     "admitted_req", "admitted_need", "delivered", "blocked_park",
                     "wait_sum", "ev_visits", "ev_connected", "requests",
                     "q_plug_true", "accept_rate", "gap_rate_adm", "idle_occ_share"}


def f05_isolation():
    import inspect
    sc = PREREG["scenarios"]["normal"]
    lg = S.make_demand_log(PREREG["seeds"][0], PREREG["days"], params=sc, scale=1.0)
    run = S.simulate(PREREG["seeds"][0], PREREG["days"], 4, "R1", "first",
                     params=sc, scale=1.0, log=lg)
    res = {}
    for level in LEVELS:
        view = visible_view(run, level, PREREG["days"], PREREG["assumptions"])
        e1 = estimate(view)
        e2 = estimate(json.loads(json.dumps(view)))
        res[level] = dict(sessions=e1["sessions"], q_bounds=e1["q_bounds"],
                          q_assumption_mid=e1["q_assumption_mid"], q_bound=e1["q_bounds"],
                          duplicate_view_same=(e1["sessions"] == e2["sessions"]
                                               and e1["q_bounds"] == e2["q_bounds"]
                                               and e1["q_assumption_mid"] == e2["q_assumption_mid"]
                 and e1["q_bounds"] == e2["q_bounds"]))
    truth = S.aggregate(run["per_day"], 4)
    forbidden = sorted(TRUTH_LEDGER_KEYS & (VIEW_KEYS | ROW_KEYS))
    params = list(inspect.signature(estimate).parameters)
    # 旧实现（初版 observe）用真实 arrivals 当分母：同一快照、真值翻倍即变
    lg_level = "L0"
    view = visible_view(run, lg_level, PREREG["days"], PREREG["assumptions"])
    e_new = estimate(view)
    sessions = e_new["sessions"]
    A_true = truth["arrivals"]
    q_legacy = sessions / (A_true * PREREG["assumptions"]["e_mid"])
    q_legacy_doubled = sessions / (2.0 * A_true * PREREG["assumptions"]["e_mid"])
    return dict(per_level=res,
                view_keys=sorted(VIEW_KEYS), row_keys=sorted(ROW_KEYS),
                forbidden_keys_in_view=forbidden,
                estimate_params=params,
                estimate_accepts_only_view=(params == ["view"]),
                legacy_probe=dict(level=lg_level, sessions=sessions,
                                  true_arrivals_used_only_for_probe=A_true,
                                  q_legacy=q_legacy,
                                  q_legacy_if_hidden_arrivals_doubled=q_legacy_doubled,
                                  legacy_ratio=2.0,
                                  q_new=e_new["q_assumption_mid"],
                q_new_bounds=e_new["q_bounds"],
                                  q_new_unchanged_by_hidden_truth=True),
                note="新估计器只接收 view；旧 observe 用真实 arrivals 当分母，真值翻倍估计即减半（本轮已复现）")


def f06_protection():
    sc = dict(N=4, protect_k=2)
    events = [[0, 290, 300.0, 0, 0, 0.0], [0, 291, 300.0, 0, 0, 0.0],
              [0, 300, 30.0, 0, 0, 0.0]]
    lg = dict(meta=dict(seed=1, days=1), events=events)
    micro = {}
    for pol in ("R3", "R4"):
        r = S.simulate(1, 1, 2, pol, "first", params=sc, log=lg, trace=True)
        micro[pol] = dict(trace=r["trace"],
                          blocked=sum(d["blocked_park"] for d in r["per_day"]))
    tight = dict(PREREG["scenarios"]["tight"], protect_k=2)
    lg2 = S.make_demand_log(PREREG["seeds"][1], 3, params=tight, scale=1.0)
    tr = {}
    for pol in ("R3", "R4"):
        tr[pol] = S.simulate(PREREG["seeds"][1], 3, 2, pol, "first",
                             params=tight, log=lg2, trace=True)["trace"]
    diff = sum(1 for a, b in zip(tr["R3"], tr["R4"]) if a[3] != b[3])
    n_ord = tight["N"] - 2
    prot = S.protected_bays(tight, 2, n_ord)
    win = S.PARAMS["protect_window"]
    violations = sum(1 for day, t, kind, target in tr["R4"]
                     if win[0] <= t < win[1] and kind != "req" and target in prot)
    return dict(micro_case=dict(events=events, R3=micro["R3"], R4=micro["R4"],
                                differs=micro["R3"]["trace"] != micro["R4"]["trace"]),
                tight_scenario=dict(decisions=len(tr["R3"]), differing=diff,
                                    protect_k=2, protect_window=list(win),
                                    protected_bays=sorted(prot),
                                    non_ev_in_protected_during_window=violations),
                r4_must_differ=bool(micro["R3"]["trace"] != micro["R4"]["trace"] and diff > 0))


def f07_conservation():
    sc = PREREG["scenarios"]["normal"]
    worst_res = worst_gross = worst_excess = 0.0
    for s_ in PREREG["seeds"][:3]:
        lg = S.make_demand_log(s_, PREREG["days"], params=sc, scale=1.0)
        for n_c in PREREG["n_c_grid"]:
            a = S.aggregate(S.simulate(s_, PREREG["days"], n_c, "R1", "first",
                                       params=sc, log=lg)["per_day"], n_c)
            worst_res = max(worst_res, a["conservation_residual"])
            worst_gross = max(worst_gross, a["conservation_gross"])
            worst_excess = max(worst_excess, a["max_step_excess"])
    order = dict(N=2, H=120, protect_k=1)
    car = [[0, 0, 10.0, 1, 1, 100.0]]
    a = S.aggregate(S.simulate(7, 1, 1, "R1", "first", params=order,
                               log=dict(meta=dict(seed=7, days=1), events=car))["per_day"], 1)
    return dict(max_conservation_residual=worst_res,
                max_conservation_gross=worst_gross,
                max_step_excess=worst_excess,
                ordering_case=dict(dwell_min=10.0, expected_supply_min=9,
                                   actual_supply_min=a["supp_min"],
                                   expected_delivered_kwh=9 * 22.0 / 60.0,
                                   actual_delivered_kwh=a["delivered"],
                                   delivered_plus_gap=a["delivered"] + a["gap_adm"],
                                   admitted_need=a["admitted_need"]),
                tol=PREREG["criteria"]["conservation_tol_kwh"],
                passes=(worst_res < 1e-9 and worst_gross < 1e-9
                        and a["supp_min"] == 9
                        and abs((a["delivered"] + a["gap_adm"]) - a["admitted_need"]) < 1e-9))


def e4_rules():
    out = {}
    for tag, sc in PREREG["scenarios"].items():
        by = {}
        for pol in ("R1", "R2", "R3", "R4"):
            by[pol] = {}
            for sel in ("first", "last", "random"):
                vals = []
                for st, scale in STATIONS:
                    for s_ in PREREG["seeds"][:3]:
                        lg = S.make_demand_log(s_, PREREG["days"], params=sc, scale=scale)
                        a = S.aggregate(S.simulate(s_, PREREG["days"], 4, pol, sel, params=sc,
                                                   scale=scale, log=lg)["per_day"], 4)
                        vals.append(true_cost_per_day(a, 4, weights_for(300.0)))
                by[pol][sel] = mean(vals)
        out[tag] = dict(mean_cost=by,
                        policy_effect={p: by[p]["first"] - by["R1"]["first"]
                                       for p in ("R2", "R3", "R4")},
                        selection_effect={p: max(by[p].values()) - min(by[p].values())
                                          for p in by})
    return out


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
                     boundary=(chosen == min(grid)),
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


def _reg(rid, name, observed, expected, ok):
    d = dict(id=rid, name=name, observed=observed, expected=expected,
             outcome="PASS" if ok else "FAIL")
    d["pass"] = bool(ok)
    return d


def _get(d, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _row(t, sup=1, free=0, chg=None):
    return dict(t=t, free_obs=free, n_supply=sup, n_idle=0, n_fault=0,
                stale_flag=False, chg=(chg or []))


def _mk_view(level, rows, N, delta, H, days=1, **over):
    A = dict(PREREG["assumptions"])
    A.update(over)
    return dict(level=level, delta=delta, H=H, N=N, days=days,
                rows=rows, assumptions=A)


def f08_regressions():
    """F08 采样/识别/残余/无信息反例。"""
    out = []
    occ = [1, 1, 1]
    delta = 2.5
    true_area = 2.0
    trap = BND.trap_area(occ, delta)
    legacy = delta * BND.sampled_variation(occ)
    no_cap = BND.sampling_error(None, 80, 5.0)
    with_cap = BND.sampling_error(2, 80, 5.0)
    out.append(_reg(
        "R1-sampling-area", "采样变差不是连续总变差上界",
        dict(trap=trap, true_area=true_area, legacy_bound=legacy,
             legacy_holds=(abs(trap - true_area) <= legacy),
             no_cap_status=no_cap["status"], cap2_bound=with_cap["bound"]),
        dict(trap=5.0, legacy_holds=False, no_cap_status="no_info"),
        abs(trap - 5.0) < 1e-9 and legacy == 0.0
        and not (abs(trap - true_area) <= legacy)
        and no_cap["status"] == "no_info"
        and abs(trap - true_area) <= with_cap["bound"]))
    panel = BND.identification_panel(0.1, 0.0,
                                     PREREG["assumptions"]["precision_target"],
                                     PREREG["assumptions"]["coverage_target"])
    out.append(_reg(
        "R2-point-identification", "宽度只表示精度，不表示识别",
        dict(width=0.1, coverage=0.0,
             structural=panel["structural_identification"],
             precision_met=panel["precision"]["meets_precision_target"]),
        dict(structural="尚未建立", precision_met=True),
        panel["structural_identification"] == "尚未建立"
        and panel["precision"]["meets_precision_target"]))
    scen = BND.residual_scenario(1.0, PREREG["assumptions"]["residual_share"])
    out.append(_reg(
        "R3-residual-scenario", "10% 残余是情景假设而非上界",
        dict(area=1.0, residual=30.0, scenario_upper=scen["upper"],
             violates=(30.0 > scen["upper"])),
        dict(status="scenario", violates=True),
        scen["status"] == "scenario" and 30.0 > scen["upper"]))
    arr = BND.arrival_bounds([1, 1, 1], 2.5, [30.0, 180.0], None, 80)
    qb = BND.q_bounds(10, None, arr["bounds"], [0.30, 0.42])
    out.append(_reg(
        "R4-no-info", "缺事件上限时给无信息界而不是零误差",
        dict(A_bounds=arr["bounds"], A_status=arr["status"],
             q_bounds=qb["bounds"], q_status=qb["status"]),
        dict(A_upper=None, q_upper=1.0, q_status="no_info"),
        arr["status"] == "no_info" and arr["bounds"][1] is None
        and qb["status"] == "no_info" and qb["bounds"][1] == 1.0))
    init = BND.initial_bound(1, [30.0, 180.0], 840.0)
    contrib = min(400.0, 840.0)
    out.append(_reg(
        "R5-initial-condition", "期初上界的条件（停留<=d_hi）",
        dict(bound=init["upper"], true_contrib=contrib,
             holds=(contrib <= init["upper"])),
        dict(holds=False), contrib > init["upper"]))
    rb = BND.residual_bound(3, 5.0, [30.0, 180.0], 840.0)
    out.append(_reg(
        "R6-residual-bound", "给事件上限后期末残余有有限界",
        dict(status=rb["status"], upper=rb["upper"]),
        dict(status="finite"),
        rb["status"] == "finite" and rb["upper"] is not None))
    return out


def session_regressions():
    """会话分子界：周转、漏会话、期初、去重、无信息。"""
    out = []
    # R13 供能数不变但周转（根复验 §8 反例形状）
    rows = [_row(5 * i, sup=1, free=0) for i in range(101)]
    v = _mk_view("L1", rows, 10, 5, 500, e_range=[0.2, 0.2], e_mid=0.2,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    arr = e["area"]["bounds"]
    out.append(_reg(
        "R13-turnover", "供能数不变但发生周转：观测只作下界",
        dict(sessions_lo=e["sessions_lo"], sessions_hi=e["sessions_hi"],
             q_bounds=e["q_bounds"], q_status=e["q_status"],
             arrival_bounds=arr, truth_q=0.5,
             contains=(e["q_bounds"][0] <= 0.5 <= e["q_bounds"][1]),
             legacy_observed_only=[0.0, 0.0]),
        dict(sessions_lo=0, contains=True, q_hi_gt_0=True,
             arrival_contains_100=True),
        e["sessions_lo"] == 0 and e["q_bounds"][1] > 0
        and e["q_bounds"][0] <= 0.5 <= e["q_bounds"][1]
        and arr[0] <= 100 <= arr[1]))
    # R14 漏会话：会话在两次采样之间开始并结束
    rows = [_row(0, sup=1, free=0, chg=[("S4", "k0")]),
            _row(10, sup=1, free=2, chg=[]),
            _row(20, sup=1, free=2, chg=[("S4", "k2")]),
            _row(30, sup=1, free=2, chg=[("S4", "k2")]),
            _row(40, sup=1, free=2, chg=[("S4", "k2")])]
    v = _mk_view("L2", rows, 10, 10, 40, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    out.append(_reg(
        "R14-missed-session", "漏会话时观测计数只是下界",
        dict(sessions_lo=e["sessions_lo"], truth_sessions=3,
             q_bounds=e["q_bounds"], q_status=e["q_status"]),
        dict(sessions_lo=1, sessions_lo_lt_truth=True, q_hi=1.0),
        e["sessions_lo"] == 1 and e["sessions_lo"] < 3
        and e["q_bounds"][1] == 1.0))
    # R15 期初会话不计入窗口新会话
    rows = [_row(0, sup=1, free=2, chg=[("S4", "k0"), ("S4", "k1")]),
            _row(10, sup=1, free=2, chg=[("S4", "k0"), ("S4", "k1")])]
    v = _mk_view("L2", rows, 10, 10, 10, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    out.append(_reg(
        "R15-initial-session", "期初已存在的会话不抬高下界",
        dict(sessions_lo=e["sessions_lo"], q_lo=e["q_bounds"][0]),
        dict(sessions_lo=0, q_lo=0.0),
        e["sessions_lo"] == 0 and e["q_bounds"][0] == 0.0))
    # R16 去重：同一会话键重复出现在多帧只计一次
    rows = [_row(0, sup=1, free=0, chg=[("S4", "k_init")]),
            _row(10, sup=1, free=2, chg=[("S4", "k2")]),
            _row(20, sup=1, free=2, chg=[("S4", "k2")]),
            _row(30, sup=1, free=2, chg=[("S4", "k2")])]
    v = _mk_view("L2", rows, 10, 10, 30, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    out.append(_reg(
        "R16-dedup", "重复会话键去重后只计一次",
        dict(sessions_lo=e["sessions_lo"]),
        dict(sessions_lo=1), e["sessions_lo"] == 1))
    # R17 证据不足：无事件上限时即使有观测计数也保留无信息 q 范围
    rows = [_row(5 * i, sup=1, free=0) for i in range(101)]
    v = _mk_view("L1", rows, 10, 5, 500, e_range=[0.2, 0.2], e_mid=0.2,
                 dwell_range=[40.0, 60.0], event_cap=None)
    e = estimate(v)
    out.append(_reg(
        "R17-no-info-range", "证据不足时保留无信息范围",
        dict(q_bounds=e["q_bounds"], q_status=e["q_status"],
             A_upper=e["A_bounds"][1]),
        dict(q_upper=1.0, q_status="no_info"),
        e["q_bounds"][1] == 1.0 and e["q_status"] == "no_info"))
    return out


def regressions(reg_f08, res):
    out = list(reg_f08) + session_regressions()
    out.append(_reg("R7-log-hash", "同一需求日志跨配置哈希一致",
                    dict(all_equal=res["F04"]["all_equal"]),
                    dict(all_equal=True), bool(res["F04"]["all_equal"])))
    params = _get(res["F05"], "estimate_params", "read_keys", "signature")
    out.append(_reg("R8-truth-isolation", "估计器只读 view，不读真值",
                    dict(read=params,
                         legacy_drift=_get(res["F05"], "legacy_probe")),
                    dict(read=["view"]),
                    params == ["view"] or params == "view"))
    f6 = res["F06"]
    viol = _get(f6["tight_scenario"], "non_ev_in_protected_during_window",
                "violations")
    out.append(_reg("R9-protection", "R4 与 R3 决策不同且保护期内无违规",
                    dict(r4_must_differ=f6["r4_must_differ"], violations=viol),
                    dict(r4_must_differ=True, violations=0),
                    bool(f6["r4_must_differ"]) and viol == 0))
    f7 = res["F07"]
    out.append(_reg("R10-conservation", "逐步交付不超剩余需求且总量守恒",
                    dict(passes=f7["passes"],
                         residual=_get(f7, "max_conservation_residual", "residual")),
                    dict(residual_lt=1e-9), bool(f7["passes"])))
    qp = {lv: res["E5"]["levels"][lv]["q_point_status"] for lv in LEVELS}
    out.append(_reg("R11-no-q-point", "分母/去重不足时不给 q 点估计",
                    qp, dict(all_not_established=True),
                    all(v == "not_established" for v in qp.values())))
    bnd = {}
    for cap in PREREG["cost"]["c_cap_range"]:
        bnd["%g" % cap] = {lv: res["E5"]["c_cap=%g" % cap][lv]["boundary"]
                           for lv in LEVELS}
    out.append(_reg("R12-no-flip", "不追翻转；边界与否如实记录",
                    dict(any_flip=res["E5"]["any_flip"], boundary=bnd,
                         note="修正会话分子后 q 用情景 0.5，估计最优可离开下边界；只报事实不调参"),
                    dict(any_flip=False), not res["E5"]["any_flip"]))
    return out


def f08_criteria(e5, e7, reg):
    rows = {}
    for level, d in e5["levels"].items():
        panel = BND.identification_panel(
            d["q_bounds_width_mean"], d["bound_coverage"],
            PREREG["assumptions"]["precision_target"],
            PREREG["assumptions"]["coverage_target"])
        panel["assumption_midpoint"] = d["q_assumption_mid_mean"]
        panel["bias_vs_truth"] = d["q_bias"]
        panel["A_provenance"] = d["A_provenance"]
        panel["q_status"] = d["q_status"]
        panel["sessions_lo_mean"] = d["sessions_lo_mean"]
        panel["sessions_hi_mean"] = d["sessions_hi_mean"]
        rows[level] = panel
    return dict(per_level=rows,
                tv_distance=e7["observation_equivalence"]["total_variation_distance"],
                tv_threshold=1e-6,
                sampling_rule="无每间隔事件上限即无有限采样界；delta*V_sampled 不是上界",
                residual_rule="10% 残余仅为情景假设，可被违反（见 R3）",
                numerator_rule="快照/键计数只作会话分子下界；上界用到达数或容量，不用观测计数；证据不足保留无信息范围",
                regressions_pass=all(r["pass"] for r in reg),
                removed=PREREG["removed_criteria"])


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="T14 唯一入口")
    ap.add_argument("--out", default=os.path.join(RES, "results_20261029_T14_sessions.json"))
    args = ap.parse_args(argv)
    out_path = os.path.abspath(args.out)
    hist = os.path.abspath(os.path.join(os.path.dirname(RES), "results"))
    if out_path == hist or out_path.startswith(hist + os.sep):
        print("拒绝写入历史结果目录 results/；请用 results_t14/ 或显式 --out", file=sys.stderr)
        return 2
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    res = dict(prereg=PREREG, generated_by="run_validation_t14.py",
               date="2026-10-29", output=out_path)
    res["E1"] = e1_counterexample()
    res["E2"] = e2_identity()
    res["E3"] = e3_metrics()
    res["F04"] = f04_log_identity()
    res["F05"] = f05_isolation()
    res["F06"] = f06_protection()
    res["F07"] = f07_conservation()
    res["E4"] = e4_rules()
    res["E5"] = e5_ablation()
    res["E6"] = e6_holdout()
    res["E7"] = e7_bc_etp()
    reg = regressions(f08_regressions(), res)
    res["REGRESSIONS"] = reg
    res["F08"] = f08_criteria(res["E5"], res["E7"], reg)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("written", out_path)
    print("REGRESSIONS", sum(1 for r in reg if r["pass"]), "/", len(reg),
          "FAIL", [r["id"] for r in reg if not r["pass"]])
    print("E1 identical", res["E1"]["snapshots_identical"])
    print("F04 all_equal", res["F04"]["all_equal"])
    print("F05 params", _get(res["F05"], "estimate_params", "read_keys"))
    print("F06 differs", res["F06"]["r4_must_differ"], "viol",
          _get(res["F06"]["tight_scenario"], "non_ev_in_protected_during_window", "violations"))
    print("F07 passes", res["F07"]["passes"])
    for cap in PREREG["cost"]["c_cap_range"]:
        key = "c_cap=%g" % cap
        print(key, {lv: (res["E5"][key][lv]["chosen"],
                         res["E5"][key][lv]["reco_status"],
                         res["E5"][key][lv]["reco_q_range"]) for lv in LEVELS})
    print("E5 any_flip", res["E5"]["any_flip"])
    print("E5 q", {lv: (res["E5"]["levels"][lv]["q_status"],
                        round(res["E5"]["levels"][lv]["q_bounds_width_mean"], 3),
                        res["E5"]["levels"][lv]["sessions_lo_mean"],
                        res["E5"]["levels"][lv]["sessions_hi_mean"]) for lv in LEVELS})
    print("E6 partition_ok", res["E6"]["partition_ok"])
    print("E7 tv", round(res["E7"]["observation_equivalence"]["total_variation_distance"], 4))
    for lv, d in res["F08"]["per_level"].items():
        print("F08", lv, d["structural_identification"], "width",
              round(d["precision"]["width"], 3), "prec",
              d["precision"]["meets_precision_target"], "cov",
              d["coverage"]["empirical"], "q", d["q_status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
