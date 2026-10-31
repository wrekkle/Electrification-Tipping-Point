# -*- coding: utf-8 -*-
"""Enumeration, scenario-by-candidate cost matrices and design evaluation.

Common random numbers: one set of daily scenarios is drawn per
(lot type, EV mode, r) and replayed for every candidate design and rule.
The reproduction unit is the day block (see run.block_days); hourly
correlation inside a day is represented by the NHPP in the v2 layer.
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


def prepare_v2_day(rng, cfg, r, q, ev_mode):
    day = demand.simulate_day_arrivals(
        rng, cfg, r, composition_of(cfg, ev_mode),
        float(cfg["demand"]["beta_variance"]),
        float(cfg["demand"]["beta_variance_ceiling"]), q=q)
    day["dwell_min"] = demand.dwell_times(rng, cfg, len(day["times"]))
    day["energy_req"] = demand.energy_requests(rng, cfg, len(day["times"]))
    day["q"] = float(q)
    return day


def v2_days(cfg, seed, lot_type, r, q, n_days, ev_mode):
    rs = config.derive_seed(seed, "v2day", lot_type, ev_mode,
                            round(float(r), 6), round(float(q), 6))
    rng = np.random.default_rng(rs)
    return [prepare_v2_day(rng, cfg, float(r), float(q), ev_mode)
            for _ in range(n_days)]


def v2_designs(v2, N):
    fracs = [float(f) for f in v2["m_fracs"]]
    overhead_fracs = [float(f) for f in v2.get("overhead_fracs", fracs)]
    theta_fracs = [float(f) for f in v2.get("theta_fracs", fracs)]
    base = {"power_kw": float(v2["power_kw"]),
            "feeder_kw": float(v2["feeder_kw"])}
    designs = []
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
        if design["m"] <= 0 or key in seen:
            continue
        seen.add(key)
        out.append(design)
    return out


V2_METRIC_KEYS = ("arrivals_A", "blocked_ev_charge", "blocked_ev_park",
                  "blocked_icev", "blocked_total", "admitted", "sessions",
                  "energy_requested_kwh", "energy_delivered_kwh",
                  "shortfall_kwh", "shortfall_rate", "peak_concurrency",
                  "peak_power_kw")


def v2_pile_cost(settings, cost_model, design):
    return mode_pile_cost(settings, cost_model, design["mode"], design["m"])


def design_label(design):
    return "%s,%s,m=%d" % (design["mode"], design["rule"], design["m"])


def v2_cell_matrix(settings, cost_model, seed, lot_type, ev_mode, r, q,
                   n_days, designs, with_timeline=False):
    """Simulate one (lot, ev_mode, r, q) cell once and reuse it for all designs.

    Returns the daily operating loss matrix (days x designs), the H-period cost
    matrix V (pile cost + losses) and averaged service metrics.  The same day
    trajectories are therefore common random numbers for every design and for
    the bootstrap statistics.
    """
    days = v2_days(settings, seed, lot_type, r, q, n_days, ev_mode)
    H = float(settings["run"]["horizon_years"])
    days_year = float(settings["run"]["operating_days_per_year"])
    n = len(days)
    loss = np.zeros((n, len(designs)))
    totals = {key: np.zeros(len(designs)) for key in V2_METRIC_KEYS}
    pile = np.array([v2_pile_cost(settings, cost_model, d) for d in designs])
    timeline = None
    for i, day in enumerate(days):
        for j, design in enumerate(designs):
            out = simulator.simulate_day(settings, cost_model, design, day)
            metrics = out["metrics"]
            loss[i, j] = metrics["daily_loss_rmb"]
            for key in V2_METRIC_KEYS:
                totals[key][j] += metrics[key]
            if timeline is None and with_timeline:
                timeline = [dict(row) for row in out["timeline"][:200]]
    means = {key: totals[key] / max(1, n) for key in V2_METRIC_KEYS}
    means["daily_loss_rmb"] = loss.mean(axis=0)
    mean_loss = means["daily_loss_rmb"]
    return {
        "lot_type": lot_type, "ev_mode": ev_mode, "r": float(r), "q": float(q),
        "designs": [dict(d) for d in designs],
        "loss": loss, "V": pile[None, :] + loss * days_year * H,
        "pile": pile, "V_mean": pile + mean_loss * days_year * H,
        "means": means, "timeline": timeline, "n_days": n,
        "H": H, "days_year": days_year,
    }


def v2_rows(cells, N):
    """Point-estimate rows (one per cell x design)."""
    rows = []
    for cell in cells.values():
        means = cell["means"]
        V_mean = cell["V_mean"]
        for j, design in enumerate(cell["designs"]):
            row = {
                "lot_type": cell["lot_type"], "ev_mode": cell["ev_mode"],
                "r": cell["r"], "q": cell["q"],
                "mode": design["mode"], "rule": design["rule"],
                "theta": design["theta"], "devices": int(design["m"]),
                "ppr": float(design["m"]) / float(N),
                "v_rmb": float(V_mean[j]),
                "mean_daily_loss_rmb": float(means["daily_loss_rmb"][j]),
            }
            for key in V2_METRIC_KEYS:
                row[key] = float(means[key][j])
            rows.append(row)
    rows.sort(key=lambda x: (x["lot_type"], x["ev_mode"], x["r"], x["q"],
                             x["mode"], x["rule"], x["theta"], x["devices"]))
    return rows


def v2_eval(settings, cost_model, seed, r_list=None, q_list=None,
            lot_types=None, ev_modes=None, designs=None, with_timeline=True):
    """Run the v2 event layer; returns (rows, cells, timeline sample)."""
    v2 = settings["v2"]
    N = int(settings["lot"]["n_spaces"])
    n_days = int(v2["scenario_count"])
    r_list = list(r_list if r_list is not None else v2["r_list"])
    q_list = list(q_list if q_list is not None else v2["q_list"])
    lot_types = list(lot_types if lot_types is not None else v2["lot_types"])
    ev_modes = list(ev_modes if ev_modes is not None else v2["ev_modes"])
    designs = designs or v2_designs(v2, N)
    cells = {}
    sample_timeline = None
    for lot_type in lot_types:
        for ev_mode in ev_modes:
            for r in r_list:
                for q in q_list:
                    cell = v2_cell_matrix(
                        settings, cost_model, seed, lot_type, ev_mode, r, q,
                        n_days, designs, with_timeline=(sample_timeline is None))
                    if cell["timeline"] is not None and sample_timeline is None:
                        sample_timeline = (dict(cell["designs"][0]), cell["timeline"])
                    cells[(lot_type, ev_mode, round(float(r), 6), round(float(q), 6))] = cell
    return v2_rows(cells, N), cells, sample_timeline


def v2_best(rows):
    """Best design per (lot, r, q)."""
    best = {}
    for row in rows:
        key = (row["lot_type"], row["ev_mode"], row["r"], row["q"])
        if key not in best or row["v_rmb"] < best[key]["v_rmb"]:
            best[key] = row
    return best


def _pick(rows, lot_type, ev_mode, r, q, mode, rule, theta, devices):
    for row in rows:
        if (row["lot_type"] == lot_type and row["ev_mode"] == ev_mode
                and row["r"] == r and row["q"] == q
                and row["mode"] == mode and row["rule"] == rule
                and abs(row["theta"] - theta) < 1e-12
                and row["devices"] == devices):
            return row
    return None


def decomposition_rows(rows, lot_type, ev_mode, r, q, N):
    """Equation (12) decomposition in both path orders (v2 matrices)."""
    partial = [row for row in rows if row["lot_type"] == lot_type
               and row["ev_mode"] == ev_mode and row["r"] == r
               and row["q"] == q and row["mode"] == "fixed" and row["rule"] == "pi_S"
               and row["devices"] < N]
    if not partial:
        return []
    m0row = min(partial, key=lambda x: x["v_rmb"])
    m0 = m0row["devices"]
    v_NF = _pick(rows, lot_type, ev_mode, r, q, "fixed", "pi_F", 0.0, N)
    v_mF = _pick(rows, lot_type, ev_mode, r, q, "fixed", "pi_F", 0.0, m0)
    v_mS = _pick(rows, lot_type, ev_mode, r, q, "fixed", "pi_S", 0.0, m0)
    v_NS = _pick(rows, lot_type, ev_mode, r, q, "fixed", "pi_S", 0.0, N)
    if not all([v_NF, v_mF, v_mS, v_NS]):
        return []
    total = v_NF["v_rmb"] - v_mS["v_rmb"]
    cap_a = v_NF["v_rmb"] - v_mF["v_rmb"]
    rule_a = v_mF["v_rmb"] - v_mS["v_rmb"]
    cap_b = v_NF["v_rmb"] - v_NS["v_rmb"]
    rule_b = v_NS["v_rmb"] - v_mS["v_rmb"]
    return [{
        "lot_type": lot_type, "ev_mode": ev_mode, "r": r, "q": q, "m0": m0,
        "v_NF": v_NF["v_rmb"], "v_mF": v_mF["v_rmb"],
        "v_mS": v_mS["v_rmb"], "v_NS": v_NS["v_rmb"],
        "total_difference": total,
        "capacity_effect_pathA": cap_a,
        "rule_effect_pathA": rule_a,
        "capacity_effect_pathB": rule_b,
        "rule_effect_pathB": cap_b,
        "path_dependence_capacity": cap_a - rule_b,
        "path_dependence_rule": rule_a - cap_b,
        "identity_gap": total - (cap_a + rule_a),
    }]

# ---------------------------------------------------------------------------
# v2 statistical layer: block bootstrap, g(r), confidence set, CVaR
# ---------------------------------------------------------------------------
def cvar_fields(daily_best, daily_full, alpha=0.95):
    """CVaR row fields with an explicit full-install evaluation flag."""
    cv = stats.empirical_cvar(daily_best, alpha)
    cv_full = stats.empirical_cvar(daily_full, alpha)
    zero_reason = ""
    if abs(cv_full["cvar"]) <= 1e-9:
        zero_reason = ("full-install daily operating loss is identically zero "
                       "(no leavers: D_EV+D_ICE<=N in every scenario)")
    return {
        "n_samples": cv["n"], "tail_samples": cv["tail_n"],
        "var_rmb": cv["var"], "cvar_rmb": cv["cvar"],
        "cvar_aux_rmb": cv["cvar_aux"], "eta_star_rmb": cv["eta_star"],
        "cvar_full_install_rmb": cv_full["cvar"],
        "tail_samples_full": cv_full["tail_n"],
        "full_install_evaluated": True,
        "full_install_zero_reason": zero_reason,
        "cost_basis": "daily_operating_loss_rmb",
    }


def v2_cell_stats(cell, settings, n_boot=1000, alpha=0.05, block_len=1,
                  rng=None, candidate_modes=("fixed",)):
    """g(r), confidence set and CVaR rows for one (lot, ev, r, q) cell.

    The candidate set is the full design list of the v2 layer; the full
    installation is fixed,pi_F,m=N and partial candidates are all m<N.
    """
    all_designs = cell["designs"]
    keep = [j for j, d in enumerate(all_designs)
            if candidate_modes is None or d["mode"] in candidate_modes]
    if len(keep) < 2:
        raise ValueError("fewer than two candidate designs after mode filter")
    designs = [all_designs[j] for j in keep]
    V = cell["V"][:, keep]
    loss = cell["loss"][:, keep]
    N = int(settings["lot"]["n_spaces"])
    labels = [design_label(d) for d in designs]
    full_idx = [j for j, d in enumerate(designs)
                if d["mode"] == "fixed" and d["rule"] == "pi_F" and d["m"] >= N]
    if not full_idx:
        raise ValueError("no full-install design (fixed, pi_F, m=N)")
    full_j = full_idx[0]
    part_idx = [j for j, d in enumerate(designs) if d["m"] < N]
    if not part_idx:
        raise ValueError("no partial design (m<N)")
    gi = stats.g_interval(V[:, full_j], V[:, part_idx], n_boot=n_boot,
                          alpha=alpha, block_len=block_len, rng=rng)
    region = stats.three_region(gi["g_hat"], gi["g_lo"], gi["g_hi"])
    cs = stats.confidence_set(V, n_boot=n_boot, alpha=alpha,
                              block_len=block_len, rng=rng)
    best = cs["best"]
    part_means = V[:, part_idx].mean(axis=0)
    best_part = part_idx[int(np.argmin(part_means))]
    cv = stats.empirical_cvar(loss[:, best], alpha)
    cv_full = stats.empirical_cvar(loss[:, full_j], alpha)
    zero_reason = ""
    if abs(cv_full["cvar"]) <= 1e-9:
        zero_reason = ("full-install daily operating loss is identically zero "
                       "(no leavers: D_EV+D_ICE<=N in every simulated day)")
    base = {"lot_type": cell["lot_type"], "ev_mode": cell["ev_mode"],
            "r": cell["r"], "q": cell["q"]}
    g_row = dict(base, g_hat=gi["g_hat"], g_lo=gi["g_lo"], g_hi=gi["g_hi"],
                 region=region, best_partial=labels[best_part],
                 best_partial_ppr=float(designs[best_part]["m"]) / float(N),
                 full_install=labels[full_j], n_days=gi["n_scenarios"],
                 n_boot=gi["n_boot"], alpha=alpha)
    conf_row = dict(base, best=labels[best],
                    best_mean_rmb=float(cs["means"][best]),
                    included=";".join(labels[j] for j in cs["included"]),
                    excluded=";".join(labels[j] for j in cs["excluded"]),
                    set_size=len(cs["included"]),
                    n_candidates=len(labels), n_scenarios=cs["n_scenarios"],
                    n_boot=cs["n_boot"], block_len=cs["block_len"],
                    critical_value=cs["critical_value"], alpha=alpha)
    cvar_row = dict(base, design=labels[best],
                    n_samples=cv["n"], tail_samples=cv["tail_n"],
                    var_rmb=cv["var"], cvar_rmb=cv["cvar"],
                    cvar_aux_rmb=cv["cvar_aux"], eta_star_rmb=cv["eta_star"],
                    full_install=labels[full_j],
                    cvar_full_install_rmb=cv_full["cvar"],
                    tail_samples_full=cv_full["tail_n"],
                    full_install_evaluated=True,
                    full_install_zero_reason=zero_reason,
                    cost_basis="daily_operating_loss_rmb", alpha=alpha)
    reg_row = dict(base, g_hat=gi["g_hat"], g_lo=gi["g_lo"], g_hi=gi["g_hi"],
                   region=region, best_partial=labels[best_part],
                   best_partial_ppr=float(designs[best_part]["m"]) / float(N))
    return {"g": g_row, "confidence": conf_row, "cvar": cvar_row,
            "regions": reg_row}


def refine_r_grid(g_rows, coarse_r, step=0.02):
    """Extra r values inserted at 'step' next to the first g(r) sign change."""
    coarse = sorted(float(x) for x in coarse_r)
    by = {}
    for row in g_rows:
        by.setdefault((row["lot_type"], row["ev_mode"]), []).append(row)
    extra = {}
    for key in sorted(by):
        series = sorted(by[key], key=lambda x: x["r"])
        crossing = None
        for a, b in zip(series, series[1:]):
            if (a["g_hat"] >= 0.0) != (b["g_hat"] >= 0.0):
                crossing = (a["r"], b["r"])
                break
        if crossing is None:
            continue
        lo, hi = crossing
        n_steps = int(round((hi - lo) / step))
        vals = [round(lo + k * step, 10) for k in range(1, max(1, n_steps))]
        extra[key] = [v for v in vals if coarse[0] < v < coarse[-1]
                      and v not in coarse]
    return extra


def v2_etp_points(g_rows):
    points = {}
    for key in sorted({(row["lot_type"], row["ev_mode"]) for row in g_rows}):
        sub = [row for row in g_rows if (row["lot_type"], row["ev_mode"]) == key]
        points["%s|%s" % key] = stats.etp_from_g(sub)
    return points


# ---------------------------------------------------------------------------
# Fig. 8 scarcity grid (static layer, arrival intensity = scarcity x N)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Cost-scale x horizon feasibility grid
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# SAA error table: repeated seeds at the same design grid
# ---------------------------------------------------------------------------
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
