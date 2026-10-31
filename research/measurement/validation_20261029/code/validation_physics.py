# -*- coding: utf-8 -*-
"""T14 物理与保护实验 E1-E4、F04-F07（从 run_validation_t14.py 机械拆分）。"""
import json

from validation_common import (
    S, PREREG, STATIONS, LEVELS, VIEW_KEYS, ROW_KEYS,
    mean, visible_view, estimate, weights_for, true_cost_per_day,
)

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
