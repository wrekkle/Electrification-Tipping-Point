
# -*- coding: utf-8 -*-
"""Final table-header polish for rev4."""
import os
from docx import Document
from docx.shared import Pt, Inches
ROOT = r"C:\Projects\停车场充电桩优化方案"
PATH = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")
doc = Document(PATH)
for table in doc.tables:
    if table.rows[0].cells[0].text.strip() != "Rule pair":
        continue
    labels = ["Rule pair", "Scen.", "Pairs", "Both", "First", "Second", "None", "Rest.", "Small.", "Disj."]
    for cell, label in zip(table.rows[0].cells, labels):
        cell.text = label
    table.autofit = False
    table.allow_autofit = False
    widths = [Inches(1.45), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42), Inches(0.42)]
    for i, w in enumerate(widths):
        table.columns[i].width = w
        for cell in table.columns[i].cells:
            cell.width = w
    for ri, row in enumerate(table.rows):
        for cell in row.cells:
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(7.5 if ri == 0 else 8)
doc.save(PATH)
print("SAVED")
