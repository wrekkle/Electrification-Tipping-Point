# -*- coding: utf-8 -*-
import json, os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"research","round6_20261031","a_info","q2_info_regimes.json"),encoding="utf-8"))
print("DELTA", json.dumps(d["delta_k_info"],ensure_ascii=False,indent=1)[:4000])
print("SCOPE", json.dumps(d["scope"],ensure_ascii=False)[:800])
