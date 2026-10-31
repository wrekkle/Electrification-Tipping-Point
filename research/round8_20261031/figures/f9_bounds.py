# -*- coding: utf-8 -*-
"""F9 (R8-F): ideal delivery bound and demand-dwell matching. Real machine outputs only."""
import csv, json, hashlib, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "research/round8_20261031"
OUT = ROOT + "/figures"
def rows(p):
    f = open(p, encoding="utf-8"); r = list(csv.DictReader(f)); f.close(); return r

ib = rows(ROOT + "/analysis/ideal_bound_allsites.csv")
dd = rows(ROOT + "/analysis/demand_dwell_matching.csv")
st = rows(ROOT + "/analysis/ideal_bound_streams.csv")

fig, axes = plt.subplots(1, 3, figsize=(13.2, 3.6), dpi=300)
gray = ["#111111", "#555555", "#999999", "#cccccc"]
# (a) ideal rate and session failure vs power
P = [float(r["P"]) for r in ib]
rate = [float(r["ideal_rate"]) for r in ib]
fail = [float(r["session_failure_rate"]) for r in ib]
axes[0].plot(P, [100 * x for x in rate], "o-", color=gray[0], lw=1.6, ms=5, label="ideal energy service rate")
axes[0].plot(P, [100 * x for x in fail], "s--", color=gray[1], lw=1.6, ms=5, label="session failure rate")
axes[0].axhline(5, color=gray[3], lw=1.0, ls=":")
axes[0].text(7, 8, "5% standard", fontsize=7, color=gray[1])
axes[0].set_xlabel("connector power (kW)"); axes[0].set_ylabel("percent")
axes[0].set_title("(a) ideal bound, all charge requests (n=6,588)", fontsize=8)
axes[0].set_xscale("log"); axes[0].set_xticks(P); axes[0].set_xticklabels([str(int(p)) for p in P])
axes[0].legend(fontsize=6, frameon=False); axes[0].grid(alpha=.25)
# (b) demand-dwell matching
E = [float(r["declared_energy_kwh"]) for r in dd]
r2 = [100 * float(r["ideal_energy_rate"]) for r in dd]
f2 = [100 * float(r["session_failure_rate"]) for r in dd]
axes[1].plot(E, r2, "o-", color=gray[0], lw=1.6, ms=5, label="ideal energy service rate")
axes[1].plot(E, f2, "s--", color=gray[1], lw=1.6, ms=5, label="session failure rate")
axes[1].axhline(5, color=gray[3], lw=1.0, ls=":")
axes[1].set_xlabel("declared energy per charging session (kWh)"); axes[1].set_ylabel("percent")
axes[1].set_title("(b) 22 kW: demand-dwell matching (n=6,588)", fontsize=8)
axes[1].legend(fontsize=6, frameon=False); axes[1].grid(alpha=.25)
# (c) per held-out stream ideal failure vs simulated unmet
sid = [r["site_id"][:12] + " " + r["day_key"][5:] for r in st]
failv = [100 * float(r["session_failure_rate"] or 0) for r in st]
axes[2].bar(range(len(st)), failv, color=gray[2], edgecolor=gray[0], lw=.5)
axes[2].axhline(5, color=gray[0], lw=1.0, ls=":")
axes[2].set_title("(c) held-out streams: dwell/power failure lower bound", fontsize=8)
axes[2].set_ylabel("session failure (%)"); axes[2].set_ylim(0, 105)
axes[2].set_xticks(range(len(st))); axes[2].set_xticklabels(sid, rotation=90, fontsize=3.5)
axes[2].grid(alpha=.25, axis="y")
fig.tight_layout()
for ext in ("png", "svg"):
    p = OUT + "/F9." + ext
    fig.savefig(p, dpi=300, bbox_inches="tight")
    print("wrote", p, os.path.getsize(p))
plt.close(fig)
# provenance entry
def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()
entry = {
 "figure": "F9", "status": "real",
 "caption_draft": "Ideal delivery upper bound and demand-dwell matching (R8-F analysis).",
 "script": ROOT + "/figures/f9_bounds.py", "script_sha256": sha(ROOT + "/figures/f9_bounds.py"),
 "inputs": [
   {"path": ROOT + "/analysis/ideal_bound_allsites.csv", "rows": len(ib), "sha256": sha(ROOT + "/analysis/ideal_bound_allsites.csv")},
   {"path": ROOT + "/analysis/demand_dwell_matching.csv", "rows": len(dd), "sha256": sha(ROOT + "/analysis/demand_dwell_matching.csv")},
   {"path": ROOT + "/analysis/ideal_bound_streams.csv", "rows": len(st), "sha256": sha(ROOT + "/analysis/ideal_bound_streams.csv")}],
 "notes": "min(E, P*T) upper bound; no connector/feeder constraint; 22 kW default; held-out 20 streams."
}
fp = OUT + "/FIGURES.json"
d = json.load(open(fp, encoding="utf-8"))
d["entries"] = [e for e in d["entries"] if e["figure"] != "F9"] + [entry]
json.dump(d, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("FIGURES.json entries:", len(d["entries"]), "real:", sum(1 for e in d["entries"] if e.get("status") == "real"))
