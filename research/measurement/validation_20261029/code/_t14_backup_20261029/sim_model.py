#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成仿真与观测层（E1-E7 共用）。所有参数都是情景假设，不是实测。

对应 SPEC_experiments.md 第 1 节。真值参数只用于评价后悔与覆盖率，估计器不得使用。
"""
import math
import random

PARAMS = dict(
    N=60, H=840, lam=0.42, ev_share=0.35, q_need=0.60,
    dwell_med=90.0, dwell_sigma=0.55, dwell_min=15.0, dwell_max=480.0,
    need_med=18.0, need_sigma=0.50, need_min=3.0, need_max=80.0,
    p_rated=22.0, feeder_cap=66.0, pause_prob=0.005,
    reserved_bias=2, delta=5,
    fault_gun=0, fault_window=(600, 720),
    c_cap=300.0, c_gap=2.0, c_ref=2.0, c_wait=6.0, c_park=4.0,
)

PEAK = (300, 540)


def clamp(x, lo, hi):
    return lo if x < lo else (hi if x > hi else x)


def poisson(rng, lam):
    if lam <= 0:
        return 0
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def lognormal(rng, med, sigma, lo, hi):
    return clamp(math.exp(rng.gauss(math.log(med), sigma)), lo, hi)


def erlang_b(n, a):
    """Erlang-B 阻塞概率，估计器的声明的近似模型（不是真值机制）。"""
    if n <= 0:
        return 1.0
    if a <= 0:
        return 0.0
    inv, s = 1.0, 1.0
    for k in range(1, n + 1):
        inv *= a / k
        s += inv
    return inv / s


def _pick(lst, sel, t=0):
    """选位规则。random 用确定性伪随机，避免消耗到达流的随机数（保证 CRN）。"""
    if not lst:
        return None
    if sel == "first":
        return min(lst)
    if sel == "last":
        return max(lst)
    s = sorted(lst)
    return s[(int(t) * 37 + len(s) * 11) % len(s)]


def choose_bay(policy, t, is_ev, req, ord_free, chg_free, sel):
    """返回车位下标或 None。R1-R4 见 SPEC_metrics.md 第 6 节。"""
    peak = PEAK[0] <= t < PEAK[1]
    if policy == "R1":
        if is_ev and req:
            return _pick(chg_free, sel, t)
        return _pick(ord_free, sel, t)
    if policy == "R2":
        return _pick(sorted(ord_free + chg_free), sel, t)
    if policy == "R3":
        if is_ev and req:
            b = _pick(chg_free, sel, t)
            return b if b is not None else _pick(ord_free, sel, t)
        b = _pick(ord_free, sel, t)
        return b if b is not None else _pick(chg_free, sel, t)
    if policy == "R4":
        if is_ev and req:
            b = _pick(chg_free, sel, t)
            return b if b is not None else _pick(ord_free, sel, t)
        if peak:
            b = _pick(ord_free, sel, t)
            return b if b is not None else _pick(chg_free, sel, t)
        b = _pick(ord_free, sel, t)
        return b if b is not None else _pick(chg_free, sel, t)
    raise ValueError("unknown policy " + str(policy))


def run_day(rng, P, n_c, policy, sel, scale, delta, day, snaps):
    N, H = P["N"], P["H"]
    n_ord = N - n_c
    ord_ids = list(range(n_ord))
    chg_ids = list(range(n_ord, N))
    bay = [None] * N

    arrivals = 0
    ev_visits = 0
    ev_connected = 0
    requests = 0
    admitted_req = 0
    rejected = 0
    rejected_need = 0.0
    blocked_park = 0
    wait_sum = 0.0
    wait_n = 0
    delivered = 0.0
    admitted_need = 0.0
    gap_adm = 0.0
    supp_min = 0
    idle_occ_min = 0
    chg_occ_min = 0
    fin_occ_min = 0
    occ = 0
    visits = []

    for t in range(H):
        fault_now = P["fault_window"][0] <= t < P["fault_window"][1]
        faulted = [fault_now and g == P["fault_gun"] for g in range(n_c)]

        # 1) 供能与状态更新（S3/S4/S5/S6/S7）
        active = []
        for g, bi in enumerate(chg_ids):
            v = bay[bi]
            if v is None or not v["req"]:
                continue
            if v["conn_t"] is None or t < v["conn_t"]:
                v["state"] = "S3"
                continue
            if v["remaining"] <= 1e-9:
                v["state"] = "S6"
                continue
            if faulted[g]:
                v["state"] = "S7"
                continue
            active.append((bi, v))
        share = (P["feeder_cap"] / len(active)) if active else 0.0
        supply_count = 0
        for bi, v in active:
            p = min(P["p_rated"], share)
            if rng.random() < P["pause_prob"]:
                p = 0.0
                v["state"] = "S5"
            else:
                v["state"] = "S4"
            if p > 0:
                supply_count += 1
                supp_min += 1
                delivered += p / 60.0
                v["delivered"] += p / 60.0
                v["remaining"] = max(0.0, v["remaining"] - p / 60.0)
        n_fault = sum(1 for f in faulted if f)

        # 2) 占用与闲占计数
        chg_row = []
        for g, bi in enumerate(chg_ids):
            v = bay[bi]
            if v is not None:
                chg_occ_min += 1
                if v["state"] != "S4":
                    idle_occ_min += 1
                if v["state"] == "S6":
                    fin_occ_min += 1
            st = "fault" if faulted[g] else (
                "supplying" if (v is not None and v["state"] == "S4") else "idle")
            chg_row.append((st, v["sess"] if (v is not None) else None))

        # 3) 离场
        for bi in range(N):
            v = bay[bi]
            if v is None:
                continue
            if t >= v["leave"]:
                if v["req"]:
                    gap_adm += max(0.0, v["need"] - v["delivered"])
                bay[bi] = None
                occ -= 1

        # 4) 到达与分配
        n_new = poisson(rng, P["lam"] * scale)
        for _ in range(n_new):
            arrivals += 1
            dwell = lognormal(rng, P["dwell_med"], P["dwell_sigma"],
                              P["dwell_min"], P["dwell_max"])
            is_ev = rng.random() < P["ev_share"]
            if is_ev:
                ev_visits += 1
            req = is_ev and (rng.random() < P["q_need"])
            need = 0.0
            if req:
                requests += 1
                admitted_need += 0.0  # 接纳后再计
                need = lognormal(rng, P["need_med"], P["need_sigma"],
                                 P["need_min"], P["need_max"])
            ord_free = [i for i in ord_ids if bay[i] is None]
            chg_free = [i for i in chg_ids if bay[i] is None]
            target = choose_bay(policy, t, is_ev, req, ord_free, chg_free, sel)
            if target is None:
                if req:
                    rejected += 1
                    rejected_need += need
                else:
                    blocked_park += 1
                continue
            v = dict(arr=t, dwell=dwell, is_ev=is_ev, req=req, need=need,
                     delivered=0.0, remaining=need, conn_t=None, leave=t + dwell,
                     state=None, sess=None, bi=target)
            bay[target] = v
            occ += 1
            if req:
                admitted_req += 1
                admitted_need += need
                if target >= n_ord:
                    v["conn_t"] = t + 1
                    v["sess"] = "%d-%d" % (day, len(visits))
                    ev_connected += 1
                    wait = 1.0
                    wait_sum += wait
                    wait_n += 1
                else:
                    v["sess"] = None
                    v["state"] = "S2"
            else:
                v["state"] = "S1" if not is_ev else "S2"
            visits.append(v)
            if t % delta == 0:
                pass

        # 5) 快照
        if t % delta == 0:
            free_phys = N - occ
            snaps.append(dict(
                t=day * H + t, free_phys=free_phys,
                free_obs=max(0, free_phys - P["reserved_bias"]),
                n_supply=supply_count, n_fault=n_fault,
                n_idle=max(0, n_c - supply_count - n_fault),
                chg=[(st, s) for st, s in chg_row],
            ))

    # 6) 收盘残余（当日未离场车辆的缺口）
    for bi in range(N):
        v = bay[bi]
        if v is None:
            continue
        if v["req"]:
            gap_adm += max(0.0, v["need"] - v["delivered"])

    cost = (P["c_cap"] * n_c + P["c_gap"] * gap_adm + P["c_ref"] * rejected_need
            + P["c_wait"] * (wait_sum / 60.0) + P["c_park"] * blocked_park)
    return dict(
        day=day, n_c=n_c, policy=policy, arrivals=arrivals, ev_visits=ev_visits,
        ev_connected=ev_connected, requests=requests, admitted_req=admitted_req,
        rejected=rejected, rejected_need=rejected_need, blocked_park=blocked_park,
        delivered=delivered, admitted_need=admitted_need, gap_adm=gap_adm,
        wait_sum=wait_sum, wait_n=wait_n, supp_min=supp_min,
        idle_occ_min=idle_occ_min, chg_occ_min=chg_occ_min, fin_occ_min=fin_occ_min,
        cost=cost,
    )


def simulate(seed, days, n_c, policy="R2", sel="first", scen=None,
             scale=1.0, delta=None, snaps=None):
    P = dict(PARAMS)
    if scen:
        P.update(scen)
    if delta is not None:
        P["delta"] = delta
    rng = random.Random(seed)
    per_day = []
    owned = snaps is None
    rows = [] if owned else snaps
    for day in range(days):
        per_day.append(run_day(rng, P, n_c, policy, sel, scale, P["delta"], day, rows))
    return dict(per_day=per_day, snapshots=rows, params=P)


def aggregate(per_day):
    keys = ["arrivals", "ev_visits", "ev_connected", "requests", "admitted_req",
            "rejected", "rejected_need", "blocked_park", "delivered",
            "admitted_need", "gap_adm", "wait_sum", "wait_n", "supp_min",
            "idle_occ_min", "chg_occ_min", "fin_occ_min", "cost"]
    out = {k: sum(d[k] for d in per_day) for k in keys}
    out["days"] = len(per_day)
    out["cost_per_day"] = out["cost"] / max(1, out["days"])
    out["q_plug_true"] = out["ev_connected"] / out["ev_visits"] if out["ev_visits"] else float("nan")
    out["accept_rate"] = out["admitted_req"] / out["requests"] if out["requests"] else float("nan")
    out["gap_rate_adm"] = out["gap_adm"] / out["admitted_need"] if out["admitted_need"] else float("nan")
    out["idle_occ_share"] = (out["idle_occ_min"] / out["chg_occ_min"]
                             if out["chg_occ_min"] else float("nan"))
    out["daily_cost"] = [d["cost"] for d in per_day]
    return out
