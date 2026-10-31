#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T14 修订仿真：外生需求日志、真实保护容量、逐车能量守恒、固定时间顺序。

相对 2026-10-29 初版（备份 code/_t14_backup_20261029/）：
- F04 预生成外生需求日志；动作侧（暂停/选位）用独立随机流，不消耗需求随机数。
- F06 R4 实现固定保护容量：protect_k 个充电位、protect_window 时段、仅 EV 请求者可用；
       非保护时段退回 R3。R4 不再等同 R3。
- F07 每步交付截断到剩余需求；离场先于供能；逐车与总账守恒可校验。
旧结果 results/ 保留不动，本轮新结果写 results_t14/。
"""
import hashlib
import json
import math
import random
import zlib

PARAMS = dict(
    N=80, H=840, lam=0.45, ev_share=0.35, q_need=0.60,
    dwell_med=90.0, dwell_sigma=0.55, dwell_min=15.0, dwell_max=480.0,
    need_med=18.0, need_sigma=0.50, need_min=3.0, need_max=80.0,
    p_rated=22.0, feeder_cap=66.0, pause_prob=0.005,
    reserved_bias=2, delta=5, fault_gun=0, fault_window=(600, 720),
    protect_k=2, protect_window=(300, 540),
    c_cap=300.0, c_gap=2.0, c_ref=3.0, c_wait=6.0, c_park=4.0,
)


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


# ------------------------------------------------------------------ F04
def make_demand_log(seed, days, params=None, scale=1.0):
    """预生成外生需求日志。只依赖需求参数，不含容量、规则或动作随机数。"""
    P = dict(PARAMS)
    P.update(params or {})
    rng = random.Random(seed)
    events = []
    for day in range(days):
        for t in range(P["H"]):
            for _ in range(poisson(rng, P["lam"] * scale)):
                dwell = lognormal(rng, P["dwell_med"], P["dwell_sigma"],
                                  P["dwell_min"], P["dwell_max"])
                is_ev = rng.random() < P["ev_share"]
                req = is_ev and (rng.random() < P["q_need"])
                need = lognormal(rng, P["need_med"], P["need_sigma"],
                                 P["need_min"], P["need_max"]) if req else 0.0
                events.append([day, t, round(dwell, 6), int(is_ev), int(req), round(need, 6)])
    meta = dict(seed=seed, days=days, scale=scale,
                demand_params={k: P[k] for k in ("H", "lam", "ev_share", "q_need",
                                                 "dwell_med", "dwell_sigma", "need_med")})
    return dict(meta=meta, events=events)


def log_hash(log):
    """对事件序列取 SHA-256；不同配置复用同一日志时哈希必须相同。"""
    payload = json.dumps(log["events"], separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def action_seed(seed, n_c, policy, sel):
    """动作侧随机流种子：与需求流隔离，配置与规则不同则动作随机数不同。"""
    tag = zlib.crc32((str(policy) + "|" + str(sel)).encode("utf-8"))
    return (seed * 7919 + n_c * 131 + tag) & 0x7FFFFFFF


# ------------------------------------------------------------------ 规则
def _pick(lst, sel, t=0):
    if not lst:
        return None
    if sel == "first":
        return min(lst)
    if sel == "last":
        return max(lst)
    s = sorted(lst)
    return s[(int(t) * 37 + len(s) * 11) % len(s)]


def protected_bays(P, n_c, n_ord):
    k = int(P["protect_k"])
    return set(range(n_ord, n_ord + min(k, n_c)))


def choose_bay(policy, t, is_ev, req, ord_free, chg_free, chg_free_unprot, sel, P):
    """返回车位下标或 None。R1-R4 见 SPEC_metrics.md 第 6 节，R4 见 T14 F06。"""
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
        peak = P["protect_window"][0] <= t < P["protect_window"][1]
        if is_ev and req:
            b = _pick(chg_free, sel, t)
            return b if b is not None else _pick(ord_free, sel, t)
        if peak:
            b = _pick(ord_free, sel, t)
            if b is not None:
                return b
            return _pick(chg_free_unprot, sel, t)
        b = _pick(ord_free, sel, t)
        return b if b is not None else _pick(chg_free, sel, t)
    raise ValueError("unknown policy " + str(policy))


# ------------------------------------------------------------------ 单日
def run_day(events, act_rng, P, n_c, policy, sel, day, snaps, trace):
    N, H = P["N"], P["H"]
    n_ord = N - n_c
    ord_ids = list(range(n_ord))
    chg_ids = list(range(n_ord, N))
    prot = protected_bays(P, n_c, n_ord)
    bay = [None] * N

    by_t = {}
    for ev in events:
        by_t.setdefault(ev[1], []).append(ev)

    m = dict(arrivals=0, ev_visits=0, ev_connected=0, requests=0, admitted_req=0,
             rejected=0, rejected_need=0.0, blocked_park=0, wait_sum=0.0, wait_n=0,
             delivered=0.0, admitted_need=0.0, gap_adm=0.0, supp_min=0,
             idle_occ_min=0, chg_occ_min=0, fin_occ_min=0, conservation_residual=0.0,
             max_step_excess=0.0)
    occ = 0

    for t in range(H):
        fault_now = P["fault_window"][0] <= t < P["fault_window"][1]
        faulted = [fault_now and g == P["fault_gun"] for g in range(n_c)]

        # 1) 先离场：离场那一分钟不再计供能
        for bi in range(N):
            v = bay[bi]
            if v is None or t < v["leave"]:
                continue
            if v["req"]:
                gap = max(0.0, v["need"] - v["delivered"])
                m["gap_adm"] += gap
                m["conservation_residual"] = max(
                    m["conservation_residual"],
                    abs((v["delivered"] + gap) - v["need"]))
            bay[bi] = None
            occ -= 1

        # 2) 供能：每步截断到剩余需求（F07）
        active = []
        for g, bi in enumerate(chg_ids):
            v = bay[bi]
            if v is None or not v["req"]:
                continue
            if v["conn_t"] is None or t < v["conn_t"]:
                v["state"] = "S3"
                continue
            if v["remaining"] <= 1e-12:
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
            if act_rng.random() < P["pause_prob"]:
                p = 0.0
                v["state"] = "S5"
            else:
                v["state"] = "S4"
            e = min(p / 60.0, v["remaining"])
            if e < -1e-12:
                m["max_step_excess"] = max(m["max_step_excess"], -e)
            if e > 0:
                supply_count += 1
                m["supp_min"] += 1
                v["delivered"] += e
                v["remaining"] = max(0.0, v["remaining"] - e)
                m["delivered"] += e
        n_fault = sum(1 for f in faulted if f)

        # 3) 占用与闲占
        chg_row = []
        for g, bi in enumerate(chg_ids):
            v = bay[bi]
            if v is not None:
                m["chg_occ_min"] += 1
                if v["state"] != "S4":
                    m["idle_occ_min"] += 1
                if v["state"] == "S6":
                    m["fin_occ_min"] += 1
            st = "fault" if faulted[g] else (
                "supplying" if (v is not None and v["state"] == "S4") else "idle")
            chg_row.append((st, v["sess"] if v is not None else None))

        # 4) 到达与分配（来自预生成日志）
        for ev in by_t.get(t, []):
            _, _, dwell, is_ev, req, need = ev
            is_ev, req = bool(is_ev), bool(req)
            m["arrivals"] += 1
            if is_ev:
                m["ev_visits"] += 1
            if req:
                m["requests"] += 1
            ord_free = [i for i in ord_ids if bay[i] is None]
            chg_free = [i for i in chg_ids if bay[i] is None]
            chg_free_unprot = [i for i in chg_free if i not in prot]
            target = choose_bay(policy, t, is_ev, req, ord_free, chg_free,
                                chg_free_unprot, sel, P)
            if trace is not None:
                trace.append((day, t, "req" if req else ("ev" if is_ev else "ord"),
                              -1 if target is None else int(target)))
            if target is None:
                if req:
                    m["rejected"] += 1
                    m["rejected_need"] += need
                else:
                    m["blocked_park"] += 1
                continue
            v = dict(arr=t, dwell=dwell, is_ev=is_ev, req=req, need=need,
                     delivered=0.0, remaining=need, conn_t=None,
                     leave=t + dwell, state=None, sess=None, bi=target)
            bay[target] = v
            occ += 1
            if req:
                m["admitted_req"] += 1
                m["admitted_need"] += need
                if target >= n_ord:
                    v["conn_t"] = t
                    v["sess"] = "%d-%d-%d" % (day, t, len(chg_row))
                    m["ev_connected"] += 1
                    m["wait_sum"] += 1.0
                    m["wait_n"] += 1
                else:
                    v["state"] = "S2"
            else:
                v["state"] = "S1" if not is_ev else "S2"

        # 5) 快照
        if t % P["delta"] == 0:
            free_phys = N - occ
            snaps.append(dict(
                t=day * H + t, free_phys=free_phys,
                free_obs=max(0, free_phys - P["reserved_bias"]),
                n_supply=supply_count, n_fault=n_fault,
                n_idle=max(0, n_c - supply_count - n_fault),
                delivered_cum=round(m["delivered"], 6),
                chg=[(st, s) for st, s in chg_row]))

    # 收盘：仍在场车辆的需求缺口
    for bi in range(N):
        v = bay[bi]
        if v is not None and v["req"]:
            gap = max(0.0, v["need"] - v["delivered"])
            m["gap_adm"] += gap
            m["conservation_residual"] = max(
                m["conservation_residual"], abs((v["delivered"] + gap) - v["need"]))

    # 总账：已接纳需求 = 交付 + 已接纳缺口
    m["conservation_gross"] = abs(m["delivered"] + m["gap_adm"] - m["admitted_need"])
    return m


def simulate(seed, days, n_c, policy="R3", sel="first", params=None, scale=1.0,
             log=None, trace=False):
    """同一 log 可被不同 n_c/policy 复用；动作随机流独立于需求流。"""
    P = dict(PARAMS)
    P.update(params or {})
    if log is None:
        log = make_demand_log(seed, days, params=params, scale=scale)
    act = random.Random(action_seed(seed, n_c, policy, sel))
    per_day, snaps, tr = [], [], ([] if trace else None)
    for day in range(days):
        evs = [e for e in log["events"] if e[0] == day]
        per_day.append(run_day(evs, act, P, n_c, policy, sel, day, snaps, tr))
    return dict(per_day=per_day, snapshots=snaps, trace=tr, params=P,
                log_hash=log_hash(log), meta=log["meta"])


KEYS = ["arrivals", "ev_visits", "ev_connected", "requests", "admitted_req", "rejected",
        "rejected_need", "blocked_park", "delivered", "admitted_need", "gap_adm",
        "wait_sum", "wait_n", "supp_min", "idle_occ_min", "chg_occ_min", "fin_occ_min",
        "conservation_residual", "conservation_gross", "max_step_excess"]


def aggregate(per_day, n_c=None):
    out = {k: sum(d[k] for d in per_day) for k in KEYS}
    out["n_c"] = n_c
    out["days"] = len(per_day)
    out["cost_per_day"] = cost(out) / max(1, out["days"])
    out["q_plug_true"] = out["ev_connected"] / out["ev_visits"] if out["ev_visits"] else float("nan")
    out["accept_rate"] = out["admitted_req"] / out["requests"] if out["requests"] else float("nan")
    out["gap_rate_adm"] = out["gap_adm"] / out["admitted_need"] if out["admitted_need"] else float("nan")
    out["idle_occ_share"] = (out["idle_occ_min"] / out["chg_occ_min"]
                             if out["chg_occ_min"] else float("nan"))
    out["daily_cost"] = [cost(dict(d, n_c=n_c)) for d in per_day]
    return out


def cost(agg, weights=None):
    """成本口径固定（可预注册多组 c_cap），其余系数不改。"""
    w = dict(c_cap=PARAMS["c_cap"], c_gap=PARAMS["c_gap"], c_ref=PARAMS["c_ref"],
             c_wait=PARAMS["c_wait"], c_park=PARAMS["c_park"])
    if weights:
        w.update(weights)
    n_c = agg["n_c"]
    return (w["c_cap"] * n_c + w["c_gap"] * agg["gap_adm"] + w["c_ref"] * agg["rejected_need"]
            + w["c_wait"] * agg["wait_sum"] / 60.0 + w["c_park"] * agg["blocked_park"])
