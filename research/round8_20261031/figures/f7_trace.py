# -*- coding: utf-8 -*-
"""F7 - non-monotone event trajectory on one instance (experiment family E7).

Illustrative family: one selected counter-example trace.  Real input:
experiments/E7/traj_E7.csv with columns
  time_h, config, equipped_occupied, ev_waiting, icev_rejected, ev_failed,
  event_type, event_class
Demo mode draws the layout only and stamps it as a placeholder.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F7"
CAPTION = ("Event trajectory on one selected instance where one extra equipped bay lowers "
           "ICEV parking failures. (a) Equipped bays in use over the operating window under "
           "k and k-1; hatching marks the extra bay. (b) Cumulative failures under the two "
           "configurations; the ICEV curve of k sits below that of k-1 while the EV curve "
           "is above it, which is the non-monotone response reported in the text.")
FIELDS = ["time_h", "config", "equipped_occupied", "event_type",
          "event_class", "cum_icev_failed", "cum_ev_failed"]


def demo_data():
    rng = np.random.default_rng(101)
    t = np.arange(0, 24, 0.25)
    base = 6 + 4.2 * np.sin((t - 7.0) / 24.0 * 2 * np.pi) + rng.normal(0, 0.5, t.size)
    occ = {"k": np.clip(np.round(base + 0.7), 0, 12).astype(int),
           "k-1": np.clip(np.round(base), 0, 11).astype(int)}
    icev_k = np.maximum.accumulate(np.clip(occ["k"] - 11 + 1, 0, None))
    icev_km1 = np.maximum.accumulate(np.clip(occ["k-1"] - 10 + 1, 0, None))
    ev_k = np.cumsum(np.clip(occ["k"] - 11, 0, None))
    ev_km1 = np.cumsum(np.clip(occ["k-1"] - 10, 0, None))
    events = {"t": t[::9], "type": rng.choice(["EV request", "ICEV request", "departure"],
                                              size=t[::9].size)}
    return {"t": t, "occ": occ, "icev": {"k": icev_k, "k-1": icev_km1},
            "ev": {"k": ev_k, "k-1": ev_km1}, "events": events, "k": 12}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E7", "traj_E7.csv"),
                            ["time_h", "config", "equipped_occupied"])
    configs = sorted({r["config"] for r in rows})
    t = np.array(sorted({float(r["time_h"]) for r in rows}))
    occ = {}
    for cfg in configs:
        sub = sorted([r for r in rows if r["config"] == cfg], key=lambda r: float(r["time_h"]))
        occ[cfg] = np.array([int(float(r["equipped_occupied"])) for r in sub])
    icev, ev = {}, {}
    for cfg in configs:
        sub = sorted([r for r in rows if r["config"] == cfg], key=lambda r: float(r["time_h"]))
        icev[cfg] = np.array([float(r.get("cum_icev_failed") or 0.0) for r in sub])
        ev[cfg] = np.array([float(r.get("cum_ev_failed") or 0.0) for r in sub])
    return {"t": t, "occ": occ, "icev": icev, "ev": ev, "k": None,
            "configs": configs, "inputs": [meta]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.0)
    ax = axes[0]
    configs = list(data["occ"].keys())
    for i, cfg in enumerate(configs):
        st = S.series_style(i, "dedicated" if i == 0 else "shared")
        st2 = dict(st)
        st2["markersize"] = 2.2
        ax.step(data["t"], data["occ"][cfg], where="post",
                label="k = %s" % cfg if data.get("k") is None else cfg,
                markevery=6, **st2)
    ax.set_xlabel("time of day (h)")
    ax.set_ylabel("equipped bays in use (count)")
    ax.set_xlim(data["t"][0], data["t"][-1])
    ax.legend(loc="upper left", title="configuration")
    ax.set_title("equipped-bay occupancy")
    S.panel_label(ax, "a")

    ax = axes[1]
    styles = [(0, ("k", "icev"), "ICEV, k"), (1, ("k", "ev"), "EV, k"),
              (2, ("k-1", "icev"), "ICEV, k-1"), (3, ("k-1", "ev"), "EV, k-1")]
    for i, (cfg, kind), label in styles:
        src = data[kind].get(cfg)
        if src is None:
            continue
        st = S.series_style(i)
        ax.plot(data["t"], src, label=label, **st)
    ax.set_xlabel("time of day (h)")
    ax.set_ylabel("cumulative failures (count)")
    ax.set_xlim(data["t"][0], data["t"][-1])
    ax.legend(loc="upper left")
    ax.set_title("cumulative failures")
    ax.text(0.97, 0.30, "one extra bay:\nICEV failures lower,\nEV failures higher",
            transform=ax.transAxes, ha="right", fontsize=6.2)
    S.panel_label(ax, "b")
    S.n_note(fig, "F7 | N and unit: one selected instance, one operating window, two "
                  "configurations replayed on the same exogenous stream. Illustrative "
                  "trajectory, not a population estimate; the instance selection rule is "
                  "reported in the text.")
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.90, bottom=0.20, wspace=0.35)
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
    print("F7", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
