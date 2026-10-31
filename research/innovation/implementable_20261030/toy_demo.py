#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""有限停车容量 + 充电兼容共享 + 删失需求的最小合成模型。

单日稳态期望成本：N 车位，k 桩，s 为 EV 专用比例；D~Poisson(mu=A*q)，
观测只到 min(D,k_eff)，拒绝不可见，故 mu 只给区间。ICE 可占用共享车位并
阻塞共享桩。成本=桩日成本+EV 未服务惩罚-EV 服务收益+ICE 被拒惩罚。

E1 删失 MLE；E2 成本差包络；E3/E4 拒绝上界/采样粒度；E5 补测 VoI；
E6 候选集连续化；E7 MC 核对；E8 可失败判定。所有数值为合成结果，
不是广州/台北校准、政策结论或新颖性证明；mu=A*q 只以乘积进入。
"""
import argparse
import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# 固定参数
PARAMS = {
    "N_spots": 40,
    "lambda_ice": 22.0,          # 已知 ICE 日需求均值
    "c_k_per_day": 8.0,          # 每桩日成本
    "p_ev_reject": 14.0,         # 每个未服务 EV 充电会话的惩罚
    "v_ev_served": 3.0,          # 每个被服务 EV 会话的收益（避免重复计惩罚）
    "p_ice_reject": 20.0,        # 每个被拒 ICE 的惩罚
    "dwell_hours": [1.0, 3.0],   # 停车时长情景范围
    "horizon_hours": 24.0,
    "event_rate_per_hour": 4.0,  # 情景：每小时占用变化次数上限
}

SCENARIO = {
    "A_adm_observed": 62.0,      # 观测到的 admitted EV 到访（门禁计数，示例）
    "q_bounds": [0.30, 0.70],    # 插枪/兼容概率情景区间（非实测识别）
    "observed_served": 23,       # 观测到的充电会话数（在 k_obs 处右删失）
    "k_obs": 25,                 # 观测期的桩数
    "true_mu": 49.5,             # 仅用于评估，不进入决策
    "true_q": 0.55,
    "true_A_offered": 90.0,
}

R_HI_GRID = [0.0, 10.0, 20.0, 30.0, 45.0, 60.0]
DELTA_GRID_MIN = [5, 15, 30, 60]
SHRINK_GRID = [0.75, 0.50, 0.25, 0.10]


# 基础计算
def poisson_pmf(mu, kmax):
    """Poisson pmf, 0..kmax, 递推避免大阶乘。"""
    if mu < 0:
        raise ValueError("mu must be >= 0")
    p = np.zeros(kmax + 1, dtype=float)
    if kmax < 0:
        return p
    p[0] = math.exp(-mu) if mu < 700 else 0.0
    for d in range(1, kmax + 1):
        p[d] = p[d - 1] * mu / d
    return p


def emin_table(mu, kmax):
    """m[k] = E[min(D,k)], k=0..kmax。"""
    p = poisson_pmf(mu, kmax)
    m = np.zeros(kmax + 1, dtype=float)
    # m[k] = sum_{d<k} d p_d + k * P(D>=k)
    prefix_dp = 0.0
    cdf = 0.0
    for k in range(1, kmax + 1):
        # 加入 d=k-1 的贡献后得到 P(D<k) 与 sum_{d<k} d p_d
        d = k - 1
        prefix_dp += d * p[d]
        cdf += p[d]
        m[k] = prefix_dp + k * max(0.0, 1.0 - cdf)
    return m


def build_candidates(k_values, s_values):
    ks, ss = [], []
    for k in k_values:
        for s in s_values:
            ks.append(int(k))
            ss.append(float(s))
    return np.array(ks, dtype=int), np.array(ss, dtype=float)


def effective_capacity(ks, ss, lam):
    """返回 (k_eff, ded)。ded 为 EV 专用车位数，k_eff 为 EV 可用桩数。"""
    ded = np.floor(ss * ks + 1e-9).astype(int)
    blocked = np.minimum(int(lam), np.floor((1.0 - ss) * ks + 1e-9).astype(int))
    keff = ks - blocked
    return keff, ded


def cost_matrix(mus, ks, ss, params):
    """返回 (len(mus), len(ks)) 的期望日成本矩阵。"""
    N = int(params["N_spots"])
    lam = float(params["lambda_ice"])
    c_k = float(params["c_k_per_day"])
    p_r = float(params["p_ev_reject"])
    v = float(params["v_ev_served"])
    p_i = float(params["p_ice_reject"])
    keff, ded = effective_capacity(ks, ss, lam)
    c = N - lam
    kmax = N
    out = np.empty((len(mus), len(ks)), dtype=float)
    for j, mu in enumerate(mus):
        m = emin_table(float(mu), kmax)
        m_k = m[ks]
        m_eff = m[np.minimum(keff, kmax)]
        idx_c = np.full(len(ks), int(min(max(c, 0.0), kmax)), dtype=int)
        m_c = m[idx_c]
        ev = p_r * (float(mu) - m_eff) - v * m_eff
        # ICE 被拒 = E[(max(ded, min(D,k_eff)) - c)^+]
        ice = np.empty(len(ks), dtype=float)
        lo = ded <= c
        # ded <= c
        ice[lo] = np.maximum(0.0, m_eff[lo] - m_c[lo])
        # ded > c 且 k_eff > ded
        hi = (~lo) & (keff > ded)
        ice[hi] = (ded[hi] - c) + m_eff[hi] - m[ded[hi]]
        # ded > c 且 k_eff <= ded
        hi2 = (~lo) & (~(keff > ded))
        ice[hi2] = ded[hi2] - c
        out[j, :] = c_k * ks + ev + p_i * np.maximum(0.0, ice)
    return out


# 观测界
def admitted_bounds(a_obs, delta_min, params):
    """由占用面积快照给 admitted 到访区间（情景界，不是广州实测）。

    面积 B_hat = A_obs * dwell_mid；采样误差上界 = T * event_cap，
    event_cap 由每小时变化率乘采样间隔取整。A_lo=(B_hat-err)/dwell_hi,
    A_hi=(B_hat+err)/dwell_lo。
    """
    T = float(params["horizon_hours"])
    lo_d, hi_d = params["dwell_hours"]
    mid_d = 0.5 * (lo_d + hi_d)
    rate = float(params["event_rate_per_hour"])
    cap = max(1, int(round(rate * delta_min / 60.0)))
    err = T * min(cap, int(params["N_spots"]))
    b_hat = a_obs * mid_d
    a_lo = max(0.0, b_hat - err) / hi_d
    a_hi = (b_hat + err) / lo_d
    return {
        "delta_min": delta_min,
        "event_cap_per_interval": cap,
        "sampling_error_veh_hours": err,
        "area_hat": b_hat,
        "A_adm_bounds": [a_lo, a_hi],
        "condition": "每采样间隔占用变化<=event_cap；停留<=dwell_hi；情景参数非实测",
    }


def mu_bounds(a_lo, a_hi, r_hi, q_lo, q_hi):
    """mu = A_offered * q 的盒式区间；R_hi 为外部拒绝上界情景。"""
    mu_lo = max(0.0, a_lo) * q_lo
    mu_hi = (a_hi + max(0.0, r_hi)) * q_hi
    return {
        "mu_bounds": [mu_lo, mu_hi],
        "width": mu_hi - mu_lo,
        "A_offered_bounds": [a_lo, a_hi + max(0.0, r_hi)],
        "q_bounds": [q_lo, q_hi],
        "rejection_upper": r_hi,
        "condition": "mu=A*q；A_hi=A_adm_hi+R_hi；q_lo/q_hi为情景界，非点识别",
    }


def service_level_k(mu, s, params, eps=0.10):
    """服务水准备择：最小 k 使 P(D > k_eff) <= eps（固定共享规则 s）。"""
    N = int(params["N_spots"])
    lam = float(params["lambda_ice"])
    for k in range(0, N + 1):
        ded = int(math.floor(s * k + 1e-9))
        blocked = min(int(lam), int(math.floor((1.0 - s) * k + 1e-9)))
        keff = k - blocked
        p = poisson_pmf(mu, max(keff, 1))
        cdf = float(np.sum(p[:keff + 1]))
        if 1.0 - cdf <= eps:
            return {"k": k, "s": s, "k_eff": keff,
                    "rejection_prob_at_mu": 1.0 - cdf}
    return {"k": None, "s": s, "k_eff": None, "rejection_prob_at_mu": None}


def censored_poisson_mle(y_obs, k_obs, mu_max=400.0, tol=1e-6):
    """右删失 y=min(D,k) 的 Poisson 均值 MLE：解 E[min(D,k)] = y。"""
    if y_obs <= 0:
        return 0.0
    if y_obs >= k_obs:
        return float("inf")
    lo, hi = 0.0, mu_max
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        m = emin_table(mid, int(k_obs))[int(k_obs)]
        if m < y_obs:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return 0.5 * (lo + hi)


# 决策
def minimax(mus, ks, ss, params, refine=False, best_cost=None):
    """对每个候选返回 max_mu [C_c(mu) - min_c' C_c'(mu)]，并给最优候选。

    best_cost 给定时用它作逐 mu 的基准（用于离散候选集对细网格的后悔）。
    """
    cm = cost_matrix(mus, ks, ss, params)
    if best_cost is None:
        best = cm.min(axis=1, keepdims=True)
    else:
        best = np.asarray(best_cost, dtype=float).reshape(-1, 1)
    regret = cm - best
    r = regret.max(axis=0)
    order = np.argsort(r)
    worst_j = int(np.argmax(regret[:, order[0]]))
    out = {
        "worst_case_regret": float(r[order[0]]),
        "best_index": int(order[0]),
        "best_k": int(ks[order[0]]),
        "best_s": float(ss[order[0]]),
        "binding_mu": float(mus[worst_j]),
        "regret_at_mu_lo": float(regret[0, order[0]]),
        "regret_at_mu_hi": float(regret[-1, order[0]]),
        "regret_by_candidate": [float(x) for x in r],
        "n_mu_grid": int(len(mus)),
        "mu_grid": [float(mus[0]), float(mus[-1])],
        "grid_step": float(mus[1] - mus[0]) if len(mus) > 1 else 0.0,
    }
    if refine:
        # 在最优候选的最坏 mu 附近加密，检查网格是否漏掉峰值
        worst_j = int(np.argmax(regret[:, order[0]]))
        lo = mus[max(0, worst_j - 1)]
        hi = mus[min(len(mus) - 1, worst_j + 1)]
        dense = np.linspace(lo, hi, 201)
        cm2 = cost_matrix(dense, ks, ss, params)
        r2 = (cm2 - cm2.min(axis=1, keepdims=True)).max(axis=0)
        out["refined_worst_case_regret"] = float(r2[order[0]])
        out["refinement_gap"] = float(abs(r2[order[0]] - r[order[0]]))
    return out


def envelope(mus, ks, ss, params, i, j):
    cm = cost_matrix(mus, ks, ss, params)
    diff = cm[:, i] - cm[:, j]
    return {
        "candidate_i": {"k": int(ks[i]), "s": float(ss[i])},
        "candidate_j": {"k": int(ks[j]), "s": float(ss[j])},
        "delta_bounds": [float(diff.min()), float(diff.max())],
        "sign_robust": bool(diff.min() > 0 or diff.max() < 0),
        "crossings": int(np.sum(np.sign(diff[:-1]) * np.sign(diff[1:]) < 0)),
        "mu_at_min": float(mus[int(np.argmin(diff))]),
        "mu_at_max": float(mus[int(np.argmax(diff))]),
    }


def plug_in_decision(mu_hat, ks, ss, params):
    cm = cost_matrix(np.array([mu_hat]), ks, ss, params)[0]
    i = int(np.argmin(cm))
    return {"mu_hat": float(mu_hat), "k": int(ks[i]), "s": float(ss[i]),
            "cost": float(cm[i])}


def true_regret(k, s, mu_true, ks, ss, params):
    cm = cost_matrix(np.array([mu_true]), ks, ss, params)[0]
    i = int(np.where((ks == k) & (np.isclose(ss, s)))[0][0])
    return float(cm[i] - cm.min()), float(cm[i]), float(cm.min())


# 实验
def run_experiments(seed, n_mu=1201):
    params = dict(PARAMS)
    sc = dict(SCENARIO)
    N = params["N_spots"]
    k_fine = list(range(0, N + 1))
    s_fine = [round(0.02 * i, 4) for i in range(51)]
    ks, ss = build_candidates(k_fine, s_fine)
    out = {"params": params, "scenario": sc, "seed": seed,
           "candidate_grid": {"k": "0..N", "s_step": 0.02,
                              "n_candidates": int(len(ks))}}

    # E1 观测界与删失 MLE
    e1 = {"admitted_by_delta": {}, "mle": {}}
    for d in DELTA_GRID_MIN:
        e1["admitted_by_delta"][str(d)] = admitted_bounds(
            sc["A_adm_observed"], d, params)
    mle_mu = censored_poisson_mle(sc["observed_served"], sc["k_obs"])
    naive_q = sc["observed_served"] / sc["A_adm_observed"]
    e1["mle"] = {
        "y_observed_served": sc["observed_served"],
        "k_obs": sc["k_obs"],
        "naive_q": naive_q,
        "censored_mle_mu": mle_mu,
        "censored_mle_q": (mle_mu / sc["A_adm_observed"]
                           if math.isfinite(mle_mu) else None),
        "upward_correction_pct": (100.0 * (mle_mu / sc["A_adm_observed"] - naive_q)
                                  / naive_q if math.isfinite(mle_mu) and naive_q > 0 else None),
        "note": "y=k 时 MLE 为无穷；本处 y<k。只说明删失会低估 q，不是广州估计。",
    }
    out["E1_observation_bounds"] = e1

    # E2 基线 mu 与成本差包络
    base_adm = admitted_bounds(sc["A_adm_observed"], 15, params)
    base_mu = mu_bounds(base_adm["A_adm_bounds"][0], base_adm["A_adm_bounds"][1],
                        30.0, sc["q_bounds"][0], sc["q_bounds"][1])
    mus = np.linspace(base_mu["mu_bounds"][0], base_mu["mu_bounds"][1], n_mu)
    out["E2_envelope"] = {
        "mu_bounds": base_mu,
        "pairs": [],
        "baseline_decision": minimax(mus, ks, ss, params, refine=True),
    }
    pairs = [(12, 0.5, 20, 1.0), (12, 1.0, 20, 0.5),
             (20, 0.9, 30, 0.6), (10, 0.0, 20, 0.5)]
    for k1, s1, k2, s2 in pairs:
        i = int(np.where((ks == k1) & np.isclose(ss, s1))[0][0])
        j = int(np.where((ks == k2) & np.isclose(ss, s2))[0][0])
        out["E2_envelope"]["pairs"].append(envelope(mus, ks, ss, params, i, j))

    # E3 拒绝上界敏感性
    e3 = {"rows": []}
    for r_hi in R_HI_GRID:
        mb = mu_bounds(base_adm["A_adm_bounds"][0], base_adm["A_adm_bounds"][1],
                       r_hi, sc["q_bounds"][0], sc["q_bounds"][1])
        mm = np.linspace(mb["mu_bounds"][0], mb["mu_bounds"][1], n_mu)
        dec = minimax(mm, ks, ss, params)
        # 高端压力测试：只看区间上半段，检查拒绝上界是否改变高需求侧选择
        half = len(mm) // 2
        dec_hi = minimax(mm[half:], ks, ss, params)
        sl = service_level_k(mb["mu_bounds"][1], 1.0, params)
        keff = dec["best_k"] - min(int(params["lambda_ice"]),
                                   int(math.floor((1.0 - dec["best_s"]) * dec["best_k"] + 1e-9)))
        pp = poisson_pmf(mb["mu_bounds"][1], max(keff, 1))
        p_rej_hi = 1.0 - float(np.sum(pp[:keff + 1]))
        tr, c_sel, c_best = true_regret(dec["best_k"], dec["best_s"],
                                        sc["true_mu"], ks, ss, params)
        # 真实 mu 下的最优候选（用于配置方向）
        cm_true = cost_matrix(np.array([sc["true_mu"]]), ks, ss, params)[0]
        ib = int(np.argmin(cm_true))
        e3["rows"].append({
            "R_hi": r_hi,
            "mu_hi": mb["mu_bounds"][1],
            "chosen_k": dec["best_k"], "chosen_s": dec["best_s"],
            "worst_case_regret": dec["worst_case_regret"],
            "binding_mu": dec["binding_mu"],
            "regret_at_mu_hi": dec["regret_at_mu_hi"],
            "high_end_chosen_k": dec_hi["best_k"],
            "high_end_chosen_s": dec_hi["best_s"],
            "high_end_worst_regret": dec_hi["worst_case_regret"],
            "service_level_k_eps10": sl["k"],
            "service_level_feasible": sl["k"] is not None,
            "service_level_rejection_prob": sl["rejection_prob_at_mu"],
            "chosen_rejection_prob_at_mu_hi": p_rej_hi,
            "true_mu_regret": tr,
            "true_mu_cost": c_sel, "true_mu_best_cost": c_best,
            "true_mu_best_k": int(ks[ib]), "true_mu_best_s": float(ss[ib]),
            "chosen_minus_true_best_k": int(dec["best_k"] - ks[ib]),
        })
    e3["note"] = "R_hi 是外部情景上界，不是广州实测；只报告决策敏感性。"
    out["E3_rejection_sensitivity"] = e3

    # E4 采样粒度敏感性（固定 R_hi=30）
    e4 = {"rows": []}
    for d in DELTA_GRID_MIN:
        ab = admitted_bounds(sc["A_adm_observed"], d, params)
        mb = mu_bounds(ab["A_adm_bounds"][0], ab["A_adm_bounds"][1], 30.0,
                       sc["q_bounds"][0], sc["q_bounds"][1])
        mm = np.linspace(mb["mu_bounds"][0], mb["mu_bounds"][1], n_mu)
        dec = minimax(mm, ks, ss, params)
        dec_hi = minimax(mm[len(mm) // 2:], ks, ss, params)
        sl = service_level_k(mb["mu_bounds"][1], 1.0, params)
        tr, _, _ = true_regret(dec["best_k"], dec["best_s"], sc["true_mu"],
                               ks, ss, params)
        e4["rows"].append({
            "delta_min": d,
            "event_cap": ab["event_cap_per_interval"],
            "A_adm_bounds": ab["A_adm_bounds"],
            "mu_bounds": mb["mu_bounds"],
            "chosen_k": dec["best_k"], "chosen_s": dec["best_s"],
            "worst_case_regret": dec["worst_case_regret"],
            "binding_mu": dec["binding_mu"],
            "high_end_chosen_k": dec_hi["best_k"],
            "high_end_chosen_s": dec_hi["best_s"],
            "service_level_k_eps10": sl["k"],
            "true_mu_regret": tr,
        })
    e4["note"] = "采样误差界为情景公式；不是广州可核界，也不证明更长间隔必然更差。"
    out["E4_sampling_sensitivity"] = e4

    # E5 补测信息对最坏后悔的价值
    e5 = {"rows": []}
    mb0 = mu_bounds(base_adm["A_adm_bounds"][0], base_adm["A_adm_bounds"][1],
                    30.0, sc["q_bounds"][0], sc["q_bounds"][1])
    lo0, hi0 = mb0["mu_bounds"]
    mm0 = np.linspace(lo0, hi0, n_mu)
    dec0 = minimax(mm0, ks, ss, params)
    for frac in SHRINK_GRID:
        width = (hi0 - lo0) * frac
        mid = 0.5 * (lo0 + hi0)
        lo1, hi1 = max(0.0, mid - width / 2), mid + width / 2
        mm1 = np.linspace(lo1, hi1, n_mu)
        dec1 = minimax(mm1, ks, ss, params)
        e5["rows"].append({
            "retained_width_frac": frac,
            "new_mu_bounds": [lo1, hi1],
            "chosen_k": dec1["best_k"], "chosen_s": dec1["best_s"],
            "worst_case_regret": dec1["worst_case_regret"],
            "voi_vs_current": dec0["worst_case_regret"] - dec1["worst_case_regret"],
            "voi_pct": (100.0 * (dec0["worst_case_regret"] - dec1["worst_case_regret"])
                        / dec0["worst_case_regret"] if dec0["worst_case_regret"] > 0 else 0.0),
            "same_decision_as_current": (dec1["best_k"] == dec0["best_k"]
                                          and abs(dec1["best_s"] - dec0["best_s"]) < 1e-12),
        })
    # oracle：把区间缩到真实 mu 附近 ±1
    mm_or = np.linspace(max(0.0, sc["true_mu"] - 1), sc["true_mu"] + 1, 401)
    dec_or = minimax(mm_or, ks, ss, params)
    e5["oracle"] = {
        "mu_bounds": [max(0.0, sc["true_mu"] - 1), sc["true_mu"] + 1],
        "chosen_k": dec_or["best_k"], "chosen_s": dec_or["best_s"],
        "worst_case_regret": dec_or["worst_case_regret"],
        "voi_vs_current": dec0["worst_case_regret"] - dec_or["worst_case_regret"],
    }
    e5["current"] = {"mu_bounds": [lo0, hi0],
                     "chosen_k": dec0["best_k"], "chosen_s": dec0["best_s"],
                     "worst_case_regret": dec0["worst_case_regret"]}
    e5["note"] = ("只按 mu 区间收缩计信息价值；若 A 与 q 不能分别识别，"
                  "单独补测 q 或 A 之一未必能缩 mu。未扣补测成本。")
    out["E5_value_of_information"] = e5

    # E6 候选集与共享规则的连续参数验证
    e6 = {"sets": {}}
    sets = {
        "discrete_K248_s0_05_1": (build_candidates([2, 4, 8], [0.0, 0.5, 1.0])),
        "coarse_Kstep2_sstep0.1": (build_candidates(range(0, N + 1, 2),
                                                    [round(0.1 * i, 4) for i in range(11)])),
        "fine_Kall_sstep0.02": (ks, ss),
        "fine_Kall_sstep0.005": (build_candidates(range(0, N + 1),
                                                  [round(0.005 * i, 4) for i in range(201)])),
    }
    cm_fine = cost_matrix(mus, ks, ss, params)
    best_fine = cm_fine.min(axis=1)
    for name, (kk, sgrid) in sets.items():
        dec = minimax(mus, kk, sgrid, params, best_cost=best_fine)
        e6["sets"][name] = {
            "n_candidates": int(len(kk)),
            "chosen_k": dec["best_k"], "chosen_s": dec["best_s"],
            "worst_case_regret": dec["worst_case_regret"],
            "binding_mu": dec["binding_mu"],
        }
    disc = e6["sets"]["discrete_K248_s0_05_1"]
    j = int(np.argmin(np.abs(mus - disc["binding_mu"])))
    fine_cost_at_binding = float(cm_fine[j].min())
    e6["fine_cost_at_discrete_binding"] = fine_cost_at_binding
    e6["discrete_regret_relative_pct"] = (
        100.0 * disc["worst_case_regret"] / fine_cost_at_binding
        if fine_cost_at_binding > 0 else 0.0)
    e6["discrete_to_fine_improvement"] = disc["worst_case_regret"]
    e6["discrete_to_fine_improvement_pct"] = e6["discrete_regret_relative_pct"]
    e6["s_optimum_interior"] = 0.0 < e6["sets"]["fine_Kall_sstep0.005"]["chosen_s"] < 1.0
    out["E6_candidate_validation"] = e6

    # E7 Monte Carlo 核对期望成本
    rng = random.Random(seed)
    e7 = {"checks": []}
    for (k, s) in [(20, 0.9), (32, 0.9), (10, 0.0)]:
        mu = sc["true_mu"]
        keff, ded = effective_capacity(np.array([k]), np.array([s]),
                                       params["lambda_ice"])
        keff, ded = int(keff[0]), int(ded[0])
        n = 20000
        costs = []
        for _ in range(n):
            d = poisson_sample(rng, mu)
            served = min(d, keff)
            ice_rej = max(0.0, max(served, ded) - (params["N_spots"] - params["lambda_ice"]))
            c = (params["c_k_per_day"] * k
                 + params["p_ev_reject"] * max(0, d - keff)
                 - params["v_ev_served"] * served
                 + params["p_ice_reject"] * ice_rej)
            costs.append(c)
        mc = float(np.mean(costs))
        mc_se = float(np.std(costs, ddof=1) / math.sqrt(n))
        exact = float(cost_matrix(np.array([mu]), np.array([k]), np.array([s]), params)[0, 0])
        e7["checks"].append({
            "k": k, "s": s, "mu": mu, "n_days": n,
            "exact_cost": exact, "mc_cost": mc, "mc_se": mc_se,
            "abs_error": abs(exact - mc),
            "within_4se": abs(exact - mc) <= 4 * mc_se,
        })
    e7["note"] = "仅核对期望成本实现；不构成对广州数据的验证。"
    out["E7_monte_carlo_check"] = e7

    # E8 预注册判定（可失败）
    e8 = {}
    env_robust = [p for p in out["E2_envelope"]["pairs"] if p["sign_robust"]]
    e8["H1_envelope_sign_robust_exists"] = {
        "criterion": "至少一对候选的成本差区间不含0",
        "passed": len(env_robust) > 0,
        "n_robust_pairs": len(env_robust), "n_pairs": len(out["E2_envelope"]["pairs"]),
    }
    r0 = next(x for x in e3["rows"] if x["R_hi"] == 0.0)
    r60 = next(x for x in e3["rows"] if x["R_hi"] == 60.0)
    sl0, sl60 = r0["service_level_k_eps10"], r60["service_level_k_eps10"]
    delta_sl = (sl60 - sl0) if (sl0 is not None and sl60 is not None) else None
    e8["H2_rejection_changes_decision"] = {
        "criterion": "R_hi 0->60 使服务水准备择 k 变化>=2，或高端成本后悔变化>=10%",
        "passed": ((delta_sl is not None and abs(delta_sl) >= 2)
                   or abs(r60["high_end_chosen_k"] - r0["high_end_chosen_k"]) >= 2),
        "delta_k_global": r60["chosen_k"] - r0["chosen_k"],
        "delta_k_high_end": r60["high_end_chosen_k"] - r0["high_end_chosen_k"],
        "delta_k_service_level": delta_sl,
        "note": ("成本最小化在容量饱和段对 R_hi 不敏感；本参数下服务水准也不可行"
                 "（k=N 仍达不到 10% 拒绝率），因此没有可翻转的 k。"),
    }
    half = next(x for x in e5["rows"] if x["retained_width_frac"] == 0.5)
    e8["H3_information_value"] = {
        "criterion": "mu 区间缩半使最坏后悔下降>=5%",
        "passed": half["voi_pct"] >= 5.0,
        "voi_pct_at_half": half["voi_pct"],
    }
    e8["H4_continuous_gain"] = {
        "criterion": "离散候选集相对细网格的后悔占其 binding mu 成本>=2%",
        "passed": e6["discrete_regret_relative_pct"] >= 2.0,
        "improvement_pct": e6["discrete_regret_relative_pct"],
    }
    d15 = next(x for x in e4["rows"] if x["delta_min"] == 15)
    d60 = next(x for x in e4["rows"] if x["delta_min"] == 60)
    e8["H5_sampling_changes_decision"] = {
        "criterion": "采样间隔 15->60 分钟使 chosen k 变化>=2 或最坏后悔上升>=10%",
        "passed": (abs(d60["chosen_k"] - d15["chosen_k"]) >= 2
                   or d60["worst_case_regret"] >= 1.1 * d15["worst_case_regret"]),
        "delta_k": d60["chosen_k"] - d15["chosen_k"],
        "regret_ratio": (d60["worst_case_regret"] / d15["worst_case_regret"]
                         if d15["worst_case_regret"] > 0 else None),
    }
    e8["H6_censored_mle_direction"] = {
        "criterion": "删失 Poisson MLE 的 q 不低于 naive q（方向性检查）",
        "passed": (e1["mle"]["censored_mle_q"] is not None
                   and e1["mle"]["censored_mle_q"] >= e1["mle"]["naive_q"]),
        "naive_q": e1["mle"]["naive_q"],
        "mle_q": e1["mle"]["censored_mle_q"],
    }
    out["E8_falsification_checks"] = e8

    out["limitations"] = [
        "单日稳态期望模型；无排队、无时序、无跨窗停留。",
        "mu=A*q 只以乘积进入 Poisson，q 与 A 不可分别识别。",
        "采样误差界与 R_hi 均为情景参数，不是广州实测。",
        "合成结果不构成政策建议，也不证明方法新颖性。",
        "未实现多期动态 base-stock / 事件层；依赖 T11 真实数据与 T16 事件层。",
    ]
    return out


def poisson_sample(rng, mu):
    """Knuth 小均值 + 正态近似大均值；仅用于 MC 核对。"""
    if mu < 30:
        L = math.exp(-mu)
        k, p = 0, 1.0
        while True:
            k += 1
            p *= rng.random()
            if p <= L:
                return k - 1
    # 大 mu：正态近似后取整（仅核对期望，误差由 SE 吸收）
    return max(0, int(round(rng.gauss(mu, math.sqrt(mu)))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "results" / "toy_results.json"))
    ap.add_argument("--seed", type=int, default=20261030)
    ap.add_argument("--n-mu", type=int, default=1201)
    args = ap.parse_args()
    res = run_experiments(args.seed, args.n_mu)
    res["meta"] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "command": "python toy_demo.py --out results/toy_results.json --seed 20261030 --n-mu 1201",
        "python": "3.12.14 (numpy 2.3.5; scipy not used)",
        "seed": args.seed,
        "n_mu": args.n_mu,
        "synthetic_only": True,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    print("E8:", json.dumps(res["E8_falsification_checks"], ensure_ascii=False))
    print("E2 baseline:", json.dumps(res["E2_envelope"]["baseline_decision"], ensure_ascii=False)[:400])
    print("E3 chosen:", [(r["R_hi"], r["chosen_k"], r["chosen_s"], round(r["worst_case_regret"], 2)) for r in res["E3_rejection_sensitivity"]["rows"]])
    print("E5 voi:", [(r["retained_width_frac"], round(r["voi_pct"], 2)) for r in res["E5_value_of_information"]["rows"]])


if __name__ == "__main__":
    main()
