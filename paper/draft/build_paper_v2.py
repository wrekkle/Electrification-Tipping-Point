
# -*- coding: utf-8 -*-
"""Build v2 draft: clone submitted manuscript, insert literature-backed blocks, append refs."""
import argparse, copy, json, os, re, shutil
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt

from paper_v2_content import REFS, ABS_ADD, BLOCKS, CIT  # noqa: E402
from omml_math import equation  # noqa: E402

SRC = r"main_paper\Electrification tipping point_manuscript 202603submit.docx"
BAK = r"paper\draft\backup\Electrification_tipping_point_manuscript_202603submit_backup_2026-10-29.docx"
OUT = r"paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx"
MAN = None  # 只在 --manifest 显式给出时写清单，避免覆盖 2026-10-29 的历史清单
_ap = argparse.ArgumentParser(description="Build the v2 working draft from the frozen submission manuscript.")
_ap.add_argument("--out", default=OUT)
_ap.add_argument("--manifest", default=MAN)
_ap.add_argument("--force", action="store_true", help="allow overwriting an existing output file")
_args = _ap.parse_args()
if os.path.abspath(_args.out) == os.path.abspath(SRC):
    raise SystemExit("refuse to overwrite the frozen submission: " + SRC)
if os.path.exists(_args.out) and not _args.force:
    raise SystemExit("output exists, pass --force to overwrite: " + _args.out)
OUT = _args.out
MAN = _args.manifest

os.makedirs(os.path.dirname(BAK), exist_ok=True)
if not os.path.exists(BAK):
    shutil.copy2(SRC, BAK)
    print("BACKUP created:", BAK, os.path.getsize(BAK))
else:
    print("BACKUP exists:", BAK)





doc = Document(SRC)

def find_para(kind, text):
    for p in doc.paragraphs:
        st = p.style.name
        if kind == "h1" and st != "Heading 1": continue
        if kind == "h2" and st != "Heading 2": continue
        if kind == "p" and st not in ("Normal",): continue
        if p.text.strip().startswith(text):
            return p
    raise SystemExit("anchor not found: %s %s" % (kind, text))

body_t = find_para("p", "Our findings indicate that charging pile planning")
h2_t = find_para("h2", "Sensitivity analysis")
h1_t = find_para("h1", "Discussion")
bib_t = None
for p in doc.paragraphs:
    if p.style.name == "Bibliography" and p.text.strip():
        bib_t = p; break

def rpr_of(p):
    for r in p.runs:
        if r._r.find(qn("w:rPr")) is not None:
            return copy.deepcopy(r._r.find(qn("w:rPr")))
    return None

body_rpr = rpr_of(body_t)
h2_rpr = rpr_of(h2_t)
bib_rpr = rpr_of(bib_t)

def make_el(tmpl_p, tmpl_rpr, segments):
    el = copy.deepcopy(tmpl_p._p)
    for ch in list(el):
        if ch.tag != qn("w:pPr"):
            el.remove(ch)
    for text, sup in segments:
        r = OxmlElement("w:r")
        if tmpl_rpr is not None:
            rp = copy.deepcopy(tmpl_rpr)
            r.append(rp)
        if sup:
            rp = r.find(qn("w:rPr"))
            if rp is None:
                rp = OxmlElement("w:rPr"); r.insert(0, rp)
            for va in rp.findall(qn("w:vertAlign")):
                rp.remove(va)
            va = OxmlElement("w:vertAlign"); va.set(qn("w:val"), "superscript"); rp.append(va)
        t = OxmlElement("w:t"); t.text = text
        t.set(qn("xml:space"), "preserve")
        r.append(t)
        el.append(r)
    return el

def make_table(spec):
    """Build a real Word table (Table Grid) from a spec dict and return its XML element."""
    header, rows = spec["header"], spec["rows"]
    widths = spec.get("widths") or [1.0] * len(header)
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    def put(cell, text, bold=False):
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        run.font.size = Pt(8)
        run.bold = bold
    for j, txt in enumerate(header):
        put(t.cell(0, j), txt, True)
    for i, row in enumerate(rows, start=1):
        for j, txt in enumerate(row):
            put(t.cell(i, j), txt)
    for j, w in enumerate(widths):
        t.columns[j].width = Inches(w)
        for cell in t.columns[j].cells:
            cell.width = Inches(w)
    trPr = t.rows[0]._tr.get_or_add_trPr()
    trPr.append(OxmlElement("w:tblHeader"))          # 跨页重复表头
    for row in t.rows:
        row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
    return t._tbl


PAGE_TEXT_WIDTH = 8306  # A4 text width in twips (11906 - 1800 - 1800)


