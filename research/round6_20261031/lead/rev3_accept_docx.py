# -*- coding: utf-8 -*-
import os, re, hashlib
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
D = os.path.join(ROOT, "paper", "draft")
rev3 = os.path.join(D, "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev3.docx")
si = os.path.join(D, "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx")
doc = Document(rev3); paras=[p.text.strip() for p in doc.paragraphs]
print("PARAS",len(paras),"TABLES",len(doc.tables),"IMAGES",len(doc.inline_shapes))
for w in ("placeholder","to be produced","to be drawn","to be reassigned","tbd","todo"):
    print("PENDING",w,sum(t.lower().count(w) for t in paras))
for kw in ("global optimum","invaluable","profound insights","socially preferable","socially optimal","social optimum","dominance coupling","count-difference","mirror coupling","value of information","specific signal-aware","within the enumerated range","Only the A rows"):
    hits=[(i,t) for i,t in enumerate(paras) if kw.lower() in t.lower()]
    print("KW[%s] %d" % (kw,len(hits)))
    for i,t in hits[:3]: print("   [%d] %s" % (i,t[:240]))
print("P77",paras[77][:1100])
print("P95",paras[95][:900])
print("P156",paras[156][:1100])
print("NOTE91",paras[91][:900])
ref_i=next(i for i,p in enumerate(doc.paragraphs) if p.text.strip().lower()=="references")
bib=[p for p in doc.paragraphs if p.style.name=="Bibliography" and p.text.strip()]
sup=set()
for p in doc.paragraphs[:ref_i]:
    seq=[r.text.strip() for r in p.runs if r.font.superscript and r.text.strip()]
    i=0
    while i<len(seq):
        t=seq[i]
        if t.isdigit():
            n=int(t)
            if i+2<len(seq) and seq[i+1]=="-" and seq[i+2].isdigit():
                m=int(seq[i+2]); sup.update(range(min(n,m),max(n,m)+1)); i+=3
            else: sup.add(n); i+=1
        elif t in ("-",","): i+=1
        else:
            for part in t.replace(";",",").split(","):
                part=part.strip()
                for dash in ("-","–","—"): part=part.replace(dash,"-")
                if "-" in part:
                    a,_,b=part.partition("-")
                    if a.strip().isdigit() and b.strip().isdigit():
                        a,b=int(a),int(b); sup.update(range(min(a,b),max(a,b)+1)); i+=1; continue
                for m in re.finditer(r"\d+",part): sup.add(int(m.group()))
            i+=1
print("BIB",len(bib),"CITED",len(sup),"OVER",sorted(n for n in sup if n>len(bib)),"MISSING",[n for n in range(1,len(bib)+1) if n not in sup])
sid=Document(si); sp=[p.text.strip() for p in sid.paragraphs]
start=next(i for i,t in enumerate(sp) if t.startswith("S2 "))
end=next(i for i,t in enumerate(sp) if t.startswith("S3 "))
print("SI_S2_PARAS",end-start)
for t in sp[start:end]:
    if t: print("SI2|",t[:1000])
