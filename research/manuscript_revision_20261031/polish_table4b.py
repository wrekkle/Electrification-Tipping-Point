
# -*- coding: utf-8 -*-
import os
from docx import Document
from docx.shared import Inches
ROOT = r"C:\Projects\停车场充电桩优化方案"
PATH = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
doc = Document(PATH)
for table in doc.tables:
    if table.rows[0].cells[0].text.strip() != "Rule pair":
        continue
    widths = [Inches(1.2), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.52), Inches(0.52), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42)]
    table.autofit = False
    table.allow_autofit = False
    for i, w in enumerate(widths):
        table.columns[i].width = w
        for cell in table.columns[i].cells:
            cell.width = w
doc.save(PATH)
print("SAVED")
