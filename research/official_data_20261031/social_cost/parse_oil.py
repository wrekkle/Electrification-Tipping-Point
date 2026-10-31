import json, sys, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
j = json.load(open("research/official_data_20261031/social_cost/raw/html/oil_price_range_2025_2026.json", encoding="utf-8"))
rows = j["data"]["gasoline"]
print("n_records", len(rows))
print("date_range", rows[-1]["Date"], "->", rows[0]["Date"])
def avg(rs, key):
    vals = [r[key] for r in rs if r.get(key) is not None]
    return round(statistics.fmean(vals), 3) if vals else None
def sel(rs, start, end):
    out = []
    for r in rs:
        d = r["Date"].replace("/", "-")
        if start <= d <= end:
            out.append(r)
    return out
for label, s, e in [("2025_full", "2025-01-01", "2025-12-31"), ("trailing12m", "2025-10-01", "2026-09-30"), ("2026_ytd", "2026-01-01", "2026-09-30")]:
    sub = sel(rows, s, e)
    print(label, "n", len(sub), "A92", avg(sub, "A92"), "A95", avg(sub, "A95"), "A98", avg(sub, "A98"), "Achai", avg(sub, "Achai"))
# list gaps: dates count per year
from collections import Counter
c = Counter(r["Date"][:4] for r in rows)
print("by_year", dict(c))
