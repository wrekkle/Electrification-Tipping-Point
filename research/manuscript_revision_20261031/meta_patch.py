# -*- coding: utf-8 -*-
import json
p="C:/Projects/停车场充电桩优化方案/papers/electrification-math/meta31.json"
d=json.load(open(p,encoding="utf-8"))
for it in d["items"]:
    if it["id"]=="M10":
        it["version"]="Transportmetrica B 10 (2022) 340-367; online 2021; TU/e publisher PDF held at research/official_data_20261031/ev_behavior/raw/M10_TUE_fulltext.pdf; first page and Table 3 checked; not in the M-group PDF directory."
json.dump(d,open(p,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
print("OK")
