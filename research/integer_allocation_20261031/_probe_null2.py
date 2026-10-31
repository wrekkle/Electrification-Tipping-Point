import json
c = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json", encoding="utf-8"))
rows = [r for r in c["rows"] if r.get("cost_complete")]
r = rows[0]
print(r["lot_id"], r["seed"], r["k"], "total", r.get("cost_total"), "missing", r.get("cost_missing_parameters"))
print(json.dumps(r.get("cost_items"), ensure_ascii=False, indent=1))
print("arrivals", r.get("arrivals"), "ev", r.get("ev_arrivals"), "charge_req", r.get("charge_requests"), "delivered", r.get("delivered_energy_kwh"), "rejected", r.get("rejected_total"))
print("occ_rate", r.get("mean_occupancy_rate"))
