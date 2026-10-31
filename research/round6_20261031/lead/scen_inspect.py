# -*- coding: utf-8 -*-
import json, os, collections
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(os.path.join(ROOT, "research", "round6_20261031", "b_feasible", "q3_feasible_sets.json"), encoding="utf-8"))
sets = b["sets"]
scen_rules = collections.defaultdict(lambda: collections.Counter())
for k in sets:
    p = k.split("|")
    scen_rules[p[0]][p[1]] += 1
for sc in sorted(scen_rules): print(sc, dict(scen_rules[sc]))
print("pair defs keys:", list(b["pairs"].keys())[:30])
for k, v in b["pairs"].items():
    print("PAIR", k, {kk: v.get(kk) for kk in ("pairs","both","first_only","second_only","neither","restored","device_saving","disjoint")})
