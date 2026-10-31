# -*- coding: utf-8 -*-
import os, re
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=[p.text.strip() for p in doc.paragraphs]
print("=== ABSTRACT 0-6 ===")
for i in range(0,7):
    if ps[i]: print("[%d] %s" % (i,ps[i]))
print("=== INTRO 7-23 ===")
for i in range(7,24):
    if ps[i]: print("[%d] %s" % (i,ps[i][:1600]))
print("=== OLD RESULTS 26-67 (first 260 chars each) ===")
for i in range(26,68):
    if ps[i]: print("[%d] %s" % (i,ps[i][:260]))
