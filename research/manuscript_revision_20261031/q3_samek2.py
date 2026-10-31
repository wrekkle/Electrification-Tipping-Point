# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"research/round6_20261031/b_feasible/q3_feasible_sets.json"),encoding="utf-8"))
from collections import defaultdict
agg=defaultdict(lambda:{"pairs":0,"restoration":0,"device_saving":0,"same_k_improvement":0,"same_k_worse":0,"both_disjoint":0})
for name,p in d["pairs"].items():
    scen,a,b=name.split("|")
    key=a+"|"+b
    for f in agg[key]: agg[key][f]+=p[f]
for k,v in agg.items(): print(k,dict(v))
