# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
for i,p in enumerate(ps):
    t=p.text
    for term in ["socially preferable","two of the eight","v1 accounting"]:
        if term in t:
            print("TERM",repr(term),"PARA",i, "|", t[:900])
