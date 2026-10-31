# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
paras = [p.text.strip() for p in doc.paragraphs]
for i in range(115, min(len(paras), 150)):
    if paras[i]:
        print("[%d] %s" % (i, paras[i][:900]))
print("=== TABLES ===")
for ti, tbl in enumerate(doc.tables):
    if ti not in (3, 4, 5): continue
    print("TABLE_IDX", ti, "rows", len(tbl.rows))
    for r in tbl.rows[:8]:
        print(" | ".join(c.text.strip().replace("\n", " ")[:40] for c in r.cells))
