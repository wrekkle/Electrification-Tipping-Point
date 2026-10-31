# -*- coding: utf-8 -*-
"""evaluate_outputs

拆分自 evaluate.py，内容逐字节搬移以保持行为不变；公共入口仍由 evaluate 提供。
"""
from __future__ import annotations
import copy
import numpy as np
from . import config, costs, demand, simulator, stats
from .evaluate_base import LOT_TYPES, m_candidates, mode_pile_cost, scenario_set, static_leavers


def fig8_rows(settings, cost_model, seed,
              scarcity_values=(0.4, 0.6, 0.8, 1.0, 1.2),
              r_values=(0.2, 0.4, 0.6, 0.8, 1.0),
              ev_modes=None, lot_types=None, n_boot=1000):
    """Three-region map over (r, scarcity); scarcity = arrivals / spaces."""
    lot_types = list(lot_types or LOT_TYPES)
    ev_modes = list(ev_modes or settings["demand"]["ev_modes"])
    N = int(settings["lot"]["n_spaces"])
    days = float(settings["run"]["operating_days_per_year"])
    H = float(settings["run"]["horizon_years"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    rows = []
    for lot_type in lot_types:
        for ev_mode in ev_modes:
            for scarcity in scarcity_values:
                settings2 = copy.deepcopy(settings)
                settings2["lot"]["arrivals_override"] = float(N) * float(scarcity)
                for r in r_values:
                    scen = scenario_set(settings2, seed, lot_type, r, ev_mode)
                    columns = []
                    for m in ms:
                        le_ev, le_ice = static_leavers(scen, "partition", m, N, 0.0)
                        dl = cost_model.daily_total_loss(le_ev, le_ice)
                        columns.append(dl * days * H
                                       + mode_pile_cost(settings2, cost_model,
                                                        "partition", m))
                    le_ev, le_ice = static_leavers(scen, "full", N, N, 0.0)
                    full_col = (cost_model.daily_total_loss(le_ev, le_ice) * days * H
                                + mode_pile_cost(settings2, cost_model, "full", N))
                    partial = np.column_stack(
                        [col for m, col in zip(ms, columns) if m < N])
                    rng = np.random.default_rng(config.derive_seed(
                        seed, "fig8", lot_type, ev_mode,
                        round(float(scarcity), 6), round(float(r), 6)))
                    gi = stats.g_interval(full_col, partial, n_boot=n_boot,
                                          alpha=0.05, block_len=1, rng=rng)
                    region = stats.three_region(gi["g_hat"], gi["g_lo"],
                                                gi["g_hi"])
                    rows.append({
                        "lot_type": lot_type, "ev_mode": ev_mode,
                        "scarcity": float(scarcity),
                        "pnc_vacancy_rate": float(1.0 - scarcity) if lot_type == "pnc" else float("nan"),
                        "plc_arrivals_ratio": float(scarcity) if lot_type == "plc" else float("nan"),
                        "r": float(r), "g_hat": gi["g_hat"],
                        "g_lo": gi["g_lo"], "g_hi": gi["g_hi"],
                        "region": region,
                        "n_scenarios": gi["n_scenarios"],
                    })
    rows.sort(key=lambda x: (x["lot_type"], x["ev_mode"], x["scarcity"], x["r"]))
    return rows


def feasibility_rows(settings, seed,
                     scales=(1.0, 8.0, 18.0, 36.0, 54.0),
                     horizons=(1.0, 5.0, 10.0),
                     r_values=(0.4, 0.6, 0.8),
                     lot_types=None, ev_modes=None):
    """Where does the optimal PPR fall inside (0, 1)?

    The horizon scales pile cost and losses by the same factor, so only the
    event-cost scale matters for the optimal proportion; the table shows both.
    """
    lot_types = list(lot_types or LOT_TYPES)
    ev_modes = list(ev_modes or ("beta", "binomial"))
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    cache = {}
    for lot_type in lot_types:
        for ev_mode in ev_modes:
            for r in r_values:
                cache[(lot_type, ev_mode, float(r))] = scenario_set(
                    settings, seed, lot_type, r, ev_mode)
    rows = []
    for scale in scales:
        for horizon in horizons:
            settings2 = copy.deepcopy(settings)
            settings2["cost"]["event_cost_scale"] = float(scale)
            settings2["run"]["horizon_years"] = float(horizon)
            cm = costs.CostModel(settings2, seed)
            for lot_type in lot_types:
                for ev_mode in ev_modes:
                    for r in r_values:
                        scen = cache[(lot_type, ev_mode, float(r))]
                        vals = []
                        for m in ms:
                            le_ev, le_ice = static_leavers(scen, "partition", m, N, 0.0)
                            vals.append(cm.psc(m, le_ev, le_ice))
                        j = int(np.argmin(vals))
                        best = int(ms[j])
                        rows.append({
                            "event_cost_scale": float(scale),
                            "horizon_years": float(horizon),
                            "lot_type": lot_type, "ev_mode": ev_mode,
                            "r": float(r), "best_m": best,
                            "best_ppr": float(best) / float(N),
                            "psc_opt_rmb": float(vals[j]),
                            "interior_optimum": bool(0 < best < N),
                        })
    return rows


def saa_rows(settings, cost_model, seed, reps=10):
    """Same-seed repeated runs: argmin hit rate and PSC standard error."""
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    rows = []
    for lot_type in LOT_TYPES:
        for ev_mode in ("beta", "binomial"):
            for r in settings["run"]["r_grid"]:
                pprs, pscs = [], []
                for k in range(int(reps)):
                    scen = scenario_set(settings, seed + k, lot_type, r, ev_mode)
                    vals = []
                    for m in ms:
                        le_ev, le_ice = static_leavers(scen, "partition", m, N, 0.0)
                        vals.append(cost_model.psc(m, le_ev, le_ice))
                    j = int(np.argmin(vals))
                    pprs.append(ms[j] / float(N))
                    pscs.append(float(vals[j]))
                values, counts = np.unique(np.round(np.asarray(pprs), 6),
                                           return_counts=True)
                modal = float(values[int(np.argmax(counts))])
                hit = float(counts.max()) / float(reps)
                rows.append({
                    "lot_type": lot_type, "ev_mode": ev_mode, "r": float(r),
                    "reps": int(reps), "best_ppr_modal": modal,
                    "hit_rate": hit,
                    "psc_mean_rmb": float(np.mean(pscs)),
                    "psc_std_rmb": float(np.std(pscs, ddof=1)),
                    "psc_opt_min_rmb": float(np.min(pscs)),
                    "psc_opt_max_rmb": float(np.max(pscs)),
                    "psc_cv_pct": float(100.0 * np.std(pscs, ddof=1) / np.mean(pscs)),
                })
    return rows
