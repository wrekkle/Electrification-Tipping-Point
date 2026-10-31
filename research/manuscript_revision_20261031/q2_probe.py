# -*- coding: utf-8 -*-
import json, os
ROOT=r"C:\Projects\停车场充电桩优化方案"
p=os.path.join(ROOT,"research","round6_20261031","a_info","q2_info_regimes.json")
d=json.load(open(p,encoding="utf-8"))
print("TOP_KEYS", list(d.keys()))
for k,v in d.items():
    if isinstance(v,list): print(k,"list",len(v),"sample",json.dumps(v[0],ensure_ascii=False)[:800] if v else None)
    elif isinstance(v,dict): print(k,"dict keys",list(v.keys())[:20])
    else: print(k,type(v),str(v)[:300])
