# -*- coding: utf-8 -*-
import os,json
ROOT=r"C:\Projects\停车场充电桩优化方案"
p=os.path.join(ROOT,"repo-discipline.json")
s=open(p,encoding="utf-8").read()
print("LEN",len(s))
for line in s.splitlines():
    if "_说明" in line or "target_note" in line or "m_download_updates" in line:
        print(repr(line[:300]))
