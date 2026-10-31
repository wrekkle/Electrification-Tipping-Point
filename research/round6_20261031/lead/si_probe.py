# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
si = Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx"))
ps=[p.text.strip() for p in si.paragraphs]
start=next(i for i,t in enumerate(ps) if t.startswith("S2 "))
end=next(i for i,t in enumerate(ps) if t.startswith("S3 "))
print("S2_RANGE", start, end)
for i in range(start, end):
    if ps[i]: print("[%d] %s" % (i, ps[i][:1500]))
print("=== S5 ===")
s5=next(i for i,t in enumerate(ps) if t.startswith("S5 "))
s6=next(i for i,t in enumerate(ps) if t.startswith("S6 "))
for i in range(s5, min(s6, s5+25)):
    if ps[i]: print("[%d] %s" % (i, ps[i][:700]))
