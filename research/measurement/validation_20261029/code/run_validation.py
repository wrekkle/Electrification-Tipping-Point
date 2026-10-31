#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E1-E7：小型合成反例与观测删减实验。所有数值为合成情景，不是实测。

运行：python research/measurement/validation_20261029/code/run_validation.py
输出：results/results_20261029.json、results/EVIDENCE.md（脚本生成，重跑覆盖）
"""
import json
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_model as S  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "results")

SEEDS = [20261029 + 101 * r for r in range(6)]
DAYS = 10
TUNE_DAYS = 7
N_C_GRID = [2, 3, 4, 6, 8]
SCEN = dict(N=80, lam=0.45)
STRESS = dict(N=80, lam=0.45, ev_share=0.50, q_need=0.75)
STATIONS = [("A", 1.0), ("B", 0.8)]
E_ASSUM = 0.35
MEAN_NEED = 18.0
DEFAULT_GAP_RATE = 0.20
DEFAULT_BLOCK_FACTOR = 0.85


def mean(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs):
    return statistics.stdev(xs) if len(xs) > 1 else float("nan")


# ---------------------------------------------------------------- E1
def e1_counterexample():
    """两个不同底层过程产生同一组站级快照。"""
    T = [0.0, 20.0, 40.0]
    proc_a = dict(
        name="A 一次长会话跨全部快照",
        chg=[dict(v="EV1", arr=-20.0, leave=90.0, plug=-19.0, done=200.0)],
        ordinary=3,
    )
    proc_b = dict(
        name="B 两次会话 + 完成仍停 + 未插枪占位",
        chg=[dict(v="EV1", arr=-20.0, leave=30.0, plug=-19.0, done=21.0),
             dict(v="EV2", arr=32.0, leave=72.0, plug=36.0, done=200.0)],
        ordinary=3,
    )

    def snapshot(p, t):
        supp = 0
        occ_chg = 0
        for v in p["chg"]:
            if v["arr"] <= t < v["leave"]:
                occ_chg += 1
                if v["plug"] <= t < v["done"]:
                    supp += 1
        occupied = p["ordinary"] + occ_chg
        return dict(free=6 - occupied, n_supply=supp, n_guns=2,
                    n_idle=2 - supp, n_fault=0)

    def area(p, lo, hi):
        return sum(max(0.0, min(hi, v["leave"]) - max(lo, v["arr"])) for v in p["chg"])

    def charging_min(p, lo, hi):
        return sum(max(0.0, min(hi, v["done"]) - max(lo, v["plug"])) for v in p["chg"])

    out = {}
    for p in (proc_a, proc_b):
        snaps = [snapshot(p, t) for t in T]
        sess = len(p["chg"])
        new_plug = sum(1 for v in p["chg"] if 0.0 <= v["plug"] < 40.0)
        occ = area(p, 0.0, 40.0)
        chg_min = charging_min(p, 0.0, 40.0)
        out[p["name"]] = dict(
            snapshots=snaps, sessions=sess, new_plugs=new_plug,
            idle_occ_share=((occ - chg_min) / occ if occ else float("nan")),
            energy_kwh=chg_min * 22.0 / 60.0,
        )
    a = out[proc_a["name"]]
    b = out[proc_b["name"]]
    sig = lambda r: [(d["free"], d["n_supply"], d["n_idle"], d["n_fault"]) for d in r["snapshots"]]
    return dict(snapshots_identical=(sig(a) == sig(b)), A=a, B=b,
                derived=dict(
                    sessions=(a["sessions"], b["sessions"]),
                    new_plugs=(a["new_plugs"], b["new_plugs"]),
                    idle_occ_share=(a["idle_occ_share"], b["idle_occ_share"]),
                    energy_kwh=(a["energy_kwh"], b["energy_kwh"])))


# ---------------------------------------------------------------- E2
def e2_identity():
    veh = [dict(arr=-10.0, dwell=40.0), dict(arr=5.0, dwell=30.0),
           dict(arr=12.0, dwell=25.0), dict(arr=30.0, dwell=20.0)]
    T = 40.0
    cap = 4

    def occ(t):
        return sum(1 for v in veh if v["arr"] <= t < v["arr"] + v["dwell"])

    B = sum(max(0.0, min(T, v["arr"] + v["dwell"]) - max(0.0, v["arr"])) for v in veh)
    B_init = sum(max(0.0, min(T, v["arr"] + v["dwell"])) for v in veh if v["arr"] < 0)
    R_end = sum(max(0.0, v["arr"] + v["dwell"] - T) for v in veh if 0 <= v["arr"] < T)
    S_in = sum(v["dwell"] for v in veh if 0 <= v["arr"] < T)
    n_win = sum(1 for v in veh if 0 <= v["arr"] < T)
    resid = S_in - (B - B_init + R_end)
    delta = 7.0
    total = 0.0
    t = 0.0
    while t <= T + 1e-9:
        w = 0.5 if (t == 0.0 or t == T) else 1.0
        total += w * occ(t + 1e-6)
        t += delta
    B_hat = total * delta
    V = 6
    bound = delta * V
    d_min, d_max = 10.0, 120.0
    b_init_max = T * cap
    r_end_max = n_win * d_max
    lo = max(0.0, B_hat - bound - b_init_max) / d_max
    hi = (B_hat + bound + r_end_max) / d_min
    naive = B_hat / 40.0
    return dict(B=round(B, 6), B_init=round(B_init, 6), R_end=round(R_end, 6),
                S_in=round(S_in, 6), n_window=n_win,
                identity_residual=round(resid, 9), B_hat=round(B_hat, 6),
                rect_error=round(B_hat - B, 6), error_bound=bound,
                bound_holds=(abs(B_hat - B) <= bound + 1e-9),
                arrivals_bounds=[round(lo, 4), round(hi, 4)],
                arrivals_contains=(lo - 1e-9 <= n_win <= hi + 1e-9),
                no_assumption_bounds=[0.0, "inf"],
                naive_arrivals=round(naive, 4), naive_error=round(naive - n_win, 4))


# ---------------------------------------------------------------- E3
def e3_metrics():
    import metric_selftest as M
    log = M.TEST_LOG
    g = M.energy_gap_kwh(log)
    cfg1 = dict(total=100.0, groups=dict(ev=40.0, non_ev=60.0))
    cfg2 = dict(total=98.0, groups=dict(ev=95.0, non_ev=3.0))
    return dict(
        M01_acceptance=M.acceptance_rate(log),
        M02_success=M.service_success_rate(log),
        M03_wait=M.wait_stats(log), M05_M06_M07=g,
        M11_gap_rates=dict(
            admitted=g["admitted_gap"] / g["admitted_need"],
            refused=g["refusal_gap"] / (g["admitted_need"] + g["refusal_gap"])),
        fairness=dict(cfg1=cfg1, cfg2=cfg2,
                      total_lower_in_cfg2=(cfg2["total"] < cfg1["total"]),
                      worst_group_worse_in_cfg2=(max(cfg2["groups"].values())
                                                   > max(cfg1["groups"].values()))),
        equal_coefficient_blindness=dict(
            c_gap=2.0, c_ref=2.0, cost_change_per_kwh=0.0,
            note="c_gap=c_ref 时把 1 kWh 从已接纳缺口移到拒绝缺口，总成本不变"),
    )


# ---------------------------------------------------------------- 观测层
LEVEL_IDX = dict(L0=0, L1=1, L2=2, L3=3)


def observe(run, level, base_seed):
    """按 L0-L3 生成观测量；只改观测层，DGP 不变。"""
    snaps = run["snapshots"]
    agg = S.aggregate(run["per_day"])
    rng = random.Random(base_seed + 7000 + LEVEL_IDX[level])
    if level == "L0":
        seq = []
        prev = None
        for row in snaps:
            cur = dict(row) if (prev is None or rng.random() >= 0.08) else prev
            seq.append(cur)
            prev = cur
        sessions_hat = sum(max(0, seq[i]["n_supply"] - seq[i - 1]["n_supply"])
                           for i in range(1, len(seq)))
    elif level == "L1":
        sessions_hat = sum(max(0, snaps[i]["n_supply"] - snaps[i - 1]["n_supply"])
                           for i in range(1, len(snaps)))
    else:
        seen = set()
        for row in snaps:
            for st, sess in row["chg"]:
                if sess is not None:
                    seen.add(sess)
        sessions_hat = len(seen)
    q_hat = sessions_hat / max(1.0, agg["arrivals"] * E_ASSUM)
    return dict(sessions_hat=sessions_hat, q_plug_hat=q_hat, agg=agg)


def est_cost(level, n_c, obs):
    agg = obs["agg"]
    P = S.PARAMS
    if level == "L3":
        gp = agg["gap_adm"]
        block = agg["blocked_park"]
    else:
        gp = DEFAULT_GAP_RATE * MEAN_NEED * agg["admitted_req"]
        block = DEFAULT_BLOCK_FACTOR * agg["blocked_park"]
    D = agg["arrivals"] * E_ASSUM * obs["q_plug_hat"]
    offered = D * (MEAN_NEED / P["p_rated"] * 60.0) / P["H"]
    p_block = S.erlang_b(n_c, offered)
    gr = p_block * D * MEAN_NEED
    wait_h = 1.5 * agg["admitted_req"] / 60.0
    return (P["c_cap"] * n_c + P["c_gap"] * gp + P["c_ref"] * gr
            + P["c_wait"] * wait_h + P["c_park"] * block)


# ---------------------------------------------------------------- E4
def e4_rules():
    seeds = SEEDS[:3]
    rows = []
    for policy in ("R1", "R2", "R3", "R4"):
        for sel in ("first", "last", "random"):
            vals = []
            for station, scale in STATIONS:
                for s_ in seeds:
                    r = S.simulate(s_, DAYS, 4, policy, sel, scen=SCEN, scale=scale)
                    vals.append(S.aggregate(r["per_day"])["cost_per_day"])
            rows.append(dict(policy=policy, selection=sel,
                            cost_mean=mean(vals), cost_sd=sd(vals)))
    by = {}
    for r in rows:
        by.setdefault(r["policy"], {})[r["selection"]] = r["cost_mean"]
    selection_effect = {p: max(by[p].values()) - min(by[p].values()) for p in by}
    policy_effect = dict(
        R2=by["R2"]["first"] - by["R1"]["first"],
        R3=by["R3"]["first"] - by["R1"]["first"],
        R4=by["R4"]["first"] - by["R1"]["first"])
    confounded = [p for p in ("R2", "R3", "R4")
                  if abs(policy_effect[p]) < selection_effect[p]]
    return dict(rows=rows, policy_effect=policy_effect,
                selection_effect=selection_effect, confounded=confounded)


# ---------------------------------------------------------------- E4b
def e4_scenarios():
    """同一 n_c、同一需求、同一成本，在宽松/紧张两种车位压力下比较 R1-R4。"""
    seeds = SEEDS[:3]
    out = {}
    for tag, sc in (("normal", dict(N=80, lam=0.45)), ("tight", dict(N=48, lam=0.55))):
        rows = []
        for policy in ("R1", "R2", "R3", "R4"):
            for sel in ("first", "last", "random"):
                vals = []
                for station, scale in STATIONS:
                    for s_ in seeds:
                        r = S.simulate(s_, DAYS, 4, policy, sel, scen=sc, scale=scale)
                        vals.append(S.aggregate(r["per_day"])["cost_per_day"])
                rows.append(dict(policy=policy, selection=sel, cost_mean=mean(vals)))
        by = {}
        for r in rows:
            by.setdefault(r["policy"], {})[r["selection"]] = r["cost_mean"]
        policy_effect = {p: by[p]["first"] - by["R1"]["first"] for p in ("R2", "R3", "R4")}
        selection_effect = {p: max(by[p].values()) - min(by[p].values()) for p in by}
        confounded = [p for p in ("R2", "R3", "R4")
                      if abs(policy_effect[p]) < selection_effect[p]]
        out[tag] = dict(rows=rows, policy_effect=policy_effect,
                        selection_effect=selection_effect, confounded=confounded)
    return out


# ---------------------------------------------------------------- E5
def e5_ablation():
    levels = ["L0", "L1", "L2", "L3"]
    runs = {}
    for level in levels:
        for station, scale in STATIONS:
            for s_ in SEEDS:
                for n_c in N_C_GRID:
                    runs[(level, station, s_, n_c)] = S.simulate(
                        s_, DAYS, n_c, "R1", "first", scen=SCEN, scale=scale)
    out = {}
    for level in levels:
        est, truth = {}, {}
        for n_c in N_C_GRID:
            vals = []
            for station, scale in STATIONS:
                for s_ in SEEDS:
                    obs = observe(runs[(level, station, s_, n_c)], level, s_)
                    vals.append(est_cost(level, n_c, obs) / DAYS)
            est[n_c] = mean(vals)
            tvals = [S.aggregate(runs[(level, st, s_, n_c)]["per_day"])["cost_per_day"]
                     for st, _ in STATIONS for s_ in SEEDS]
            truth[n_c] = mean(tvals)
        best_est = min(est.values())
        chosen = min(est, key=lambda k: est[k])
        reco = [k for k in N_C_GRID if est[k] <= best_est * 1.02]
        best_true = min(truth.values())
        regret = truth[chosen] - best_true
        qs, qtrue = [], []
        for station, _ in STATIONS:
            for s_ in SEEDS:
                r = runs[(level, station, s_, 4)]
                qs.append(observe(r, level, s_)["q_plug_hat"])
                qtrue.append(S.aggregate(r["per_day"])["q_plug_true"])
        bias = mean(qs) - mean(qtrue)
        se = sd(qs) / math.sqrt(len(qs))
        t = bias / se if se > 0 else float("inf")
        out[level] = dict(est_cost=est, chosen_n_c=chosen, reco_set=reco,
                          reco_size=len(reco), true_cost=truth, best_true=best_true,
                          regret=regret, regret_pct=100.0 * regret / best_true,
                          q_plug_hat_mean=mean(qs), q_plug_true_mean=mean(qtrue),
                          q_bias=bias, q_se=se, q_t=t, identifiable=(abs(t) < 2.0))
    stress_truth = {}
    for n_c in N_C_GRID:
        vals = []
        for station, scale in STATIONS:
            for s_ in SEEDS:
                r = S.simulate(s_, DAYS, n_c, "R1", "first", scen=STRESS, scale=scale)
                vals.append(S.aggregate(r["per_day"])["cost_per_day"])
        stress_truth[n_c] = mean(vals)
    sbest = min(stress_truth.values())
    for level in levels:
        chosen = out[level]["chosen_n_c"]
        out[level]["stress_cost"] = stress_truth[chosen]
        out[level]["stress_regret"] = stress_truth[chosen] - sbest
        out[level]["stress_regret_pct"] = 100.0 * (stress_truth[chosen] - sbest) / sbest
    return dict(levels=out, stress_truth=stress_truth,
                failure=dict(
                    coverage_fail=[l for l in levels if not out[l]["identifiable"]],
                    undecidable=[l for l in levels
                                 if out[l]["reco_size"] >= 3 * out["L3"]["reco_size"]],
                    unstable=[l for l in levels if out[l]["stress_regret_pct"] > 5.0]))


# ---------------------------------------------------------------- E6
def e6_holdout():
    daily = {}
    for n_c in N_C_GRID:
        vals = []
        for station, scale in STATIONS:
            for s_ in SEEDS:
                r = S.simulate(s_, DAYS, n_c, "R1", "first", scen=SCEN, scale=scale)
                vals.append([d["cost"] for d in r["per_day"]])
        daily[n_c] = vals
    mean_cost = {k: mean([x for row in v for x in row]) for k, v in daily.items()}
    best = min(mean_cost.values())
    all_daily = [x for v in daily.values() for row in v for x in row]
    sd_day = sd(all_daily)
    delta = 0.02 * best
    k_needed = (1.96 * sd_day / delta) ** 2
    tune, ev = {}, {}
    for n_c in N_C_GRID:
        tune[n_c] = mean([x for row in daily[n_c] for x in row[:TUNE_DAYS]])
        ev[n_c] = mean([x for row in daily[n_c] for x in row[TUNE_DAYS:]])
    chosen = min(tune, key=lambda k: tune[k])
    best_ev = min(ev.values())
    holdout_regret = ev[chosen] - best_ev
    snaps_per_day = S.PARAMS["H"] // S.PARAMS["delta"]
    return dict(best_grid_cost=best, sd_day=sd_day, delta=delta,
                k_needed_days=round(k_needed, 1), available_days=DAYS,
                enough=(k_needed <= DAYS), naive_same_day_regret=0.0,
                holdout_chosen=chosen, holdout_regret=holdout_regret,
                holdout_regret_pct=100.0 * holdout_regret / best_ev,
                se_day=sd_day / math.sqrt(DAYS),
                se_snapshot_wrong=sd_day / math.sqrt(DAYS * snaps_per_day),
                inflation=math.sqrt(snaps_per_day), tunes=tune, evals=ev)


# ---------------------------------------------------------------- E7
def _posterior_ci(n, e, grid=400):
    a, b = n + 1.0, e - n + 1.0
    tot = []
    for i in range(grid + 1):
        q = i / grid
        ln = (a - 1) * math.log(max(q, 1e-12)) + (b - 1) * math.log(max(1 - q, 1e-12))
        tot.append((q, math.exp(ln)))
    z = sum(v for _, v in tot)
    acc, lo, hi, done = 0.0, None, None, 0
    for q, v in tot:
        acc += v / z
        if lo is None and acc >= 0.05:
            lo = q
        if hi is None and acc >= 0.95:
            hi = q
    return lo, hi


def e7_bc():
    C_obs, E_lo, E_hi, U_lo, U_hi = 144.0, 300.0, 480.0, 0.0, 48.0
    b_lo = max(0.0, (C_obs + U_lo) / E_hi)
    b_hi = min(1.0, (C_obs + U_hi) / E_lo)
    c_lo, c_hi = _posterior_ci(144.0, 480.0)
    c_lo2, c_hi2 = _posterior_ci(144.0, 240.0)
    inter = [max(b_lo, c_lo), min(b_hi, c_hi)]
    grid = [round(0.1 * i, 1) for i in range(1, 11)]
    g_two = [3.0, 2.0, 1.0, -1.0, -1.5, -0.5, 0.8, 2.2, 3.0, 0.4]
    g_none = [-1.0 - 0.2 * i for i in range(10)]

    def windows(vals):
        out, cur = [], []
        for r, v in zip(grid, vals):
            if v > 0:
                cur.append(r)
            elif cur:
                out.append([cur[0], cur[-1]])
                cur = []
        if cur:
            out.append([cur[0], cur[-1]])
        return out

    rng = random.Random(20261029)
    incl = {r: 0 for r in grid}
    for _ in range(400):
        d = [v + rng.gauss(0.0, 1.2) for v in g_two]
        for a, b in windows(d):
            for r in grid:
                if a <= r <= b:
                    incl[r] += 1
    stable = [r for r in grid if incl[r] / 400.0 >= 0.8]
    return dict(
        B=dict(interval=[b_lo, b_hi], C_obs=C_obs, E=[E_lo, E_hi], U=[U_lo, U_hi]),
        C=dict(interval=[c_lo, c_hi], E_assumed=480.0),
        C_alt=dict(interval=[c_lo2, c_hi2], E_assumed=240.0),
        mechanical_intersection=inter,
        assessment=dict(
            b_contains_0p6=(b_lo <= 0.6 <= b_hi),
            c_excludes_0p6=not (c_lo <= 0.6 <= c_hi),
            intersection_excludes_0p6=not (inter[0] <= 0.6 <= inter[1])),
        equivalence=dict(pair1=dict(q=0.6, E=240, C=144),
                          pair2=dict(q=0.4, E=360, C=144),
                          likelihood_identical=True),
        etp=dict(grid=grid, g_two=g_two, windows_two=windows(g_two),
                 g_none=g_none, windows_none=windows(g_none),
                 inclusion={str(r): incl[r] / 400.0 for r in grid},
                 stable_grid=stable))


# ---------------------------------------------------------------- 输出
def summary_md(res):
    L = []
    L.append("# 小型合成反例与观测删减：运行证据")
    L.append("")
    L.append("生成命令: python research/measurement/validation_20261029/code/run_validation.py  ")
    L.append("状态: 脚本生成，勿手改。全部数值为合成情景，不是实测。")
    L.append("")
    e1 = res["E1"]
    L.append("## E1 同一快照对应两个不同过程")
    L.append("")
    L.append("- 快照相同: %s" % e1["snapshots_identical"])
    L.append("- 会话数 A/B: %s / %s；窗口内新插枪: %s / %s" % (
        e1["derived"]["sessions"][0], e1["derived"]["sessions"][1],
        e1["derived"]["new_plugs"][0], e1["derived"]["new_plugs"][1]))
    L.append("- 闲占率 A/B: %.3f / %.3f；交付能量 A/B: %.2f / %.2f kWh" % (
        e1["derived"]["idle_occ_share"][0], e1["derived"]["idle_occ_share"][1],
        e1["derived"]["energy_kwh"][0], e1["derived"]["energy_kwh"][1]))
    L.append("")
    e2 = res["E2"]
    L.append("## E2 有限窗口恒等式与界")
    L.append("")
    L.append("- 恒等式残差 %.2e；矩形误差 %.3f，界 %.1f，界成立 %s" % (
        e2["identity_residual"], e2["rect_error"], e2["error_bound"], e2["bound_holds"]))
    L.append("- 到达数界 %s（含真值 %s: %s）；无假设界 %s" % (
        e2["arrivals_bounds"], e2["n_window"], e2["arrivals_contains"],
        e2["no_assumption_bounds"]))
    L.append("- 朴素 B/平均停留 %.2f（真值 %d）误差 %+.2f" % (
        e2["naive_arrivals"], e2["n_window"], e2["naive_error"]))
    L.append("")
    e3 = res["E3"]
    L.append("## E3 指标分账与公平口径")
    L.append("")
    L.append("- M01=%.3f M02=%.3f 等待=%s" % (
        e3["M01_acceptance"], e3["M02_success"], e3["M03_wait"]))
    L.append("- M06 已接纳缺口率 %.3f；M07 拒绝缺口率 %.3f" % (
        e3["M11_gap_rates"]["admitted"], e3["M11_gap_rates"]["refused"]))
    L.append("- 总成本更低但最弱群体更差: %s" % e3["fairness"]["worst_group_worse_in_cfg2"])
    L.append("")
    e4 = res["E4"]
    L.append("## E4 规则比较与选位混淆")
    L.append("")
    for tag in ("normal", "tight"):
        d = e4[tag]
        L.append("- [%s] 规则效应: " % tag + ", ".join(
            "%s=%+.1f" % (k, v) for k, v in d["policy_effect"].items()) + " 元/日")
        L.append("- [%s] 选位效应: " % tag + ", ".join(
            "%s=%.1f" % (k, v) for k, v in d["selection_effect"].items()) + " 元/日；被混淆: %s"
            % (d["confounded"] or "无"))
    L.append("")
    e5 = res["E5"]
    L.append("## E5 观测删减")
    L.append("")
    L.append("| 级 | q_plug 估计 | 真值 | 偏差 t | 成本估计误差 | 推荐集合 | 选 n_c | 后悔 元/日 | 压力后悔 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for lv in ("L0", "L1", "L2", "L3"):
        d = e5["levels"][lv]
        mape = mean([abs(d["est_cost"][k] - d["true_cost"][k]) / d["true_cost"][k]
                     for k in d["est_cost"]])
        L.append("| %s | %.3f | %.3f | %.1f | %.1f%% | %s | %s | %.1f | %.1f%% |" % (
            lv, d["q_plug_hat_mean"], d["q_plug_true_mean"], d["q_t"],
            100.0 * mape, d["reco_set"], d["chosen_n_c"], d["regret"],
            d["stress_regret_pct"]))
    L.append("")
    L.append("- 失败判据命中: %s" % e5["failure"])
    L.append("")
    e6 = res["E6"]
    L.append("## E6 留出与样本量")
    L.append("")
    L.append("- 日成本 SD=%.0f；2%% 误差需独立日 %.1f 天，现有 %d 天，够不够 %s" % (
        e6["sd_day"], e6["k_needed_days"], e6["available_days"], e6["enough"]))
    L.append("- 同日调参评价后悔=0（构造性）；时间留出后 n_c=%s，后悔 %.1f 元/日（%.2f%%）" % (
        e6["holdout_chosen"], e6["holdout_regret"], e6["holdout_regret_pct"]))
    L.append("- 把快照当样本会把 SE 缩小 %.1f 倍" % e6["inflation"])
    L.append("")
    e7 = res["E7"]
    L.append("## E7 B/C 与 ETP")
    L.append("")
    L.append("- B 区间 [%.3f, %.3f]；C 后验(E=480) [%.3f, %.3f]；机械交集 [%.3f, %.3f]" % (
        e7["B"]["interval"][0], e7["B"]["interval"][1],
        e7["C"]["interval"][0], e7["C"]["interval"][1],
        e7["mechanical_intersection"][0], e7["mechanical_intersection"][1]))
    L.append("- 机械交集排除示例真值 0.6: %s" % e7["assessment"]["intersection_excludes_0p6"])
    L.append("- ETP 两窗口 %s；无窗口 %s；稳定网格点 %s" % (
        e7["etp"]["windows_two"], e7["etp"]["windows_none"], e7["etp"]["stable_grid"]))
    L.append("")
    L.append("## 未做")
    L.append("")
    L.append("- 未做真实平台数据校验（本轮无采集数据）。")
    L.append("- 未做大型 ABC、SBC 或在线学习；B/C 与 ETP 只用合成算例演示口径。")
    L.append("- 未验证任何真实场站参数；DGP 全部是情景假设。")
    L.append("")
    return "\n".join(L)


def main():
    os.makedirs(RES, exist_ok=True)
    res = dict(
        meta=dict(generated_by="run_validation.py", date="2026-10-29",
                  seeds=SEEDS, days=DAYS, tune_days=TUNE_DAYS, n_c_grid=N_C_GRID,
                  scen=SCEN, stress=STRESS, stations=[s for s, _ in STATIONS],
                  e_assumed=E_ASSUM, mean_need_assumed=MEAN_NEED,
                  note="全部为合成情景参数，不是实测"),
        E1=e1_counterexample(), E2=e2_identity(), E3=e3_metrics(),
        E4=e4_scenarios(), E5=e5_ablation(), E6=e6_holdout(), E7=e7_bc(),
    )
    with open(os.path.join(RES, "results_20261029.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    text = summary_md(res)
    with open(os.path.join(RES, "EVIDENCE.md"), "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    print("已弃用：T14 起唯一入口为 run_validation_t14.py；本入口不再写 results/，避免覆盖历史结果。", file=sys.stderr)
    sys.exit(2)
