# -*- coding: utf-8 -*-
"""Graphical abstract for the submission package (Elsevier: 1328 x 531 px, 300 dpi)."""
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC = os.path.join(REPO, "data", "t5_summary", "paired_worlds_2026-11-04.csv")
OUT = os.path.join(REPO, "results", "figures", "graphical_abstract.png")

SITES = ["nyc-bri", "nyc-jgu", "nyc-jon", "nyc-qfa", "nyc-sge"]


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    for r in rows:
        r["d21"] = float(r["delta_S2_S1"])
        r["f21"] = float(r["fixed_config_delta_S2_S1"])
    mean = {s: sum(r["d21"] for r in rows if r["site_id"] == s) /
            len([r for r in rows if r["site_id"] == s]) for s in SITES}
    fixed = {s: sum(r["f21"] for r in rows if r["site_id"] == s) /
             len([r for r in rows if r["site_id"] == s]) for s in SITES}
    down = sum(1 for r in rows if r["d21"] < 0)

    fig = plt.figure(figsize=(1328 / 300, 531 / 300), dpi=300)
    ax = fig.add_axes([0.06, 0.20, 0.42, 0.66])
    x = range(len(SITES))
    ax.bar([i - 0.19 for i in x], [mean[s] for s in SITES], width=0.36,
           color="#2f6f9f", label="re-optimised")
    ax.bar([i + 0.19 for i in x], [fixed[s] for s in SITES], width=0.36,
           color="#b8c6d1", label="fixed at S1 bays")
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_xticks(list(x))
    ax.set_xticklabels([s.replace("nyc-", "") for s in SITES], fontsize=7)
    ax.set_ylabel("Mean paired difference, USD", fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    ax.legend(frameon=False, fontsize=6, loc="lower left")
    ax.set_title("Opening idle charging bays", fontsize=8)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax2 = fig.add_axes([0.52, 0.20, 0.44, 0.66])
    ax2.axis("off")
    box = FancyBboxPatch((0.02, 0.02), 0.96, 0.96, boxstyle="round,pad=0.02,rounding_size=0.04",
                         linewidth=0.8, edgecolor="#cccccc", facecolor="#f7f9fb")
    ax2.add_patch(box)
    lines = [
        ("Fixed parking capacity", "sizing and sharing are one decision", "#222222", 6.5, "bold"),
        ("%d of 120 worlds" % down, "lower the 7-day social cost", "#2f6f9f", 8.5, "bold"),
        ("-345.56 USD", "mean paired change, re-optimised", "#2f6f9f", 7, "bold"),
        ("-77.66 USD", "same rule, bay count held fixed", "#555555", 6.5, None),
        ("k_mob = 0.289", "mobile service dominated at declared costs", "#b03a48", 6.5, "bold"),
    ]
    y = 0.90
    for big, small, colour, size, weight in lines:
        ax2.text(0.06, y, big, fontsize=size, color=colour, weight=weight or "normal",
                 transform=ax2.transAxes, va="top")
        ax2.text(0.06, y - 0.095, small, fontsize=5.8, color="#444444", transform=ax2.transAxes,
                 va="top")
        y -= 0.185
    fig.text(0.06, 0.02, "Five New York sites; semi-synthetic stream; declared costs; "
             "descriptive paired evidence, not a field estimate.", fontsize=5.2, color="#666666")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT, dpi=300)
    print("wrote", OUT)


if __name__ == "__main__":
    main()