# -*- coding: utf-8 -*-
"""evaluate_base

拆分自 evaluate.py，内容逐字节搬移以保持行为不变；公共入口仍由 evaluate 提供。
"""
from __future__ import annotations
import copy
import numpy as np
from . import config, costs, demand, simulator, stats


LOT_TYPES = ("pnc", "plc")


STATIC_MODES = ("partition", "partial", "full", "overhead")


def arrivals_mean(settings, lot_type):
    lot = settings["lot"]
    N = int(lot["n_spaces"])
    override = lot.get("arrivals_override")
    if override is not None:
        return float(override)
    if lot_type == "pnc":
        return (1.0 - float(lot["pnc_vacancy_rate"])) * N
    if lot_type == "plc":
        return float(lot["plc_arrivals_ratio"]) * N
    raise ValueError("unknown lot type %r" % lot_type)


def v2_lot_arrival_scale(settings, lot_type):
    """Arrival-intensity multiplier that makes the site labels real parameters.

    The static layer already separates the two sites through the manuscript
    vacancy rate (pnc) and arrivals/capacity ratio (plc).  The v2 event layer
    reproduces that separation by scaling the shipped hourly intensity profile
    so that plc keeps the reference level and pnc scales down by
    arrival_mean(pnc)/arrival_mean(plc).  This mapping is an ASSUMPTION: the
    manuscript does not calibrate the v2 hourly profile per site, and dwell /
    energy tables remain shared by both sites.  Set
    v2.lot_arrival_calibration to "seed_only" to reproduce the old behaviour
    in which the two labels differed only through the random seed.
    """
    lot = settings["lot"]
    N = int(lot["n_spaces"])
    v2 = settings.get("v2", {}) if isinstance(settings, dict) else {}
    mode = str(v2.get("lot_arrival_calibration", "static_layer_ratio")).lower()
    if mode in ("seed_only", "none", "off"):
        return 1.0
    reference = float(lot["plc_arrivals_ratio"]) * N
    if reference <= 0.0:
        return 1.0
    return float(arrivals_mean(settings, lot_type)) / reference


def composition_of(settings, ev_mode):
    return {"beta": "beta", "binomial": "binomial", "fluid": "fluid"}[ev_mode]


def m_candidates(N, step):
    n_steps = int(round(1.0 / float(step)))
    vals = sorted({int(round(step * k * N)) for k in range(n_steps + 1)})
    return [m for m in vals if 0 <= m <= N]


def integer_candidates(N):
    return list(range(int(N) + 1))


def scenario_set(settings, seed, lot_type, r, ev_mode):
    """Draw the shared daily scenarios for one (lot, EV mode, r)."""
    spec = settings["demand"]
    n_scen = int(settings["run"]["scenario_count"])
    rs = config.derive_seed(seed, "scen", lot_type, ev_mode, round(float(r), 6))
    rng = np.random.default_rng(rs)
    scen = demand.draw_scenarios(
        rng, n_scen, arrivals_mean(settings, lot_type), float(r),
        beta_variance=float(spec["beta_variance"]),
        composition=composition_of(settings, ev_mode),
        beta_ceiling=float(spec["beta_variance_ceiling"]),
    )
    if ev_mode != "fluid":
        demand.check_integer_conservation(scen)
    scen["r"] = float(r)
    scen["lot_type"] = lot_type
    scen["ev_mode"] = ev_mode
    return scen


def static_leavers(scen, mode, m, N, sharing_ratio=0.0):
    """Leaving counts by class for the static (batch) operation modes."""
    D_EV = np.asarray(scen["D_EV"], dtype=float)
    D_ICE = np.asarray(scen["D_ICE"], dtype=float)
    m = int(m)
    if mode == "partition":
        return np.maximum(0.0, D_EV - m), np.maximum(0.0, D_ICE - (N - m))
    if mode == "partial":
        open_extra = int(round(float(sharing_ratio) * m))
        cap_ice = (N - m) + open_extra
        return np.maximum(0.0, D_EV - m), np.maximum(0.0, D_ICE - cap_ice)
    if mode == "full":
        ev_used = np.minimum(D_EV, m)
        le_ev = np.maximum(0.0, D_EV - m)
        le_ice = np.maximum(0.0, D_ICE - (N - ev_used))
        return le_ev, le_ice
    if mode == "overhead":
        le_ev = np.maximum(0.0, D_EV - m)
        le_ice = np.maximum(0.0, D_ICE - (N - np.minimum(D_EV, m)))
        return le_ev, le_ice
    raise ValueError("unknown static mode %r" % mode)


