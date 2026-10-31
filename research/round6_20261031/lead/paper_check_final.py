# -*- coding: utf-8 -*-
import json, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
page = ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx"
doc = Document(page)
paras = [p.text for p in doc.paragraphs]
full = "\n".join(paras)
print("paras:", len(paras), "tables:", len(doc.tables), "images:", len(doc.inline_shapes))
print("PENDING:", {s: full.count(s) for s in ["placeholder", "to be produced", "To be drawn", "to be reassigned", "reassign", "TBD"]})
print("BIB:", sum(1 for p in doc.paragraphs if p.style.name == "Bibliography"))
caps = [(i, t.strip()) for i, t in enumerate(paras) if re.match(r"^(Fig\.|Figure|Table)\s*\d", t.strip())]
for i, t in caps: print("CAP", i, "|", t[:120])
print("BODY_REFS_FIG:", {n: len(re.findall(r"(?:Fig\.?|Figure)\s*" + str(n) + r"\b", full)) for n in range(1, 7)})
print("BODY_REFS_TAB:", {n: len(re.findall(r"Table\s*" + str(n) + r"\b", full)) for n in range(1, 7)})
print("SOCIAL:", full.lower().count("social optimum"), "proves:", full.lower().count("proves"), "theorem:", full.lower().count("theorem"))
print("FIRST:", paras[0][:150])
print("ABS_HAS_656:", "656" in full, "ABS_143:", "143" in full)
