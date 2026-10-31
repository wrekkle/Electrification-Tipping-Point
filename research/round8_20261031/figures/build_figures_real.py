# -*- coding: utf-8 -*-
"""Build the round-8 real figures F1-F7 and SI S1-S4 from machine outputs.

Primary regime = research/round8_20261031/experiments_main22/ (22 kW declared
scenario layer, decidable online metrics).  The 7 kW regime
(research/round8_20261031/experiments/, run label scenario_charging_layer_not_observed)
is used only as the infeasibility / sensitivity case.  No synthetic output is read.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import style as S

ROUND = os.path.dirname(HERE)
MAIN22 = os.path.join(ROUND, "experiments_main22")
BASE7 = os.path.join(ROUND, "experiments")

SEED = 20261031
N_BOOT = 1000


def csv2(relpath, required, root=None):
    root = root or MAIN22
    rows, meta = S.read_csv(os.path.join(root, relpath), required)
    return rows, {"path": meta["path"], "rows": meta["rows"], "fields": meta["fields"]}


def fnum(x, default=None):
    try:
        if x is None or str(x).strip() == "":
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def boot_ci(values, rng):
    vals = np.asarray([v for v in values if v is not None], dtype=float)
    if vals.size == 0:
        return None, None
    means = np.empty(N_BOOT)
    for i in range(N_BOOT):
        means[i] = vals[rng.integers(0, vals.size, vals.size)].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def mean_ci(rows, field, rng):
    vals = [fnum(r.get(field)) for r in rows]
    m = float(np.mean([v for v in vals if v is not None]))
    lo, hi = boot_ci(vals, rng)
    return m, lo, hi


# --------------------------------------------------------------------- F1 data
def fig_f1():
    cov, m1 = csv2("E1/coverage.csv", ["site_id", "events", "site_days", "n_spaces",
                                       "charging_bays", "connectors"])
    fit, m2 = csv2("E1/fit_metrics.csv", ["row_kind", "category", "ks_statistic"])
    fp_path = os.path.join(MAIN22, "E1", "fit_params.json")
    fp = json.load(open(fp_path, encoding="utf-8"))
    dwell = [r for r in fit if r["row_kind"] == "dwell_fit"]
    arrival = [r for r in fit if r["row_kind"] == "arrival_fit"]
    return {"cov": cov, "dwell": dwell, "arrival": arrival[0], "fp": fp,
            "inputs": [m1, m2, {"path": fp_path, "rows": 1,
                                "fields": ["n_sites", "n_site_days", "n_events", "criteria"]}]}


def draw_f1(d):
    fig, axes = S.new_fig(1, 3, width=7.2, height=3.0)
    cov = sorted(d["cov"], key=lambda r: -int(r["site_days"]))
    ax = axes[0]
    y = np.arange(len(cov))
    sd = [int(r["site_days"]) for r in cov]
    ax.barh(y, sd, color=S.PALETTE["A"], height=0.62, label="complete site-days")
    ax.set_yticks(y)
    ax.set_yticklabels([r["site_id"] for r in cov], fontsize=6)
    ax.invert_yaxis()
    ax.set_xlabel("complete site-days")
    ax.set_title("coverage by site")
    for yi, r in zip(y, cov):
        ax.text(int(r["site_days"]) + 1, yi, "n=%s" % r["events"], va="center", fontsize=5.6)
    ax.text(0.02, 0.04, "total %d site-days, %d events" % (sum(sd), d["fp"]["n_events"]),
            transform=ax.transAxes, fontsize=6, va="bottom")
    S.panel_label(ax, "a")

    ax = axes[1]
    cats = [r["category"] for r in d["dwell"]]
    x = np.arange(len(cats))
    mc = [float(r["mean_calibration"]) for r in d["dwell"]]
    mt = [float(r["mean_test"]) for r in d["dwell"]]
    ax.bar(x - 0.19, mc, 0.36, color=S.PALETTE["A"], label="calibration")
    ax.bar(x + 0.19, mt, 0.36, color=S.PALETTE["B"], label="hold-out")
    for xi, r in zip(x, d["dwell"]):
        ax.text(xi, max(float(r["mean_calibration"]), float(r["mean_test"])) + 1.5,
                "KS=%.4f" % float(r["ks_statistic"]), ha="center", fontsize=5.6)
    ax.set_xticks(x)
    ax.set_xticklabels([c.upper() if c != "all" else "all" for c in cats])
    ax.set_ylabel("mean dwell (min)")
    ax.set_title("dwell calibration vs hold-out")
    ax.legend(loc="lower right", fontsize=6)
    S.panel_label(ax, "b")

    ax = axes[2]
    rel = [float(r["holdout_mean_rel_error"]) * 100.0 for r in d["dwell"]]
    ax.bar(x, rel, 0.55, color=S.PALETTE["D"])
    for xi, v in zip(x, rel):
        ax.text(xi, v + 0.25, "%.2f%%" % v, ha="center", fontsize=6)
    ax.set_xticks(x)
    ax.set_xticklabels([c.upper() if c != "all" else "all" for c in cats])
    ax.set_ylabel("mean relative error (%)")
    ax.set_title("hold-out mean error")
    ar = d["arrival"]
    ax.text(0.03, 0.96, "arrival-gap KS=%.4f\nmean gap %.2f -> %.2f min\nenergy_kWh present on %d/%d events"
            % (float(ar["ks_statistic"]), float(ar["mean_gap_calibration"]),
               float(ar["mean_gap_test"]), d["fp"]["missing"]["energy_kwh"] == 0 and 0 or
               d["fp"]["criteria"][-1]["value"]["energy_kwh"], d["fp"]["n_events"]),
            transform=ax.transAxes, fontsize=5.6, va="top")
    S.panel_label(ax, "c")
    S.n_note(fig, "F1 | unit = site-day; %d sites, %d complete site-days, %d events, %d days "
                  "(%d complete 24 h days pass P3). Empirical dwell/arrival distributions, no "
                  "parametric fit (fit_metrics.csv). Right panel: mean relative error of the "
                  "hold-out mean per category, not RMSE."
                  % (d["fp"]["n_sites"], d["fp"]["n_site_days"], d["fp"]["n_events"],
                     d["fp"]["n_days"], 789))
    fig.subplots_adjust(left=0.115, right=0.985, top=0.88, bottom=0.25, wspace=0.52)
    return fig


# --------------------------------------------------------------------- F2 data
def fig_f2():
    rows, m1 = csv2("E2/curve_E2.csv", ["policy", "k", "service_capacity_unmet_rate",
                                        "charging_access_rate"])
    summ, m2 = csv2("E2/curve_E2_summary.csv", ["policy", "k", "n_streams",
                                                "service_capacity_unmet_rate_mean",
                                                "service_capacity_unmet_rate_low",
                                                "service_capacity_unmet_rate_high"], root=BASE7)
    return {"rows": rows, "summ": summ,
            "inputs": [m1, m2]}


def draw_f2(d):
    fig, axes = S.new_fig(1, 3, width=7.2, height=3.0)
    rng = np.random.default_rng(SEED)
    by = {}
    for r in d["rows"]:
        by.setdefault((r["policy"], int(r["k"])), []).append(r)
    ax = axes[0]
    for pol, sty in (("A", S.series_style(0, "A")), ("D", S.series_style(2, "D"))):
        ks, means, los, his, ns = [], [], [], [], []
        for k in sorted({k for p, k in by if p == pol}):
            sub = by[(pol, k)]
            m, lo, hi = mean_ci(sub, "service_capacity_unmet_rate", rng)
            ks.append(k); means.append(m * 100.0); los.append(lo * 100.0)
            his.append(hi * 100.0); ns.append(len(sub))
        ax.fill_between(ks, los, his, color=sty["color"], alpha=0.16, linewidth=0)
        ax.plot(ks, means, color=sty["color"], marker=sty["marker"], markersize=3.6,
                linestyle=sty["linestyle"], linewidth=1.2, label="policy %s" % pol)
    ax.axhline(5.0, color=S.PALETTE["reference"], linestyle=(0, (4, 2)), linewidth=0.8)
    ax.text(0.99, 5.0, "5% tolerance ", transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=6, color=S.PALETTE["reference"])
    ax.set_xlabel("charging berths k (berths)")
    ax.set_ylabel("capacity-only unmet requests (%)")
    ax.set_title("capacity constraint vs k")
    ax.set_ylim(0, 105)
    ax.legend(loc="upper right", fontsize=6)
    ax.text(0.02, 0.92, "A: 92.4% at k=1 -> min 60.8% at k=8\nnever <= 5%: infeasible in k-grid",
            transform=ax.transAxes, fontsize=5.6, va="top")
    S.panel_label(ax, "a")
    ax = axes[1]
    for pol, sty in (("A", S.series_style(0, "A")), ("D", S.series_style(2, "D"))):
        ks, means, ns = [], [], []
        for k in sorted({k for p, k in by if p == pol}):
            sub = by[(pol, k)]
            m, _, _ = mean_ci(sub, "charging_access_rate", rng)
            ks.append(k); means.append(m * 100.0); ns.append(len(sub))
        ax.plot(ks, means, color=sty["color"], marker=sty["marker"], markersize=3.6,
                linestyle=sty["linestyle"], linewidth=1.2, label="policy %s (n streams)" % pol)
    ax.axhline(95.0, color=S.PALETTE["reference"], linestyle=(0, (4, 2)), linewidth=0.8)
    ax.text(0.99, 95.0, "access target 95% ", transform=ax.get_yaxis_transform(),
            ha="right", va="bottom", fontsize=6, color=S.PALETTE["reference"])
    ax.set_xlabel("charging berths k (berths)")
    ax.set_ylabel("charging access rate (%)")
    ax.set_title("access target vs k")
    ax.set_ylim(0, 105)
    ax.legend(loc="lower right", fontsize=6)
    ax.text(0.02, 0.62, "A: 19.7% at k=1 -> 95.1% at k=7\n(24 streams at every k)",
            transform=ax.transAxes, fontsize=5.6, va="top")
    S.panel_label(ax, "b")
    ax = axes[2]
    sm = {}
    for r in d["summ"]:
        sm.setdefault(r["policy"], []).append(r)
    for i, (pol, sty) in enumerate((("A", S.series_style(0, "A")),
                                    ("D", S.series_style(2, "D")))):
        rows = sorted(sm[pol], key=lambda r: int(r["k"]))
        ks = [int(r["k"]) for r in rows]
        mean = [float(r["service_capacity_unmet_rate_mean"]) * 100.0 for r in rows]
        lo = [float(r["service_capacity_unmet_rate_low"]) * 100.0 for r in rows]
        hi = [float(r["service_capacity_unmet_rate_high"]) * 100.0 for r in rows]
        ax.fill_between(ks, lo, hi, color=sty["color"], alpha=0.16, linewidth=0)
        ax.plot(ks, mean, color=sty["color"], marker=sty["marker"], markersize=3.4,
                linestyle=sty["linestyle"], linewidth=1.2, label=pol)
    S.tolerance_line(ax)
    ax.set_xlabel("charging berths k (berths)")
    ax.set_ylabel("capacity-only unmet requests (%)")
    ax.set_title("7 kW regime: infeasibility case")
    ax.set_ylim(0, 105)
    ax.legend(loc="lower left", fontsize=6)
    ax.annotate("bootstrap CI by site-day", xy=(0.97, 0.16), xycoords="axes fraction",
                ha="right", fontsize=5.6)
    S.panel_label(ax, "c")
    S.n_note(fig, "F2 | panels a-b from experiments_main22/E2/curve_E2.csv: one point per "
                  "(stream, policy, k); intervals = percentile bootstrap of the mean over "
                  "independent streams, 1000 draws, seed %d; the same 24 streams are present at "
                  "every k in 0..8 (site-day, not event, is the unit). "
                  "Panel c = 7 kW run curve_E2_summary.csv with the engine's own bootstrap CIs. "
                  "The five-percent tolerance is the design-matrix service standard, drawn "
                  "identical in both regimes." % SEED)
    fig.subplots_adjust(left=0.075, right=0.985, top=0.88, bottom=0.28, wspace=0.42)
    return fig


# --------------------------------------------------------------------- F3 data
def fig_f3():
    rows, m1 = csv2("E3/search_E3.csv", ["row_kind", "instance_id", "k", "status", "k_class"])
    cls_path = os.path.join(MAIN22, "E3", "classes.json")
    cls = json.load(open(cls_path, encoding="utf-8"))
    return {"rows": rows, "cls": cls,
            "inputs": [m1, {"path": cls_path, "rows": 8, "fields": ["classes", "instances"]}]}


def draw_f3(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.1)
    per = [r for r in d["rows"] if r["row_kind"] == "per_k"]
    inst = []
    for r in per:
        if r["instance_id"] not in inst:
            inst.append(r["instance_id"])
    kmax = max(int(r["k"]) for r in per)
    ax = axes[0]
    for yi, iid in enumerate(inst):
        cells = {int(r["k"]): r["status"] for r in per if r["instance_id"] == iid}
        for k in range(kmax + 1):
            if k not in cells:
                color, alpha = "white", 1.0
                ax.add_patch(plt.Rectangle((k - 0.5, yi - 0.42), 1, 0.84,
                                           facecolor="white", edgecolor="#DDDDDD",
                                           hatch="////", linewidth=0))
            elif cells[k] == "feasible":
                ax.add_patch(plt.Rectangle((k - 0.5, yi - 0.42), 1, 0.84,
                                           facecolor=S.PALETTE["confirmed_minimal"],
                                           edgecolor="white", linewidth=0.4))
            else:
                ax.add_patch(plt.Rectangle((k - 0.5, yi - 0.42), 1, 0.84,
                                           facecolor=S.PALETTE["physically_infeasible"],
                                           edgecolor="white", linewidth=0.4))
    ax.set_xlim(-0.6, kmax + 0.6)
    ax.set_ylim(len(inst) - 0.5, -0.5)
    ax.set_yticks(range(len(inst)))
    ax.set_yticklabels([i.replace(":", "\n") for i in inst], fontsize=5.4)
    ax.set_xlabel("candidate k (berths)")
    ax.set_title("offline enumeration grid")
    ax.grid(False)
    handles = [Patch(facecolor=S.PALETTE["physically_infeasible"], label="infeasible"),
               Patch(facecolor="white", edgecolor="#999999", hatch="////", label="not in range"),
               Patch(facecolor=S.PALETTE["confirmed_minimal"], label="feasible")]
    ax.legend(handles=handles, loc="lower right", fontsize=6)
    S.panel_label(ax, "a")
    ax = axes[1]
    classes = d["cls"]["classes"]
    order = S.CLASS_ORDER
    vals = [classes.get(c, 0) for c in order]
    x = np.arange(len(order))
    ax.bar(x, vals, 0.6, color=[S.PALETTE[c] for c in order])
    for xi, v in zip(x, vals):
        ax.text(xi, v + 0.08, str(v), ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([c.replace("_", "\n") for c in order], fontsize=5.8)
    ax.set_ylabel("site-day instances")
    ax.set_title("minimality classes (main22)")
    ax.text(0.03, 0.9, "physically_infeasible: 6/8 -> window_too_short\n"
                       "budget_not_covered: 2/8 -> cap k=8, bounds 16/14",
            transform=ax.transAxes, fontsize=5.8, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "F3 | unit = site-day instance (offline, future information available); 8 "
                  "held-out instances, k enumerated 0..physical bound, 1-minute uniform-power "
                  "grid max-flow, model offline_uniform_power_minute_grid. confirmed_minimal is "
                  "a statement inside the declared offline model, never a physical lower bound; "
                  "the 22 kW run produced the same class counts as the 7 kW run. Budget cap = 8.")
    fig.subplots_adjust(left=0.30, right=0.985, top=0.88, bottom=0.24, wspace=0.42)
    return fig


# --------------------------------------------------------------------- F4 data
def fig_f4():
    rows, m1 = csv2("E4/test_E4.csv", ["policy", "stream_id", "energy_service_rate",
                                       "charging_access_rate", "service_capacity_unmet_rate",
                                       "delivered_kwh", "demand_kwh"])
    mrows, m2 = csv2("M/m_summaries.csv", ["comparison", "pair", "point", "low", "high",
                                          "n_pairs"])
    return {"rows": rows, "m": mrows, "inputs": [m1, m2]}


def draw_f4(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.1)
    pol_order = ["A", "B", "C", "D", "B0_FCFS", "B1_QUOTA", "B2_LITERATURE"]
    rng = np.random.default_rng(SEED)
    by = {}
    for r in d["rows"]:
        by.setdefault(r["policy"], []).append(r)
    ax = axes[0]
    x = np.arange(len(pol_order))
    vals = []
    for pol in pol_order:
        m, lo, hi = mean_ci(by[pol], "energy_service_rate", rng)
        vals.append((m * 100.0, lo * 100.0, hi * 100.0))
    for xi, (m, lo, hi) in zip(x, vals):
        col = S.PALETTE["B0_FCFS"] if "B0" in pol_order[xi] else S.PALETTE["A"]
        ax.errorbar(xi, m, yerr=[[m - lo], [hi - m]], fmt="o", color=col, markersize=5,
                    capsize=2.0, linewidth=1.0)
    ax.set_xticks(x)
    ax.set_xticklabels([p.replace("_", "\n") for p in pol_order], fontsize=5.8)
    ax.set_ylabel("energy service rate (%)")
    ax.set_title("delivered/required energy (mean, 95% CI)")
    ax.text(0.03, 0.94, "A %.1f%%, B/C/D %.1f%%, B0 %.1f%%\ndemand %.1f kWh per stream"
            % (vals[0][0], vals[1][0], vals[4][0],
               float(np.mean([float(r["demand_kwh"]) for r in by["A"]]))),
            transform=ax.transAxes, fontsize=5.8, va="top")
    S.panel_label(ax, "a")
    ax = axes[1]
    metrics = [("charging_access_rate", "access rate", S.PALETTE["A"]),
               ("service_capacity_unmet_rate", "capacity unmet", S.PALETTE["B"])]
    w = 0.16
    for i, pol in enumerate(["A", "B", "B0_FCFS", "B1_QUOTA"]):
        vals2 = []
        for field, _, _ in metrics:
            m, _, _ = mean_ci(by[pol], field, rng)
            vals2.append(m * 100.0)
        ax.bar(i - w / 2, vals2[0], w, color=S.PALETTE["A"])
        ax.bar(i + w / 2, vals2[1], w, color=S.PALETTE["B"])
    ax.set_xticks(range(4))
    ax.set_xticklabels(["A", "B", "B0", "B1"], fontsize=6.5)
    ax.set_ylabel("rate (%)")
    ax.set_title("access vs capacity-only unmet")
    ax.legend(handles=[Patch(facecolor=S.PALETTE["A"], label="charging access rate"),
                       Patch(facecolor=S.PALETTE["B"], label="capacity-only unmet requests")],
              loc="upper left", fontsize=6)
    S.tolerance_line(ax)
    S.panel_label(ax, "b")
    S.n_note(fig, "F4 | unit = independent held-out stream (site-day); 20 streams per policy, "
                  "one k = 1 fixed from training (k_source=training_max_offline_min_k) for every "
                  "policy; same 20 streams across policies, so dots are paired. Intervals: "
                  "figure-side percentile bootstrap over streams (1000 draws, seed %d); the "
                  "confirmatory paired tests are in M/m_summaries.csv, direction baseline "
                  "minus A (negative = A better): B0_FCFS-A -0.2276 [-0.3217,-0.1421]; "
                  "B1_QUOTA-A and B2_LITERATURE-A +0.00767 [0.0,+0.02237], n=20 pairs."
                  % SEED)
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.30, wspace=0.35)
    return fig


# --------------------------------------------------------------------- F5 data
def fig_f5():
    rows, m1 = csv2("constraint_thresholds.csv", ["policy", "stream_id", "site_id",
                                                 "parking_service_k", "charging_access_k",
                                                 "energy_service_k", "three_constraints_k",
                                                 "infeasible_reason"])
    info, m2 = csv2("E5/info_E5.csv", ["policy", "k_min_feasible", "confirmed_minimal_sim",
                                       "delta_k_vs_A"])
    return {"rows": rows, "info": info, "inputs": [m1, m2]}


def draw_f5(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.4)
    ax = axes[0]
    rows = sorted([r for r in d["rows"] if r["policy"] == "A"],
                  key=lambda r: (r["site_id"], r["stream_id"]))
    cols = [("parking_service_k", "parking\nservice"),
            ("charging_access_k", "charging\naccess"),
            ("energy_service_k", "energy\nservice"),
            ("three_constraints_k", "three\nconstraints")]
    for yi, r in enumerate(rows):
        for xi, (field, _) in enumerate(cols):
            v = r[field]
            if str(v).strip() == "":
                ax.add_patch(plt.Rectangle((xi - 0.45, yi - 0.42), 0.9, 0.84,
                                           facecolor="#EDEDED", edgecolor="white"))
                ax.text(xi, yi, "x", ha="center", va="center", fontsize=5.4, color="#888888")
            else:
                ax.add_patch(plt.Rectangle((xi - 0.45, yi - 0.42), 0.9, 0.84,
                                           facecolor=S.PALETTE["confirmed_minimal"],
                                           edgecolor="white"))
                ax.text(xi, yi, "k=%s" % v, ha="center", va="center", fontsize=5.2,
                        color="white")
    ax.set_xlim(-0.6, len(cols) - 0.4)
    ax.set_ylim(len(rows) - 0.5, -0.5)
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([c[1] for c in cols], fontsize=6)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["stream_id"].split("#")[0].replace(":", " ") for r in rows],
                       fontsize=4.8)
    ax.grid(False)
    ax.set_title("smallest k meeting each constraint (policy A)")
    S.panel_label(ax, "a")
    ax = axes[1]
    n = len(d["info"])
    empty = sum(1 for r in d["info"] if str(r["k_min_feasible"]).strip() == "")
    ax.bar([0, 1], [n - empty, empty], color=[S.PALETTE["A"], S.PALETTE["physically_infeasible"]])
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["k_min recorded", "k_min blank\n(no feasible k)"], fontsize=6.5)
    ax.set_ylabel("stream-policy rows")
    ax.set_title("E5 signal experiment (main22)")
    ax.text(0.03, 0.94, "%d/%d rows blank; confirmed_minimal_sim=False\non all; no delta_k_vs_A -> "
                        "missing_data" % (empty, n), transform=ax.transAxes, fontsize=5.8, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "F5 | panel a: unit = independent held-out stream (site-day), policy A, k grid "
                  "0..connector slots (12/16/14/3/7/4); a cell shows the smallest k satisfying that "
                  "constraint, x = no k in the grid satisfies it. 23/24 streams have no k for the "
                  "capacity-only 5% standard, and charging access is the binding constraint. Panel "
                  "b: E5 reports no k_min for any of the 10 streams x 2 policies, so the "
                  "information-signal comparison is missing_data, not a null result.")
    fig.subplots_adjust(left=0.28, right=0.985, top=0.88, bottom=0.24, wspace=0.35)
    return fig


# --------------------------------------------------------------------- F6 data
def fig_f6():
    rows, m1 = csv2("E6/energy_E6.csv", ["site_id", "day_key", "connector_kw", "feeder_kw",
                                        "feeder_share", "demand_kwh", "delivered_kwh",
                                        "energy_service_rate", "rejected", "charge_requests",
                                        "offline_status", "offline_reason"])
    return {"rows": rows, "inputs": [m1]}


def draw_f6(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.2)
    rows = d["rows"]
    keys = []
    for r in rows:
        key = (float(r["connector_kw"]), float(r["feeder_kw"]))
        if key not in keys:
            keys.append(key)
    keys.sort()
    days = []
    for r in rows:
        day = "%s %s" % (r["site_id"], r["day_key"][5:])
        if day not in days:
            days.append(day)
    ax = axes[0]
    x = np.arange(len(days))
    w = 0.2
    dem = {}
    for r in rows:
        dem[("%s %s" % (r["site_id"], r["day_key"][5:]))] = float(r["demand_kwh"])
    for i, key in enumerate(keys):
        vals = []
        for day in days:
            hit = [r for r in rows if "%s %s" % (r["site_id"], r["day_key"][5:]) == day
                   and float(r["connector_kw"]) == key[0] and float(r["feeder_kw"]) == key[1]]
            vals.append(float(hit[0]["delivered_kwh"]) if hit else 0.0)
        ax.bar(x + (i - 1.5) * w, vals, w, label="%.0f kW / %.1f kW feeder" % key)
    ax.plot(x, [dem[day] for day in days], marker="D", linestyle="none", color="black",
            markersize=4.5, label="demand")
    ax.set_xticks(x)
    ax.set_xticklabels([day.replace(" ", "\n") for day in days], fontsize=5.4)
    ax.set_ylabel("energy (kWh)")
    ax.set_title("energy ledger by site-day")
    ax.legend(fontsize=5.2, loc="upper left", ncol=2)
    ax.text(0.02, 0.62, "delivered totals: %.1f / %.1f / %.1f / %.1f kWh\nof %.1f kWh demand"
            % tuple([sum(float(r["delivered_kwh"]) for r in rows
                         if float(r["connector_kw"]) == k and float(r["feeder_kw"]) == f)
                     for k, f in keys] + [sum(dem.values())]),
            transform=ax.transAxes, fontsize=5.4, va="top")
    S.panel_label(ax, "a")
    ax = axes[1]
    for i, key in enumerate(keys):
        ys = []
        for day in days:
            hit = [r for r in rows if "%s %s" % (r["site_id"], r["day_key"][5:]) == day
                   and float(r["connector_kw"]) == key[0] and float(r["feeder_kw"]) == key[1]]
            if hit and str(hit[0]["energy_service_rate"]).strip():
                ys.append((i, float(hit[0]["energy_service_rate"]) * 100.0))
        if ys:
            ax.scatter([p[0] for p in ys], [p[1] for p in ys], s=13, alpha=0.8,
                       color=S.PALETTE[[k for k in ("A", "B", "C", "D")][i]])
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels(["%.0f/%.1f" % k for k in keys], fontsize=6)
    ax.set_xlabel("connector kW / feeder kW")
    ax.set_ylabel("energy service rate (%)")
    ax.set_title("service rate per configuration")
    ax.text(0.03, 0.94, "20/24 rows offline infeasible\nreason=window_too_short; 4 rows\n"
                        "no_charge_demand (feasible, 0 demand)", transform=ax.transAxes,
            fontsize=5.6, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "F6 | unit = site-day x configuration; 24 rows = 6 held-out site-days x 2 "
                  "connector powers (7/11 kW) x feeder 100%/50% share, fixed k=1; delivered "
                  "includes only energy delivered before departure, rejected requests stay in the "
                  "denominator; offline_status=infeasible on 20/24 rows. The main22 run's E6 "
                  "output carries the same 7/11 kW rows as the 7 kW run (the 22 kW flag changes "
                  "the online layer, not this ledger), so this figure is the 7 kW/11 kW energy "
                  "sensitivity case.")
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.28, wspace=0.38)
    return fig


# --------------------------------------------------------------------- F7 data
def fig_f7():
    mp = os.path.join(MAIN22, "E7", "meta_E7.json")
    meta = json.load(open(mp, encoding="utf-8"))
    tpath = os.path.join(MAIN22, "E7", "traj_E7.csv")
    nrows = 0
    with open(tpath, encoding="utf-8-sig") as fh:
        nrows = max(0, sum(1 for _ in fh) - 1)
    return {"meta": meta, "nrows": nrows,
            "inputs": [{"path": mp, "rows": 1, "fields": ["status", "reason"]},
                       {"path": tpath, "rows": nrows, "fields": []}]}


def draw_f7(d):
    fig, ax = S.new_fig(1, 1, width=7.2, height=2.7)
    ax.axis("off")
    lines = [
        "F7 non-monotone event trajectory - machine status: missing_data",
        "",
        "family E7, regime experiments_main22 (22 kW layer), seed 20261031",
        "rows in traj_E7.csv: %d" % d["nrows"],
        "status in meta_E7.json: %s" % d["meta"].get("status"),
        "reason (meta_E7.json records it in Chinese; English rendering):",
        "  no non-monotone event in which the service rate decreases as k",
        "  increases was observed in the held-out block; no trajectory is",
        "  fabricated (original text stays in the machine file).",
        "",
        "Requirement: one held-out site-day whose served-service rate falls when k grows.",
        "Result: no such event was observed in the held-out block, so no trajectory is drawn.",
        "",
        "No synthetic substitute is used here; the negative result is the evidence.",
    ]
    ax.text(0.02, 0.96, "\n".join(lines), transform=ax.transAxes, fontsize=7.2,
            family="DejaVu Sans Mono", va="top", linespacing=1.55)
    S.n_note(fig, "F7 | E7 is a pre-registered search for a non-monotone k response; the "
                  "machine output records missing_data with zero trajectory rows. Drawing a "
                  "trajectory from another family or from synthetic data would fabricate a "
                  "result, so this panel reports the status instead.")
    fig.subplots_adjust(left=0.02, right=0.98, top=0.98, bottom=0.18)
    return fig


# ------------------------------------------------------------------- SI S1-S4
def fig_s1():
    cov, m1 = csv2("E1/coverage.csv", ["site_id", "events", "site_days", "n_spaces",
                                       "charging_bays"])
    return {"cov": cov, "inputs": [m1]}


def draw_s1(d):
    fig, ax = S.new_fig(1, 1, width=7.2, height=2.9)
    rows = sorted(d["cov"], key=lambda r: -int(r["n_spaces"]))
    x = np.arange(len(rows))
    ax.bar(x - 0.22, [int(r["n_spaces"]) for r in rows], 0.42, color=S.PALETTE["band"],
           label="parking spaces")
    ax.bar(x + 0.22, [int(r["charging_bays"]) for r in rows], 0.42, color=S.PALETTE["A"],
           label="charging berths (contract)")
    ax.set_xticks(x)
    ax.set_xticklabels([r["site_id"].replace(" ", "\n") for r in rows], fontsize=5.8)
    ax.set_ylabel("berths / spaces")
    ax.legend(fontsize=6)
    ax2 = ax.twinx()
    ax2.plot(x, [int(r["events"]) for r in rows], color=S.PALETTE["B"], marker="o",
             markersize=3.5, linewidth=1.0, label="events")
    ax2.set_ylabel("observed events")
    ax2.grid(False)
    ax.set_title("S1 site inventory and observed events")
    S.n_note(fig, "S1 | source E1/coverage.csv; 10 sites, %d events, %d site-days."
                  % (sum(int(r["events"]) for r in rows), sum(int(r["site_days"]) for r in rows)))
    fig.subplots_adjust(left=0.09, right=0.90, top=0.88, bottom=0.22)
    return fig


def fig_s2():
    rows, m1 = csv2("E4/test_E4.csv", ["policy", "energy_service_rate", "charging_access_rate",
                                       "service_capacity_unmet_rate", "delivered_kwh",
                                       "demand_kwh", "rejected", "charge_requests"], root=BASE7)
    return {"rows": rows, "inputs": [m1]}


def draw_s2(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=2.9)
    pol_order = ["A", "B", "C", "D", "B0_FCFS", "B1_QUOTA", "B2_LITERATURE"]
    rng = np.random.default_rng(SEED)
    by = {}
    for r in d["rows"]:
        by.setdefault(r["policy"], []).append(r)
    ax = axes[0]
    for i, pol in enumerate(pol_order):
        m1, _, _ = mean_ci(by[pol], "energy_service_rate", rng)
        m2, _, _ = mean_ci(by[pol], "service_capacity_unmet_rate", rng)
        ax.scatter(m1 * 100, m2 * 100, color=S.PALETTE["B0_FCFS"] if "B0" in pol
                   else S.PALETTE["A"], s=22)
        ax.annotate(pol, (m1 * 100, m2 * 100), xytext=(3, 2), textcoords="offset points",
                    fontsize=5.6)
    ax.set_xlabel("energy service rate (%)")
    ax.set_ylabel("capacity-only unmet (%)")
    ax.set_title("7 kW run: policies")
    S.panel_label(ax, "a")
    ax = axes[1]
    k = np.arange(len(pol_order))
    rej = [float(np.mean([float(r["rejected"]) / max(1.0, float(r["charge_requests"]))
                          for r in by[p]])) * 100.0 for p in pol_order]
    ax.bar(k, rej, 0.6, color=S.PALETTE["physically_infeasible"])
    ax.set_xticks(k)
    ax.set_xticklabels([p.replace("_", "\n") for p in pol_order], fontsize=5.4)
    ax.set_ylabel("rejected charge requests (%)")
    ax.set_title("rejection at k=1 (7 kW run)")
    ax.text(0.03, 0.94, "A 93%% rejection: 5/137 served\nE4 declares k=1 from offline min-k",
            transform=ax.transAxes, fontsize=5.6, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "S2 | unit = held-out stream (site-day), 20 per policy, k=1, 7 kW run; panel b "
                  "shows rejected charge requests as a share of charge requests per stream. In "
                  "the 22 kW run the same policies reach about 24% energy service (F4).")
    fig.subplots_adjust(left=0.09, right=0.985, top=0.88, bottom=0.28, wspace=0.38)
    return fig


def fig_s3():
    rows, m1 = csv2("E6/energy_E6.csv", ["connector_kw", "feeder_kw", "delivered_kwh",
                                        "demand_kwh", "offline_status"], root=BASE7)
    return {"rows": rows, "inputs": [m1]}


def draw_s3(d):
    fig, ax = S.new_fig(1, 1, width=7.2, height=2.8)
    keys = sorted({(float(r["connector_kw"]), float(r["feeder_kw"])) for r in d["rows"]})
    dem = sum(float(r["demand_kwh"]) for r in d["rows"]) / len(keys)
    deliv = [sum(float(r["delivered_kwh"]) for r in d["rows"]
                 if float(r["connector_kw"]) == k and float(r["feeder_kw"]) == f)
             for k, f in keys]
    x = np.arange(len(keys))
    ax.bar(x, deliv, 0.55, color=S.PALETTE["A"], label="delivered")
    ax.axhline(dem, color="black", linestyle=(0, (4, 2)), linewidth=0.9,
               label="demand = %.1f kWh" % dem)
    for xi, v in zip(x, deliv):
        ax.text(xi, v + 2, "%.1f" % v, ha="center", fontsize=6)
    ax.set_xticks(x)
    ax.set_xticklabels(["%.0f kW / %.1f kW" % k for k in keys], fontsize=6.2)
    ax.set_ylabel("energy (kWh)")
    ax.set_title("S3 delivered vs required energy by configuration (7/11 kW)")
    ax.legend(fontsize=6, loc="upper left")
    S.n_note(fig, "S3 | source E6/energy_E6.csv; 24 rows = 6 site-days x 4 configurations, k=1, "
                  "7 kW run. All 20 charging site-days are offline infeasible (window_too_short); "
                  "4 rows have no charge demand and are feasible with zero denominator.")
    fig.subplots_adjust(left=0.10, right=0.98, top=0.88, bottom=0.22)
    return fig


def fig_s4():
    rows, m1 = csv2("M/m_summaries.csv", ["comparison", "pair", "point", "low", "high",
                                          "n_pairs"])
    rows7, m2 = csv2("M/m_summaries.csv", ["comparison", "pair", "point", "low", "high"])
    return {"rows": rows, "inputs": [m1]}


def draw_s4(d):
    fig, ax = S.new_fig(1, 1, width=7.2, height=2.9)
    pairs = []
    for r in d["rows"]:
        if r["comparison"] == "M2" and str(r["point"]).strip():
            pairs.append(r)
    y = np.arange(len(pairs))
    for yi, r in zip(y, pairs):
        p, lo, hi = float(r["point"]), float(r["low"]), float(r["high"])
        ax.plot([lo, hi], [yi, yi], color=S.PALETTE["A"], linewidth=1.4)
        ax.plot([p], [yi], marker="o", color=S.PALETTE["A"], markersize=5)
        ax.text(hi + 0.006, yi, "%+.4f [%+.4f, %+.4f], n=%s" % (p, lo, hi, r["n_pairs"]),
                va="center", fontsize=5.8)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_yticks(y)
    ax.set_yticklabels([r["pair"] for r in pairs], fontsize=6.5)
    ax.set_xlabel("paired difference in energy service rate (main22)")
    ax.set_title("S4 confirmatory paired comparisons (M2)")
    ax.set_xlim(-0.36, 0.06)
    S.n_note(fig, "S4 | source M/m_summaries.csv (experiments_main22), unit = site-day, "
                  "20 paired streams, percentile bootstrap CI, seed 20261031. The engine "
                  "declares direction = baseline minus A (negative = A delivers more energy "
                  "service); B1 and B2 are identical on 20/20 streams. M1/M3 are missing_data, "
                  "not shown as effects.")
    fig.subplots_adjust(left=0.28, right=0.98, top=0.88, bottom=0.24)
    return fig


def fig_f6_main22():
    rows, m1 = csv2("E6/energy_E6.csv", ["site_id", "day_key", "connector_kw", "feeder_kw",
                                        "demand_kwh", "delivered_kwh", "energy_service_rate",
                                        "offline_status", "offline_reason", "charge_requests",
                                        "rejected"])
    return {"rows": rows, "inputs": [m1]}


def draw_f6_main22(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.0)
    rows = d["rows"]
    days = ["%s %s" % (r["site_id"], r["day_key"][5:]) for r in rows]
    x = np.arange(len(rows))
    ax = axes[0]
    dem = [float(r["demand_kwh"]) for r in rows]
    got = [float(r["delivered_kwh"]) for r in rows]
    ax.bar(x, dem, 0.56, color="#DDDDDD", label="required energy")
    ax.bar(x, got, 0.56, color=S.PALETTE["A"], label="delivered")
    for xi, g in zip(x, got):
        ax.text(xi, g + 3, "%.1f" % g, ha="center", fontsize=5.2)
    ax.set_xticks(x)
    ax.set_xticklabels([day.replace(" ", "\n") for day in days], fontsize=5.2)
    ax.set_ylabel("energy (kWh)")
    ax.set_title("22 kW ledger at k=1: delivered vs required")
    ax.legend(fontsize=6, loc="upper left")
    ax.text(0.02, 0.72, "total %.1f / %.1f kWh = %.1f%%\n5/6 site-days offline infeasible "
                        "(window_too_short)\n1/6 no charge demand"
            % (sum(got), sum(dem), 100.0 * sum(got) / sum(dem)),
            transform=ax.transAxes, fontsize=5.4, va="top")
    S.panel_label(ax, "a")
    ax = axes[1]
    rates = [float(r["energy_service_rate"]) * 100.0 for r in rows
             if str(r["energy_service_rate"]).strip()]
    ax.scatter([r["site_id"] + "\n" + r["day_key"][5:] for r in rows
                if str(r["energy_service_rate"]).strip()], rates,
               color=S.PALETTE["physically_infeasible"], s=22, zorder=3)
    ax.axhline(100.0, color="black", linewidth=0.8, linestyle=(0, (4, 2)))
    ax.text(0.03, 0.96, "target 100%% (no shortfall); max observed %.1f%%"
            % max(rates), transform=ax.transAxes, fontsize=5.6, va="top")
    ax.set_ylabel("energy service rate (%)")
    ax.set_title("per site-day, 22 kW / full feeder")
    ax.tick_params(axis="x", labelsize=4.8)
    S.panel_label(ax, "b")
    S.n_note(fig, "F6 | unit = held-out site-day x configuration; the corrected main22 E6 output "
                  "has 6 rows = 6 held-out site-days x one configuration (22 kW connector, feeder "
                  "22 kW = 100% of connector power), k=1, seed 20261031. Delivered excludes "
                  "energy after departure and energy from rejected requests; rejected stays in the "
                  "denominator. Five rows are offline infeasible with reason window_too_short; "
                  "one row has no charge demand. The 7/11 kW 2x2 ledger is in S3.")
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.26, wspace=0.38)
    return fig


def fig_f8():
    rows, m1 = csv2("evidence_at_n_spaces.csv", ["site_id", "day_key", "policy",
                                                "n_spaces", "k_eval", "charge_requests",
                                                "rejected_at_gate", "shortfall_sessions",
                                                "delivered_kwh", "demand_kwh",
                                                "energy_service_rate_incl_rejected",
                                                "sessions_dwell_lt_required"],
                    root=os.path.join(ROUND, "experiments_condshare"))
    agg_path = os.path.join(ROUND, "experiments_condshare", "evidence_at_n_spaces.json")
    agg = json.load(open(agg_path, encoding="utf-8"))
    return {"rows": [r for r in rows if r["policy"] == "A"],
            "agg": agg, "inputs": [m1, {"path": agg_path, "rows": 1, "fields": ["aggregate"]}]}


def draw_f8(d):
    fig, axes = S.new_fig(1, 2, width=7.2, height=3.0)
    rows = d["rows"]
    x = np.arange(len(rows))
    ax = axes[0]
    dem = [float(r["demand_kwh"]) for r in rows]
    got = [float(r["delivered_kwh"]) for r in rows]
    ax.bar(x, dem, 0.6, color="#DDDDDD", label="required (scenario)")
    ax.bar(x, got, 0.6, color=S.PALETTE["A"], label="delivered")
    ax.set_xticks(x)
    ax.set_xticklabels(["%s %s" % (r["site_id"].replace(" ", "")[:8], r["day_key"][5:])
                        for r in rows], fontsize=4.0, rotation=90)
    ax.margins(x=0.02)
    ax.set_ylabel("energy (kWh)")
    ax.set_title("k = n_spaces: delivered vs required per stream")
    ax.legend(fontsize=5.6, loc="upper right")
    S.panel_label(ax, "a")
    ax = axes[1]
    agg = d["agg"]["aggregate"]["A"]
    labels = ["charge\nrequests", "gate\nrejections", "shortfall\nsessions", "unmet\nshare"]
    vals = [agg["charge_requests"], agg["rejected_at_gate"], agg["shortfall_sessions"],
            round(100.0 * agg["unmet_total"] / agg["charge_requests"], 1)]
    colors = [S.PALETTE["band"], S.PALETTE["confirmed_minimal"],
              S.PALETTE["physically_infeasible"], S.PALETTE["B"]]
    ax.bar(range(len(vals)), vals, 0.58, color=colors)
    for xi, v in zip(range(len(vals)), vals):
        ax.text(xi, v + 2, ("%.1f%%" % v) if xi == 3 else "%d" % v, ha="center", fontsize=6.2)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, fontsize=5.8)
    ax.set_ylabel("sessions / percent")
    ax.set_title("conditional run, 20 streams, k = n_spaces")
    ax.text(0.03, 0.95, "20/20 streams fail the 5%% standard\ndelivered %.1f / %.1f kWh = %.1f%%"
            % (agg["delivered_kwh"], agg["demand_kwh"],
               100.0 * agg["delivered_kwh"] / agg["demand_kwh"]),
            transform=ax.transAxes, fontsize=5.6, va="top")
    S.panel_label(ax, "b")
    S.n_note(fig, "F8 | conditional uncapped-connector analysis (experiments_condshare/): every "
                  "parking space is a charging berth (k = n_spaces), 22 kW per connector, feeder = "
                  "k x 22 kW, same three constraints, no future information. Unit = held-out "
                  "stream (site-day), 20 streams, policy A. Gate rejection is 0/137 because no "
                  "connector is scarce; the unmet share is entirely shortfall sessions whose "
                  "observed dwell is shorter than the scenario charging time.")
    fig.subplots_adjust(left=0.085, right=0.985, top=0.88, bottom=0.26, wspace=0.40)
    return fig


BUILDERS = [
    ("F1", fig_f1, draw_f1, "Data coverage, dwell/arrival calibration and hold-out error (E1)."),
    ("F2", fig_f2, draw_f2, "Capacity-only unmet and charging access against k (E2, main22) with the 7 kW infeasibility case."),
    ("F3", fig_f3, draw_f3, "Offline k-grid and minimality classes per held-out instance (E3)."),
    ("F4", fig_f4, draw_f4, "Held-out policy comparison at fixed k=1: energy service, access and capacity (E4)."),
    ("F5", fig_f5, draw_f5, "Smallest k meeting each service constraint per stream (constraint_thresholds, E5)."),
    ("F6", fig_f6_main22, draw_f6_main22, "22 kW energy ledger: delivered vs required energy per site-day at k=1 (E6)."),
    ("F7", fig_f7, draw_f7, "Non-monotone trajectory: machine status missing_data (E7)."),
    ("F8", fig_f8, draw_f8, "Conditional uncapped-connector analysis: k=n_spaces still misses the standard (condshare)."),
    ("S1", fig_s1, draw_s1, "SI: site inventory and observed events."),
    ("S2", fig_s2, draw_s2, "SI: 7 kW policy comparison and charge-request rejection."),
    ("S3", fig_s3, draw_s3, "SI: 7 kW energy ledger, delivered vs required energy by configuration."),
    ("S4", fig_s4, draw_s4, "SI: confirmatory paired differences in energy service rate (M2)."),
]


def main():
    outdir = HERE
    only = sys.argv[1:] or [b[0] for b in BUILDERS]
    for fid, loader, drawer, caption in BUILDERS:
        if fid not in only:
            continue
        data = loader()
        fig = drawer(data)
        rec = S.save(fig, fid, inputs=data["inputs"], fields=[], demo=False,
                     caption=caption, outdir=outdir, script=os.path.abspath(__file__),
                     note="real machine output (regime: main22 for E2/E3/E4/E5/M; E1/E6 base; E7 status)")
        print("%s %s %s" % (fid, rec["status"], rec["outputs"]["png"]))


if __name__ == "__main__":
    sys.exit(main())
