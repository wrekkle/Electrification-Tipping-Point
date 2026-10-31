# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"research/round6_20261031/b_feasible/q3_feasible_sets.json"),encoding="utf-8"))
for name in ["REF|A|B","REF|A|C","REF|A|D","REF|B|C","REF|B|D","REF|C|D"]:
    p=d["pairs"][name]
    print(name,"pairs",p["pairs"],"restored",p["restoration"],"smaller",p["device_saving"],"same_k_improve",p["same_k_improvement"],"same_k_worse",p["same_k_worse"],"disjoint",p["both_disjoint"])
