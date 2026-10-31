# -*- coding: utf-8 -*-
import re, sys, os
import pymupdf
ROOT = r"C:\Projects\停车场充电桩优化方案"
pdf = sys.argv[1]
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)
doc = pymupdf.open(pdf)
W, H = doc[0].rect.width, doc[0].rect.height
print("PAGES", doc.page_count, "SIZE", round(W,1), round(H,1))
blank = []; overflow = []; imgs = 0; rendered = 0
for i, page in enumerate(doc):
    txt = page.get_text()
    pics = page.get_images(full=True)
    imgs += len(pics)
    if len(txt.strip()) == 0 and not pics:
        blank.append(i + 1)
    blocks = page.get_text("blocks")
    for b in blocks:
        x0, y0, x1, y1 = b[:4]
        if x1 > W - 5 or y1 > H - 5 or x0 < -1 or y0 < -1:
            overflow.append({"page": i + 1, "bbox": [round(v,1) for v in (x0,y0,x1,y1)], "text": b[4][:60]})
    page.get_pixmap(dpi=80).save(os.path.join(outdir, "p%03d.png" % (i + 1)))
    rendered += 1
print("BLANK_PAGES", blank)
print("OVERFLOW_BLOCKS", len(overflow), overflow[:6])
print("IMAGES", imgs, "RENDERED", rendered)
caps = ["Table 1 Fixed-k", "Table 2 Three minimal", "Table 3 Smallest", "Table 4 Admissible", "Table 5 Observed", "Table 6 Parameters",
        "Fig. 1 PREI", "Fig. 2 Optimized", "Fig. 3 Sensitivity", "Fig. 4 PSC", "Fig. 5 ETP"]
for c in caps:
    pages = [i+1 for i in range(doc.page_count) if c in doc[i].get_text()]
    print("CAP", c, "->", pages)
print("image pages", [i+1 for i in range(doc.page_count) if doc[i].get_images(full=True)])
