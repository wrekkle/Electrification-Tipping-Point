# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=[p.text.strip() for p in doc.paragraphs]
print("=== NEW RESULTS 68-80 ===")
for i in range(68,81):
    if ps[i]: print("[%d] %s" % (i,ps[i]))
print("=== TABLES ===")
for ti,t in enumerate(doc.tables):
    txt=" | ".join(" / ".join(c.text.strip() for c in row.cells) for row in t.rows)
    if "TPE0008" in txt or "A vs B" in txt or "A|B" in txt:
        print("TABLE",ti,"rows",len(t.rows),"cols",len(t.columns))
        for row in t.rows: print(" || ".join(c.text.strip() for c in row.cells))
