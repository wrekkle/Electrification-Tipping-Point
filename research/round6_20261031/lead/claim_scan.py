# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx"))
paras=[p.text.strip() for p in doc.paragraphs]
for kw in ("global optimum","social optimum","socially preferable","guarantee","optimal PPR","optimal solution","optimal"):
    hits=[(i,t) for i,t in enumerate(paras) if kw.lower() in t.lower()]
    print("KW[%s] %d" % (kw,len(hits)))
    for i,t in hits[:8]: print("  [%d] %s" % (i,t[:420]))
