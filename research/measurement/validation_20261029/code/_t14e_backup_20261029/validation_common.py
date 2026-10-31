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
    """输入只有可见字段与声明假设。会话分子只给下界，上界用到达/容量。

    q 的分子是「窗口新到达车辆中至少插枪一次的独立到访」，不是会话数：
    首帧在场的车辆晚些插枪也会产生后帧首见键，且同一新到访可产生多个会话。
    因此先按期初车辆上界 occ0 与每访会话上限扣除期初可解释的键，再把剩余
    会话数按 ceil(remaining/c) 换算成插枪到访下界；c 未知或非法时下界取 0。
    上界与下界矛盾时不取 max 掩盖，而是撤去该有限上界。
    """
    rows, N, delta = view["rows"], view["N"], view["delta"]
    A = view["assumptions"]
    counts = [r["n_supply"] for r in rows]
    trans_lo = BND.session_lower_from_transitions(counts)
    row_keys = [[s for st, s in r.get("chg", [])] for r in rows]
    occ = [N - r["free_obs"] for r in rows]
    occ0 = max(0, min(N, occ[0])) if occ else 0
    if view["level"] in ("L2", "L3"):
        keys_lo = BND.session_lower_from_keys(row_keys)
        first_keys = [s for st, s in rows[0].get("chg", [])] if rows else []
        init = BND.new_arrival_session_lower(
            keys_lo, occ0, A.get("session_per_visit_max"), first_keys)
        sessions_lo = init["lower"]
        src = "session_keys"
    else:
        keys_lo = None
        init = None
        sessions_lo = 0
        src = "counting_transitions"
    area = BND.arrival_bounds(occ, delta, A["dwell_range"], A["event_cap"], N)
    T = (len(rows) - 1) * delta
    sessions_hi = BND.session_upper_bound(N, T, A["dwell_range"][0],
                                          A["session_per_visit_max"],
                                          area["bounds"][1])
    sessions_hi_status = "ok"
    if sessions_hi is not None and sessions_hi + 1e-12 < sessions_lo:
        sessions_hi = None
        sessions_hi_status = "contradicted_by_new_arrival_lower"
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
                sessions_hi=sessions_hi, sessions_hi_status=sessions_hi_status,
                sessions_observed=dict(
                    transitions=trans_lo, keys=keys_lo,
                    new_arrival_lower=sessions_lo,
                    initial_vehicle_cap=occ0,
                    first_frame_sessions=(init["first_frame_sessions"] if init else None),
                    initial_deduction=(init["deduction"] if init else None),
                    remaining_sessions=(init["remaining_sessions"] if init else None),
                    per_visit_cap=(init["per_visit_cap"] if init else None),
                    initial_status=(init["status"] if init else None)),
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
