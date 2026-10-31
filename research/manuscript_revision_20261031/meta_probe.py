# -*- coding: utf-8 -*-
import pymupdf, os
ROOT=r"C:\Projects\停车场充电桩优化方案"
for path in [os.path.join(ROOT,"papers","electrification-math","M18_joint-operation-parking-charging_TRD2025.pdf"),
             os.path.join(ROOT,"research","official_data_20261031","ev_behavior","raw","M10_TUE_fulltext.pdf")]:
    d=pymupdf.open(path)
    print("FILE",os.path.basename(path),"PAGES",d.page_count)
    print(d[0].get_text()[:2500])
    print("---")
