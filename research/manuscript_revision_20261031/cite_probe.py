# -*- coding: utf-8 -*-
import os,re
from docx import Document
from docx.oxml.ns import qn
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx"))
ps=list(doc.paragraphs)
def cites(p):
    out=[]
    for r in p.runs:
        xml=r._element
        va=xml.find('.//'+qn('w:vertAlign'))
        if va is not None and va.get(qn('w:val'))=='superscript':
            out.append(r.text)
    s="".join(out)
    nums=set()
    for m in re.finditer(r'(\d+)(?:\s*[-–]\s*(\d+))?',s):
        a=int(m.group(1)); b=int(m.group(2)) if m.group(2) else a
        if b>=a and b-a<50: nums.update(range(a,b+1))
    return nums,s
allc={}
for i,p in enumerate(ps):
    n,s=cites(p)
    if n: allc[i]=(n,s)
print("PARAS WITH CITES",len(allc))
for i in range(24,30): print(i,ps[i].text.strip()[:80],allc.get(i))
print("OLD_RESULTS cites union",sorted(set().union(*[allc[i][0] for i in range(26,68) if i in allc])) if any(i in allc for i in range(26,68)) else [])
print("OLD_METHODS cites union",sorted(set().union(*[allc[i][0] for i in range(128,147) if i in allc]+[allc[i][0] for i in range(182,206) if i in allc])) if True else [])
# all cites outside old regions
keep=set()
for i,(n,s) in allc.items():
    if 26<=i<=67: continue
    if 128<=i<=146: continue
    if i==156: continue
    if 172<=i<=205: continue
    keep |= n
print("KEEP MAX",max(keep) if keep else None,"COUNT",len(keep))
print("KEEP NUMBERS",sorted(keep))
print("ORPHANS",sorted(set(range(1,77))-keep))
