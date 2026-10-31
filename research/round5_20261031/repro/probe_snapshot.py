# -*- coding: utf-8 -*-
"""P0: try to reproduce the three stale round-3 hashes with the round-2 pre-fix generator snapshot."""
import hashlib, importlib.util, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
path = os.path.join(ROOT, "research", "round2_20261031", "traffic_fix", "pre_fix_traffic_gen_snapshot.py")
spec = importlib.util.spec_from_file_location("pre_fix_traffic_gen", path)
mod = importlib.util.module_from_spec(spec)
sys.modules["pre_fix_traffic_gen"] = mod
spec.loader.exec_module(mod)
print("has generate_for_lot:", hasattr(mod,"generate_for_lot"), "version:", getattr(mod,"GENERATOR_VERSION","?"))
params = json.load(open(os.path.join(ROOT,"research","traffic_generation_20261031","fitted_parameters.json"),encoding="utf-8"))
def h(seq):
    return hashlib.sha256(json.dumps([[a.vehicle_id,a.time_min,a.is_ev,a.needs_charge,a.dwell_min,a.energy_kwh] for a in seq],sort_keys=True).encode()).hexdigest()
TA = {"TPE0330":2,"TPE0401":2,"TPE0695":3}
want = {"TPE0330":("c922d50ed5db","fefaf373f9f3"),"TPE0401":("38a5beabafe7","e650dbf91b67"),"TPE0695":("cd57a6f63c99","620ebdfeb142")}
for lot,seed in TA.items():
    try:
        out = mod.generate_for_lot(params, lot, seed, horizon_min=1440.0, p_ev=0.1, q_need=0.36,
                                   scenario_model="independent")
        arr = out[0] if isinstance(out,tuple) else out
        hh = h(arr)[:12]
        print(lot, seed, "snapshot:", hh, "want r3:", want[lot][0], "r4:", want[lot][1],
              "MATCH_R3" if hh==want[lot][0] else "")
    except Exception as e:
        print(lot, seed, "ERROR", type(e).__name__, str(e)[:160])
