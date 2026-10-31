# -*- coding: utf-8 -*-
"""Build the round-6 supplementary docx from supplementary_round6_content.py + tables_si.json."""
import io, json, os, sys, hashlib
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "paper", "draft")
CP = os.path.join(ROOT, "research", "round6_20261031", "c_paper")
sys.path.insert(0, D)
import supplementary_round6_content as C

OUT = os.path.join(D, "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx")
TA = json.load(io.open(os.path.join(CP, "tables_si.json"), encoding="utf-8"))
TABLES = TA["tables"]

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

def set_font(run, size=11, bold=False, italic=False):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rFonts.set(qn(a), "Times New Roman")

def para(doc, text, size=11, bold=False, italic=False, align="just", before=0, after=6,
         spacing=1.15, keep=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = spacing
    if align == "just":
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    elif align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if keep:
        pf.keep_with_next = True
    r = p.add_run(text)
    set_font(r, size, bold, italic)
    return p

def heading(doc, text):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = Pt(14)
    pf.space_after = Pt(6)
    pf.keep_with_next = True
    r = p.add_run(text)
    set_font(r, 13, bold=True)

def cell_text(cell, text, bold=False, size=8.5):
    cell.text = ""
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    r = p.add_run(text)
    set_font(r, size, bold)

def add_table(doc, t):
    header = t["header"]; rows = t["rows"]; widths = t["widths"]
    table = doc.add_table(rows=len(rows) + 1, cols=len(header))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    cant = t.get("cant_split", True)
    # header
    tr = table.rows[0]._tr
    trPr = tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader"); trPr.append(th)
    for j, h in enumerate(header):
        cell_text(table.rows[0].cells[j], h, bold=True)
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            cell_text(table.rows[i].cells[j], v)
        if cant:
            trPr = table.rows[i]._tr.get_or_add_trPr()
            cs = OxmlElement("w:cantSplit"); trPr.append(cs)
    for j, w in enumerate(widths):
        table.columns[j].width = Inches(w)
        for row in table.rows:
            row.cells[j].width = Inches(w)
    return table

def footer_page_numbers(doc):
    sec = doc.sections[0]
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("S")
    set_font(r, 9)
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve"); instr.text = " PAGE "
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "end")
    run = p.add_run()
    run._r.append(fld1); run._r.append(instr); run._r.append(fld2)
    set_font(run, 9)

def main():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, attr, Cm(2.54))
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(11)
    footer_page_numbers(doc)

    para(doc, C.TITLE, size=15, bold=True, align="left", after=8, spacing=1.1)
    para(doc, C.SUBTITLE, size=9.5, italic=True, after=14)

    for section in C.SECTIONS:
        heading(doc, section["title"])
        for kind, payload in section["blocks"]:
            if kind == "p":
                para(doc, payload)
            elif kind == "pagebreak":
                p = doc.add_paragraph()
                p.paragraph_format.space_after = Pt(0)
                p.add_run().add_break(WD_BREAK.PAGE)
            elif kind == "caption":
                para(doc, payload, size=9, bold=True, align="left", before=8, after=3, spacing=1.0, keep=True)
            elif kind == "table":
                t = TABLES[payload]
                add_table(doc, t)
            elif kind == "note":
                notes = TABLES[payload]["notes"]
                para(doc, " ".join(notes), size=8.5, align="left", before=3, after=10, spacing=1.0)
    doc.save(OUT)
    n_paras = len(doc.paragraphs)
    n_tables = len(doc.tables)
    words = sum(len(p.text.split()) for p in doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                words += len(c.text.split())
    manifest = {
        "output": {"path": os.path.relpath(OUT, ROOT).replace("\\", "/"), "bytes": os.path.getsize(OUT),
                   "sha256": sha(OUT)},
        "content_module_sha256": sha(os.path.join(D, "supplementary_round6_content.py")),
        "tables_sha256": sha(os.path.join(CP, "tables_si.json")),
        "checks": {"paragraphs": n_paras, "tables": n_tables, "words_all_paragraphs_cells": words,
                   "sections": len(C.SECTIONS)},
        "inputs": TA["inputs"],
    }
    with io.open(os.path.join(CP, "build_manifest_supplement.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    print(json.dumps(manifest["checks"], ensure_ascii=False))
    print("saved:", OUT, manifest["output"]["bytes"])

main()
