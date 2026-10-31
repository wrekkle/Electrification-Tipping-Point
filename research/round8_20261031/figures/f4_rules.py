# -*- coding: utf-8 -*-
"""F4 - rules and baselines on the held-out test (experiment family E4).

Real input: experiments/E4/test_E4.csv with columns
  rule, service_rate, rate_kind, mean, lower, upper, n_site_days, alpha
where rate_kind is one of refused / ev_parking_failure / icev_parking_failure.
Demo mode draws the layout only and stamps it as a placeholder.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F4"
CAPTION = ("Independent-test performance of the allocation rules and the baseline set. "
           "Points are means over held-out site-days with 95% interval bars; the dashed "
           "line is the tolerance. B0 FCFS, B1 fixed quota and B2 literature-adapted are "
           "baselines; B2 is offline and not online executable where flagged.")
FIELDS = ["rule", "rate_kind", "mean", "lower", "upper", "n_site_days", "alpha"]
RULES = ["A", "B", "C", "D", "B0_FCFS", "B1_quota", "B2_literature"]
RATE_KINDS = [("refused", "no compatible berth"), ("ev_parking_failure", "EV parking"),
              ("icev_parking_failure", "ICEV parking")]


BASE_BY_KIND = {
    "refused": {"A": 2.1, "B": 2.6, "C": 3.4, "D": 3.0,
                "B0_FCFS": 4.1, "B1_quota": 3.8, "B2_literature": 2.9},
    "ev_parking_failure": {"A": 1.4, "B": 1.7, "C": 2.2, "D": 1.9,
                           "B0_FCFS": 2.6, "B1_quota": 2.4, "B2_literature": 2.0},
    "icev_parking_failure": {"A": 1.1, "B": 1.5, "C": 1.9, "D": 1.6,
                             "B0_FCFS": 2.3, "B1_quota": 2.1, "B2_literature": 1.8},
}


def demo_data():
    rng = np.random.default_rng(4)
    out = {}
    for kind, _ in RATE_KINDS:
        base = BASE_BY_KIND[kind]
        out[kind] = {rule: (base[rule] + rng.normal(0, 0.18), 0.35 + 0.05 * i)
                     for i, rule in enumerate(RULES)}
    return {"data": out, "n": 96, "alpha": S.TOLERANCE_PCT}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E4", "test_E4.csv"),
                            ["rule", "rate_kind", "mean", "lower", "upper", "n_site_days"])
    data = {}
    for r in rows:
        data.setdefault(r["rate_kind"], {})[r["rule"]] = (
            float(r["mean"]), float(r["upper"]) - float(r["mean"]))
    n = int(float(rows[0]["n_site_days"]))
    return {"data": data, "n": n, "alpha": S.TOLERANCE_PCT, "inputs": [meta]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 3, width=7.2, height=3.0, sharey=True)
    for ax, (kind, label) in zip(axes, RATE_KINDS):
        curve = data["data"].get(kind, {})
        y = np.arange(len(RULES))
        for i, rule in enumerate(RULES):
            if rule not in curve:
                ax.plot([np.nan], [i], marker="x", color="grey", markersize=5,
                        linestyle="none")
                continue
            mean, err = curve[rule]
            st = S.series_style(i, rule if rule in S.PALETTE else None)
            ax.errorbar(mean, i, xerr=err, fmt=st["marker"], color=st["color"],
                        ecolor=st["color"], elinewidth=0.8, capsize=2,
                        markersize=4, linestyle="none")
        S.tolerance_line(ax, data["alpha"], vertical=True)
        ax.set_xlabel("failure rate (%)")
        ax.set_title(label)
        ax.set_yticks(y)
        ax.set_yticklabels(RULES)
        ax.set_xlim(0, max(6.0, data["alpha"] * 1.6))
    S.panel_label(axes[0], "a")
    S.panel_label(axes[1], "b")
    S.panel_label(axes[2], "c")
    S.n_note(fig, "F4 | N and unit: %d held-out site-days per rule; interval bars are the "
                  "site-day bootstrap 95%% interval. B2 is a literature-adapted baseline; "
                  "where it uses future information it is an offline upper bound, not an "
                  "online-executable rule. Same replayed stream within each site-day."
                  % data.get("n", 0))
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.12, right=0.98, top=0.90, bottom=0.22, wspace=0.28)
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
    print("F4", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
