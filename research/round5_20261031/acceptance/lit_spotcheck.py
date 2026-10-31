# -*- coding: utf-8 -*-
"""Independent spot-check: cited pages contain claimed sentences; M18 keyword scan."""
import json, os, re, sys, unicodedata
import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PDF = {
 "M18": os.path.join(ROOT, "papers", "electrification-math", "M18_joint-operation-parking-charging_TRD2025.pdf"),
 "M06": os.path.join(ROOT, "papers", "electrification-math", "M06_shared-private-parking-EV_ALR_ESWA2026.pdf"),
 "M07": os.path.join(ROOT, "papers", "electrification-math", "M07_dynamic-rolling-parking-charging-unpunctuality_TRC2025.pdf"),
}
def norm(t):
    t = unicodedata.normalize("NFKC", t).replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", t)
docs = {k: pymupdf.open(v) for k, v in PDF.items()}
pages = {k: [norm(p.get_text()) for p in d] for k, d in docs.items()}

spot = [
 ("M18", 15, "No data was used", "data availability -> M18 has no empirical data"),
 ("M18", 5, "cost coefficient of constructing unit charging pile", "cost coefficient k in n^2 cost"),
 ("M18", 4, "monopolized by two differentiated operators", "two differentiated operators / supply-chain sharing"),
 ("M18", 6, "we solve the following GNB", "three-stage game solved by GNB"),
 ("M06", 24, "without incorporating factors such as charging power and grid load", "M06 explicitly excludes power/grid"),
 ("M06", 7, "Rule 1: Parking users who do not require charging", "M06 admission rules"),
 ("M07", 8, "charging power required by request m", "M07 uses charging power as request attribute"),
 ("M07", 11, "probability", "M07 chance constraints / unpunctuality"),
 ("M07", 15, "Hangzhou", "M07 empirical Hangzhou data"),
 ("M06", 1, "reduces computation time by 80.31%", "author-reported speed-up (tier B)"),
]
def ctx(paper, page, needle, width=260):
    text = pages[paper][page - 1]
    i = text.lower().find(needle.lower())
    if i < 0: return None
    return text[max(0, i - width): i + len(needle) + width]

out = {"spot_checks": [], "m18_keyword_scan": {}, "m18_pages": len(pages["M18"])}
for paper, page, needle, why in spot:
    c = ctx(paper, page, needle)
    out["spot_checks"].append({"paper": paper, "page": page, "needle": needle, "why": why,
                               "found": c is not None, "context": c})
kw = ["kW", "kWh", "energy", "queue", "waiting time", "service level", "charging power", "capacity"]
scan = {}
for w in kw:
    hits = []
    for p in range(len(pages["M18"])):
        for m in re.finditer(re.escape(w), pages["M18"][p], re.I):
            s = pages["M18"][p][max(0, m.start() - 80): m.end() + 80]
            hits.append({"page": p + 1, "snippet": s})
    scan[w] = hits
out["m18_keyword_scan"] = {k: {"count": len(v), "hits": v[:6]} for k, v in scan.items()}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lit_spotcheck.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(json.dumps({"asks": len(out["spot_checks"]),
                  "all_found": all(x["found"] for x in out["spot_checks"]),
                  "m18_keyword_counts": {k: v["count"] for k, v in out["m18_keyword_scan"].items()}},
                 ensure_ascii=False))
