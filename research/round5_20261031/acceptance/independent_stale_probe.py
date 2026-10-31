# -*- coding: utf-8 -*-
"""Independent check: can the 3 stale round-3 demand hashes be recovered by sorting/renumbering
the CURRENT generator's records? Plus permutation sanity on the current record set."""
import hashlib, json, os, sys, itertools, random
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
from apps.parking_lab.workbench import traffic_gen

STALE = {("TPE0330", 2): "c922d50ed5db", ("TPE0401", 2): "38a5beabafe7", ("TPE0695", 3): "cd57a6f63c99"}
CUR = {("TPE0330", 2): "fefaf373f9f3", ("TPE0401", 2): "e650dbf91b67", ("TPE0695", 3): "620ebdfeb142"}
params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json"), encoding="utf-8"))

def fields(a):
    return [a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh]
def h(seq):
    return hashlib.sha256(json.dumps([fields(a) for a in seq], sort_keys=True).encode()).hexdigest()
def renum(seq):
    class V:
        def __init__(s, x, i):
            s.vehicle_id = i; s.time_min = x.time_min; s.is_ev = x.is_ev
            s.needs_charge = x.needs_charge; s.dwell_min = x.dwell_min; s.energy_kwh = x.energy_kwh
    return [V(x, i) for i, x in enumerate(seq)]

out = {}
found = []
for (lot, seed), want in STALE.items():
    arr, _ = traffic_gen.generate_for_lot(
        params, lot, seed, horizon_min=1440.0, p_ev=0.1, q_need=0.36,
        demand_scale=None, scenario_model="independent", strict=True,
        charge_provenance=None, dwell_scale=1.0)
    arr = list(arr)
    keys = {
        "as_generated": None,
        "time_id": lambda a: (a.time_min, a.vehicle_id),
        "time_desc_id": lambda a: (-a.time_min, a.vehicle_id),
        "vid": lambda a: a.vehicle_id,
        "vid_desc": lambda a: -a.vehicle_id,
        "time_ev": lambda a: (a.time_min, a.is_ev),
        "dwell": lambda a: a.dwell_min,
        "energy": lambda a: a.energy_kwh,
        "time_dwell": lambda a: (a.time_min, a.dwell_min),
        "ie": lambda a: (a.is_ev, a.time_min),
    }
    variants = {}
    for name, key in keys.items():
        seq = arr if key is None else sorted(arr, key=key)
        variants[name] = h(seq)[:12]
        variants[name + "_renum"] = h(renum(seq))[:12]
    for name, seq in (("reversed", list(reversed(arr))), ("canonical_renum", renum(sorted(arr, key=lambda a: tuple(fields(a)[1:]))))):
        variants[name] = h(seq)[:12]
    rng = random.Random(20261031)
    perm_hits = [s for s in range(200) if (lambda p: h([arr[i] for i in p])[:12] == want)(rng.sample(range(len(arr)), len(arr)))]
    hits = [n for n, hh in variants.items() if hh == want]
    cur_ok = variants["as_generated"] == CUR[(lot, seed)]
    out["%s/s%d" % (lot, seed)] = {
        "n": len(arr), "want_r3": want, "as_current": variants["as_generated"],
        "current_matches_own_repro": cur_ok, "variants_tested": len(variants),
        "variants_matching_r3": hits, "random_permutation_matches": len(perm_hits),
        "multiset_hash": hashlib.sha256(json.dumps(sorted(fields(a) for a in arr), sort_keys=True).encode()).hexdigest()[:12],
    }
    if hits: found.append((lot, seed, hits))
print(json.dumps({"streams": out, "any_variant_reproduced_r3": found,
                  "verdict": "no sorting/renumbering variant reproduces stale round-3 hashes" if not found else "VARIANT FOUND"},
                 ensure_ascii=False, indent=1))
raise SystemExit(0 if not found else 1)
