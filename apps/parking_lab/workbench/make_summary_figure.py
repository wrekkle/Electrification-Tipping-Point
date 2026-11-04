# -*- coding: utf-8 -*-
"""Public summary figure for the three-scheme comparison.

Reads the published derived table (120 evaluation worlds, one paired
difference per world) and writes results/figures/T5_scheme_summary.png.
"""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(REPO, "data", "t5_summary", "paired_worlds_2026-11-04.csv")
OUT = os.path.join(REPO, "results", "figures", "T5_scheme_summary.png")

SITE_ORDER = ["nyc-bri", "nyc-jgu", "nyc-jon", "nyc-qfa", "nyc-sge"]
COLOURS = {"nyc-bri": "#2f6f9f", "nyc-jgu": "#4f9d69", "nyc-jon": "#c46a2f",
           "nyc-qfa": "#8a5fa8", "nyc-sge": "#b03a48"}


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    for r in rows:
        r["d21"] = float(r["delta_S2_S1"])
        r["f21"] = float(r["fixed_config_delta_S2_S1"])
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10.5, 4.2),
                                   gridspec_kw={"width_ratios": [1.35, 1]})

    for i, site in enumerate(SITE_ORDER):
        vals = [r["d21"] for r in rows if r["site_id"] == site]
        xs = [i + (j - (len(vals) - 1) / 2) * 0.022 for j in range(len(vals))]
        ax1.scatter(xs, vals, s=14, color=COLOURS[site], alpha=0.75, linewidths=0)
        ax1.hlines(sum(vals) / len(vals), i - 0.28, i + 0.28, color="black", linewidth=1.6)
    ax1.axhline(0, color="grey", linewidth=1, linestyle="--")
    ax1.set_xticks(range(len(SITE_ORDER)))
    ax1.set_xticklabels(SITE_ORDER)
    ax1.set_ylabel("Paired difference in 7-day social cost, USD")
    ax1.set_title("(a) Re-optimised minus dedicated, one point per world", fontsize=10)
    ax1.grid(axis="y", color="#dddddd", linewidth=0.6)

    means_re = [sum(r["d21"] for r in rows if r["site_id"] == s) /
                len([r for r in rows if r["site_id"] == s]) for s in SITE_ORDER]
    means_fx = [sum(r["f21"] for r in rows if r["site_id"] == s) /
                len([r for r in rows if r["site_id"] == s]) for s in SITE_ORDER]
    x = range(len(SITE_ORDER))
    ax2.bar([i - 0.19 for i in x], means_re, width=0.36, color="#2f6f9f",
            label="re-optimised")
    ax2.bar([i + 0.19 for i in x], means_fx, width=0.36, color="#b8c6d1",
            label="fixed at S1 bays")
    ax2.axhline(0, color="grey", linewidth=1)
    ax2.set_xticks(list(x))
    ax2.set_xticklabels(SITE_ORDER, fontsize=9)
    ax2.set_ylabel("Mean paired difference, USD")
    ax2.set_title("(b) Operating effect and re-sizing effect", fontsize=10)
    ax2.legend(frameon=False, fontsize=8)
    ax2.grid(axis="y", color="#dddddd", linewidth=0.6)

    allv = [r["d21"] for r in rows]
    down = sum(1 for v in allv if v < 0)
    fig.suptitle("Shared opening of idle charging bays: %d of %d evaluation worlds "
                 "lower the seven-day social cost (mean %.0f USD)" %
                 (down, len(allv), sum(allv) / len(allv)), fontsize=10.5)
    fig.text(0.01, 0.005, "Semi-synthetic three-class stream built from New York parking "
             "records; declared cost scenario; 120 evaluation worlds from five sites. "
             "Descriptive, not a field estimate.", fontsize=7, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 0.94))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=200)
    print("wrote", OUT)
    print("worlds", len(rows), "down", down, "mean", round(sum(allv) / len(allv), 3))


if __name__ == "__main__":
    main()