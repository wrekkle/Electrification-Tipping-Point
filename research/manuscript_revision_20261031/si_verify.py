# -*- coding: utf-8 -*-
import hashlib,os
from docx import Document
p="C:/Projects/停车场充电桩优化方案/paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx"
print("SHA",hashlib.sha256(open(p,"rb").read()).hexdigest())
doc=Document(p)
for para in doc.paragraphs:
    if para.text.strip().startswith("The heuristic reaches") or para.text.strip().startswith("Citation check:"):
        print("TEXT",para.text[:700])
