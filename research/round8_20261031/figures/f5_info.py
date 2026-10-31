# -*- coding: utf-8 -*-
"""F5 - per-stream change in k and service trade-off under the intention signal (E5).

Exploratory family: the comparison is between two implemented policies, not the
value of information.  Real input: experiments/E5/info_E5.csv with columns
  stream_id, policy_I0, policy_I1, k_I0, k_I1, delta_k, refused_delta_pp,
  ev_fail_delta_pp, icev_fail_delta_pp
Demo mode draws the layout only and stamps it as a placeholder.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F5"
CAPTION = ("Change in the smallest admissible k on each independent stream when the "
           "charging-intention field is added (condition I1 vs I0). (a) Paired k per "
           "stream, sorted by delta k; a negative delta means fewer equipped berths are "
           "needed under I1. (b) Service trade-off per stream; points off the y=0 line are "
           "cases where the signal changes the service rates as well as k. Exploratory "
           "result, not a value-of-information estimate.")
FIELDS = ["stream_id", "k_I0", "k_I1", "delta_k", "refused_delta_pp",
          "ev_fail_delta_pp", "icev_fail_delta_pp"]


def demo_data():
    rng = np.random.default_rng(23)
    n = 8
    k0 = rng.integers(6, 26, size=n)
    dk = np.clip(np.round(rng.normal(-2.0, 3.3, size=n)), -7, 4).astype(int)
    k1 = np.maximum(0, k0 + dk)
    return {"stream": ["T%02d" % i for i in range(1, n + 1)],
            "k0": k0, "k1": k1, "delta_k": dk,
            "refused": rng.normal(0.2, 0.9, size=n),
            "icev": rng.normal(-0.3, 1.1, size=n),
            "n_streams": n}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E5", "info_E5.csv"),
                            ["stream_id", "k_I0", "k_I1", "delta_k"])
    return {"stream": [r["stream_id"] for r in rows],
            "k0": np.array([int(float(r["k_I0"])) for r in rows]),
            "k1": np.array([int(float(r["k_I1"])) for r in rows]),
            "delta_k": np.array([int(float(r["delta_k"])) for r in rows]),
            "refused": np.array([float(r.get("refused_delta_pp") or 0.0) for r in rows]),
            "icev": np.array([float(r.get("icev_fail_delta_pp") or 0.0) for r in rows]),
            "n_streams": len(rows), "inputs": [meta]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.1, gridspec_kw={"width_ratios": [1.5, 1.0]})
    ax = axes[0]
    order = np.argsort(data["delta_k"])
    y = np.arange(len(order))
    k0 = data["k0"][order]
    k1 = data["k1"][order]
    for yi, a, b in zip(y, k0, k1):
        ax.plot([a, b], [yi, yi], color=S.PALETTE["band"], linewidth=1.4, zorder=1)
    ax.scatter(k0, y, marker="o", s=26, facecolor="white",
               edgecolor=S.PALETTE["info_I0"], linewidth=1.0, zorder=3, label="I0 (no signal)")
    ax.scatter(k1, y, marker="s", s=26, color=S.PALETTE["info_I1"], zorder=4,
               label="I1 (intention field)")
    ax.set_yticks(y)
    ax.set_yticklabels([data["stream"][i] for i in order], fontsize=6.5)
    ax.set_xlabel("smallest admissible k (berths)")
    ax.set_title("paired k per independent stream")
    ax.legend(loc="lower right")
    S.panel_label(ax, "a")

    ax = axes[1]
    ax.axhline(0.0, color=S.PALETTE["reference"], linewidth=0.8, linestyle=(0, (4, 2)))
    ax.scatter(data["refused"], data["icev"], s=24,
               facecolor=S.PALETTE["info_I1"], edgecolor="white", linewidth=0.5,
               zorder=3)
    for xi, yi, name in zip(data["refused"], data["icev"], data["stream"]):
        ax.annotate(name, (xi, yi), xytext=(3, 3), textcoords="offset points", fontsize=5.5)
    ax.set_xlabel("change in refused-request rate (percentage points)")
    ax.set_ylabel("change in ICEV failure rate (pp)")
    ax.set_title("service trade-off (I1 - I0)")
    n_better = int((data["delta_k"] < 0).sum())
    ax.text(0.03, 0.03, "k lower in %d/%d streams; not uniformly better\n(service rates "
            "are not monotone in k)" % (n_better, data["n_streams"]),
            transform=ax.transAxes, fontsize=6.2, va="bottom")
    S.panel_label(ax, "b")
    S.n_note(fig, "F5 | N and unit: %d independent exogenous streams, paired within stream "
                  "(same stream_id under both policies); the interval is not a sample size. "
                  "Exploratory: direction shown per stream, no confirmatory claim."
                  % data["n_streams"])
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.10, right=0.98, top=0.90, bottom=0.20, wspace=0.42)
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
    print("F5", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
