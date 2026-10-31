import json
d = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/cost_curve_pi0_feeder120.json", encoding="utf-8"))
rows = [r for r in d["rows"] if r["lot_id"] == "TPE0930" and r["seed"] == 1]
print("k  ev_arr  charge_req  rejected_chg  no_connector  plugged  unmet_nc  dw_short  overstay")
for r in rows:
    print(r["k"], r["ev_arrivals"], r.get("charge_requests"), r.get("charge_requests_rejected"),
          (r.get("unmet_no_connector_events") or 0) - (r.get("charge_requests_rejected") or 0),
          (r.get("charge_requests") or 0) - (r.get("charge_requests_rejected") or 0) - ((r.get("unmet_no_connector_events") or 0) - (r.get("charge_requests_rejected") or 0)),
          r.get("unmet_no_connector_events"), r.get("power_dwell_shortfall_events"),
          round(r["type_occupancy"]["overstay_after_complete_min"] or 0, 0))
