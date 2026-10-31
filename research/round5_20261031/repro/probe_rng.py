# -*- coding: utf-8 -*-
"""P0 probe: is demand generation deterministic across processes for a fixed (lot, seed)?

Uses the same entry point as run_cost_curve.run_lot_seed (traffic_gen.generate_for_lot),
with the round-3 reference parameters. Prints only the demand hash of the raw record list.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from apps.parking_lab.workbench import traffic_gen  # noqa: E402

lot, seed = sys.argv[1], int(sys.argv[2])
params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json"), encoding="utf-8"))
arrivals, meta = traffic_gen.generate_for_lot(
    params, lot, seed, horizon_min=1440.0, p_ev=0.1, q_need=0.36,
    demand_scale=None, scenario_model="independent", strict=True,
    charge_provenance=None, dwell_scale=1.0)
h = hashlib.sha256(json.dumps(
    [[a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh] for a in arrivals],
    sort_keys=True).encode()).hexdigest()
print(json.dumps({"lot": lot, "seed": seed, "n": len(arrivals), "hash": h[:16], "full": h}))
