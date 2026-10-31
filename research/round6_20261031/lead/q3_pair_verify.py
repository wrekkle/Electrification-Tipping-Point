# -*- coding: utf-8 -*-
import json, os
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json"), encoding="utf-8"))
sets = b["sets"]
def K(s):
    return sets[s]["K"]
expected = {
 "A|B": (190,153,3,0,34,0,0,2), "A|C": (90,72,3,0,15,0,0,2), "A|D": (190,155,1,0,34,0,0,1),
 "B|C": (90,72,0,0,18,0,0,0), "B|D": (190,153,0,2,35,2,1,0), "C|D": (90,72,0,2,16,2,1,0)}
agg = {k: {"pairs":0,"both":0,"first_only":0,"second_only":0,"neither":0,"restored":0,"smaller":0,"disjoint":0,"smaller_groups":[]} for k in expected}
for pair_key in sorted(b["pairs"]):
    sc, r1, r2 = pair_key.split("|")
    key = r1 + "|" + r2
    groups = sorted({k.rsplit("|",2)[1] + "|" + k.rsplit("|",1)[1] for k in sets if k.startswith(sc + "|" + r1 + "|")})
    for lotseed in groups:
        ka = K(sc + "|" + r1 + "|" + lotseed); kb = K(sc + "|" + r2 + "|" + lotseed)
        a = agg[key]; a["pairs"] += 1
        if ka and kb:
            a["both"] += 1
            if set(ka).isdisjoint(set(kb)): a["disjoint"] += 1
            if min(kb) < min(ka):
                a["smaller"] += 1; a["smaller_groups"].append({"scenario":sc,"group":lotseed,"K_first":ka,"K_second":kb})
        elif ka: a["first_only"] += 1
        elif kb: a["second_only"] += 1; a["restored"] += 1
        else: a["neither"] += 1
ok = True
for key, a in agg.items():
    got = (a["pairs"],a["both"],a["first_only"],a["second_only"],a["neither"],a["restored"],a["smaller"],a["disjoint"])
    a["got"] = got; a["expected_table4"] = expected[key]; a["match"] = got == expected[key]
    ok = ok and a["match"]
    print(key, got, "vs", expected[key], "MATCH" if a["match"] else "MISMATCH")
print("ALL_MATCH", ok)
print("SMALLER_GROUPS", json.dumps({k:v["smaller_groups"] for k,v in agg.items() if v["smaller_groups"]}, ensure_ascii=False))
open(os.path.join(ROOT, "research", "round6_20261031", "lead", "q3_pair_verify.json"), "w", encoding="utf-8").write(json.dumps({"all_match": ok, "by_pair": agg}, ensure_ascii=False, indent=2))
