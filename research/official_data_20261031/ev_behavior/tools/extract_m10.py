
import fitz, os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw", "M10_TUE_fulltext.pdf")
doc = fitz.open(p)
outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source_review")
os.makedirs(outdir, exist_ok=True)
with open(os.path.join(outdir, "m10_text.txt"), "w", encoding="utf-8") as f:
    f.write("pages=%d\n" % doc.page_count)
    for i, pg in enumerate(doc):
        f.write("\n===== PDF PAGE %d =====\n" % (i+1))
        f.write(pg.get_text())
print("pages", doc.page_count)
