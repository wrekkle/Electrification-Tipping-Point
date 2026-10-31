
import fitz, re, os, json
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
raw = os.path.join(base, "raw")
out = os.path.join(base, "source_review")
os.makedirs(out, exist_ok=True)
# IOT PDF: scan for Taiwan EV stock / charging demand numbers
p = os.path.join(raw, "IOT_public_charging_demand_table.pdf")
doc = fitz.open(p)
hits = []
with open(os.path.join(out, "iot_report_hits.txt"), "w", encoding="utf-8") as f:
    for i, pg in enumerate(doc):
        t = pg.get_text()
        if re.search(r"87,182|電動小客車|公共充(電)?樁|充電樁|電動車", t):
            hits.append(i + 1)
            f.write("\n===== PDF PAGE %d =====\n" % (i + 1))
            f.write(t)
print("IOT pages:", doc.page_count, "hit pages:", hits[:40])
