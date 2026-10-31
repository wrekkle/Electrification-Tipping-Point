# -*- coding: utf-8 -*-
import json, os, random, sys
ROOT = r"C:\Projects\停车场充电桩优化方案"
sys.path.insert(0, os.path.join(ROOT, "research", "round4_20261031", "mechanism"))
import shared_capacity_mechanism as scm

def strict_ice_fail(instance, k):
    n = instance["n"]
    occ = {}; fail = set()
    for idx, a in enumerate(sorted(instance["arrivals"], key=lambda a: (a["t"], a["is_ev"]))):
        t = a["t"]
        for b in [b for b, dep in occ.items() if dep <= t + 1e-12]:
            del occ[b]
        if a["is_ev"]:
            continue
        free = [b for b in range(k, n) if b not in occ]
        if not free:
            fail.add(idx)
        else:
            occ[free[0]] = t + a["dwell"]
    return fail

def violations(inst):
    n = inst["n"]; fails = [strict_ice_fail(inst, k) for k in range(n + 1)]; out = []
    for k in range(n):
        extra = fails[k] - fails[k + 1]
        if extra: out.append({"k": k, "extra": sorted(extra)})
    return out

grid_v = 0; grid_n = 0
for inst in scm.grid():
    grid_n += 1
    if violations(inst): grid_v += 1
rng = random.Random(20261031); rand_v = 0; rand_n = 0
for _ in range(12000):
    n = rng.randint(2, 7); arr = []
    for i in range(rng.randint(1, 10)):
        t = rng.randint(0, 12); is_ev = rng.random() < 0.4
        arr.append({"t": t, "is_ev": is_ev, "needs": is_ev and rng.random() < 0.5, "dwell": rng.randint(1, 6)})
    arr.sort(key=lambda a: (a["t"], a["is_ev"]))
    rand_n += 1
    if violations({"n": n, "arrivals": arr}): rand_v += 1

def occ_after_first(k):
    inst = {"n": 4, "arrivals": [{"t": 0, "is_ev": False, "needs": False, "dwell": 10},
                                 {"t": 1, "is_ev": False, "needs": False, "dwell": 10}]}
    occ = {}; rows = []
    for idx, a in enumerate(inst["arrivals"]):
        for b in [b for b, dep in occ.items() if dep <= a["t"] + 1e-12]:
            del occ[b]
        free = [b for b in range(k, 4) if b not in occ]
        bay = free[0] if free else None
        if bay is not None: occ[bay] = a["t"] + a["dwell"]
        rows.append({"arrival": idx, "bay": bay, "occupied": dict(occ)})
    return rows

p1 = {
  "grid_instances": grid_n, "grid_failures": grid_v,
  "random_instances": rand_n, "random_failures": rand_v,
  "occupancy_claim_counterexample": {"k0": occ_after_first(0), "k1": occ_after_first(1)},
  "note": "P1 enumeration is supportive, not a proof; corrected dominance proof in consistency_check.md section 4."
}
open(os.path.join(ROOT, "research", "round6_20261031", "lead", "p1_indep.json"), "w", encoding="utf-8").write(json.dumps(p1, ensure_ascii=False, indent=2))
print("P1", json.dumps(p1, ensure_ascii=False)[:600])

b = json.load(open(os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json"), encoding="utf-8"))
sets = b["sets"]
def K(s):
    return sets[s]["K"]
rule_pairs = [("A","B"),("A","C"),("A","D"),("B","C"),("B","D"),("C","D")]
scens = sorted({k.split("|")[0] for k in sets})
desc = {}
for sc in scens:
    lots = sorted({(k.split("|")[2], k.split("|")[3]) for k in sets if k.startswith(sc + "|")})
    for r1, r2 in rule_pairs:
        c = {"both":0,"first_only":0,"second_only":0,"neither":0,"restored":0,"smaller":0,"disjoint":0,"groups":0}
        for lot, seed in lots:
            a = "REF" if False else None
            ka = K(sc + "|" + r1 + "|" + lot + "|" + seed)
            kb = K(sc + "|" + r2 + "|" + lot + "|" + seed)
            c["groups"] += 1
            if ka and kb:
                c["both"] += 1
                if set(ka).isdisjoint(set(kb)): c["disjoint"] += 1
                if min(kb) < min(ka): c["smaller"] += 1
            elif ka: c["first_only"] += 1
            elif kb: c["second_only"] += 1; c["restored"] += 1
            else: c["neither"] += 1
        desc["%s|%s|%s" % (sc, r1, r2)] = c
print("SCENARIOS", scens)
for key, c in desc.items(): print(key, c)
# totals matching Table 4 rows
print("TOTALS:")
for r1, r2 in rule_pairs:
    agg = {k: sum(v[k] for v in desc.values() if set([r1, r2]) == set(k.split("|")[1:])) for k in ("both","first_only","second_only","neither","restored","smaller","disjoint")}
    print(r1, r2, agg)
open(os.path.join(ROOT, "research", "round6_20261031", "lead", "q3_pair_verify.json"), "w", encoding="utf-8").write(json.dumps({"scenarios": scens, "by_scenario": desc}, ensure_ascii=False, indent=2))
print("saved q3_pair_verify.json")
