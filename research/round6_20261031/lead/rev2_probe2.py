# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
p = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
doc = Document(p)
paras = [x.text.strip() for x in doc.paragraphs]
for i in list(range(86, 94)) + list(range(114, 123)):
    print("[%d] %s" % (i, paras[i]))
    print("---")
for ti, tbl in enumerate(doc.tables):
    first = " | ".join(c.text.strip() for c in tbl.rows[0].cells)
    if "Rule pair" in first:
        print("TABLE4_IDX", ti)
        for row in tbl.rows:
            print("  ", " | ".join(c.text.strip().replace("\n"," ") for c in row.cells))
print("MIRROR", [i for i,t in enumerate(paras) if "mirror" in t.lower()])
print("PENDING", {w: sum(t.lower().count(w) for t in paras) for w in ("placeholder","to be produced","to be drawn","to be reassigned","tbd","todo")})
si = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx"))
h = [x.text.strip() for x in si.paragraphs if x.style.name.startswith("Heading")]
print("SI_HEADINGS", h)
print("SI_PARAS", len(si.paragraphs), "SI_TABLES", len(si.tables), "SI_IMAGES", len(si.inline_shapes))
