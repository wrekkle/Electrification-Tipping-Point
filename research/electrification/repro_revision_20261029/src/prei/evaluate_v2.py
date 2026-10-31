# -*- coding: utf-8 -*-
"""evaluate_v2

拆分自 evaluate.py，内容逐字节搬移以保持行为不变；公共入口仍由 evaluate 提供。
"""
from __future__ import annotations
import copy
import numpy as np
from . import config, costs, demand, simulator, stats
from .evaluate_base import V2_METRIC_KEYS, design_label, v2_days, v2_designs, v2_pile_cost


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
    # T12: ratios must be formed from the aggregated numerator/denominator,
    # not averaged day by day (mean of ratios weights small days differently).
    def _ratio(num, den):
        return np.divide(means[num], means[den],
                         out=np.zeros_like(means[num], dtype=float),
                         where=means[den] > 0)
    means["refused_rate_all"] = _ratio("rejected_energy_kwh",
                                       "energy_requested_all_kwh")
    means["shortfall_rate_aggregate"] = _ratio("shortfall_kwh",
                                               "energy_requested_admitted_kwh")
    means["unserved_rate_all_aggregate"] = _ratio("unserved_energy_kwh",
                                                   "energy_requested_all_kwh")
    means["q_request_realized"] = _ratio("ev_charge_requests", "ev_arrivals")
    means["q_plug_realized"] = _ratio("sessions", "ev_arrivals")
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
            for key in ("shortfall_rate_aggregate",
                        "unserved_rate_all_aggregate"):
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
        "tail_weight": cv["tail_weight"], "cvar_exact": cv["exact"],
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
    # which rule does the comparison change, and what if the rule is held fixed?
    full_rule = designs[full_j]["rule"]
    part_rules = sorted({designs[j]["rule"] for j in part_idx})
    best_partial_rule = designs[best_part]["rule"]
    rule_fixed_idx = [j for j in part_idx if designs[j]["rule"] == full_rule]
    g_rule = None
    if rule_fixed_idx:
        rule_rng = np.random.default_rng(int(rng.integers(0, 2 ** 31 - 1)))
        g_rule = stats.g_interval(V[:, full_j], V[:, rule_fixed_idx],
                                  n_boot=n_boot, alpha=alpha,
                                  block_len=block_len, rng=rule_rng)
    cv = stats.empirical_cvar(loss[:, best], alpha)
    cv_full = stats.empirical_cvar(loss[:, full_j], alpha)
    zero_reason = ""
    if abs(cv_full["cvar"]) <= 1e-9:
        zero_reason = ("full-install daily operating loss is identically zero "
                       "(no leavers: D_EV+D_ICE<=N in every simulated day)")
    base = {"lot_type": cell["lot_type"], "ev_mode": cell["ev_mode"],
            "r": cell["r"], "q": cell["q"]}
    scope = ("fixed_mode_only" if candidate_modes == ("fixed",)
             else "all_modes")
    g_row = dict(base, g_hat=gi["g_hat"], g_lo=gi["g_lo"], g_hi=gi["g_hi"],
                 region=region, best_partial=labels[best_part],
                 best_partial_ppr=float(designs[best_part]["m"]) / float(N),
                 best_partial_index=gi["best_partial_index"],
                 n_partial=gi["n_partial"], g_method=gi["method"],
                 g_paired=gi["paired"], g_unit=gi["unit"],
                 g_critical_value=gi["critical_value"],
                 g_se_best=gi["se_best"],
                 g_coverage_scope=gi["coverage_scope"],
                 g_nominal_coverage=gi["nominal_coverage"],
                 g_diagnostic_only=gi["diagnostic_only"],
                 g_interval_scope=gi["interval_scope"],
                 g_joint_across_r=gi["joint_across_r"],
                 region_confidence=("nominal" if gi["nominal_coverage"]
                                    else "diagnostic"),
                 region_scope=("per-r pointwise interval; the region label "
                               "inherits that interval status and carries no "
                               "joint guarantee across the r grid"),
                 full_rule=full_rule,
                 best_partial_rule=best_partial_rule,
                 rule_changed_vs_full=bool(best_partial_rule != full_rule),
                 partial_rule_count=len(part_rules),
                 partial_rules=";".join(part_rules),
                 n_partial_rule_fixed=len(rule_fixed_idx),
                 g_hat_rule_fixed=(g_rule["g_hat"] if g_rule else None),
                 g_lo_rule_fixed=(g_rule["g_lo"] if g_rule else None),
                 g_hi_rule_fixed=(g_rule["g_hi"] if g_rule else None),
                 candidate_scope=scope, candidate_count=len(designs),
                 full_install=labels[full_j], n_days=gi["n_scenarios"],
                 n_boot=gi["n_boot"], alpha=alpha)
    conf_row = dict(base, best=labels[best],
                    best_mean_rmb=float(cs["means"][best]),
                    included=";".join(labels[j] for j in cs["included"]),
                    excluded=";".join(labels[j] for j in cs["excluded"]),
                    set_size=len(cs["included"]),
                    n_candidates=len(labels), n_scenarios=cs["n_scenarios"],
                    n_boot=cs["n_boot"], block_len=cs["block_len"],
                    critical_value=cs["critical_value"], alpha=alpha,
                    method=cs["method"], family_size=cs["family_size"],
                    zero_se_count=len(cs["zero_se"]),
                    candidate_scope=scope)
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
                   best_partial_ppr=float(designs[best_part]["m"]) / float(N),
                   g_nominal_coverage=gi["nominal_coverage"],
                   g_diagnostic_only=gi["diagnostic_only"],
                   g_interval_scope=gi["interval_scope"],
                   g_joint_across_r=gi["joint_across_r"],
                   region_confidence=("nominal" if gi["nominal_coverage"]
                                      else "diagnostic"),
                   region_scope=("per-r pointwise interval; no joint "
                                 "guarantee across the r grid"))
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


