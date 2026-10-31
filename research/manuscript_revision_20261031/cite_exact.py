# -*- coding: utf-8 -*-
import os,re
from docx import Document
ROOT=r"C:\Projects\停车场充电桩优化方案"
doc=Document(os.path.join(ROOT,"paper","draft","Electrification_tipping_point_v2_draft_2026-10-31_round7_rev4.docx"))
body=[p for p in doc.paragraphs if p.style.name!="Bibliography"]
sup=set()
for p in body:
    seq=[r.text.strip() for r in p.runs if r.font.superscript and r.text.strip()]
    i=0
    while i<len(seq):
        t=seq[i]
        if t.isdigit():
            n=int(t)
            if i+2<len(seq) and seq[i+1]=="-" and seq[i+2].isdigit():
                m=int(seq[i+2]); sup.update(range(min(n,m),max(n,m)+1)); i+=3
            else:
                sup.add(n); i+=1
            continue
        if t in ("-",","): i+=1; continue
        for part in t.replace(";",",").split(","):
            part=part.strip()
            for dash in ("-","–","—"): part=part.replace(dash,"-")
            if "-" in part:
                a_s,_,b_s=part.partition("-")
                if a_s.strip().isdigit() and b_s.strip().isdigit():
                    a,b=int(a_s),int(b_s); sup.update(range(min(a,b),max(a,b)+1)); i+=1; continue
            for m in re.finditer(r"\d+",part): sup.add(int(m.group(0)))
        i+=1
print("CITED",sorted(sup))
print("MISSING",[i for i in range(1,77) if i not in sup])
print("OUT",[i for i in sup if i>76])
print("COUNT",len(sup))
