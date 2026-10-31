# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"research/round6_20261031/b_feasible/q3_feasible_sets.json"),encoding="utf-8"))
print("PAIR KEYS",list(d["pairs"].keys()))
for k,v in d["pairs"].items():
    print("PAIR",k,json.dumps(v,ensure_ascii=False)[:2500])
    break
print("SET0",json.dumps(d["sets"][0],ensure_ascii=False,indent=1)[:2200])
