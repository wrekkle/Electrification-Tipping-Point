# -*- coding: utf-8 -*-
"""F3 - feasible configuration set and minimality classes (experiment family E3).

Real input: experiments/E3/search_E3.csv with columns
  site_id, rule, seed, k, feasible, minimality_class, alpha
Demo mode draws the layout only and stamps it as a placeholder.

The classes are exactly those of DESIGN_MATRIX.json E3: confirmed_minimal,
minimality_unconfirmed, physically_infeasible, budget_not_covered, missing_data.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F3"
CAPTION = ("Feasible configuration set and minimality class per site-rule cell. "
           "(a) Minimality class of the smallest admissible k, one cell per site x rule. "
           "(b) Class counts over the enumerated grid; the empty-set and truncated-range "
           "counts are reported next to the bars rather than merged.")
FIELDS = ["site_id", "rule", "k", "feasible", "minimality_class", "alpha"]


def demo_data():
    rng = np.random.default_rng(11)
    sites = ["S%02d" % i for i in range(1, 7)]
    rules = ["A", "B", "C", "D", "B0_FCFS", "B1_quota", "B2_literature"]
    grid = rng.choice(S.CLASS_ORDER, size=(len(sites), len(rules)),
                      p=[0.55, 0.15, 0.12, 0.06, 0.12])
    return {"sites": sites, "rules": rules, "grid": grid,
            "k_min": rng.integers(4, 30, size=grid.shape),
            "empty_cells": 3, "truncated_cells": 9, "alpha": S.TOLERANCE_PCT}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E3", "search_E3.csv"),
                            ["site_id", "rule", "minimality_class"])
    sites = sorted({r["site_id"] for r in rows})
    rules = sorted({r["rule"] for r in rows})
    grid = np.empty((len(sites), len(rules)), dtype=object)
    grid[:] = "missing_data"
    kmin = np.full(grid.shape, np.nan)
    for r in rows:
        i, j = sites.index(r["site_id"]), rules.index(r["rule"])
        grid[i, j] = r["minimality_class"]
        if r.get("k") not in (None, ""):
            kmin[i, j] = float(r["k"])
    return {"sites": sites, "rules": rules, "grid": grid, "k_min": kmin,
            "alpha": S.TOLERANCE_PCT, "inputs": [meta]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.0, gridspec_kw={"width_ratios": [2.1, 1.0]})
    ax = axes[0]
    grid = data["grid"]
    for i, cls in enumerate(S.CLASS_ORDER):
        st = S.series_style(i, cls)
        ii, jj = np.where(grid == cls)
        ax.scatter(jj, ii, s=42, marker=st["marker"], color=st["color"],
                   edgecolor="white", linewidth=0.6,
                   label=cls.replace("_", " "), zorder=3)
    ax.set_xticks(range(len(data["rules"])))
    ax.set_xticklabels(data["rules"], rotation=35, ha="right")
    ax.set_yticks(range(len(data["sites"])))
    ax.set_yticklabels(data["sites"])
    ax.set_xlim(-0.7, len(data["rules"]) - 0.3)
    ax.set_ylim(len(data["sites"]) - 0.4, -0.6)
    ax.set_xlabel("rule")
    ax.set_ylabel("site")
    ax.grid(True, linewidth=0.4)
    ax.set_title("minimality class per site-rule cell")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.42), ncol=3,
              fontsize=6, handletextpad=0.3, columnspacing=0.8)
    S.panel_label(ax, "a")

    ax = axes[1]
    labels = [c.replace("_", " ") for c in S.CLASS_ORDER]
    counts = [int((grid == c).sum()) for c in S.CLASS_ORDER]
    colors = [S.series_style(i, c)["color"] for i, c in enumerate(S.CLASS_ORDER)]
    y = np.arange(len(labels))
    ax.barh(y, counts, color=colors, height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    for yi, c in zip(y, counts):
        ax.text(c + 0.3, yi, str(c), va="center", fontsize=6.5)
    ax.set_xlabel("cells (count)")
    empty = data.get("empty_cells", 0)
    trunc = data.get("truncated_cells", 0)
    ax.set_title("class counts")
    S.panel_label(ax, "b")
    S.n_note(fig, "F3 | N and unit: %d site-rule cells, one cell per site x rule; grid "
                  "enumerated on integers 0..K_max and every class is recorded, not inferred. "
                  "Empty admissible set in %d cells; range truncated at K_max in %d cells."
                  % (grid.size, empty, trunc))
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.92, bottom=0.42, wspace=0.55)
    return fig


def build(mode="demo", outdir=None, experiments=None):
    experiments = experiments or S.EXPERIMENTS
    if mode == "demo":
        data, outdir = demo_data(), outdir or S.DEMO_DIR
    else:
        data = load_real(experiments)
        outdir = outdir or S.HERE
    fig = draw(data, demo=(mode == "demo"))
    return S.save(fig, FIG, inputs=data.get("inputs", []), fields=FIELDS,
                  demo=(mode == "demo"), caption=CAPTION, outdir=outdir,
                  script=os.path.abspath(__file__))


def main(argv=None):
    args = S.parse_args([FIG], __doc__.splitlines()[0])
    rec = build(mode="real" if args.real else "demo", outdir=args.outdir,
                experiments=args.experiments)
    print("F3", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
