# -*- coding: utf-8 -*-
import os, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
p = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
doc = Document(p)
paras = [x.text.strip() for x in doc.paragraphs]
print("N", len(paras))
print("TITLE", paras[0])
print("ABSTRACT", paras[3][:2200])
keys = ["value of information", "specific signal-aware", "shared rule restores", "restores admissibility",
        "smaller count", "dedicated vs shared", "shared vs shared", "within the enumerated", "0–40", "0-40",
        "proof in Supplementary", "mirror coupling", "dominance", "second experiment", "feasible-set experiment",
        "two smaller counts", "same lot-seed", "TPE1376", "interval"]
for kw in keys:
    hits = [(i, t) for i, t in enumerate(paras) if kw.lower() in t.lower()]
    print("KW[%s] %d" % (kw, len(hits)))
    for i, t in hits[:4]:
        print("   [%d] %s" % (i, t[:420]))
print("=== TABLE 4 ===")
for ti, tbl in enumerate(doc.tables):
    first = " | ".join(c.text.strip() for c in tbl.rows[0].cells)
    if "Rule pair" in first:
        print("IDX", ti)
        for row in tbl.rows:
            print("  ", " | ".join(c.text.strip() for c in row.cells))
