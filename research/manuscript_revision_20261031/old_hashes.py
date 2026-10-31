# -*- coding: utf-8 -*-
import hashlib,os
ROOT="C:/Projects/停车场充电桩优化方案"
files=["main_paper/Electrification tipping point_manuscript 202603submit.docx",
"paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx",
"paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx",
"paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round6.docx",
"paper/draft/Electrification_tipping_point_v2_draft_2026-10-30_round5.docx",
"paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx"]
for f in files:
    p=os.path.join(ROOT,f)
    if os.path.exists(p): print(f,hashlib.sha256(open(p,"rb").read()).hexdigest(),os.path.getsize(p))
    else: print("MISSING",f)
