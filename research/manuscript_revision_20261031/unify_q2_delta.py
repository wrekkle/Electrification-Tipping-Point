
# -*- coding: utf-8 -*-
import os, re
from docx import Document
ROOT = "C:/Projects/停车场充电桩优化方案"
MAIN = os.path.join(ROOT, "paper/draft/Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
doc = Document(MAIN)
for p in doc.paragraphs:
    if p.text.strip().startswith("Public parking that serves both electric vehicles"):
        p.text = p.text.replace("the table defines the change as k(I1) - k(I0)", "the table defines Delta k as k(I1) - k(I0)")
    if p.text.strip().startswith("Table 3 Smallest admissible integer count"):
        p.text = p.text.replace("Change = k(I1) - k(I0)", "Delta k = k(I1) - k(I0)")
    if p.text.strip().startswith("Note. The two conditions replay"):
        p.text = p.text.replace("the change is a difference", "the difference is a difference")
doc.save(MAIN)
print("MAIN_SAVED")
