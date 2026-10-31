# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
for i,p in enumerate(ps):
    t=p.text.strip()
    if not t: continue
    if 0<=i<=6 or 60<=i<=120:
        print("[%d] %s | %s" % (i,p.style.name,t[:260]))
