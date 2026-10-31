# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
p = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
doc = Document(p); paras = [x.text.strip() for x in doc.paragraphs]
for i in range(68, 73):
    print("[%d] %s" % (i, paras[i])); print("---")
for kw in ("3,456", "3,456", "proved", "proposition", "assumption", "social optimum", "theorem"):
    hits = [(i,t) for i,t in enumerate(paras) if kw in t.lower()]
    print("KW", kw, len(hits))
    for i,t in hits[:4]: print("  [%d] %s" % (i, t[:300]))
# SI content
si = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx"))
print("SI_STYLES", sorted({x.style.name for x in si.paragraphs}))
for i, x in enumerate(si.paragraphs[:35]):
    if x.text.strip(): print("SI[%d][%s] %s" % (i, x.style.name, x.text.strip()[:260]))
