# -*- coding: utf-8 -*-
"""P0: test whether the three stale round-3 hashes are a pure ORDERING change."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import traffic_gen  # noqa: E402

STALE = {("TPE0330",2):"c922d50ed5db", ("TPE0401",2):"38a5beabafe7", ("TPE0695",3):"cd57a6f63c99"}
params = json.load(open(os.path.join(ROOT,"research","traffic_generation_20261031","fitted_parameters.json"),encoding="utf-8"))
def h(seq):
    return hashlib.sha256(json.dumps([[a.vehicle_id,a.time_min,a.is_ev,a.needs_charge,a.dwell_min,a.energy_kwh] for a in seq],sort_keys=True).encode()).hexdigest()
for (lot,seed),want in STALE.items():
    arr,_ = traffic_gen.generate_for_lot(params,lot,seed,horizon_min=1440.0,p_ev=0.1,q_need=0.36,
        demand_scale=None,scenario_model="independent",strict=True,charge_provenance=None,dwell_scale=1.0)
    arr=list(arr)
    variants={
      "as_generated": arr,
      "by_time_vid": sorted(arr,key=lambda a:(a.time_min,a.vehicle_id)),
      "by_vid": sorted(arr,key=lambda a:a.vehicle_id),
      "by_time_only": sorted(arr,key=lambda a:a.time_min),
      "by_ev_vid": sorted(arr,key=lambda a:(a.time_min,a.is_ev,a.vehicle_id)),
    }
    print(f"{lot} s{seed} want={want} n={len(arr)}")
    for k,v in variants.items():
        hh=h(v)[:12]
        print(f"   {k:14s} {hh} {'MATCH' if hh==want else ''}")
    # multiset equality across orderings is implied; report first/last times
    print("   t range", min(a.time_min for a in arr), max(a.time_min for a in arr))
