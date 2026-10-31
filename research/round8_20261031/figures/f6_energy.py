# -*- coding: utf-8 -*-
"""F6 - energy constraint against k, power and feeder capacity (experiment family E6).

Real input: experiments/E6/energy_E6.csv with columns
  site_id, k, power_kw, feeder_kw, energy_delivered_kwh, energy_required_kwh,
  shortfall_rate, feasible
Demo mode draws the layout only and stamps it as a placeholder.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style as S

FIG = "F6"
CAPTION = ("Energy feasibility against the number of equipped berths, charger power and "
           "the site feeder. (a) Energy shortfall rate on the k x power grid at the "
           "smallest tested feeder; the white line marks the feasible boundary and the "
           "chevrons mark the feeder-limited edge. (b) Shortfall against charger power for "
           "three feeder sizes at the selected k; points to the right of a feeder's limit "
           "are capped, not measured.")
FIELDS = ["site_id", "k", "power_kw", "feeder_kw", "energy_delivered_kwh",
          "energy_required_kwh", "shortfall_rate", "feasible"]
K_SEL = 12


def demo_data():
    rng = np.random.default_rng(31)
    k = np.arange(2, 21)
    powers = np.array([7.0, 11.0, 22.0, 43.0])
    feeder = 120.0
    shortfall = np.zeros((k.size, powers.size))
    for i, kv in enumerate(k):
        for j, pw in enumerate(powers):
            cap = min(kv * pw, feeder)
            demand = 0.9 * kv * pw * 0.55
            shortfall[i, j] = max(0.0, 1.0 - cap / demand) + rng.normal(0, 0.004)
    shortfall = np.clip(shortfall, 0.0, 0.65)
    feeders = np.array([60.0, 120.0, 240.0])
    pw_dense = np.linspace(6, 50, 12)
    curves = {}
    for f in feeders:
        curves[f] = np.clip(1.0 - np.minimum(K_SEL * pw_dense, f) /
                            (0.9 * K_SEL * pw_dense * 0.55), 0.0, 0.7)
    return {"k": k, "powers": powers, "shortfall": shortfall, "feeders": feeders,
            "pw_dense": pw_dense, "curves": curves, "k_sel": K_SEL,
            "feasible_boundary": [10, 7, 5, 3]}


def load_real(exp_root):
    rows, meta = S.read_csv(os.path.join(exp_root, "E6", "energy_E6.csv"),
                            ["k", "power_kw", "feeder_kw", "shortfall_rate"])
    ks = np.array(sorted({int(float(r["k"])) for r in rows}))
    pws = np.array(sorted({float(r["power_kw"]) for r in rows}))
    feeders = np.array(sorted({float(r["feeder_kw"]) for r in rows}))
    grid = np.full((ks.size, pws.size), np.nan)
    for r in rows:
        i, j = int(np.where(ks == int(float(r["k"])))[0][0]), int(np.where(pws == float(r["power_kw"]))[0][0])
        grid[i, j] = float(r["shortfall_rate"])
    curves = {}
    pw_dense = np.array([])
    for f in feeders:
        sub = sorted([r for r in rows if float(r["feeder_kw"]) == f
                      and int(float(r["k"])) == K_SEL], key=lambda r: float(r["power_kw"]))
        if sub:
            pw_dense = np.array([float(r["power_kw"]) for r in sub])
            curves[f] = np.array([float(r["shortfall_rate"]) for r in sub])
    return {"k": ks, "powers": pws, "shortfall": grid, "feeders": feeders,
            "pw_dense": pw_dense, "curves": curves, "k_sel": K_SEL,
            "inputs": [meta]}


def draw(data, demo):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.1, gridspec_kw={"width_ratios": [1.25, 1.0]})
    ax = axes[0]
    im = ax.imshow(data["shortfall"].T * 100.0, aspect="auto", origin="lower",
                   cmap="viridis", extent=[data["k"][0] - 0.5, data["k"][-1] + 0.5,
                                           -0.5, len(data["powers"]) - 0.5],
                   interpolation="nearest")
    ax.set_yticks(range(len(data["powers"])))
    ax.set_yticklabels(["%.0f kW" % p for p in data["powers"]])
    ax.set_xlabel("equipped berths k (count)")
    ax.set_ylabel("charger power")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label("energy shortfall rate (%)", fontsize=6)
    cb.ax.tick_params(labelsize=6)
    if "feasible_boundary" in data:
        ax.plot(data["feasible_boundary"], np.arange(len(data["powers"])),
                color="white", linewidth=1.0, linestyle="-")
    S.boundary_marker(ax, data["k"][-1], len(data["powers"]) - 1.5, "feeder-limited", dx=-10, dy=0)
    ax.grid(False)
    ax.set_title("shortfall on the k x power grid")
    S.panel_label(ax, "a")

    ax = axes[1]
    for i, f in enumerate(data["feeders"]):
        if f not in data["curves"] or data["curves"][f].size == 0:
            continue
        st = S.series_style(i)
        ax.plot(data["pw_dense"], data["curves"][f] * 100.0, label="feeder %.0f kW" % f, **st)
    ax.set_xlabel("charger power (kW)")
    ax.set_ylabel("energy shortfall rate (%)")
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", title="site feeder", fontsize=6)
    ax.set_title("k = %d, by feeder" % data["k_sel"])
    ax.text(0.03, 0.92, "values are capped at the feeder limit,\nnot outcomes beyond it",
            transform=ax.transAxes, fontsize=6.2, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "F6 | N and unit: one cell = one site-day at the given k and power; "
                  "energy shortfall = 1 - delivered kWh / required kWh, censored departures "
                  "reported separately; feeder limit is a physical constraint on installed "
                  "power, not a service standard.")
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
    print("F6", rec["status"], rec["outputs"])


if __name__ == "__main__":
    sys.exit(main())
