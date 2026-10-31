import json, sys
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案")
from apps.parking_lab.workbench import traffic_gen
params = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json", encoding="utf-8"))
for lot in ("TPE0930", "TPE0008", "TPE1380"):
    arrivals, meta = traffic_gen.generate_for_lot(params, lot, 1)
    keep = {k: meta.get(k) for k in ("n_ev","n_arrivals","p_ev","q_need","charging_requests","expected_charge_sessions","observed_charge_sessions","n_initial_occupancy","mean_dwell_min")}
    print(lot, json.dumps(keep, ensure_ascii=False))
curve = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json", encoding="utf-8"))
seen = {}
for r in curve["rows"]:
    if r["seed"] == 1 and r["k"] == 10:
        seen[r["lot_id"]] = (r.get("ev_arrivals"), r.get("charge_requests"), r.get("initial_occupancy_vehicles"), r.get("new_arrivals"), round(r.get("mean_occupancy_rate") or 0,3))
print(json.dumps(seen, ensure_ascii=False))
