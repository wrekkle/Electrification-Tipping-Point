# -*- coding: utf-8 -*-
import json, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(ROOT + r"\research\round6_20261031\b_feasible\q3_feasible_sets.json", encoding="utf-8"))
pairs = b["pairs"]
print("PAIRS_TYPE:", type(pairs), "keys:", list(pairs)[:10] if isinstance(pairs, dict) else len(pairs))
print("PAIRS_JSON:", json.dumps(pairs, ensure_ascii=False)[:1800])
doc = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
paras = doc.paragraphs
print("FIG_CAPTIONS:")
for i, p in enumerate(paras):
    t = p.text.strip()
    if re.match(r"^(Fig\.|Figure)\s*\d", t):
        print(i, "|", t[:150], "| img_near=", any(paras[j]._p.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing") for j in range(max(0,i-2), min(len(paras), i+2))))
print("TABLE_CAPS:")
for i, p in enumerate(paras):
    t = p.text.strip()
    if re.match(r"^Table\s*\d", t):
        print(i, "|", t[:160])
# refs styles
ri = [i for i, p in enumerate(paras) if p.text.strip() == "References"][0]
print("REF_STYLES:", [(p.style.name, p.text.strip()[:40]) for p in paras[ri+1:ri+8]])
print("REF_TAIL_STYLES:", [(p.style.name, p.text.strip()[:40]) for p in paras[-8:]])