def _windows_to_text(windows):
    return ";".join("%.2f-%.2f" % (a, b) for a, b in windows)


def v2_g_structure(g_rows):
    """Per (lot, ev mode) sheet: dominant windows vs the sustained ETP suffix.

    Also reports how often the best partial design changes the admission rule
    relative to the full installation, i.e. whether the g comparison bundles
    capacity and rule changes (it does: the candidate set spans pi_S/pi_F/
    pi_theta, and g_hat_rule_fixed in v2_g_curve.csv isolates the capacity
    effect under a fixed rule when such a candidate exists).
    """
    out = []
    for key in sorted({(row["lot_type"], row["ev_mode"]) for row in g_rows}):
        sub = [row for row in g_rows if (row["lot_type"], row["ev_mode"]) == key]
        st = stats.g_structure(sub)
        rules = [row.get("best_partial_rule") for row in sub]
        changed = sum(1 for row in sub if row.get("rule_changed_vs_full"))
        fixed = [row.get("g_hat_rule_fixed") for row in sub]
        out.append({
            "lot_type": key[0], "ev_mode": key[1],
            "etp_sustained_suffix": st["etp_sustained_suffix"],
            "full_dominant_windows": _windows_to_text(st["full_dominant_windows"]),
            "partial_dominant_windows": _windows_to_text(st["partial_dominant_windows"]),
            "negative_islands": _windows_to_text(st["negative_islands"]),
            "n_grid_points": st["n_grid_points"],
            "r_grid_first": st["r_grid"][0], "r_grid_last": st["r_grid"][1],
            "suffix_basis": st["suffix_basis"],
            "full_dominant_basis": st["full_dominant_basis"],
            "partial_dominant_basis": st["partial_dominant_basis"],
            "interval_scope": st["interval_scope"],
            "joint_across_r": st["joint_across_r"],
            "n_non_finite": st["n_non_finite"],
            "n_inconsistent_sign_rows": st["n_inconsistent_sign_rows"],
            "rows_nominal": sum(1 for row in sub
                                if row.get("g_nominal_coverage") is True),
            "rows_diagnostic": sum(1 for row in sub
                                   if row.get("g_nominal_coverage") is not True),
            "all_rows_nominal": all(row.get("g_nominal_coverage") is True
                                    for row in sub),
            "n_cells_rule_changed": changed,
            "n_cells_rule_fixed_evaluated": sum(1 for x in fixed if x is not None),
            "g_hat_rule_fixed_min": (min([x for x in fixed if x is not None])
                                     if any(x is not None for x in fixed) else None),
            "g_hat_rule_fixed_max": (max([x for x in fixed if x is not None])
                                     if any(x is not None for x in fixed) else None),
            "best_partial_rules_seen": ";".join(sorted({str(r) for r in rules if r})),
        })
    return out
