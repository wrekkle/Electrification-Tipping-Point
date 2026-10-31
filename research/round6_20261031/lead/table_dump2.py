# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
for ti, tbl in enumerate(doc.tables):
    first = " | ".join(c.text.strip() for c in tbl.rows[0].cells)
    if any(x in first for x in ("Pair", "Rule pair", "Trace", "Rule", "Scenario", "Symbol")):
        print("TABLE_IDX", ti, "ROWS", len(tbl.rows), "FIRST:", first[:160])
        if "Pair" in first or "Rule pair" in first:
            for r in tbl.rows:
                print("   ", " | ".join(c.text.strip().replace("\n", " ")[:36] for c in r.cells))
