# -*- coding: utf-8 -*-
"""Independent replay of the 16 pi0 ICE-failure monotonicity counter-examples.

1) Enumerate the documented grid with an independent simulation (rules re-read from
   shared_capacity_mechanism.py docstring), find every instance where
   ice_parking_failure_rate decreases when k increases.
2) Cross-check the count against summary.monotonicity_pi0_ice in the stored JSON.
3) Dump the two simplest instances' fixed trajectories and confirm the violation by replay.
"""
import importlib.util, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MECH = os.path.join(ROOT, "research", "round4_20261031", "mechanism")
spec = importlib.util.spec_from_file_location("scm", os.path.join(MECH, "shared_capacity_mechanism.py"))
scm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scm)

def indep_sim(instance, k, rule):
    """Independent re-implementation from the documented rules (not calling scm.simulate)."""
    n = instance["n"]
    slots = [None] * n            # None or departure time
    c = {"req": 0, "ev": 0, "ev_fail": 0, "ice": 0, "ice_fail": 0, "cup": 0, "ev_ordinary": 0}
    events = sorted(instance["arrivals"], key=lambda a: (a["t"], a["is_ev"]))
    for a in events:
        for b in range(n):
            if slots[b] is not None and slots[b] <= a["t"] + 1e-12:
                slots[b] = None
        is_ev, needs = a["is_ev"], a["needs"]
        if is_ev:
            c["ev"] += 1
            if needs: c["req"] += 1
        else:
            c["ice"] += 1
        if is_ev:
            order = [b for b in range(k)] + [b for b in range(k, n)]
        else:
            order = [b for b in range(k, n)]
        free = [b for b in order if slots[b] is None]
        if not free:
            if is_ev:
                c["ev_fail"] += 1
                if needs: c["cup"] += 1
            else:
                c["ice_fail"] += 1
            continue
        bay = free[0]
        slots[bay] = a["t"] + a["dwell"]
        if is_ev and bay >= k:
            c["ev_ordinary"] += 1
            if needs: c["cup"] += 1
    rate = lambda x, y: None if y == 0 else x / y
    return {"k": k, "ice": c["ice"], "ice_fail": c["ice_fail"],
            "ice_rate": rate(c["ice_fail"], c["ice"]),
            "ev_fail": c["ev_fail"], "ev_ordinary": c["ev_ordinary"],
            "capacity_unmet": c["cup"], "req": c["req"]}

def violations(instance):
    rows = [indep_sim(instance, k, "pi0") for k in range(instance["n"] + 1)]
    out = []
    for a, b in zip(rows, rows[1:]):
        if a["ice_rate"] is not None and b["ice_rate"] is not None and b["ice_rate"] < a["ice_rate"] - 1e-12:
            out.append({"k_low": a["k"], "k_high": b["k"],
                        "rate_low": a["ice_rate"], "rate_high": b["ice_rate"],
                        "ice_fail_low": a["ice_fail"], "ice_fail_high": b["ice_fail"],
                        "ice_visits_low": a["ice"], "ice_visits_high": b["ice"],
                        "ev_ordinary_low": a["ev_ordinary"], "ev_ordinary_high": b["ev_ordinary"]})
    return out

all_v, checked = [], 0
for inst in scm.grid():
    checked += 1
    v = violations(inst)
    if v:
        all_v.append({"params": {x: inst[x] for x in ("seed", "n", "ev_share", "q_need",
                                                      "dwell_ev", "dwell_ice", "rate_per_slot",
                                                      "ev_offset", "ice_offset")},
                      "n_arrivals": len(inst["arrivals"]), "violations": v})
stored = json.load(open(os.path.join(MECH, "shared_capacity_mechanism.json"), encoding="utf-8"))
stored_count = stored["summary"]["monotonicity_pi0_ice"]["non_monotone_instances"]
all_v.sort(key=lambda x: (x["params"]["n"], x["n_arrivals"], x["params"]["seed"]))
picked = []
for item in all_v[:2]:
    inst = scm.make_instance(item["params"]["seed"], item["params"]["n"], item["params"]["ev_share"],
                             item["params"]["q_need"], item["params"]["dwell_ev"],
                             item["params"]["dwell_ice"], item["params"]["rate_per_slot"],
                             item["params"]["ev_offset"], item["params"]["ice_offset"])
    rows = [indep_sim(inst, k, "pi0") for k in range(inst["n"] + 1)]
    picked.append({"params": item["params"], "n_arrivals": item["n_arrivals"],
                   "violations": item["violations"], "trajectory": inst["arrivals"],
                   "ice_rates_by_k": [{"k": r["k"], "ice_fail": r["ice_fail"], "ice": r["ice"],
                                       "rate": r["ice_rate"], "ev_ordinary": r["ev_ordinary"],
                                       "capacity_unmet": r["capacity_unmet"]} for r in rows]})
# cross-check independent replay against the documented implementation on the picked instances
def scm_rates(instance):
    return [scm.simulate(instance, k, "pi0")["rates"]["ice_parking_failure_rate"] for k in range(instance["n"] + 1)]

def ev_first_sim(instance, k):
    n = instance["n"]; slots = [None] * n
    c = {"ice": 0, "ice_fail": 0}
    events = sorted(instance["arrivals"], key=lambda a: (a["t"], not a["is_ev"]))
    for a in events:
        for b in range(n):
            if slots[b] is not None and slots[b] <= a["t"] + 1e-12: slots[b] = None
        if not a["is_ev"]: c["ice"] += 1
        if a["is_ev"]:
            order = list(range(k)) + list(range(k, n))
        else:
            order = list(range(k, n))
        free = [b for b in order if slots[b] is None]
        if not free:
            if not a["is_ev"]: c["ice_fail"] += 1
            continue
        slots[free[0]] = a["t"] + a["dwell"]
    return c["ice_fail"] / c["ice"] if c["ice"] else None

cross = []
for item in picked:
    inst = scm.make_instance(item["params"]["seed"], item["params"]["n"], item["params"]["ev_share"],
                             item["params"]["q_need"], item["params"]["dwell_ev"],
                             item["params"]["dwell_ice"], item["params"]["rate_per_slot"],
                             item["params"]["ev_offset"], item["params"]["ice_offset"])
    mine = [r["ice_rate"] for r in [indep_sim(inst, k, "pi0") for k in range(inst["n"] + 1)]]
    theirs = scm_rates(inst)
    evf = [ev_first_sim(inst, k) for k in range(inst["n"] + 1)]
    drops_evf = [(k, evf[k], evf[k + 1]) for k in range(len(evf) - 1)
                 if evf[k] is not None and evf[k + 1] is not None and evf[k + 1] < evf[k] - 1e-12]
    cross.append({"params": item["params"], "mine": mine, "scm": theirs,
                  "equal": all((a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-12)
                               for a, b in zip(mine, theirs)),
                  "ev_first_tiebreak_rates": evf,
                  "ev_first_tiebreak_violations": drops_evf})
picked = picked
out = {"grid_instances_checked": checked, "independent_violating_instances": len(all_v),
       "stored_summary_count": stored_count,
       "count_matches": len(all_v) == stored_count,
       "violation_list": all_v,
       "picked_two": picked, "cross_check_and_tiebreak": cross}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mechanism_counterexamples.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps({"checked": checked, "violations": len(all_v), "stored": stored_count,
                  "picked_params": [p["params"] for p in picked],
                  "picked_violations": [p["violations"] for p in picked],
                  "cross_equal": [c["equal"] for c in cross],
                  "ev_first_violations": [c["ev_first_tiebreak_violations"] for c in cross]}, ensure_ascii=False, indent=1))
