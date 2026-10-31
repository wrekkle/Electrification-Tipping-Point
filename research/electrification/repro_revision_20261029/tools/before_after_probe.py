
import copy, importlib, json, sys
import numpy as np

ORIG = r"research/electrification/repro"
REV = r"research/electrification/repro_revision_20261029"

def load(which_root):
    for name in [m for m in list(sys.modules) if m == "prei" or m.startswith("prei.")]:
        del sys.modules[name]
    for p in (ORIG + r"\src", REV + r"\src"):
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, which_root + r"\src")
    import prei
    return importlib.reload(prei)

def settings_for(root):
    # import fresh modules and load configs from the same root
    load(root)
    from prei import config
    import os
    cfg = config.load_config(os.path.join(root, "configs", "baseline.yaml"))
    s = cfg.resolved()
    modes = config.load_config(os.path.join(root, "configs", "modes.yaml")).resolved()
    s["modes"] = modes["modes"]
    s["seed"] = 42
    s["run"]["scenario_count"] = 4
    v2 = config.load_config(os.path.join(root, "configs", "v2.yaml")).resolved()["v2"]
    out = copy.deepcopy(s)
    out["v2"] = v2
    out["demand"] = dict(out["demand"]); out["demand"].update(v2["demand"])
    out["cost"] = dict(out["cost"]); out["cost"].update(v2.get("cost", {}))
    return out

def design(mode="fixed", m=2, rule="pi_F", coverage=1, reposition_min=0.0,
           power_kw=50.0, feeder_kw=500.0):
    return {"mode": mode, "m": m, "rule": rule, "theta": 0.0, "coverage": coverage,
            "reposition_min": reposition_min, "power_kw": power_kw, "feeder_kw": feeder_kw}

def base_day(times, n, dwell, energy, key="times"):
    classes = np.array(["ev_charge"] * n, dtype=object)
    return {key: np.asarray(times, float), "classes": classes,
            "dwell_min": np.asarray(dwell, float), "energy_req": np.asarray(energy, float),
            "r_draw": 1.0, "counts": {"A": n, "ev": n, "ev_charge": n, "ev_park": 0, "icev": 0}}

res = {}
# ---------- BEFORE (original repro copy) ----------
s = settings_for(ORIG); s["lot"]["n_spaces"] = 4
from prei import costs, simulator, stats
cm = costs.CostModel(s, 42)
day = base_day([11.5], 1, [60.0], [20.0])
o = simulator.simulate_day(s, cm, design(m=4), day)["timeline"][0]
res["R1_before"] = {k: o[k] for k in ("t_a","t_c","t_d","t_r","energy_delivered_kwh")}
day = base_day([0.0,0.0,1.0,3.0], 4, [600.0]*4, [80.0,2.5,2.5,2.5])
o = simulator.simulate_day(s, cm, design(mode="overhead", m=2, coverage=2), day)["timeline"]
res["R4_before"] = [{k: r[k] for k in ("t_a","t_c","t_d","device")} for r in o]
rng = np.random.default_rng(11)
part = 100.0 + rng.normal(100.0, 10.0, size=(10,1)); full = part[:,0] + 10.0
gi = stats.g_interval(full, part, n_boot=400, rng=np.random.default_rng(3))
res["R2_before"] = {k: gi[k] for k in ("g_hat","g_lo","g_hi")}
rng = np.random.default_rng(21)
base = rng.normal(100.0, 4.0, size=(60,1)); noise = rng.normal(0.0,2.0,size=(60,5))
mat = base + noise + np.array([0.0,6.0,8.0,10.0,12.0])[None,:]
mat[:,3] = mat[:,0]
cs = stats.confidence_set(mat, n_boot=500, rng=np.random.default_rng(22))
res["R3_before"] = {"best": cs["best"], "included": cs["included"],
                    "pvalues": [round(float(x),6) for x in cs["pvalues"]], "method": cs["method"]}
cv = stats.empirical_cvar(list(range(0,24)) + [100.0], 0.95)
res["R5_before"] = {"cvar": cv["cvar"], "cvar_aux": cv["cvar_aux"]}
res["R6_before"] = stats.etp_from_g([{"r": r, "g_hat": g} for r, g in
                                     zip((0.2,0.4,0.6,0.8), (-1.0, 2.0, -3.0, -1.0))])

# ---------- AFTER (revision copy) ----------
s = settings_for(REV); s["lot"]["n_spaces"] = 4
from prei import costs as c2, simulator as s2, stats as st2
cm = c2.CostModel(s, 42)
day = base_day([690.0], 1, [60.0], [20.0], key="times_min")
o = s2.simulate_day(s, cm, design(m=4), day)["timeline"][0]
res["R1_after"] = {k: o[k] for k in ("t_a","t_c","t_d","t_r","energy_delivered_kwh")}
res["R1_after"]["metrics_time_unit"] = s2.simulate_day(s, cm, design(m=4), day)["metrics"]["time_unit"]
day = base_day([0.0,0.0,1.0,3.0], 4, [600.0]*4, [80.0,2.5,2.5,2.5], key="times_min")
o = s2.simulate_day(s, cm, design(mode="overhead", m=2, coverage=2), day)["timeline"]
res["R4_after"] = [{k: r[k] for k in ("t_a","t_c","t_d","device")} for r in o]
rng = np.random.default_rng(11)
part = 100.0 + rng.normal(100.0, 10.0, size=(10,1)); full = part[:,0] + 10.0
gi = st2.g_interval(full, part, n_boot=400, rng=np.random.default_rng(3))
res["R2_after"] = {k: gi[k] for k in ("g_hat","g_lo","g_hi")}
rng = np.random.default_rng(21)
base = rng.normal(100.0, 4.0, size=(60,1)); noise = rng.normal(0.0,2.0,size=(60,5))
mat = base + noise + np.array([0.0,6.0,8.0,10.0,12.0])[None,:]
mat[:,3] = mat[:,0]
cs = st2.confidence_set(mat, n_boot=500, rng=np.random.default_rng(22))
res["R3_after"] = {"best": cs["best"], "included": cs["included"],
                   "pvalues": [round(float(x),6) for x in cs["pvalues"]],
                   "method": cs["method"], "family_size": cs["family_size"]}
cv = st2.empirical_cvar(list(range(0,24)) + [100.0], 0.95)
res["R5_after"] = {"cvar": cv["cvar"], "cvar_aux": cv["cvar_aux"], "tail_weight": cv["tail_weight"]}
res["R6_after"] = st2.etp_from_g([{"r": r, "g_hat": g} for r, g in
                                  zip((0.2,0.4,0.6,0.8), (-1.0, 2.0, -3.0, -1.0))])
payload = json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True,
                     default=lambda o: float(o))
target = r"research/electrification/repro_revision_20261029/reports/before_after_r1_r6.json"
import io as _io
with _io.open(target, "w", encoding="utf-8", newline="\n") as fh:
    fh.write(payload + "\n")
print(payload[:400])