
# -*- coding: utf-8 -*-
"""Round-7 rev4 builder: delete historical v1 sections from rev3, retain new results.
The first pass is structural; text edits are added in a second pass.
"""
import os, shutil
from docx import Document

ROOT = r"C:\Projects\停车场充电桩优化方案"
SRC = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx")
DST = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx")

doc = Document(SRC)
paras = list(doc.paragraphs)

def starts(p, s):
    return p.text.strip().startswith(s)

def remove_para(p):
    el = p._element
    el.getparent().remove(el)

def remove_between(start_pred, end_pred):
    """Remove paragraphs from first start_pred through before first end_pred (document order)."""
    start_i = None
    end_i = None
    for i, p in enumerate(paras):
        if start_i is None and start_pred(p):
            start_i = i
            continue
        if start_i is not None and end_pred(p):
            end_i = i
            break
    if start_i is None:
        raise RuntimeError("start not found")
    if end_i is None:
        raise RuntimeError("end not found")
    for p in paras[start_i:end_i]:
        remove_para(p)
    return start_i, end_i

# 1. Old v1 Results: v1 intro + all five old result subsections, up to the new first result.
remove_between(lambda p: starts(p, "The results in this section were computed under the v1 accounting"),
               lambda p: starts(p, "Integer provision under joint service constraints"))
# 2. Old v1 Optimization Framework in Methods, through before Data.
remove_between(lambda p: starts(p, "Optimization Framework"),
               lambda p: starts(p, "Data, calibration, and scenario transfer"))
# 3. Old solution-method paragraph left between Table 5 and Arrivals.
for p in paras:
    if starts(p, "Optimization problems can be solved using various methods"):
        remove_para(p)
# 4. Old evaluation protocol + all cost-accounting subsections + Table 6, through before References.
remove_between(lambda p: starts(p, "Evaluation protocol, statistical reliability, and risk measures"),
               lambda p: starts(p, "References"))
# 5. Old v1 discussion (paragraphs 95-108) through before 'One assumption carries more weight'.
remove_between(lambda p: starts(p, "To address the PREI problem"),
               lambda p: starts(p, "One assumption carries more weight"))

# 6. Remove old equation tables (first cell empty) and Table 6 (first cell Symbol); keep five data tables.
for table in list(doc.tables):
    first = table.rows[0].cells[0].text.strip() if table.rows and table.columns else ""
    if first == "" or first == "Symbol":
        el = table._tbl
        el.getparent().remove(el)

doc.save(DST)
print("SAVED", DST)
print("PARAS", len(doc.paragraphs), "TABLES", len(doc.tables))
print("FIRST_AFTER_RESULTS", [p.text.strip()[:100] for p in doc.paragraphs if p.style.name.startswith("Heading")][:20])
