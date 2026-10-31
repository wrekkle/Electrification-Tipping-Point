# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
for f in ["research/round6_20261031/b_feasible/q3_feasible_sets.json","research/round6_20261031/lead/q3_scan.json"]:
    d=json.load(open(os.path.join(ROOT,f),encoding="utf-8"))
    print("FILE",f,"TYPE",type(d).__name__)
    if isinstance(d,dict):
        print("KEYS",list(d.keys())[:30])
        for k,v in list(d.items())[:5]:
            print(k,type(v).__name__,json.dumps(v,ensure_ascii=False)[:500])
    elif isinstance(d,list):
        print("LEN",len(d),"FIRST",json.dumps(d[0],ensure_ascii=False)[:1000])
