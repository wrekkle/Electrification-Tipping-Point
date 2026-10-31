# -*- coding: utf-8 -*-
"""Round-5 REF config comparability and cost arithmetic check (exit 0/1)."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(ROOT, "apps", "parking_lab", "workbench"))
from costs import facility_cost  # noqa: E402

R4 = os.path.join(ROOT, "research", "round4_20261031", "results", "scenario_REF_A_s5.json")
R336 = os.path.join(ROOT, "research", "round5_20261031", "repro", "ref_feeder336.json")

def load(p):
    with open(p, encoding="utf-8") as h:
        return json.load(h)

def key3(doc):
    return {(r["lot_id"], int(r["seed"]), int(r["k"])): r for r in doc["rows"]}

def main():
    a, b = key3(load(R4)), key3(load(R336))
    failures = []
    if len(a) != 1025 or len(b) != 1025:
        failures.append("row count != 1025")
    if {k: v["demand_hash"] for k, v in a.items()} != {k: v["demand_hash"] for k, v in b.items()}:
        failures.append("demand_hash differs across feeder setting")
    metric_fields = ["unserved_charge_events", "unserved_charge_energy_kwh", "facility_cost",
                     "unmet_no_connector_events", "mean_occupancy_rate"]
    metric_diff = [f for f in metric_fields if any(
        abs(float(a[k].get(f) or 0) - float(b[k].get(f) or 0)) > 1e-9 for k in a)]
    if metric_diff:
        failures.append("service/cost metrics differ: %r" % metric_diff)
    peak120 = max(float(r["peak_power_kw"] or 0) for r in load(R4)["rows"])
    peak336 = max(float(r["peak_power_kw"] or 0) for r in load(R336)["rows"])
    if not (peak120 <= 120.0 + 1e-9 and peak336 < 336.0):
        failures.append("peak power bound unexpected")

    cost = load(os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json"))
    params = cost["cost"]
    func = facility_cost(1, params, days=1)["value"]
    doc = cost["facility_cost"]["per_connector_day_TWD"]
    identity = params["depreciation_capex"] / params["depreciation_life_years"] / 365.0 + params["maintenance_per_bay_day"]
    if abs(func - identity) > 1e-12:
        failures.append("facility_cost(1,days=1) differs from explicit formula")
    rel = abs(doc - func) / func
    if not (0.0026e-2 < rel < 0.0028e-2):
        failures.append("documented-vs-computed relative gap not ~0.0027%%: %r" % rel)
    print(json.dumps({
        "rows": len(a),
        "feeder120_vs_336_demand_identical": {k: v["demand_hash"] for k, v in a.items()} == {k: v["demand_hash"] for k, v in b.items()},
        "service_metric_diffs": metric_diff, "peak120": peak120, "peak336": peak336,
        "feeder336_nonbinding_for_REF_set": peak336 < 336.0,
        "cost_func": func, "cost_doc": doc, "abs_diff": doc - func, "rel_diff": rel,
        "doc_decomposition": {"capital_rounded": 32.0, "maintenance_annual": params["maintenance_per_bay_day"] * 365.0},
        "failures": failures}, ensure_ascii=False, indent=1))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
