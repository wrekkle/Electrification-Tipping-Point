# -*- coding: utf-8 -*-
import json,os
ROOT=r"C:\Projects\停车场充电桩优化方案"
d=json.load(open(os.path.join(ROOT,"literature","index.json"),encoding="utf-8"))
for it in d["items"]:
    if it["id"] in ("M18","M10"):
        print(it["id"],"year",it.get("year"),"authors",it.get("authors"),"venue",it.get("venue"),"title",it.get("title")[:80],"pdf",it.get("local_pdf"))
