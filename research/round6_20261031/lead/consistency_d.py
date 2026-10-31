# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"))
paras = [p.text.strip() for p in doc.paragraphs]
for i in list(range(0, 6)) + list(range(58, 122)):
    if i < len(paras) and paras[i]:
        print("[%d] %s" % (i, paras[i][:1400]))
        print("---")
