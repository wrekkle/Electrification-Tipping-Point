# -*- coding: utf-8 -*-
import json, re
from docx import Document
from docx.oxml.ns import qn
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(ROOT + r"\paper\draft\Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
paras = doc.paragraphs
print("IMAGE_PARAS:")
for i, p in enumerate(paras):
    if p._p.findall(".//" + qn("w:drawing")):
        print(i, "PREV:", paras[max(0,i-1)].text[:90], "|| IMG_PARA:", p.text[:90])
print("PH_CTX:")
for i, p in enumerate(paras):
    if "placeholder" in p.text:
        print(i, "|", p.text[:220])
# tables_v3 same-k keys
t = json.load(open(ROOT + r"\research\round6_20261031\c_paper\tables_v3.json", encoding="utf-8"))
print("TABLES_KEYS:", list(t["tables"].keys()))
for k, v in t["tables"].items():
    s = json.dumps(v, ensure_ascii=False)
    if "same" in s.lower() or "worse" in s.lower() or "improve" in s.lower():
        print("SAMEK_TABLE", k, v.get("title"), s[:400])
# b q3 summary keys
b = json.load(open(ROOT + r"\research\round6_20261031\b_feasible\q3_feasible_sets.json", encoding="utf-8"))
print("B_Q3_TOP:", list(b.keys()))
print("B_Q3_SUMMARY:", json.dumps(b.get("summary"), ensure_ascii=False)[:1500])
