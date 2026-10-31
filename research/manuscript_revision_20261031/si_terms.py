# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT="C:/Projects/停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx"))
for i,p in enumerate(doc.paragraphs):
    if "author list" in p.text or "pixel-level" in p.text or "Citation check" in p.text:
        print(i,repr(p.text))
