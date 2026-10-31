# -*- coding: utf-8 -*-
import os,re
from docx import Document
from docx.oxml.ns import qn
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=list(doc.paragraphs)
def cites(p):
    runs=[]
    for r in p.runs:
        va=r._element.find('.//'+qn('w:vertAlign'))
        if va is not None and va.get(qn('w:val'))=='superscript':
            runs.append(r.text)
    s=",".join(runs)
    nums=set()
    for m in re.finditer(r'(\d+)(?:\s*[-–]\s*(\d+))?',s):
        a=int(m.group(1)); b=int(m.group(2)) if m.group(2) else a
        if b>=a and b-a<50: nums.update(range(a,b+1))
    return nums,runs
allc={}
for i,p in enumerate(ps):
    n,s=cites(p)
    if n: allc[i]=(n,s)
print("CITE PARAS")
for i in sorted(allc): print(i,sorted(allc[i][0]),allc[i][1])
# old blocks
old=set(range(26,68))|set(range(128,147))|{156}|set(range(172,206))
oldc=set(); keep=set()
for i,(n,s) in allc.items():
    if i in old: oldc|=n
    else: keep|=n
print("OLD",sorted(oldc)); print("KEEP",sorted(keep)); print("ORPHANS",sorted(oldc-keep))
