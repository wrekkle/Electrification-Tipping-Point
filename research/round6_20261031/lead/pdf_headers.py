# -*- coding: utf-8 -*-
import pymupdf, os
ROOT = r"C:\Projects\停车场充电桩优化方案"
pdf = os.path.join(ROOT,"research","round6_20261031","c_paper","round6_rev2_draft.pdf")
doc = pymupdf.open(pdf)
pairs = [("Table 1 Fixed-k","Both\nfeasible"),("Table 2 Three minimal","Trace"),("Table 3 Smallest","Rule"),
         ("Table 4 Admissible","Rule pair"),("Table 5 Observed","Scenario"),("Table 6 Parameters","Symbol")]
for cap, head in pairs:
    cpages=[i+1 for i in range(doc.page_count) if cap in doc[i].get_text()]
    hpages=[i+1 for i in range(doc.page_count) if head in doc[i].get_text()]
    print(cap, "cap", cpages, "header", hpages)
si = os.path.join(ROOT,"research","round6_20261031","c_paper","round6_rev2_supplement.pdf")
d2 = pymupdf.open(si)
print("SI_PAGES", d2.page_count)
blank=[]; over=[]
for i,pg in enumerate(d2):
    if not pg.get_text().strip() and not pg.get_images(full=True): blank.append(i+1)
    for b in pg.get_text("blocks"):
        x0,y0,x1,y1=b[:4]
        if x1>d2[0].rect.width-5 or y1>d2[0].rect.height-5: over.append((i+1,b[4][:40]))
print("SI_BLANK", blank, "SI_OVERFLOW", over[:5])
