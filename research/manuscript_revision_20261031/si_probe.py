# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx"))
for i,p in enumerate(doc.paragraphs):
    t=p.text.strip()
    if t: print("[%d] %s | %s" % (i,p.style.name,t[:1200]))
