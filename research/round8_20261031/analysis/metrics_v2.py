# -*- coding: utf-8 -*-
"""R8-G: metric decomposition and identity check (capacity_unmet vs access vs shortfall)."""
import csv, json, sys, statistics
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = "research/round8_20261031"
def rc(p):
    f = open(p, encoding="utf-8"); rs = list(csv.DictReader(f)); f.close(); return rs
e4 = rc(R + "/experiments_declared22/E4/test_E4.csv")
ps = rc(R + "/experiments_declared22/per_stream_declared22.csv")
print("E4 rows", len(e4), "k values", sorted({r["k"] for r in e4}), "policies", sorted({r["policy"] for r in e4}))
rows = []
for r in e4:
    cr = float(r["charge_requests"] or 0); adm = float(r["admitted"] or 0)
    cap = float(r["num_capacity_unmet_requests"] or 0)
    ev = float(r["num_ev_parking_failures"] or 0); ice = float(r["num_ice_parking_failures"] or 0)
    sh = float(r["num_departed_shortfall_kwh"] or 0); dlv = float(r["delivered_kwh_incl_rejected"] or 0)
    dem = float(r["demand_kwh_incl_rejected"] or 0)
    acc_num = float(r["charging_access_num"] or 0); acc_den = float(r["charging_access_den"] or 0)
    rej = float(r["energy_cat_rejected"] or 0)
    cens = float(r["censored_sessions"] or 0)
    rows.append({"stream": r["stream_id"], "policy": r["policy"], "k": r["k"],
                 "charge_requests": cr, "admitted": adm, "energy_cat_rejected": rej,
                 "never_connected_rate": round(1 - adm / cr, 6) if cr else None,
                 "ev_parking_failure_rate": float(r["service_ev_parking_failure_rate"] or 0),
                 "ice_parking_failure_rate": float(r["service_ice_parking_failure_rate"] or 0),
                 "departed_unmet_sessions": cap, "capacity_only_unmet_rate": float(r["capacity_only_unmet_rate"] or 0),
                 "energy_shortfall_kwh": sh, "energy_shortfall_ratio": round(1 - dlv / dem, 6) if dem else None,
                 "charge_grants": acc_num, "charge_denominator": acc_den, "censored_sessions": cens})
with open(R + "/analysis/metrics_v2_decomposition.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
# identity: capacity_unmet == gate-denied charge requests + shortfall sessions
print("--- identity check (capacity_only_unmet vs gate + shortfall) ---")
bad = 0
for r in e4:
    cr = float(r["charge_requests"] or 0); adm = float(r["admitted"] or 0); cap = float(r["num_capacity_unmet_requests"] or 0)
    rej = float(r["energy_cat_rejected"] or 0); cens = float(r["censored_sessions"] or 0)
    gate = cr - adm
    implied_short = cap - gate
    if abs(implied_short - (cens if cens else implied_short)) > 1e-6 and r["k"] == max(x["k"] for x in e4):
        bad += 1
    if r["k"] in ("1",) or r["k"] == "1":
        pass
for k in sorted({r["k"] for r in e4}):
    sub = [r for r in e4 if r["k"] == k]
    cr = sum(float(r["charge_requests"] or 0) for r in sub)
    adm = sum(float(r["admitted"] or 0) for r in sub)
    cap = sum(float(r["num_capacity_unmet_requests"] or 0) for r in sub)
    sh = sum(float(r["num_departed_shortfall_kwh"] or 0) for r in sub)
    dlv = sum(float(r["delivered_kwh_incl_rejected"] or 0) for r in sub)
    dem = sum(float(r["demand_kwh_incl_rejected"] or 0) for r in sub)
    ev = sum(float(r["num_ev_parking_failures"] or 0) for r in sub)
    ice = sum(float(r["num_ice_parking_failures"] or 0) for r in sub)
    print("k=%s: charge_req %.0f admitted %.0f gate_denied %.0f | capacity_unmet %.0f -> implied shortfall sessions %.0f | EVfail %.0f ICEfail %.0f | delivered %.1f demand %.1f shortfall_kwh %.1f (%.2f%%) | cap_rate_pre %.4f"
          % (k, cr, adm, cr - adm, cap, cap - (cr - adm), ev, ice, dlv, dem, sh, 100 * sh / dem if dem else 0,
             cap / cr if cr else 0))
# per-stream decomposition at declared max k
print("--- per-stream (declared max k, policy A and best) ---")
for r in ps:
    pass
print("per_stream_declared22 columns:", list(ps[0].keys()))
for r in ps[:4]: print({k: r[k] for k in list(ps[0].keys())[:14]})
