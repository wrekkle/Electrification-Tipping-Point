# -*- coding: utf-8 -*-
"""F2 - k vs service rate with uncertainty (experiment family E2).

Real input: experiments/E2/curve_E2.csv with columns
  k, rule, service_rate, lower, upper, n_site_days, selection, alpha
Demo mode draws the layout only and stamps it as a placeholder.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F2"
CAPTION = ("Service rate against the integer number of equipped berths k. "
           "Solid line: mean over replayed site-days; band: 95% interval from the "
           "site-day bootstrap. Dashed line: tolerance alpha; filled marker: selected "
           "k under the risk-margin rule. Open chevron: search range ended before the "
           "tolerance was met (grid truncated, not infeasible).")
FIELDS = ["k", "rule", "service_rate", "lower", "upper", "n_site_days", "alpha"]
K_MAX = 40


def demo_data():
    rng = np.random.default_rng(7)
    k = np.arange(0, K_MAX + 1)
    out = {}
    for i, rule in enumerate(("dedicated", "shared")):
        rate = 5.0 + 62.0 * np.exp(-(k + 1) / (6.5 + 1.5 * i))
        band = 1.6 + 0.8 * np.exp(-k / 12.0)
        out[rule] = {"rate": rate + rng.normal(0, 0.15, size=k.size),
                     "lo": rate - band, "hi": rate + band}
    sel = {"dedicated": 13, "shared": 11}
    return {"k": k, "curves": out, "selected": sel, "alpha": S.TOLERANCE_PCT,
            "n_site_days": 96, "truncated": {}}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E2", "curve_E2.csv"),
                            ["k", "rule", "service_rate", "lower", "upper", "n_site_days"])
    curves = {}
    for rule in sorted({r["rule"] for r in rows}):
        sub = sorted([r for r in rows if r["rule"] == rule], key=lambda r: int(r["k"]))
        curves[rule] = {
            "rate": np.array([float(r["service_rate"]) for r in sub]),
            "lo": np.array([float(r["lower"]) for r in sub]),
            "hi": np.array([float(r["upper"]) for r in sub]),
        }
    k = np.array([int(r["k"]) for r in sorted(rows, key=lambda r: int(r["k"]))])
    selected, truncated = {}, {}
    for rule in curves:
        sub = [r for r in rows if r["rule"] == rule]
        sel = [r for r in sub if str(r.get("selection", "")).lower() in ("1", "true", "selected")]
        selected[rule] = int(sel[0]["k"]) if sel else None
        truncated[rule] = any(str(r.get("truncated", "")).lower() in ("1", "true") for r in sub)
    n = int(float(rows[0]["n_site_days"]))
    return {"k": k, "curves": curves, "selected": selected, "alpha": S.TOLERANCE_PCT,
            "n_site_days": n, "truncated": truncated, "inputs": [meta]}


def draw(data, demo):
    fig, ax = S.new_fig(1, 1, width=4.6, height=3.2)
    k = data["k"]
    for i, (rule, curve) in enumerate(sorted(data["curves"].items())):
        st = S.series_style(i, rule if rule in S.PALETTE else None)
        ax.fill_between(k, curve["lo"], curve["hi"], color=st["color"], alpha=0.16,
                        linewidth=0)
        ax.plot(k, curve["rate"], label=rule, **st)
        sel = data["selected"].get(rule)
        if sel is not None:
            j = int(np.argmin(np.abs(k - sel)))
            ax.plot([k[j]], [curve["rate"][j]], marker="o", markersize=6,
                    markerfacecolor=st["color"], markeredgecolor="white",
                    markeredgewidth=0.8, linestyle="none", zorder=6)
            ax.annotate("k* = %d" % k[j], (k[j], curve["rate"][j]),
                        xytext=(6, 8), textcoords="offset points", fontsize=6.5,
                        color=st["color"])
        if data["truncated"].get(rule, False):
            S.boundary_marker(ax, k[-1], curve["rate"][-1], "grid truncated", dx=-12, dy=4)
    S.tolerance_line(ax, data["alpha"], "alpha = %.0f%%" % data["alpha"])
    ax.set_xlabel("equipped berths k (count)")
    ax.set_ylabel("service failure rate (%)")
    ax.set_xlim(0, k[-1] + 1)
    ax.set_ylim(bottom=0)
    ax.legend(loc="upper right", title="rule")
    S.n_note(fig, "F2 | N and unit: %d held-out site-days replayed at each k; one k-step is one "
                  "point, the band is the site-day bootstrap interval (not the number of draws). "
                  "Interval is conditional on the tested model and scenario range."
                  % data.get("n_site_days", 0))
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.14, right=0.97, top=0.95, bottom=0.20)
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
    print("F2", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
