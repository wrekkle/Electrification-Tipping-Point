# -*- coding: utf-8 -*-
import os, re
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
doc = Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps = doc.paragraphs
words = lambda s: len(re.findall(r"[A-Za-z][A-Za-z'’\-]*", s))
heads=[]
for i,p in enumerate(ps):
    if p.style.name.startswith("Heading"):
        heads.append((i,p.style.name,p.text.strip()))
print("HEADINGS", len(heads))
for k in range(len(heads)):
    i,st,t=heads[k]; end=heads[k+1][0] if k+1<len(heads) else len(ps)
    w=sum(words(ps[j].text) for j in range(i,end))
    print("%4d-%4d [%s] w=%5d | %s" % (i,end,st,w,t[:100]))
# broad ranges
refi=next(i for i,p in enumerate(ps) if p.style.name=="Heading 1" and p.text.strip()=="References")
abstract=sum(words(ps[j].text) for j in range(0,7))
intro=sum(words(ps[j].text) for j in range(7,24))
oldres=sum(words(ps[j].text) for j in range(26,68))
newres=sum(words(ps[j].text) for j in range(68,94))
disc=sum(words(ps[j].text) for j in range(94,123))
meth=sum(words(ps[j].text) for j in range(123,refi))
refs=sum(words(ps[j].text) for j in range(refi,next(i for i,p in enumerate(ps) if p.style.name=="Heading 1" and p.text.strip().startswith("Data availability"))))
print("RANGES abstract",abstract,"intro",intro,"old_results",oldres,"new_results",newres,"discussion",disc,"methods",meth,"references",refs)
