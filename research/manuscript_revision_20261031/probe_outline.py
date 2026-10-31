# -*- coding: utf-8 -*-
import os, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
p = os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx")
doc = Document(p)
words = lambda s: len(re.findall(r"[A-Za-z][A-Za-z'’\-]*", s))
total=0
print("OUTLINE")
for i, para in enumerate(doc.paragraphs):
    t = para.text.strip()
    w = words(t)
    total += w
    st = para.style.name
    if st.startswith("Heading") or (t and (t.isupper() or re.match(r"^(Abstract|Keywords|[0-9]+(\.[0-9]+)?\s+[A-Z])", t))):
        print("%4d [%s] w=%d | %s" % (i, st, w, t[:120]))
print("TOTAL_BODY_WORDS", total)
# tables words
tw=0
for ti,tbl in enumerate(doc.tables):
    w=sum(words(c.text) for r in tbl.rows for c in r.cells)
    tw+=w
    print("TABLE",ti,"rows",len(tbl.rows),"words",w,"first"," | ".join(c.text.strip()[:30] for c in tbl.rows[0].cells)[:100])
print("TABLE_WORDS",tw)
