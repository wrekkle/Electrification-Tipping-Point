# -*- coding: utf-8 -*-
import os,hashlib
ROOT="C:/Projects/停车场充电桩优化方案"
for rel in ["paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx",
            "paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx"]:
    p=os.path.join(ROOT,rel); h=hashlib.sha256(open(p,"rb").read()).hexdigest()
    print(rel); print("SHA256",h); print("BYTES",os.path.getsize(p))
