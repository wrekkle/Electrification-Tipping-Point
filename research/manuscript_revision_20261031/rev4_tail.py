# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
for i in [34,39,40,45,49,52,58,60,64,65]:
    print("=== [%d] ===" % i); print(ps[i].text.strip())
print("=== TABLE Q2 ===")
for t in doc.tables:
    if t.rows and t.rows[0].cells[0].text.strip()=="Lot":
        for row in t.rows: print(" || ".join(c.text.strip() for c in row.cells))
