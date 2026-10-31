# -*- coding: utf-8 -*-
r"""Q1：第五轮 16 个非单调反例的事件级机制轨迹（workbench Simulation 复跑 + 控制变量）。

只读导入 round4 机制模型（scm）与 workbench；不写 apps/。输出 q1_traces.json。
命令：C:/anaconda/python.exe research/round6_20261031/b_mechanism/q1_trace_mechanism.py
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import Arrival
from apps.parking_lab.workbench.simulation import Simulation

SCM_PATH = ROOT / "research" / "round4_20261031" / "mechanism" / "shared_capacity_mechanism.py"
R5_JSON = ROOT / "research" / "round5_20261031" / "acceptance" / "mechanism_counterexamples.json"
spec = importlib.util.spec_from_file_location("scm", SCM_PATH)
scm = importlib.util.module_from_spec(spec); spec.loader.exec_module(scm)
ALPHA = 0.05
EPS = 1e-12

EXAMPLES = [
    ("E1_TPE-like_n6_k0-1", dict(seed=1, n=6, ev_share=0.4, q_need=0.1, dwell_ev=5, dwell_ice=5,
                                rate_per_slot=1.6, ev_offset=-1, ice_offset=1), 0),
    ("E2_n8_k5-6", dict(seed=1, n=8, ev_share=0.6, q_need=0.1, dwell_ev=5, dwell_ice=2,
                        rate_per_slot=1.6, ev_offset=0, ice_offset=0), 5),
    ("E3_n8_seed3_k2-3", dict(seed=3, n=8, ev_share=0.4, q_need=0.5, dwell_ev=5, dwell_ice=5,
                              rate_per_slot=1.6, ev_offset=-1, ice_offset=1), 2),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------- 1) 文档规则的可追踪重放（与 scm.simulate 逐值对齐） ----------
def trace_sim(inst, k, variant="base", dwell_scale=1.0, reverse=False, initial=None):
    n = inst["n"]
    occupied = dict(initial or {})
    rows, counters = [], {"ev": 0, "ev_fail": 0, "ice": 0, "ice_fail": 0,
                          "req": 0, "cap_unmet": 0, "ev_ordinary": 0}
    events = sorted(inst["arrivals"], key=lambda a: (a["t"], a["is_ev"]))
    for seq, a in enumerate(events):
        t = a["t"]; dwell = a["dwell"] * dwell_scale
        released = sorted([b for b, dep in occupied.items() if dep <= t + 1e-12])
        for b in released:
            del occupied[b]
        is_ev, needs = a["is_ev"], a["needs"]
        if is_ev:
            counters["ev"] += 1
            if needs: counters["req"] += 1
        else:
            counters["ice"] += 1
        if is_ev:
            order = [b for b in range(k)]
            if variant != "strict_pi0":
                order += [b for b in range(k, n)]
        else:
            order = list(range(k, n))
        free = [b for b in order if b not in occupied]
        if reverse:
            free = free[::-1]
        chosen = free[0] if free else None
        row = {"seq": seq, "t": round(t, 6), "vehicle_id": seq, "is_ev": is_ev,
               "needs_charge": needs, "dwell": dwell, "released": released,
               "free_in_order": free, "bay": chosen,
               "zone": None if chosen is None else ("equipped" if chosen < k else "ordinary")}
        if chosen is None:
            row["outcome"] = "rejected"
            if is_ev:
                counters["ev_fail"] += 1
                if needs: counters["cap_unmet"] += 1
            else:
                counters["ice_fail"] += 1
        else:
            row["outcome"] = "admitted"
            occupied[chosen] = t + dwell
            if is_ev and needs and chosen >= k:
                counters["cap_unmet"] += 1
                counters["ev_ordinary"] += 1
            elif is_ev and chosen >= k:
                counters["ev_ordinary"] += 1
        rows.append(row)
    rate = lambda x, y: None if y == 0 else x / y
    return {"k": k, "rows": rows, "ev": counters["ev"], "ev_fail": counters["ev_fail"],
            "ice": counters["ice"], "ice_fail": counters["ice_fail"], "req": counters["req"],
            "cap_unmet": counters["cap_unmet"], "ev_ordinary": counters["ev_ordinary"],
            "ev_rate": rate(counters["ev_fail"], counters["ev"]),
            "ice_rate": rate(counters["ice_fail"], counters["ice"])}


def wb_run(inst, k, dwell_scale=1.0, tie_ev_first=False):
    arrivals = []
    for i, a in enumerate(inst["arrivals"]):
        energy = 14.0 if (a["is_ev"] and a["needs"]) else 0.0
        arrivals.append(Arrival(i, (a["t"] + 1.0) * 60.0, a["is_ev"], a["needs"],
                                a["dwell"] * dwell_scale * 60.0, energy))
    if tie_ev_first:
        arrivals.sort(key=lambda x: (x.time_min, not x.is_ev))
    cfg = Config(n_spaces=inst["n"], charging_bays=k, chargers=k, duration_hours=32.0,
                 start_hour=0.0, policy="dedicated_by_type", arrival_rate_hour=2.0,
                 charger_kw=7.0, feeder_kw=336.0)
    sim = Simulation(cfg, arrivals=tuple(arrivals))
    sim.run()
    visits = sim.visits
    ev_fail = sum(1 for v in visits if v["is_ev"] and not v["admitted"])
    ice_fail = sum(1 for v in visits if (not v["is_ev"]) and not v["admitted"])
    cap_unmet = sum(1 for v in visits if v["is_ev"] and v["needs_charge"]
                    and (not v["admitted"] or v["bay"] >= k))
    return {"k": k, "visits": visits, "ev": sum(v["is_ev"] for v in visits),
            "ice": sum(not v["is_ev"] for v in visits), "ev_fail": ev_fail,
            "ice_fail": ice_fail, "cap_unmet": cap_unmet,
            "events": sim.events}


def wb_rate(res):
    return {name: (None if res[den] == 0 else res[num] / res[den]) for name, num, den in (
        ("ev_parking_failure_rate", "ev_fail", "ev"), ("ice_parking_failure_rate", "ice_fail", "ice"))}


def check_all_k(inst):
    n = inst["n"]
    out = []
    for k in range(n + 1):
        base = scm.simulate(inst, k, "pi0")
        wb = wb_run(inst, k)
        ok = (base["ev_fail"] == wb["ev_fail"] and base["ice_fail"] == wb["ice_fail"]
              and base["cap_unmet"] == wb["cap_unmet"])
        out.append({"k": k, "base": {"ev_fail": base["ev_fail"], "ice_fail": base["ice_fail"],
                                     "cap_unmet": base["cap_unmet"]},
                    "workbench": {"ev_fail": wb["ev_fail"], "ice_fail": wb["ice_fail"],
                                  "cap_unmet": wb["cap_unmet"]}, "equal": ok})
    return out


def occupancy_at(visits, t):
    return sorted({v["vehicle_id"]: v for v in visits
                   if v["admitted"] and v["time_min"] < t - 1e-9
                   and v["departure_min"] > t}.keys())


def divergence(inst, k, wb_k, wb_k1):
    by0 = {v["vehicle_id"]: v for v in wb_k["visits"]}
    by1 = {v["vehicle_id"]: v for v in wb_k1["visits"]}
    changed = []
    for vid in sorted(by0):
        a, b = by0[vid], by1[vid]
        if (a["admitted"] != b["admitted"]) or (a["admitted"] and a["bay"] != b["bay"]):
            changed.append({
                "vehicle_id": vid, "t": round(a["time_min"] / 60.0, 6),
                "is_ev": a["is_ev"], "needs_charge": a["needs_charge"],
                "dwell": round(a["dwell_min"] / 60.0, 4),
                "k": {"admitted": a["admitted"], "bay": a["bay"],
                      "occupants_at_arrival": occupancy_at(wb_k["visits"], a["time_min"]),
                      "ev_ordinary": bool(a["is_ev"] and a["admitted"] and a["bay"] >= k)},
                "k1": {"admitted": b["admitted"], "bay": b["bay"],
                       "occupants_at_arrival": occupancy_at(wb_k1["visits"], b["time_min"]),
                       "ev_ordinary": bool(b["is_ev"] and b["admitted"] and b["bay"] >= k + 1)}})
    ice0 = {v["vehicle_id"] for v in wb_k["visits"] if not v["is_ev"] and not v["admitted"]}
    ice1 = {v["vehicle_id"] for v in wb_k1["visits"] if not v["is_ev"] and not v["admitted"]}
    ev0 = {v["vehicle_id"] for v in wb_k["visits"] if v["is_ev"] and not v["admitted"]}
    ev1 = {v["vehicle_id"] for v in wb_k1["visits"] if v["is_ev"] and not v["admitted"]}
    return {"changed_vehicles": changed, "n_changed": len(changed),
            "ice_fail_at_k": sorted(ice0), "ice_fail_at_k1": sorted(ice1),
            "ice_recovered": sorted(ice0 - ice1), "ice_lost": sorted(ice1 - ice0),
            "ev_fail_at_k": sorted(ev0), "ev_fail_at_k1": sorted(ev1),
            "ev_recovered": sorted(ev0 - ev1), "ev_lost": sorted(ev1 - ev0)}


def variants(inst, k):
    n = inst["n"]
    res = {}
    base0, base1 = trace_sim(inst, k), trace_sim(inst, k + 1)
    res["base_trace"] = {"k": [base0["ice_fail"], base1["ice_fail"]],
                         "rates": [base0["ice_rate"], base1["ice_rate"]]}
    strict = {"k": [], "rates": [], "ev_fail": []}
    for kk in (k, k + 1):
        t = trace_sim(inst, kk, variant="strict_pi0")
        strict["k"].append(t["ice_fail"]); strict["rates"].append(t["ice_rate"])
        strict["ev_fail"].append(t["ev_fail"])
    res["strict_pi0_no_fallback"] = strict
    rev = {"k": [], "rates": [], "ev_ordinary": []}
    for kk in (k, k + 1):
        t = trace_sim(inst, kk, reverse=True)
        rev["k"].append(t["ice_fail"]); rev["rates"].append(t["ice_rate"])
        rev["ev_ordinary"].append(t["ev_ordinary"])
    res["slot_order_reverse"] = rev
    for label, scale in (("dwell_minus20", 0.8), ("dwell_plus20", 1.2)):
        r = {"k": [], "rates": [], "ev_fail": [], "ice_fail": []}
        for kk in (k, k + 1):
            wb = wb_run(inst, kk, dwell_scale=scale)
            rt = wb_rate(wb)
            r["k"].append(kk); r["rates"].append(rt["ice_parking_failure_rate"])
            r["ice_fail"].append(wb["ice_fail"]); r["ev_fail"].append(wb["ev_fail"])
        res[label] = r
    init = {b: 4.0 for b in range(n - max(1, n // 3), n)}
    ini = {"k": [], "rates": [], "ev_fail": [], "initial": init}
    for kk in (k, k + 1):
        t = trace_sim(inst, kk, initial=init)
        ini["k"].append(t["ice_fail"]); ini["rates"].append(t["ice_rate"])
        ini["ev_fail"].append(t["ev_fail"])
    res["initial_occupancy_last_third_until_t4"] = ini
    evf = {"k": [], "rates": [], "ice_fail": []}
    for kk in (k, k + 1):
        wb = wb_run(inst, kk, tie_ev_first=True)
        rt = wb_rate(wb)
        evf["k"].append(kk); evf["rates"].append(rt["ice_parking_failure_rate"])
        evf["ice_fail"].append(wb["ice_fail"])
    res["same_tick_ev_first"] = evf
    ties = len(inst["arrivals"]) - len({a["t"] for a in inst["arrivals"]})
    for name, item in list(res.items()):
        if isinstance(item, dict) and "rates" in item:
            rates = item["rates"]
            item["violation_persists"] = (rates[0] is not None and rates[1] is not None
                                          and rates[1] < rates[0] - EPS)
    res["same_tick_exact_ties"] = ties
    return res


def grid_sweep():
    out = {"instances": 0, "base_violations": 0, "strict_pi0_violations": 0,
           "reverse_order_violations": 0}
    for inst in scm.grid():
        out["instances"] += 1
        n = inst["n"]
        for variant, key, rev in (("base", "base_violations", False),
                                  ("strict_pi0", "strict_pi0_violations", False),
                                  ("base", "reverse_order_violations", True)):
            rates = [trace_sim(inst, k, variant=variant, reverse=rev)["ice_rate"] for k in range(n + 1)]
            for a, b in zip(rates, rates[1:]):
                if a is not None and b is not None and b < a - EPS:
                    out[key] += 1
                    break
    return out


def main():
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stored = json.loads(R5_JSON.read_text(encoding="utf-8"))
    fallback_all = all(item["violations"][0]["ev_ordinary_low"] > item["violations"][0]["ev_ordinary_high"]
                       for item in stored["violation_list"])
    examples = []
    for name, params, k in EXAMPLES:
        inst = scm.make_instance(**params)
        check = check_all_k(inst)
        wb0, wb1 = wb_run(inst, k), wb_run(inst, k + 1)
        base0, base1 = scm.simulate(inst, k, "pi0"), scm.simulate(inst, k + 1, "pi0")
        traces = {}
        for kk in (k, k + 1):
            tr = trace_sim(inst, kk)
            traces[str(kk)] = tr
        examples.append({
            "id": name, "params": params, "k": k,
            "base_rates": [base0["rates"]["ice_parking_failure_rate"], base1["rates"]["ice_parking_failure_rate"]],
            "base_ice_fail": [base0["ice_fail"], base1["ice_fail"]],
            "base_ev_ordinary": [traces[str(k)]["ev_ordinary"], traces[str(k + 1)]["ev_ordinary"]],
            "workbench": {"k": {"ice_fail": wb0["ice_fail"], "ev_fail": wb0["ev_fail"],
                                "cap_unmet": wb0["cap_unmet"], "rates": wb_rate(wb0)},
                          "k1": {"ice_fail": wb1["ice_fail"], "ev_fail": wb1["ev_fail"],
                                 "cap_unmet": wb1["cap_unmet"], "rates": wb_rate(wb1)}},
            "workbench_equal_all_k": all(r["equal"] for r in check),
            "workbench_check": check,
            "trajectories": {kk: [{"seq": r["seq"], "t": r["t"], "is_ev": r["is_ev"],
                                   "needs_charge": r["needs_charge"], "dwell": r["dwell"],
                                   "bay": r["bay"], "zone": r["zone"], "outcome": r["outcome"]}
                                  for r in tr["rows"]] for kk, tr in traces.items()},
            "divergence": divergence(inst, k, wb0, wb1),
            "variants": variants(inst, k),
            "n_arrivals": len(inst["arrivals"]),
        })
    out = {"schema": "round6/b_mechanism/q1_traces/v1", "generated_utc": generated,
           "command": "C:\\anaconda\\python.exe research/round6_20261031/b_mechanism/q1_trace_mechanism.py",
           "interpreter": sys.version.split()[0],
           "inputs": {"shared_capacity_mechanism.py": sha(SCM_PATH),
                      "mechanism_counterexamples.json": sha(R5_JSON)},
           "method": {
               "counterexample_source": "round5 acceptance/mechanism_counterexamples.json（16 条身份）",
               "workbench_encoding": "round4 机制轨迹按 t×60 min、dwell×60 min、needs_charge EV 能量 14 kWh 编入 workbench Simulation；n_spaces=n、charging_bays=chargers=k、π0=dedicated_by_type",
               "trace_model": "按 round4 文档规则逐事件重放（与 workbench 逐 k 对账）",
               "alpha": ALPHA},
           "stored_summary": {"grid_instances_checked": stored["grid_instances_checked"],
                              "independent_violating_instances": stored["independent_violating_instances"],
                              "all_16_involve_ev_fallback": fallback_all},
           "examples": examples,
           "grid_sweep": grid_sweep()}
    (HERE / "q1_traces.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"examples": [{"id": e["id"], "match": e["workbench_equal_all_k"],
                                    "base": e["base_ice_fail"], "wb": [e["workbench"]["k"]["ice_fail"],
                                                                       e["workbench"]["k1"]["ice_fail"]],
                                    "n_changed": e["divergence"]["n_changed"],
                                    "variants": {k: v.get("violation_persists")
                                                 for k, v in e["variants"].items()
                                                 if isinstance(v, dict)}} for e in examples],
                      "all_16_fallback": fallback_all, "grid_sweep": out["grid_sweep"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