def make_math_para(tmpl_p, tmpl_rpr, name):
    """Numbered display equation: centre tab, OMML formula, right tab, number.

    The formula is a real Word equation object (m:oMath), so it can be edited in
    the equation editor, and the number is placed by tab stops rather than by
    padding the formula with spaces.
    """
    el = copy.deepcopy(tmpl_p._p)
    for ch in list(el):
        if ch.tag != qn("w:pPr"):
            el.remove(ch)
    pPr = el.find(qn("w:pPr"))
    tabs = OxmlElement("w:tabs")
    ctab = OxmlElement("w:tab")
    ctab.set(qn("w:val"), "center")
    ctab.set(qn("w:pos"), str(PAGE_TEXT_WIDTH // 2))
    tabs.append(ctab)
    rtab = OxmlElement("w:tab")
    rtab.set(qn("w:val"), "right")
    rtab.set(qn("w:pos"), str(PAGE_TEXT_WIDTH))
    tabs.append(rtab)
    order = [qn("w:spacing"), qn("w:ind"), qn("w:jc"), qn("w:rPr")]
    anchor = None
    for ch in list(pPr):
        if ch.tag in order:
            anchor = ch
            break
    if anchor is not None:
        anchor.addprevious(tabs)
    else:
        pPr.append(tabs)
    jc = pPr.find(qn("w:jc"))
    if jc is not None:
        pPr.remove(jc)

    def tab_run():
        r = OxmlElement("w:r")
        if tmpl_rpr is not None:
            r.append(copy.deepcopy(tmpl_rpr))
        r.append(OxmlElement("w:tab"))
        return r

    el.append(tab_run())
    el.append(equation(name))
    el.append(tab_run())
    num = OxmlElement("w:r")
    if tmpl_rpr is not None:
        num.append(copy.deepcopy(tmpl_rpr))
    t = OxmlElement("w:t")
    t.text = "(%s)" % name
    num.append(t)
    el.append(num)
    return el


def keep_with_next(el):
    """Mark a paragraph element to stay on the same page as the next block."""
    pPr = el.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        el.insert(0, pPr)
    pStyle = pPr.find(qn("w:pStyle"))
    kn = OxmlElement("w:keepNext")
    if pStyle is not None:
        pStyle.addnext(kn)
    else:
        pPr.insert(0, kn)


refs_existing = [p for p in doc.paragraphs if p.style.name == "Bibliography" and p.text.strip()]
BASE = len(refs_existing) + 1
print("existing numbered refs:", len(refs_existing), "| new refs start at", BASE)
order = []
num = {}
def cite_segments(text):
    segs = []
    pos = 0
    for m in CIT.finditer(text):
        if m.start() > pos:
            segs.append((text[pos:m.start()], False))
        for tok in [x.strip() for x in m.group(1).split(",")]:
            if tok not in num:
                num[tok] = BASE + len(order)
                order.append(tok)
        segs.append((",".join(str(num[x.strip()]) for x in m.group(1).split(",")), True))
        pos = m.end()
    if pos < len(text):
        segs.append((text[pos:], False))
    return segs

manifest = []
for b in BLOCKS:
    anchor = find_para(b["anchor"][0], b["anchor"][1])
    cursor = anchor._p
    inserted = []
    prev_el = None
    for kind, text in b["nodes"]:
        if kind == "table":
            if prev_el is not None and prev_el.tag == qn("w:p"):
                keep_with_next(prev_el)          # 表题与表格同页
            el = make_table(text)
        elif kind == "h2":
            el = make_el(h2_t, h2_rpr, [(text, False)])
        elif kind == "eq":
            el = make_el(body_t, body_rpr, [(text, False)])
        elif kind == "math":
            el = make_math_para(body_t, body_rpr, str(text))
        else:
            el = make_el(body_t, body_rpr, cite_segments(text))
        if b["pos"] == "before":
            cursor.addprevious(el)
        else:
            cursor.addnext(el)
            cursor = el
        inserted.append((kind, text))
        prev_el = el
    manifest.append({"anchor": b["anchor"], "pos": b["pos"], "nodes": len(inserted),
                     "first": str(inserted[0][1])[:80]})

# abstract sentence
abs_p = find_para("p", "With electric vehicle (EV) proliferation")
last = [r for r in abs_p.runs if r.font.superscript is not True][-1]
print("abstract last 3 runs:", [(r.text[-20:], r.font.superscript) for r in abs_p.runs[-3:]])
new_r = copy.deepcopy(last._r)
for t in new_r.findall(qn("w:t")):
    new_r.remove(t)
t = OxmlElement("w:t"); t.text = ABS_ADD; t.set(qn("xml:space"), "preserve"); new_r.append(t)
abs_p._p.append(new_r)

# append references
refs_all = [p for p in doc.paragraphs if p.style.name == "Bibliography"]
last_nonempty = [p for p in refs_all if p.text.strip()][-1]
target = last_nonempty._p
for tok in order:
    el = make_el(bib_t, bib_rpr, [(REFS[tok], False)])
    target.addnext(el)
    target = el

doc.save(OUT)

# verify
v = Document(OUT)
paras = v.paragraphs
bib = [p for p in paras if p.style.name == "Bibliography" and p.text.strip()]
words = lambda s: len(re.findall(r"[A-Za-z]+", s))
added_words = sum(words(t) for b in BLOCKS for k, t in b["nodes"] if k in ("p", "eq"))
orig_words = sum(words(p.text) for p in Document(SRC).paragraphs)
print("saved:", OUT, os.path.getsize(OUT))
print("paragraphs: before", len(Document(SRC).paragraphs), "after", len(paras))
print("references: before 41, after", len(bib))
print("citation map:", json.dumps(num, ensure_ascii=False))
print("ref order:", order)
print("added body words:", added_words, "| total words:", sum(words(p.text) for p in paras), "| original:", orig_words)
heads = [p.text for p in paras if p.style.name in ("Heading 1", "Heading 2")]
print("headings:", json.dumps(heads, ensure_ascii=False))
missing = [t for t in REFS if t not in num]
print("refs not cited:", missing)
print("tables: before", len(Document(SRC).tables), "after", len(v.tables))
if MAN:
    os.makedirs(os.path.dirname(MAN) or ".", exist_ok=True)
    json.dump({"citation_map": num, "order": order, "blocks": manifest,
               "added_body_words": added_words, "total_words_after": sum(words(p.text) for p in paras),
               "paragraphs_after": len(paras), "references_after": len(bib),
               "tables_after": len(v.tables)},
              open(MAN, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("manifest:", MAN)
else:
    print("manifest: not written (pass --manifest to write it)")