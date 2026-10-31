# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
for i in [26,27,30,32,34,38,39,40,44,45,49,50,52,53,54,55,57,58,59,61,62,63,64,65,72,73,74,89,90]:
    print("=== [%d] %s ===" % (i,ps[i].style.name)); print(ps[i].text.strip())
