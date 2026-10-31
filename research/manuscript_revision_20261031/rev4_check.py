# -*- coding: utf-8 -*-
import os,re
from docx import Document
from docx.oxml.ns import qn
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
ps=list(doc.paragraphs)
full="\n".join(p.text for p in ps)
for term in ["global optimum","invaluable","profound insights","socially preferable","submitted comparison","published curves","earlier subsections","660 integer grids","all eight paired","two of the eight","submitted model","v1 accounting"]:
    print("TERM",repr(term),full.count(term))
print("CAPTIONS")
for i,p in enumerate(ps):
    if p.style.name=="Caption" or p.text.strip().startswith("Table "):
        print(i,p.text.strip()[:260])
print("DISCUSSION/METHODS HEADINGS")
for i,p in enumerate(ps):
    if p.style.name.startswith("Heading"): print(i,p.style.name,p.text.strip())
# citations
def cites(p):
    runs=[]
    for r in p.runs:
        va=r._element.find('.//'+qn('w:vertAlign'))
        if va is not None and va.get(qn('w:val'))=='superscript': runs.append(r.text)
    s=",".join(runs); nums=set()
    for m in re.finditer(r'(\d+)(?:\s*[-–]\s*(\d+))?',s):
        a=int(m.group(1)); b=int(m.group(2)) if m.group(2) else a
        if b>=a and b-a<50: nums.update(range(a,b+1))
    return nums
keep=set()
for p in ps:
    keep |= cites(p)
print("CITED COUNT",len(keep),"MAX",max(keep) if keep else None)
print("ORPHANS",sorted(set(range(1,77))-keep))
