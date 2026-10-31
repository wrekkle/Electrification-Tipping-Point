# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=list(doc.paragraphs)
for i,p in enumerate(ps):
    t=p.text.strip()
    if not t: continue
    if 120<=i<=235:
        print("[%d] %s | %s" % (i,p.style.name,t[:180]))