def mode_pile_cost(settings, cost_model, mode, m):
    modes = settings["modes"]
    if mode == "overhead":
        ratio = float(modes["overhead"]["unit_cost_ratio"])
        return cost_model.pile_cost(float(m) * ratio)
    return cost_model.pile_cost(float(m))


def static_matrices(settings, cost_model, seed, ev_modes=None, modes=None):
    """Cost matrices for every (lot, ev_mode, r, static mode).

    Returns (total_matrices, daily_matrices, candidates, meta_rows) where
    matrices[(lot, ev_mode, r, mode)] has shape scenarios x candidates and
    contains H-period social cost per scenario (pile cost + losses).
    """
    run = settings["run"]
    N = int(settings["lot"]["n_spaces"])
    ev_modes = ev_modes or list(settings["demand"]["ev_modes"])
    modes = modes or list(settings["static"]["modes"])
    ms = m_candidates(N, float(run["m_grid_step"]))
    sharing = float(settings["modes"]["partial_sharing_ratio"])
    total, daily, meta = {}, {}, []
    for lot_type in LOT_TYPES:
        for ev_mode in ev_modes:
            for r in run["r_grid"]:
                scen = scenario_set(settings, seed, lot_type, r, ev_mode)
                for mode in modes:
                    columns_total = []
                    columns_daily = []
                    for m in ms:
                        le_ev, le_ice = static_leavers(scen, mode, m, N, sharing)
                        dl = cost_model.daily_total_loss(le_ev, le_ice)
                        pile = mode_pile_cost(settings, cost_model, mode, m)
                        columns_total.append(dl + pile)
                        columns_daily.append(dl)
                    total[(lot_type, ev_mode, float(r), mode)] = np.column_stack(columns_total)
                    daily[(lot_type, ev_mode, float(r), mode)] = np.column_stack(columns_daily)
                    meta.append({"lot_type": lot_type, "ev_mode": ev_mode, "r": float(r),
                                 "mode": mode, "candidates": ms})
    return total, daily, ms, meta


def curves_rows(settings, total, daily):
    rows = []
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    for (lot_type, ev_mode, r, mode), mat in total.items():
        for j, m in enumerate(ms):
            rows.append({
                "lot_type": lot_type, "ev_mode": ev_mode, "r": r,
                "mode": mode, "m": int(m),
                "ppr": float(m) / float(N),
                "psc_rmb": float(mat[:, j].mean()),
                "daily_loss_rmb": float(daily[(lot_type, ev_mode, r, mode)][:, j].mean()),
            })
    return rows


def optimum_rows(settings, cost_model, total, seed):
    """Optimal / passive designs, PSC-increase percentage, integer check."""
    run = settings["run"]
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(run["m_grid_step"]))
    rows, integer_rows = [], []
    for (lot_type, ev_mode, r, mode), mat in total.items():
        means = mat.mean(axis=0)
        best_j = int(np.argmin(means))
        rows.append({
            "lot_type": lot_type, "ev_mode": ev_mode, "r": r, "mode": mode,
            "best_m": int(ms[best_j]), "best_ppr": float(ms[best_j]) / N,
            "psc_opt": float(means[best_j]),
            "m_grid_size": len(ms),
        })
        if mode == "partition":
            passive_m = min(int(round(float(r) * N)), N)
            if passive_m in ms:
                jp = ms.index(passive_m)
            else:
                jp = int(np.argmin(np.abs(np.asarray(ms) - passive_m)))
            psc_passive = float(means[jp])
            rows[-1].update({
                "passive_m": int(ms[jp]),
                "passive_ppr": float(ms[jp]) / N,
                "psc_passive": psc_passive,
                "psc_increase_pct": ((psc_passive - float(means[best_j]))
                                     / float(means[best_j]) * 100.0
                                     if means[best_j] > 0 else float("nan")),
            })
            scen = scenario_set(settings, seed, lot_type, float(r), ev_mode)
            allm = integer_candidates(N)
            best_int, best_int_val = None, float("inf")
            for m in allm:
                le_ev, le_ice = static_leavers(
                    scen, mode, m, N, float(settings["modes"]["partial_sharing_ratio"]))
                val = cost_model.psc(m, le_ev, le_ice)
                if val < best_int_val:
                    best_int_val, best_int = val, m
            integer_rows.append({
                "lot_type": lot_type, "ev_mode": ev_mode, "r": float(r),
                "grid_best_m": int(ms[best_j]),
                "integer_best_m": int(best_int),
                "grid_psc": float(means[best_j]),
                "integer_psc": float(best_int_val),
                "grid_gap_rmb": float(means[best_j]) - float(best_int_val),
            })
    return rows, integer_rows


