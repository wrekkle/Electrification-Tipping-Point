# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
sup = []
for pi, p in enumerate(doc.paragraphs):
    for ri, r in enumerate(p.runs):
        if r.font.superscript:
            sup.append((pi, ri, r.text))
print("SUP_COUNT", len(sup))
print(sup[:40])
print("PARA15_RUNS", [(r.text, r.font.superscript) for r in doc.paragraphs[15].runs][:20])
# reference paragraphs: find "References" heading and following 3
for i, p in enumerate(doc.paragraphs):
    if p.text.strip().lower() == "references":
        print("REF_HEAD", i)
        for j in range(i+1, i+4):
            print(j, [ (r.text, r.font.superscript) for r in doc.paragraphs[j].runs][:8])
        break
