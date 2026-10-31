
# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
PATH = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx")
doc = Document(PATH)
for p in doc.paragraphs:
    if p.text.strip().startswith("Citation check:"):
        p.text = "Citation check: the manuscript cites 76 of its 76 listed references and lists no reference that is never cited, with no number outside the range. Pending production strings are zero. The residual limits of this round are listed in the main text and in the run log: no pixel-level comparison against a journal template, and the appendix of M18 was not obtained; the M10 author list was completed from the first page of the TU/e fulltext."
doc.save(PATH)
print("SAVED")
