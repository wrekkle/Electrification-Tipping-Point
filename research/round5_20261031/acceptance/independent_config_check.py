# -*- coding: utf-8 -*-
"""Independent cost/feeder verification (does not import verify_config)."""
import json, os, sys, math
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "apps", "parking_lab", "workbench"))
from costs import facility_cost
L = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
r4 = L("research/round4_20261031/results/scenario_REF_A_s5.json")
r336 = L("research/round5_20261031/repro/ref_feeder336.json")
k = lambda d: {(r["lot_id"], int(r["seed"]), int(r["k"])): r for r in d["rows"]}
a, b = k(r4), k(r336)
res = {"rows_a": len(a), "rows_b": len(b), "same_keys": set(a) == set(b)}
res["demand_hash_same"] = sum(a[x]["demand_hash"] == b[x]["demand_hash"] for x in a)
fields = ["unserved_charge_events", "unserved_charge_energy_kwh", "facility_cost",
          "unmet_no_connector_events", "mean_occupancy_rate", "peak_power_kw"]
fdr = {}
for f in fields:
    diffs = [x for x in a if abs(float(a[x][f] or 0) - float(b[x][f] or 0)) > 1e-9]
    fdr[f] = len(diffs)
    if f == "peak_power_kw":
        res["peak_diff_rows"] = sorted("%s/s%d/k%d" % x for x in diffs)[:20]
        res["peak_a_max"] = max(float(r["peak_power_kw"] or 0) for r in a.values())
        res["peak_b_max"] = max(float(r["peak_power_kw"] or 0) for r in b.values())
        res["peak_a_eq_120"] = sum(abs(float(r["peak_power_kw"] or 0) - 120.0) < 1e-9 for r in a.values())
        res["peak_b_gt_120"] = sum(float(r["peak_power_kw"] or 0) > 120.0 + 1e-9 for r in b.values())
res["field_diff_counts"] = fdr
# cost
cs = L("research/integer_allocation_20261031/cost_scenario.json")
p = cs["cost"]
fn = facility_cost(1, p, days=1)
manual = p["depreciation_capex"] / p["depreciation_life_years"] / 365.0 + p["maintenance_per_bay_day"]
doc = cs["facility_cost"]["per_connector_day_TWD"]
doc_from_parts = 32.0 + 15804.4 / 365.0
res["cost"] = {
    "params": {kk: p[kk] for kk in ("depreciation_capex", "depreciation_life_years", "maintenance_per_bay_day")},
    "facility_cost_value": fn["value"], "manual": manual, "func_eq_manual": abs(fn["value"] - manual) < 1e-12,
    "doc_value": doc, "abs_diff": doc - fn["value"], "rel_diff": abs(doc - fn["value"]) / fn["value"],
    "rel_pct": abs(doc - fn["value"]) / fn["value"] * 100,
    "doc_equals_32_plus_15804.4_over_365": abs(doc - doc_from_parts) < 1e-12,
    "doc_parts": doc_from_parts,
    "maintenance_annual_from_field": p["maintenance_per_bay_day"] * 365.0,
    "doc_implied_capex": 32.0 * 10 * 365.0,
}
res["failures"] = []
if res["demand_hash_same"] != 1025: res["failures"].append("demand hashes differ")
for f, n in fdr.items():
    if f != "peak_power_kw" and n: res["failures"].append("metric differs: " + f)
if fdr["peak_power_kw"] != 8: res["failures"].append("peak diff rows != 8")
if res["peak_a_max"] > 120.0 + 1e-9: res["failures"].append("feeder120 peak > 120")
if res["peak_b_max"] >= 336.0: res["failures"].append("feeder336 binding")
if not res["cost"]["func_eq_manual"]: res["failures"].append("facility_cost != manual formula")
if not (0.0026e-2 < abs(doc - fn["value"]) / fn["value"] < 0.0028e-2): res["failures"].append("relative gap not 0.0027%")
if not res["cost"]["doc_equals_32_plus_15804.4_over_365"]: res["failures"].append("doc decomposition mismatch")
print(json.dumps(res, ensure_ascii=False, indent=1))
raise SystemExit(1 if res["failures"] else 0)
