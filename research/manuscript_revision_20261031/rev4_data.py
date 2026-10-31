# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
for i in [68,69,70,72,73,74,89,90,92,93]:
    print("=== [%d] ===" % i); print(ps[i].text.strip())
