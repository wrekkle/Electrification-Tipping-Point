# -*- coding: utf-8 -*-
import json, os, random, sys
ROOT = r"C:\Projects\停车场充电桩优化方案"
sys.path.insert(0, os.path.join(ROOT, "research", "round4_20261031", "mechanism"))
import shared_capacity_mechanism as scm

def strict_ice_fail(instance, k, descending=False):
    n = instance["n"]
    arrivals = sorted(instance["arrivals"], key=lambda a: (a["t"], a["is_ev"]))
    occ = {}
    fail = set()
    for idx, a in enumerate(arrivals):
        t = a["t"]
        for b in [b for b, dep in occ.items() if dep <= t + 1e-12]:
            del occ[b]
        if a["is_ev"]:
            continue
        free = [b for b in range(k, n) if b not in occ]
        if descending:
            free = list(reversed(free))
        if not free:
            fail.add(idx)
        else:
            occ[free[0]] = t + a["dwell"]
    return fail

def check_instance(inst):
    n = inst["n"]
    fails = [strict_ice_fail(inst, k) for k in range(n + 1)]
    viol = []
    for k in range(n):
        extra = fails[k] - fails[k + 1]
        if extra:
            viol.append({"k": k, "extra": sorted(extra)})
    return viol, fails

grid_viol = 0; grid_inst = 0; examples = []
for inst in scm.grid():
    grid_inst += 1
    viol, fails = check_instance(inst)
    if viol:
        grid_viol += 1
        if len(examples) < 3: examples.append({"n": inst["n"], "seed": inst["seed"], "viol": viol[:2]})
print("GRID_INSTANCES", grid_inst, "VIOLATIONS", grid_viol, "EX", examples)

rng = random.Random(20261031)
rand_viol = 0; rand_inst = 0; first = None
for trial in range(12000):
    n = rng.randint(2, 7)
    m = rng.randint(1, 10)
    arr = []
    for i in range(m):
        t = rng.randint(0, 12)
        is_ev = rng.random() < 0.4
        arr.append({"t": t, "is_ev": is_ev, "needs": is_ev and rng.random() < 0.5,
                    "dwell": rng.randint(1, 6)})
    arr.sort(key=lambda a: (a["t"], a["is_ev"]))
    inst = {"n": n, "arrivals": arr}
    rand_inst += 1
    viol, fails = check_instance(inst)
    if viol:
        rand_viol += 1
        if first is None: first = {"n": n, "arrivals": arr, "viol": viol[:2]}
print("RANDOM_INSTANCES", rand_inst, "VIOLATIONS", rand_viol, "FIRST", json.dumps(first, ensure_ascii=False)[:500])

# claim in B proof: shared-bay occupancy identical between k and k+1 at same time
inst = {"n": 4, "arrivals": [{"t": 0, "is_ev": False, "needs": False, "dwell": 10},
                             {"t": 1, "is_ev": False, "needs": False, "dwell": 10}]}
occ = {}
rows = []
for t, k in ((0, 0), (0, 1)):
    pass

def occupancy_after_first(inst, k):
    n = inst["n"]; occ = {}; rows = []
    for idx, a in enumerate(sorted(inst["arrivals"], key=lambda a: (a["t"], a["is_ev"]))):
        for b in [b for b, dep in occ.items() if dep <= a["t"] + 1e-12]:
            del occ[b]
        if a["is_ev"]: continue
        free = [b for b in range(k, n) if b not in occ]
        bay = free[0] if free else None
        if bay is not None: occ[bay] = a["t"] + a["dwell"]
        rows.append((idx, bay, dict(occ)))
    return rows
r0 = occupancy_after_first(inst, 0); r1 = occupancy_after_first(inst, 1)
print("OCC_CLAIM_COUNTEREXAMPLE", r0, r1)

# K sets for TPE1376 seed10
b = json.load(open(os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json"), encoding="utf-8"))
for rule in ("A", "B", "C", "D"):
    rec = b["sets"]["REF|%s|TPE1376|10" % rule]
    print("K_%s" % rule, "min", rec.get("min_known_feasible"), "K", rec.get("K"), "strict", rec.get("K_strict"), "trunc", rec.get("truncated_at_kmax"), "empty", rec.get("empty_set"))
