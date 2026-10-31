# -*- coding: utf-8 -*-
"""F1 - data coverage, arrival/dwell fit and hold-out error (experiment family E1).

Real inputs (research/round8_20261031/experiments/E1/):
  coverage.csv  - one row per site-day: site_id, day, share_observed, slots
  fit_metrics.csv - one row per parameter: fit_id, metric, value, unit
  fit_params.json - fitted arrival-rate and dwell parameters
Demo mode (--demo) draws the same layout with generated placeholder numbers and
stamps the figure as a placeholder: it is a layout check, not a result.
"""

import os
import sys

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F1"
CAPTION = ("Data coverage and arrival/dwell calibration. (a) Share of five-minute "
           "slots observed per site-day; open cells are missing days. "
           "(b) Dwell-time histogram with the fitted distribution. "
           "(c) Hold-out check of the fitted arrival/dwell model on held-out site-days.")
FIELDS = ["site_id", "day", "share_observed", "slots",
          "dwell_min", "dwell_shape", "dwell_scale",
          "holdout_observed_rate", "holdout_predicted_rate", "split"]
N_SITES = 6
N_DAYS = 14


def demo_data():
    rng = np.random.default_rng(20261031)
    share = np.clip(rng.normal(0.86, 0.10, size=(N_SITES, N_DAYS)), 0.25, 1.0)
    holes = rng.choice(N_SITES * N_DAYS, size=4, replace=False)
    share.flat[holes] = np.nan
    dwell = rng.gamma(shape=2.4, scale=52.0, size=900)
    obs = rng.uniform(0.02, 0.16, size=24)
    pred = obs + rng.normal(0.0, 0.012, size=24)
    return {"share": share, "dwell": dwell, "shape": 2.4, "scale": 52.0,
            "holdout_obs": obs, "holdout_pred": pred}


def load_real(exp_root):
    import json
    rows, meta_cov = S.read_csv(os.path.join(exp_root, "E1", "coverage.csv"),
                                ["site_id", "day", "share_observed"])
    sites = sorted({r["site_id"] for r in rows})
    days = sorted({r["day"] for r in rows})
    share = np.full((len(sites), len(days)), np.nan)
    for r in rows:
        share[sites.index(r["site_id"]), days.index(r["day"])] = float(r["share_observed"])
    mrows, meta_fit = S.read_csv(os.path.join(exp_root, "E1", "fit_metrics.csv"),
                                 ["metric", "value"])
    metrics = {r["metric"]: float(r["value"]) for r in mrows}
    hrows, meta_h = S.read_csv(os.path.join(exp_root, "E1", "holdout_metrics.csv"),
                               ["observed_rate", "predicted_rate"])
    with open(os.path.join(exp_root, "E1", "fit_params.json"), "r", encoding="utf-8") as fh:
        params = json.load(fh)
    return {"share": share, "sites": sites, "days": days,
            "dwell": None, "shape": params.get("dwell_shape"),
            "scale": params.get("dwell_scale"), "metrics": metrics,
            "holdout_obs": np.array([float(r["observed_rate"]) for r in hrows]),
            "holdout_pred": np.array([float(r["predicted_rate"]) for r in hrows]),
            "inputs": [meta_cov, meta_fit, meta_h,
                       {"path": os.path.join(exp_root, "E1", "fit_params.json")}]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 3, width=7.2, height=2.9)
    ax = axes[0]
    share = np.atleast_2d(data["share"])
    im = ax.imshow(np.ma.masked_invalid(share), aspect="auto", cmap="Blues",
                   vmin=0.0, vmax=1.0, interpolation="nearest")
    ax.set_xlabel("day index")
    ax.set_ylabel("site index")
    ax.set_title("coverage")
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    cb.ax.tick_params(labelsize=6)
    miss = int(np.isnan(share).sum())
    for i, j in zip(*np.where(np.isnan(share))):
        ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, facecolor="none",
                                   hatch="////", edgecolor="#666666", linewidth=0))
    S.panel_label(ax, "a")

    ax = axes[1]
    dwell = data["dwell"]
    if dwell is not None:
        ax.hist(dwell, bins=28, density=True, color=S.PALETTE["band"],
                edgecolor="white", linewidth=0.3)
        x = np.linspace(0, np.percentile(dwell, 99), 300)
        shape, scale = data["shape"], data["scale"]
        from math import gamma
        pdf = x ** (shape - 1) * np.exp(-x / scale) / (gamma(shape) * scale ** shape)
        ax.plot(x, pdf, color=S.PALETTE["A"], linewidth=1.3,
                label="fitted gamma\nshape=%.2f, scale=%.0f min" % (shape, scale))
        ax.legend(loc="upper right", fontsize=6)
    else:
        ax.text(0.5, 0.5, "dwell sample not in machine outputs\n(fit_params.json only)",
                ha="center", va="center", fontsize=7, transform=ax.transAxes)
    ax.set_xlabel("dwell time (min)")
    ax.set_ylabel("density (1/min)")
    ax.set_title("dwell fit")
    S.panel_label(ax, "b")

    ax = axes[2]
    obs, pred = data["holdout_obs"], data["holdout_pred"]
    lim = max(obs.max(), pred.max()) * 1.1
    ax.plot([0, lim], [0, lim], color=S.PALETTE["reference"], linewidth=0.8,
            linestyle=(0, (4, 2)))
    ax.scatter(obs, pred, s=14, facecolor="white", edgecolor=S.PALETTE["A"],
               linewidth=0.8, zorder=3)
    rmse = float(np.sqrt(np.mean((pred - obs) ** 2)))
    ax.text(0.04, 0.92, "RMSE = %.4f\nn = %d held-out site-days" % (rmse, obs.size),
            transform=ax.transAxes, fontsize=6.5, va="top")
    ax.set_xlabel("observed failure rate (%)")
    ax.set_ylabel("predicted failure rate (%)")
    ax.set_title("hold-out check")
    S.panel_label(ax, "c")
    S.n_note(fig, "F1 | N and unit: %d site-days in the coverage panel (colour = share of "
                  "five-minute slots observed, 0-1; hatched cells = %d missing site-days, not "
                  "zero coverage), %d site-days in the hold-out panel; one point = one site-day. "
                  "Panel b fits the calibration split." % (share.size, miss, obs.size))
    if demo:
        S.watermark(fig)
    fig.subplots_adjust(left=0.07, right=0.96, top=0.90, bottom=0.22, wspace=0.62)
    return fig


def build(mode="demo", outdir=None, experiments=None):
    experiments = experiments or S.EXPERIMENTS
    if mode == "demo":
        data = demo_data()
        outdir = outdir or S.DEMO_DIR
    else:
        data = load_real(experiments)
        outdir = outdir or S.HERE
    fig = draw(data, demo=(mode == "demo"))
    return S.save(fig, FIG, inputs=data.get("inputs", []), fields=FIELDS,
                  demo=(mode == "demo"), caption=CAPTION, outdir=outdir,
                  script=os.path.abspath(__file__),
                  note="demo layout check" if mode == "demo" else "from E1 machine outputs")


def main(argv=None):
    args = S.parse_args([FIG], __doc__.splitlines()[0])
    mode = "real" if args.real else "demo"
    rec = build(mode=mode, outdir=args.outdir, experiments=args.experiments)
    print("F1", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