def modes_summary(settings, total):
    """Best design and PSC reduction for each operation mode."""
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    rows = []
    for (lot_type, ev_mode, r, mode), mat in total.items():
        if mode != "partition":
            continue
        part_best = float(mat.mean(axis=0).min())
        for other in ("partial", "full", "overhead"):
            mat_o = total.get((lot_type, ev_mode, r, other))
            if mat_o is None:
                continue
            means = mat_o.mean(axis=0)
            j = int(np.argmin(means))
            rows.append({
                "lot_type": lot_type, "ev_mode": ev_mode, "r": r, "mode": other,
                "best_m": int(ms[j]), "best_ppr": float(ms[j]) / N,
                "psc_opt": float(means[j]),
                "psc_reduction_pct_vs_partition": (
                    (part_best - float(means[j])) / part_best * 100.0),
            })
    return rows


def etp_rows(settings, cost_model, total, seed):
    """Full installation (m=N, pi_F) versus the best strict-partition design."""
    N = int(settings["lot"]["n_spaces"])
    ms = m_candidates(N, float(settings["run"]["m_grid_step"]))
    rows = []
    for (lot_type, ev_mode, r, mode), mat in total.items():
        if mode != "full":
            continue
        full_mat = total[(lot_type, ev_mode, r, "full")]
        jN = int(np.argmin(np.abs(np.asarray(ms) - N)))
        v_full = float(full_mat[:, jN].mean())
        part_mat = total[(lot_type, ev_mode, r, "partition")]
        j_part = int(np.argmin(part_mat.mean(axis=0)))
        v_part = float(part_mat[:, j_part].mean())
        scen = scenario_set(settings, seed, lot_type, float(r), ev_mode)
        le_ev_p, le_ice_p = static_leavers(
            scen, "partition", ms[j_part], N,
            float(settings["modes"]["partial_sharing_ratio"]))
        le_ev_f, le_ice_f = static_leavers(scen, "full", N, N, 0.0)
        days = float(settings["run"]["operating_days_per_year"])
        H = float(settings["run"]["horizon_years"])
        n_lpart = float(np.mean(le_ev_p + le_ice_p)) * days * H
        n_lfull = float(np.mean(le_ev_f + le_ice_f)) * days * H
        delta = n_lpart - n_lfull
        c_full = cost_model.pile_cost(N)
        c_lfull = (1.0 - float(r)) * c_full / delta if delta > 0 else float("nan")
        stable = bool(delta > max(1.0, 0.01 * n_lpart))
        rows.append({
            "lot_type": lot_type, "ev_mode": ev_mode, "r": r,
            "m0_partial": int(ms[j_part]), "ppr_partial": float(ms[j_part]) / N,
            "v_full": v_full, "v_partial_best": v_part,
            "g_rmb": v_full - v_part,
            "full_cheaper": bool(v_full < v_part),
            "delta_leavers_horizon": delta,
            "full_installation_cost_rmb": c_full,
            "c_lfull_rmb_per_vehicle": c_lfull,
            "net_benefit_ev_rmb": (cost_model.event_cost("ev") - c_lfull) if stable else float("nan"),
            "net_benefit_icev_rmb": (cost_model.event_cost("icev") - c_lfull) if stable else float("nan"),
            "denominator_stable": stable,
        })
    return rows


