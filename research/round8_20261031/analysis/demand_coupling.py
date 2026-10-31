# -*- coding: utf-8 -*-
"""R8-G: demand-dwell coupling scenarios (A independent / B dwell-conditioned) with preserved marginals.
Plan recorded before run: analysis/DEMAND_COUPLING_PLAN.md.
Ideal bound min(target, P*T); no cropping of demand; no deletion of hard requests."""
import csv, json, sys, math, random, statistics
from collections import defaultdict
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
R = "research/round8_20261031"
P = 22.0
TARGETS = [1.0, 0.75, 0.5, 0.25]   # fraction of requested energy; pre-recorded, not chosen by results
c = json.load(open(R + "/data/processed/public_parking_events.json", encoding="utf-8"))
ev = c["events"]
req = [e for e in ev if e.get("is_ev") and e.get("needs_charge")]
print("charge requests", len(req), "demand kWh", round(sum(float(e["energy_kwh"]) for e in req), 2))
E = [float(e["energy_kwh"]) for e in req]; T = [float(e["dwell_min"]) / 60.0 for e in req]
def ideal(E, T, frac, P=22.0):
    n = len(E); dem = sum(E); dlv = 0.0; ok = 0
    for e, t in zip(E, T):
        cap = P * t; need = frac * e
        dlv += min(need, cap); ok += 1 if need <= cap + 1e-9 else 0
    return {"n": n, "demand_kwh": round(dem, 3), "delivered_kwh": round(dlv, 3),
            "energy_rate": dlv / dem if dem else None, "session_success": ok / n, "session_failure": 1 - ok / n}
out = []
for frac in TARGETS:
    for label, EE, TT in (("A_independent", E, T),):
        out.append(dict(scenario=label, target=frac, **ideal(EE, TT, frac)))
# Scenario B: dwell-conditioned charge intention with marginals matched to A.
# Mechanism: logistic propensity p(T)=1/(1+exp(-(a+b*(T-med)/sd))) then exact-count weighted sampling
# without replacement so the number of charge requests is unchanged; EV count and energy draws unchanged.
rng = random.Random(20261031)
Tmed = statistics.median(T); Tsd = statistics.pstdev(T)
b = 1.0  # pre-recorded correlation strength: one SD of dwell changes odds by e^1
def propensity(t):
    z = (t - Tmed) / (Tsd if Tsd else 1.0)
    return 1.0 / (1.0 + math.exp(-b * z))
# candidate pool: all EV events (incl. non-charging) -> re-select same count with dwell-weighted sampling
ev_all = [e for e in ev if e.get("is_ev")]
w = [propensity(float(e["dwell_min"]) / 60.0) for e in ev_all]
order = sorted(range(len(ev_all)), key=lambda i: -w[i] * rng.random())
chosen = set(order[: len(req)])
reqB = [ev_all[i] for i in sorted(chosen)]
assert len(reqB) == len(req), (len(reqB), len(req))
# energy marginals preserved: keep the same multiset E of A but assigned in rank order of dwell (E independent of T)
EB = sorted(E)  # same multiset
TB = [float(e["dwell_min"]) / 60.0 for e in reqB]
for frac in TARGETS:
    out.append(dict(scenario="B_dwell_conditioned", target=frac, **ideal(EB, TB, frac)))
with open(R + "/analysis/demand_coupling.csv", "w", newline="", encoding="utf-8") as f:
    w2 = csv.DictWriter(f, fieldnames=list(out[0].keys())); w2.writeheader(); w2.writerows(out)
for o in out:
    print("%-22s target=%.2f n=%d demand=%.1f delivered=%.1f rate=%.3f session_fail=%.3f"
          % (o["scenario"], o["target"], o["n"], o["demand_kwh"], o["delivered_kwh"], o["energy_rate"] or 0, o["session_failure"]))
print("A median dwell %.2f min, mean %.2f; B median %.2f, mean %.2f"
      % (statistics.median(T) * 60, statistics.mean(T) * 60, statistics.median(TB) * 60, statistics.mean(TB) * 60))
# dwell scaling sensitivity (stress test, not CI)
scale_rows = []
for s in (0.88, 1.0, 1.12):
    for frac in (1.0, 0.5):
        for label, EE, TT in (("A", E, T), ("B", EB, TB)):
            r = ideal(EE, [t * s for t in TT], frac)
            scale_rows.append({"scale": s, "scenario": label, "target": frac, "energy_rate": round(r["energy_rate"], 4),
                               "session_failure": round(r["session_failure"], 4)})
with open(R + "/analysis/dwell_scaling.csv", "w", newline="", encoding="utf-8") as f:
    w3 = csv.DictWriter(f, fieldnames=list(scale_rows[0].keys())); w3.writeheader(); w3.writerows(scale_rows)
print("--- dwell scaling ---")
for r in scale_rows: print(r)
# connector-only bound: max concurrent charge sessions per site-day (access feasibility, no energy)
sessions = defaultdict(list)
for e in req:
    day = e["arrival_ts"][:10]
    sessions[(e["site_id"], day)].append((e["arrival_ts"][11:19], float(e["dwell_min"])))
conc = []
for key, lst in sessions.items():
    pts = []
    for t, d in lst:
        h, m, s = [int(x) for x in t.split(":")]
        start = h * 60 + m + s / 60.0
        pts.append((start, 1)); pts.append((start + d, -1))
    pts.sort(key=lambda x: (x[0], x[1]))
    cur = mx = 0
    for _, dl in pts:
        cur += dl; mx = max(mx, cur)
    conc.append(mx)
print("max concurrent charge sessions per site-day: n=%d min=%d median=%.1f max=%d"
      % (len(conc), min(conc), statistics.median(conc), max(conc)))
