# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
paras = [p.text.strip() for p in doc.paragraphs]
print("N_SEG", len(paras))
for i in [3, 4] + list(range(82, 96)) + list(range(108, 126)) + list(range(len(paras)-18, len(paras))):
    if 0 <= i < len(paras) and paras[i]:
        print("[%d] %s" % (i, paras[i]))
        print("---")
