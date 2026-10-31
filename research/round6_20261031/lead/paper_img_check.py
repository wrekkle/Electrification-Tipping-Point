# -*- coding: utf-8 -*-
import re
from docx import Document
from docx.oxml.ns import qn
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
paras = doc.paragraphs
full = "\n".join(p.text for p in paras)
print("FIG_REFS:", {n: len(re.findall(r"(?:Fig\.?|Figure)\s*" + str(n) + r"\b", full)) for n in range(1, 10)})
print("IMAGE PARAS:")
for i, p in enumerate(paras):
    if p._p.findall(".//" + qn("w:drawing")):
        prev = paras[i-1].text.strip()[:80] if i else ""
        nxt = paras[i+1].text.strip()[:80] if i+1 < len(paras) else ""
        print(i, "| prev:", prev, "| this:", p.text.strip()[:60], "| next:", nxt)
print("CAPS:")
for i, p in enumerate(paras):
    t = p.text.strip()
    if re.match(r"^(Fig\.|Table)\s*\d", t):
        print(i, "|", t[:100])
