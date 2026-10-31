# -*- coding: utf-8 -*-
import json, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
texts = [p.text for p in doc.paragraphs]
full = "\n".join(texts)
print("BUILD_MANIFEST:", json.dumps(json.load(open(ROOT + r"\research\round6_20261031\c_paper\build_manifest.json", encoding="utf-8")), ensure_ascii=False)[:800])
st = open(ROOT + r"\research\round6_20261031\c_paper\paper_stats.json", encoding="utf-8").read()
print("STATS_HEAD:", st[:600].replace("\n", " | "))
for pat in ["placeholder", "proves", "theorem", "social optimum", "identified as"]:
    for m in re.finditer(pat, full, re.I):
        s = max(0, m.start()-180); e = min(len(full), m.end()+180)
        print("CTX[%s]:" % pat, full[s:e].replace("\n", " ")[:400])
# refs count
paras = [p.text.strip() for p in doc.paragraphs]
try:
    ri = [i for i, t in enumerate(paras) if t == "References"][0]
except IndexError:
    ri = None
tail = [t for t in paras[ri+1:] if t]
entries = [t for t in tail if re.match(r"^[A-Z][^.]{2,}\b(19|20)\d{2}\b", t) or re.match(r"^\d+\.", t)]
print("REF_TAIL_N:", len(tail), "REF_ENTRIES_HEUR:", len(entries))
# numeric claims sentences
for key in ["656", "660", "840", "677", "152", "124", "139", "437", "143", "61", "98", "3,456", "3456", "8 of 8", "all eight"]:
    for m in re.finditer(re.escape(key), full):
        s = max(0, m.start()-140); e = min(len(full), m.end()+140)
        print("NUM[%s]:" % key, full[s:e].replace("\n", " ")[:330]); break
# section paragraphs between headings
idx = [i for i, t in enumerate(paras) if t in ("Why an extra equipped bay can lower ICEV parking failures", "What a charging-intention signal changes", "Shape of the feasible-configuration set")]
for i in idx[:3]:
    print("SEC:", paras[i], "->", " | ".join(paras[i+1:i+4])[:500])
