
# -*- coding: utf-8 -*-
import os
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
PATH = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx")
doc = Document(PATH)
for p in doc.paragraphs:
    if p.text.strip().startswith("The heuristic reaches a smaller minimal count in all eight paired units"):
        p.text = p.text.replace("all eight paired units", "all eight lot-seed-rule units").replace("two of the eight cells", "two rule-A cells on the two TPE0401 streams")
    if p.text.strip().startswith("Commands, interpreters and exit codes are recorded"):
        old = "the author list of one reference still incomplete and the appendix of one reference not obtained."
        new = "and the appendix of one reference not obtained; the M10 author list was completed from the first page of the TU/e fulltext."
        if old in p.text:
            p.text = p.text.replace(old, new)
        else:
            print("S6 old clause not found:", p.text[-300:])
doc.save(PATH)
print("SAVED")
