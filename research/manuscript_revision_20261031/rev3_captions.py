# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=list(doc.paragraphs)
print("CAPTIONS")
for i,p in enumerate(ps):
    if p.style.name=="Caption" or p.text.strip().startswith(("Table ","Fig.")):
        print("[%d] %s | %s" % (i,p.style.name,p.text.strip()[:300]))
print("TABLES")
for ti,t in enumerate(doc.tables):
    print("TABLE_OBJ",ti,"rows",len(t.rows),"cols",len(t.columns),"first", " || ".join(c.text.strip() for c in t.rows[0].cells)[:250])
