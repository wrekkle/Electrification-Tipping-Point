# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"research/round6_20261031/a_info/q2_info_regimes.json"),encoding="utf-8"))
print("FIXED CELLS")
for r in d["four_categories_at_fixed_k"]: print(r)
print("COUNTS",d["four_categories"]["counts"])
print("HAND",json.dumps(d["hand_check"],ensure_ascii=False,indent=1)[:2500])
