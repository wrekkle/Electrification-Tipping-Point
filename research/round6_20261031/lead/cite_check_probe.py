# -*- coding: utf-8 -*-
import os, re, collections
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
path = os.path.join(ROOT, "paper", "draft", "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
doc = Document(path)
paras = doc.paragraphs
ref_i = next(i for i,p in enumerate(paras) if p.text.strip().lower() == "references")
body = paras[:ref_i]
refs = [p.text.strip() for p in paras[ref_i+1:] if p.text.strip()]
print("BODY_PARAS", len(body), "REFS", len(refs), "REF_FIRST", refs[0][:60], "REF_LAST", refs[-1][:60])
sup_text = []
for pi, p in enumerate(body):
    s = "".join(r.text for r in p.runs if r.font.superscript)
    if s.strip(): sup_text.append((pi, s))
print("PARAS_WITH_SUP", len(sup_text))
print("FIRST20", sup_text[:20])
nums = collections.Counter()
for pi, s in sup_text:
    for m in re.finditer(r"\d+", s):
        nums[int(m.group())] += 1
print("UNIQUE", len(nums), "MAX", max(nums) if nums else None, "MIN", min(nums) if nums else None)
print("OUT_OF_RANGE", sorted(n for n in nums if n > 76)[:20])
missing = [n for n in range(1, 77) if n not in nums]
print("MISSING_1_76", missing)
print("TOP", nums.most_common(15))
