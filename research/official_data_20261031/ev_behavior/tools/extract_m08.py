
import fitz, json, os
path = r"papers/electrification-math/M08_INL-parking-event-charging-rate_2015.pdf"
outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "source_review")
os.makedirs(outdir, exist_ok=True)
doc = fitz.open(path)
with open(os.path.join(outdir, "m08_text.txt"), "w", encoding="utf-8") as f:
    f.write("M08 local PDF: papers/electrification-math/M08_INL-parking-event-charging-rate_2015.pdf\n")
    f.write("pages=%d sha256_expected=afaf43d93c73008bce329d2b76ab12a5e41060be7337d172b1b1f785a509d866\n" % doc.page_count)
    for i, p in enumerate(doc):
        f.write("\n===== PDF PAGE %d =====\n" % (i + 1))
        f.write(p.get_text())
print("wrote m08_text.txt")
