import json
p = r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json"
d = json.load(open(p, encoding="utf-8"))
print("top keys:", list(d.keys()))
for key in d:
    v = d[key]
    if isinstance(v, dict): print(" ", key, "dict", list(v.keys())[:10])
    elif isinstance(v, list): print(" ", key, "list", len(v))
    else: print(" ", key, "=", repr(v)[:120])
lots = d.get("per_lot") or []
print("n lots", len(lots))
for row in lots:
    lid = row.get("lot_id")
    if lid in ("TPE0008","TPE0007","TPE0151","TPE0003","TPE1011","TPE0827"):
        cons = row.get("consistency") or {}
        print("--", lid, "N=", row.get("n_spaces"), "split=", row.get("fit_split"))
        print("   lambda_mean=", row.get("lambda_mean_hour"), "dwell_mean_min=", (row.get("dwell_dist") or {}).get("mean_min"),
              "sessions_obs=", row.get("n_charge_sessions_observed"), "sessions_exp=", row.get("expected_charge_sessions_per_day"),
              "lambda_charge=", row.get("lambda_charge_per_hour"))
        print("   consistency:", json.dumps(cons, ensure_ascii=False)[:500])