def prepare_v2_day(rng, cfg, r, q, ev_mode, lot_type="pnc"):
    """One v2 demand day in the documented minute contract.

    lot_type enters as a parameter (arrival-intensity scale, see
    v2_lot_arrival_scale), not only as a seed tag.  Dwell and energy tables
    are shared by both sites and remain flagged as an assumption.
    """
    scale = v2_lot_arrival_scale(cfg, lot_type)
    day = demand.simulate_day_arrivals(
        rng, cfg, r, composition_of(cfg, ev_mode),
        float(cfg["demand"]["beta_variance"]),
        float(cfg["demand"]["beta_variance_ceiling"]), q=q,
        arrival_scale=scale)
    n = len(day["times_min"])
    day["dwell_min"] = demand.dwell_times(rng, cfg, n)
    day["energy_req"] = demand.energy_requests(rng, cfg, n)
    day["q"] = float(q)
    day["lot_type"] = str(lot_type)
    return day


def v2_days(cfg, seed, lot_type, r, q, n_days, ev_mode):
    rs = config.derive_seed(seed, "v2day", lot_type, ev_mode,
                            round(float(r), 6), round(float(q), 6))
    rng = np.random.default_rng(rs)
    return [prepare_v2_day(rng, cfg, float(r), float(q), ev_mode, lot_type)
            for _ in range(n_days)]


def v2_designs(v2, N):
    """Declared candidate set of the v2 layer (reported, not exhaustive).

    The set is the configured m_fracs grid plus the moving (overhead) designs.
    When include_m0 is on it also contains the zero-charger fixed designs, so
    the equation (12) decomposition has a genuine no-charger reference instead
    of borrowing the best skipped partial design.  The optimum is therefore
    best-in-candidates, not best over all integer m nor over every technology;
    the g(r)/ETP statistics use the fixed-mode candidates unless the caller
    widens candidate_modes (see v2_cell_stats).
    """
    fracs = [float(f) for f in v2["m_fracs"]]
    overhead_fracs = [float(f) for f in v2.get("overhead_fracs", fracs)]
    theta_fracs = [float(f) for f in v2.get("theta_fracs", fracs)]
    include_m0 = bool(v2.get("include_m0", True))
    base = {"power_kw": float(v2["power_kw"]),
            "feeder_kw": float(v2["feeder_kw"])}
    designs = []
    if include_m0:
        for rule in ("pi_S", "pi_F"):
            designs.append(dict(base, mode="fixed", m=0, rule=rule, theta=0.0,
                                coverage=1, reposition_min=0.0))
    for rule in ("pi_S", "pi_F"):
        for frac in fracs:
            designs.append(dict(base, mode="fixed", m=int(round(frac * N)),
                                rule=rule, theta=0.0, coverage=1,
                                reposition_min=0.0))
    for theta in v2["theta_list"]:
        for frac in theta_fracs:
            designs.append(dict(base, mode="fixed", m=int(round(frac * N)),
                                rule="pi_theta", theta=float(theta),
                                coverage=1, reposition_min=0.0))
    for frac in overhead_fracs:
        designs.append(dict(base, mode="overhead", m=int(round(frac * N)),
                            rule="pi_F", theta=0.0,
                            coverage=int(v2["coverage"]),
                            reposition_min=float(v2["reposition_min"])))
    seen, out = set(), []
    for design in designs:
        key = (design["mode"], design["m"], design["rule"], design["theta"])
        if design["m"] < 0 or key in seen:
            continue
        seen.add(key)
        out.append(design)
    return out


V2_METRIC_KEYS = ("arrivals_A", "blocked_ev_charge", "blocked_ev_park",
                  "blocked_icev", "blocked_total", "rejected_ev_charge",
                  "admitted", "sessions",
                  "energy_requested_kwh", "energy_requested_admitted_kwh",
                  "energy_requested_all_kwh", "rejected_energy_kwh",
                  "energy_delivered_kwh", "shortfall_kwh", "shortfall_rate",
                  "unserved_energy_kwh", "unserved_rate_all",
                  "refused_rate_all", "ev_arrivals", "ev_charge_requests",
                  "q_request_realized", "q_plug_realized",
                  "peak_concurrency", "peak_power_kw",
                  "device_moves_executed", "device_moves_cancelled",
                  "device_moves_planned", "device_move_conflicts")


def v2_pile_cost(settings, cost_model, design):
    return mode_pile_cost(settings, cost_model, design["mode"], design["m"])


def design_label(design):
    return "%s,%s,m=%d" % (design["mode"], design["rule"], design["m"])
