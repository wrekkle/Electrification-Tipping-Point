# -*- coding: utf-8 -*-
import os, re, hashlib
from docx import Document
ROOT = r"C:\Projects\停车场充电桩优化方案"
D = os.path.join(ROOT, "paper", "draft")
rev2 = os.path.join(D, "Electrification_tipping_point_v2_draft_2026-10-31_round6_rev2.docx")
rev1 = os.path.join(D, "Electrification_tipping_point_v2_draft_2026-10-31_round6.docx")
si = os.path.join(D, "Electrification_tipping_point_v2_supplementary_2026-10-31_round6.docx")
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
print("SHA_REV2", sha(rev2)); print("SHA_REV1", sha(rev1)); print("SHA_SI", sha(si))
doc = Document(rev2); paras = [p.text.strip() for p in doc.paragraphs]
print("PARAS", len(paras), "TABLES", len(doc.tables), "IMAGES", len(doc.inline_shapes))
print("TITLE", paras[0])
for w in ("placeholder","to be produced","to be drawn","to be reassigned","tbd","todo"):
    print("PENDING", w, sum(t.lower().count(w) for t in paras))
print("P77", paras[77][:1500])
for i in (82,83,87,88): print("P%d" % i, paras[i][:1500]); print("---")
print("NOTE91", paras[91])
for ti, tbl in enumerate(doc.tables):
    first = " | ".join(c.text.strip() for c in tbl.rows[0].cells)
    if "Rule pair" in first:
        for row in tbl.rows[:7]:
            print("T4", " | ".join(c.text.strip() for c in row.cells))
ref_i = next(i for i,p in enumerate(doc.paragraphs) if p.text.strip().lower() == "references")
bib = [p for p in doc.paragraphs if p.style.name == "Bibliography" and p.text.strip()]
body = doc.paragraphs[:ref_i]
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
                for m in re.finditer(r"\d+", part): sup.add(int(m.group()))
            i+=1
print("BIB", len(bib), "CITED", len(sup), "OVER", sorted(n for n in sup if n>len(bib)), "MISSING", [n for n in range(1,len(bib)+1) if n not in sup])
sidoc = Document(si); sip=[p.text.strip() for p in sidoc.paragraphs if p.text.strip()]
print("SI_PARAS", len(sidoc.paragraphs), "SI_TABLES", len(sidoc.tables), "SHA_SI_OK")
for t in sip:
    if re.match(r"^S[1-6]\b", t): print("SI_SEC", t[:140])
s2 = "\n".join(t for t in sip if "A1" in t or "A2" in t or "A3" in t or "A4" in t or "A5" in t or "A6" in t)
print("SI_S2_ASSUMPTIONS", s2[:1800])
