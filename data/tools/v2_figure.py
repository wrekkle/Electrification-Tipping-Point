#!/usr/bin/env python3
"""Figure 1 for the v8 draft: V2 reliability (pooled overload rate vs nominal) and
cell disposition (tested / censored / no_cert) under the default D convention.

Reads data/demand/v2_holdout.json (row level + summary); writes
docs/reports/figs/v2_reliability_2026-11-02.png.  Requires matplotlib.
"""
import json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "docs", "reports", "figs", "v2_reliability_2026-11-02.png")
d = json.load(open(os.path.join(ROOT, "data", "demand", "v2_holdout.json"), encoding="utf-8"))
S = d["summary"]
RHOS = [0.10, 0.15, 0.20]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.2))

for conv, style in (("D", dict(marker="o", linestyle="-", color="C0")),
                    ("A", dict(marker="s", linestyle="--", color="C1"))):
    rows = [a for a in S[conv]["kfold"]]
    xs = [a["rho"] for a in rows]
    ys = [a["pooled_rate"] for a in rows]
    ax1.plot(xs, ys, label=f"convention {conv} (3-fold)", **style)
    for x, y, a in zip(xs, ys, rows):
        ax1.annotate(f'{a["tested"]}', (x, y), textcoords="offset points",
                     xytext=(0, -14), ha="center", fontsize=8, color=style["color"])
lim = [0.0, 0.235]
ax1.plot(lim, lim, color="0.6", lw=1, label="observed = nominal")
ax1.set_xlim(0.08, 0.22)
ax1.set_ylim(*lim)
ax1.set_xlabel("nominal overload risk $\\rho$")
ax1.set_ylabel("pooled held-out overload rate")
ax1.set_title("(a) reliability of the Prop.10 certificate")
ax1.legend(fontsize=8, loc="upper left")
ax1.grid(alpha=0.3)

width = 0.26
for i, rho in enumerate(RHOS):
    a = [x for x in S["D"]["kfold"] if abs(x["rho"] - rho) < 1e-9][0]
    bottom = 0
    for key, color, lab in (("tested", "C2", "tested"), ("censored", "C7", "censored"),
                            ("no_cert", "C3", "no certificate")):
        v = a[key]
        ax2.bar(i, v, width, bottom=bottom, color=color, label=lab if i == 0 else None)
        bottom += v
    ax2.annotate(f'{a["tested"]}/{a["censored"]}/{a["no_cert"]}', (i, bottom + 0.4),
                 ha="center", fontsize=8)
ax2.set_xticks(range(len(RHOS)))
ax2.set_xticklabels([f"$\\rho$={r:.2f}" for r in RHOS])
ax2.set_ylabel("cells (12 garages x 3 folds)")
ax2.set_title("(b) what the 99 cells of one risk grid actually contain")
ax2.legend(fontsize=8)
ax2.grid(alpha=0.3, axis="y")

fig.suptitle("NYC municipal garages: out-of-sample calibration of daily-peak certificates (D default; annotation = tested cells)", fontsize=9)
fig.tight_layout(rect=[0, 0, 1, 0.94])
os.makedirs(os.path.dirname(OUT), exist_ok=True)
fig.savefig(OUT, dpi=160)
print("written", OUT)
for conv in ("D", "A"):
    print(conv, [(a["rho"], a["tested"], a["censored"], a["no_cert"], round(a["pooled_rate"], 4)) for a in S[conv]["kfold"]])
