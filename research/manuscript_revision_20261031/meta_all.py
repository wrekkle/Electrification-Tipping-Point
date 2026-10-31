# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"literature","index.json"),encoding="utf-8"))
for it in d["items"]:
    if it["id"] in ("M06","M07","M08","M18","M10"):
        print(it["id"],"|",it.get("authors"),"|",it.get("year"),"|",it.get("venue"),"|",it.get("title"),"|",it.get("version"))
