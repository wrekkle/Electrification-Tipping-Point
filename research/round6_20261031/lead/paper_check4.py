# -*- coding: utf-8 -*-
import json, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
b = json.load(open(ROOT + r"\research\round6_20261031\b_feasible\q3_feasible_sets.json", encoding="utf-8"))
agg = {"pairs": 0, "both": 0, "only_first": 0, "only_second": 0, "neither": 0, "restoration": 0,
       "device_saving": 0, "same_k_improvement": 0, "same_k_worse": 0, "both_disjoint": 0, "both_partial_overlap": 0}
for v in b["pairs"].values():
    for k in agg:
        agg[k] += v.get(k, 0)
print("PAIRS_AGG:", agg)
doc = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
paras = doc.paragraphs
print("BIB_COUNT:", sum(1 for p in paras if p.style.name == "Bibliography"))
full = "\n".join(p.text for p in paras)
print("BODY_REFS_FIG:", {n: len(re.findall(r"(?:Fig\.?|Figure)\s*" + str(n) + r"\b", full)) for n in range(1, 10)})
print("BODY_REFS_TAB:", {n: len(re.findall(r"(?:Table)\s*" + str(n) + r"\b", full)) for n in range(1, 19)})
caps = [(i, p.text.strip()) for i, p in enumerate(paras) if re.match(r"^(Fig\.|Figure|Table)\s*\d", p.text.strip())]
for i, t in caps:
    print("CAP", i, "|", t[:110])
print("PENDING_STRINGS:", {s: full.count(s) for s in ["placeholder", "to be produced", "To be drawn", "to be reassigned", "provisional"]})
# base draft comparison
base = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-30.docx")
bt = "\n".join(p.text for p in base.paragraphs)
print("BASE_PENDING:", {s: bt.count(s) for s in ["placeholder", "to be produced", "To be drawn", "to be reassigned"]})
