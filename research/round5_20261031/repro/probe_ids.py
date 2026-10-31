# -*- coding: utf-8 -*-
"""P0: test id-assignment/order variants against the stale round-3 hashes."""
import hashlib, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import traffic_gen

want = {("TPE0330",2):"c922d50ed5db", ("TPE0401",2):"38a5beabafe7", ("TPE0695",3):"cd57a6f63c99"}
r4h  = {("TPE0330",2):"fefaf373f9f3", ("TPE0401",2):"e650dbf91b67", ("TPE0695",3):"620ebdfeb142"}
params = json.load(open(os.path.join(ROOT,"research","traffic_generation_20261031","fitted_parameters.json"),encoding="utf-8"))
def hh(seq):
    return hashlib.sha256(json.dumps([[a.vehicle_id,a.time_min,a.is_ev,a.needs_charge,a.dwell_min,a.energy_kwh] for a in seq],sort_keys=True).encode()).hexdigest()[:12]
class V:  # lightweight mutable copy
    def __init__(s,a,i): s.vehicle_id=i; s.time_min=a.time_min; s.is_ev=a.is_ev; s.needs_charge=a.needs_charge; s.dwell_min=a.dwell_min; s.energy_kwh=a.energy_kwh
for (lot,seed),w in want.items():
    arr,_ = traffic_gen.generate_for_lot(params,lot,seed,horizon_min=1440.0,p_ev=0.1,q_need=0.36,
        demand_scale=None,scenario_model="independent",strict=True,charge_provenance=None,dwell_scale=1.0)
    a=list(arr)
    print(lot,seed,"n=",len(a),"ids:",a[0].vehicle_id,a[-1].vehicle_id,"sorted_ids:",all(a[i].vehicle_id<=a[i+1].vehicle_id for i in range(len(a)-1)))
    schemes={}
    for name,key in [("time",lambda x:x.time_min),("time_ev",lambda x:(x.time_min,x.is_ev)),
                     ("dwell",lambda x:x.dwell_min),("time_desc",lambda x:-x.time_min)]:
        s=sorted(a,key=key)
        schemes[name+"_renum"]=[V(x,i) for i,x in enumerate(s)]
    for name,seq in schemes.items():
        x=hh(seq)
        print("   ",name,x,"MATCH3" if x==w else "")
