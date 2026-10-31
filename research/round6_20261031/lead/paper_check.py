# -*- coding: utf-8 -*-
import json, re, sys
from docx import Document
DOCX = r"C:\Projects\停车场充电桩优化方案\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"
doc = Document(DOCX)
texts = [p.text for p in doc.paragraphs]
full = "\n".join(texts)
print("paragraphs:", len(doc.paragraphs), "tables:", len(doc.tables), "sections:", len(doc.sections))
print("inline_shapes:", len(doc.inline_shapes))
# headings
heads = [(p.style.name, p.text.strip()) for p in doc.paragraphs if p.style.name.lower().startswith("heading") and p.text.strip()]
print("HEADINGS:")
for s, t in heads[:40]:
    print(" ", s, "|", t[:100])
# title + abstract start
print("FIRST_PARAS:", [t[:120] for t in texts[:6] if t.strip()])
forbidden = [r"\bAgent\b", r"round\s*\d", r"task[- ]\d", r"第[一二三四五六]轮", r"TODO", r"UNVERIFIED", r"TBD", r"placeholder", r"\[insert", r"\?\?"]
print("FORBIDDEN:", {pat: len(re.findall(pat, full)) for pat in forbidden})
overclaim = ["proves", "theorem", "socially optimal", "social optimum", "always reduces", "distributionally equivalent", "observational equivalence", "identified as"]
low = full.lower()
print("OVERCLAIM:", {w: low.count(w) for w in overclaim})
keys = ["656", "8/8", "9.5", "143", "26", "61", "98", "660", "124", "139", "437", "840", "677", "152", "3456", "66", "310", "51", "780", "765"]
print("NUMBERS:", {k: len(re.findall(re.escape(k), full)) for k in keys})
# references
ref_idx = None
for i, t in enumerate(texts):
    if t.strip().lower() == "references":
        ref_idx = i
if ref_idx is not None:
    tail = [t.strip() for t in texts[ref_idx+1:] if t.strip()]
    print("REFERENCES:", len(tail), "first:", tail[:2], "last:", tail[-2:])
# tables: captions and headers
for i, tb in enumerate(doc.tables):
    hdr = [c.text.strip()[:26] for c in tb.rows[0].cells]
    print("TABLE", i+1, "rows=", len(tb.rows), "cols=", len(tb.columns), "hdr=", hdr)
# equations count
xml = doc.element.xml
print("oMath_count:", xml.count("<m:oMath"))
