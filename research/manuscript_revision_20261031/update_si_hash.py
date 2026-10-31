
# -*- coding: utf-8 -*-
import os, hashlib
from docx import Document
ROOT = "C:/Projects/停车场充电桩优化方案"
SI = os.path.join(ROOT, "paper/draft/Electrification_tipping_point_v2_supplementary_2026-10-31_round7.docx")
doc = Document(SI)
old = "2ddff021f67e00b95af008b578167a30f8e4aea54d3818c2997324c8489b4845"
new = "5b4056db55ad3d42c9ff49fdb3d84fff545e1a8d868f7cb309b9cdd0e7c08a24"
n = 0
for p in doc.paragraphs:
    if old in p.text:
        p.text = p.text.replace(old, new); n += 1
doc.save(SI)
print("PATCHED", n)
print("SI_SHA", hashlib.sha256(open(SI, "rb").read()).hexdigest())
