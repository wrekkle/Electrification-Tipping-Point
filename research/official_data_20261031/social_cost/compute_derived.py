"""Compute sha256/bytes for raw files, oil stats, vot conversion chains. Writes JSON to tmp for authoring."""
import hashlib, json, os, statistics, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RAW = os.path.dirname(os.path.abspath(__file__))
out = {"files": [], "oil": {}, "vot": {}, "cpi": {}}

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

for dirpath, _, names in os.walk(os.path.join(RAW, "raw")):
    for n in sorted(names):
        p = os.path.join(dirpath, n)
        rel = os.path.relpath(p, ROOT).replace("\\", "/")
        out["files"].append({"local_path": rel, "bytes": os.path.getsize(p), "sha256": sha(p)})

# carried-over sources from prior task (read-only)
for p in [
    "research/cost_model_20261030/downloads/ey_time_value_handbook_excerpt.pdf",
    "research/ev_parking_math_20261029/PDFs/P26_An_Online_Admission_Control_Mechanism_for_Electric_Vehicles_at_Public_Parking_Infrastructures.pdf",
]:
    ap = os.path.join(ROOT, p)
    if os.path.exists(ap):
        out["files"].append({"local_path": p, "bytes": os.path.getsize(ap), "sha256": sha(ap), "carried_over": True})

# oil
j = json.load(open(os.path.join(RAW, "raw", "html", "oil_price_range_2025_2026.json"), encoding="utf-8"))
rows = j["data"]["gasoline"]
def avg(rs, k):
    v = [r[k] for r in rs if r.get(k) is not None]
    return round(statistics.fmean(v), 4) if v else None
def sel(s, e):
    return [r for r in rows if s <= r["Date"].replace("/", "-") <= e]
periods = {
    "2025_full": ("2025-01-01", "2025-12-31"),
    "2026_ytd": ("2026-01-01", "2026-09-30"),
    "trailing12m": ("2025-10-01", "2026-09-30"),
    "full_range": ("2025-01-01", "2026-09-30"),
}
for k, (s, e) in periods.items():
    rs = sel(s, e)
    out["oil"][k] = {"n": len(rs), "start": s, "end": e,
                     "A92": avg(rs, "A92"), "A95": avg(rs, "A95"), "A98": avg(rs, "A98"),
                     "diesel": avg(rs, "Achai")}
out["oil"]["date_range"] = [rows[-1]["Date"], rows[0]["Date"]]
out["oil"]["n_obs"] = len(rows)

# CPI (base 110年=100) from 表1-8 yearly indices
cpi2009, cpi2018, cpi2024 = 89.07, 97.76, 107.81
g2025 = 1.66 / 100.0
g2026ytd = 1.94 / 100.0
cpi2025 = round(cpi2024 * (1 + g2025), 4)
cpi2026 = round(cpi2025 * (1 + g2026ytd), 4)
out["cpi"] = {"base": "110年=100", "2009": cpi2009, "2018": cpi2018, "2024": cpi2024,
              "2025_derived": cpi2025, "2026_ytd_derived": cpi2026,
              "growth_2025_pct": 1.66, "growth_2026_ytd_pct": 1.94}
v2009_city, v2009_inter = 3.61, 5.23
v2018_city, v2018_inter = 5.93, 7.58
out["vot"] = {
    "chain_2009_to_2026_min": round(v2009_city * cpi2026 / cpi2009, 4),
    "chain_2009_to_2026_hour": round(v2009_city * cpi2026 / cpi2009 * 60, 2),
    "chain_2018_to_2026_min": round(v2018_city * cpi2026 / cpi2018, 4),
    "chain_2018_to_2026_hour": round(v2018_city * cpi2026 / cpi2018 * 60, 2),
    "chain_2009_to_2024_min": round(v2009_city * cpi2024 / cpi2009, 4),
    "intercity_2009_to_2026_min": round(v2009_inter * cpi2026 / cpi2009, 4),
    "intercity_2018_to_2026_min": round(v2018_inter * cpi2026 / cpi2018, 4),
    "handbook_revision_ratio_2009_2018": round(v2018_city / v2009_city, 4),
    "cpi_ratio_2009_2018": round(cpi2018 / cpi2009, 4),
}
out["emission"] = {"co2_kg_per_TJ": 69300, "ch4_kg_per_TJ": 3, "n2o_kg_per_TJ": 0.6}
out["electricity"] = {"ev_tariff_offpeak_summer": 3.05, "ev_tariff_offpeak_nonsummer": 2.90,
                      "ev_tariff_peak_summer": 12.47, "ev_tariff_peak_nonsummer": 12.14,
                      "lowvoltage_flat_summer": 4.08, "lowvoltage_flat_nonsummer": 3.87}
tmp = os.path.join(os.path.dirname(__file__), "_computed.json")
json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"n_files": len(out["files"]), "oil": out["oil"], "vot": out["vot"], "cpi": out["cpi"]}, ensure_ascii=False, indent=1))
