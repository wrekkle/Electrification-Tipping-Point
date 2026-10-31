# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=[p.text.strip() for p in doc.paragraphs]
for i in range(94,123):
    if ps[i]: print("[%d] %s" % (i,ps[i]))
