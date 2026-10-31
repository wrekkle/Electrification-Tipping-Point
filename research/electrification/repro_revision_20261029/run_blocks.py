# -*- coding: utf-8 -*-
"""run_blocks

拆分自 run_all.py，内容逐字节搬移以保持行为不变；公共入口仍由 run_all 提供。
"""
from __future__ import annotations
import argparse
import copy
import os
import platform
import sys
import time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
import numpy as np
from prei import config as cfgmod
from prei import costs, evaluate, io, rules, stats


REQUIRED = [
    "run.scenario_count", "run.horizon_years", "run.operating_days_per_year",
    "run.r_grid", "run.m_grid_step", "lot.n_spaces", "lot.pnc_vacancy_rate",
    "lot.plc_arrivals_ratio", "demand.ev_modes", "demand.beta_variance",
    "demand.beta_variance_ceiling", "cost.c_char", "cost.pile_life_years",
    "cost.c_om_year", "cost.c_en_ev", "cost.c_en_icev", "cost.t_hunt_min",
    "cost.k_delay", "cost.v_kmh", "cost.c_fu_ev", "cost.c_fu_icev",
    "cost.vot_mu", "cost.vot_sigma", "cost.c_com", "cost.complaint_logit_a",
    "cost.complaint_logit_b", "cost.complaint_accounting",
    "cost.event_cost_scale", "cost.c_com_scale", "cost.vot_scale",
    "cost.vot_sigma_scale", "static.modes",
]


CHOICES = {
    "cost.complaint_accounting": ["embedded", "separate"],
    "cost.event_cost_scale": None,
}


def static_block(settings, seed, cost_model):
    total, daily, ms, meta = evaluate.static_matrices(settings, cost_model, seed)
    curves = evaluate.curves_rows(settings, total, daily)
    optimum, integer_rows = evaluate.optimum_rows(settings, cost_model, total, seed)
    modes = evaluate.modes_summary(settings, total)
    etp = evaluate.etp_rows(settings, cost_model, total, seed)
    return {
        "total": total, "daily": daily, "ms": ms,
        "curves": curves, "optimum": optimum, "integer": integer_rows,
        "modes": modes, "etp": etp,
    }


def static_stats(settings, cost_model, seed, block_len, block):
    total = block["total"]
    daily = block["daily"]
    ms = block["ms"]
    N = int(settings["lot"]["n_spaces"])
    jN = ms.index(N) if N in ms else len(ms) - 1
    partial_idx = [j for j, m in enumerate(ms) if m < N]
    rng = np.random.default_rng(cfgmod.derive_seed(seed, "stats"))
    rows_conf, rows_g, rows_cvar = [], [], []
    alpha = 0.05
    n_boot = int(settings["run"].get("bootstrap_reps", 1000))
    for lot_type in evaluate.LOT_TYPES:
        for ev_mode in settings["demand"]["ev_modes"]:
            g_rows = []
            for r in settings["run"]["r_grid"]:
                part = total[(lot_type, ev_mode, float(r), "partition")]
                full_col = total[(lot_type, ev_mode, float(r), "full")][:, jN]
                candidates = np.column_stack(
                    [full_col] + [part[:, j] for j in partial_idx])
                labels = (["V(N,pi_F)"] +
                          ["m=%d,pi_S" % ms[j] for j in partial_idx])
                cs = stats.confidence_set(candidates, n_boot=n_boot, alpha=alpha,
                                          block_len=block_len, rng=rng)
                rows_conf.append({
                    "lot_type": lot_type, "ev_mode": ev_mode, "r": float(r),
                    "best": labels[cs["best"]],
                    "best_mean_rmb": float(cs["means"][cs["best"]]),
                    "included": ";".join(labels[j] for j in cs["included"]),
                    "excluded": ";".join(labels[j] for j in cs["excluded"]),
                    "set_size": len(cs["included"]),
                    "n_scenarios": cs["n_scenarios"], "n_boot": cs["n_boot"],
                    "block_len": cs["block_len"], "critical_value": cs["critical_value"],
                })
                gi = stats.g_interval(full_col, part[:, partial_idx],
                                      n_boot=n_boot, alpha=alpha,
                                      block_len=block_len, rng=rng)
                region = stats.three_region(gi["g_hat"], gi["g_lo"], gi["g_hi"])
                g_rows.append({"lot_type": lot_type, "ev_mode": ev_mode,
                               "r": float(r), **gi, "region": region})
                # CVaR of the daily operating loss for the best partial design
                means_part = part.mean(axis=0)
                jbest = partial_idx[int(np.argmin(means_part[partial_idx]))]
                daily_loss = daily[(lot_type, ev_mode, float(r), "partition")][:, jbest]
                daily_full = daily[(lot_type, ev_mode, float(r), "full")][:, jN]
                rows_cvar.append({
                    "lot_type": lot_type, "ev_mode": ev_mode, "r": float(r),
                    "design": "m=%d,pi_S" % ms[jbest],
                    **evaluate.cvar_fields(daily_loss, daily_full),
                })
            g_rows.sort(key=lambda x: x["r"])
            rows_g.extend(g_rows)
    etp_by = {}
    for row in rows_g:
        key = (row["lot_type"], row["ev_mode"])
        etp_by.setdefault(key, []).append(row)
    etp_points = {("%s|%s" % key): stats.etp_from_g(val)
                  for key, val in etp_by.items()}
    return {"confidence": rows_conf, "g": rows_g, "cvar": rows_cvar,
            "etp_point": etp_points}


def sensitivity_block(cfg, settings, seed, sens):
    r_grid = sens["sensitivity"]["r_grid"]
    scenarios = sens["sensitivity"]["scenarios"]
    base_settings = copy.deepcopy(settings)
    base_cost = costs.CostModel(base_settings, seed)
    base_opt = {}
    for lot_type in evaluate.LOT_TYPES:
        for ev_mode in ("beta", "binomial"):
            for r in r_grid:
                s = evaluate.scenario_set(base_settings, seed, lot_type, r, ev_mode)
                N = int(base_settings["lot"]["n_spaces"])
                ms = evaluate.m_candidates(N, float(base_settings["run"]["m_grid_step"]))
                vals = []
                for m in ms:
                    le_ev, le_ice = evaluate.static_leavers(s, "partition", m, N, 0.0)
                    vals.append(base_cost.psc(m, le_ev, le_ice))
                j = int(np.argmin(vals))
                base_opt[(lot_type, ev_mode, float(r))] = (ms[j] / N, vals[j])
    rows = []
    for scen in scenarios:
        overrides = scen.get("overrides") or {}
        cfg2 = cfg.apply_overrides(overrides)
        settings2 = cfg2.resolved()
        settings2["seed"] = int(seed)
        settings2["modes"] = settings["modes"]
        cost2 = costs.CostModel(settings2, seed)
        for lot_type in evaluate.LOT_TYPES:
            for ev_mode in ("beta", "binomial"):
                for r in r_grid:
                    s = evaluate.scenario_set(settings2, seed, lot_type, r, ev_mode)
                    N = int(settings2["lot"]["n_spaces"])
                    ms = evaluate.m_candidates(N, float(settings2["run"]["m_grid_step"]))
                    vals = []
                    for m in ms:
                        le_ev, le_ice = evaluate.static_leavers(s, "partition", m, N, 0.0)
                        vals.append(cost2.psc(m, le_ev, le_ice))
                    j = int(np.argmin(vals))
                    base_ppr, base_psc = base_opt[(lot_type, ev_mode, float(r))]
                    rows.append({
                        "scenario": scen["name"], "lot_type": lot_type,
                        "ev_mode": ev_mode, "r": float(r),
                        "best_ppr": ms[j] / N,
                        "psc_opt_rmb": float(vals[j]),
                        "base_ppr": base_ppr, "base_psc_rmb": base_psc,
                        "ppr_change": ms[j] / N - base_ppr,
                        "psc_change_pct": ((vals[j] - base_psc) / base_psc * 100.0),
                    })
    return rows


def v2_stats_rows(cells, settings, seed):
    """g(r), confidence sets, CVaR and region labels for every v2 cell.

    The statistical candidate set is the fixed-mode set (pi_S/pi_F/pi_theta);
    overhead/mobile charging is reported separately in v2_best and is not part
    of the sharing-rule tipping-point comparison (same scope as the static layer).
    """
    n_boot = int(settings["run"].get("bootstrap_reps", 1000))
    block_len = int(settings["run"].get("block_days", 1))
    out = {"g": [], "confidence": [], "cvar": [], "regions": []}
    for key in sorted(cells):
        cell = cells[key]
        rng = np.random.default_rng(cfgmod.derive_seed(
            seed, "v2stats", key[0], key[1], round(cell["r"], 6),
            round(cell["q"], 6)))
        stats_cell = evaluate.v2_cell_stats(
            cell, settings, n_boot=n_boot, alpha=0.05,
            block_len=block_len, rng=rng, candidate_modes=("fixed",))
        for name in out:
            out[name].append(stats_cell[name])
    return out


def v2_q_sensitivity(settings, cost_model, seed, designs):
    """Cheap q scan (fewer days): does the best rule/mode change with q?"""
    v2 = settings["v2"]
    spec = v2.get("q_sensitivity") or {}
    q_list = [float(q) for q in spec.get("q_list", [])]
    r_list = [float(r) for r in spec.get("r_list", [])]
    n_days = int(spec.get("scenario_count", 100))
    N = int(settings["lot"]["n_spaces"])
    rows = []
    if not q_list:
        return rows
    for lot_type in v2["lot_types"]:
        for ev_mode in v2["ev_modes"]:
            for r in r_list:
                for q in q_list:
                    cell = evaluate.v2_cell_matrix(
                        settings, cost_model, seed, lot_type, ev_mode, r, q,
                        n_days, designs)
                    j = int(np.argmin(cell["V_mean"]))
                    design = designs[j]
                    rows.append({
                        "lot_type": lot_type, "ev_mode": ev_mode, "r": r, "q": q,
                        "best_mode": design["mode"], "best_rule": design["rule"],
                        "best_theta": design["theta"],
                        "best_m": int(design["m"]),
                        "best_ppr": float(design["m"]) / float(N),
                        "best_v_rmb": float(cell["V_mean"][j]),
                        "mean_daily_loss_rmb": float(cell["means"]["daily_loss_rmb"][j]),
                        "n_days": n_days,
                    })
    return rows


def v2_block(settings, seed, cost_model):
    v2 = settings["v2"]
    N = int(settings["lot"]["n_spaces"])
    designs = evaluate.v2_designs(v2, N)
    r_list = [float(r) for r in v2["r_list"]]
    q_list = [float(q) for q in v2["q_list"]]
    rows, cells, sample = evaluate.v2_eval(
        settings, cost_model, seed, r_list=r_list, q_list=q_list,
        designs=designs, with_timeline=True)
    stats_rows = v2_stats_rows(cells, settings, seed)
    extra = evaluate.refine_r_grid(
        stats_rows["g"], r_list,
        step=float(v2.get("r_refinement_step", 0.02)))
    extra_cells = 0
    for (lot_type, ev_mode), r_extra in sorted(extra.items()):
        if not r_extra:
            continue
        add_rows, add_cells, _ = evaluate.v2_eval(
            settings, cost_model, seed, r_list=r_extra, q_list=q_list,
            lot_types=[lot_type], ev_modes=[ev_mode], designs=designs,
            with_timeline=False)
        rows.extend(add_rows)
        cells.update(add_cells)
        extra_cells += len(r_extra)
    if extra_cells:
        stats_rows = v2_stats_rows(cells, settings, seed)
    best = evaluate.v2_best(rows)
    best_rows = sorted((dict(x) for x in best.values()),
                       key=lambda x: (x["lot_type"], x["ev_mode"], x["r"], x["q"]))
    decomp = []
    for lot_type in settings["v2"]["lot_types"]:
        for ev_mode in settings["v2"]["ev_modes"]:
            for q in settings["v2"]["q_list"]:
                decomp.extend(evaluate.decomposition_rows(
                    rows, lot_type, ev_mode, 0.7, float(q), N))
    timeline_rows = []
    if sample is not None:
        design, timeline = sample
        for row in timeline:
            timeline_rows.append({**{k: v for k, v in row.items()},
                                  "mode": design["mode"], "rule": design["rule"],
                                  "design_m": design["m"]})
    service = []
    for row in rows:
        service.append({
            "lot_type": row["lot_type"], "ev_mode": row["ev_mode"],
            "r": row["r"], "q": row["q"],
            "mode": row["mode"], "rule": row["rule"], "theta": row["theta"],
            "devices": row["devices"],
            "berths_reachable": (min(N, row["devices"]) if row["mode"] == "fixed"
                                 else min(N, row["devices"] * int(settings["v2"]["coverage"]))),
            "max_sessions": min(row["devices"],
                                int(settings["v2"]["feeder_kw"] // settings["v2"]["power_kw"])),
            "rated_power_kw": settings["v2"]["power_kw"],
            "feeder_kw": settings["v2"]["feeder_kw"],
            "energy_requested_kwh": row["energy_requested_kwh"],
            "energy_requested_admitted_kwh": row["energy_requested_admitted_kwh"],
            "energy_requested_all_kwh": row["energy_requested_all_kwh"],
            "rejected_energy_kwh": row["rejected_energy_kwh"],
            "rejected_ev_charge": row["rejected_ev_charge"],
            "energy_delivered_kwh": row["energy_delivered_kwh"],
            "unserved_energy_kwh": row["unserved_energy_kwh"],
            "unserved_rate_all": row["unserved_rate_all"],
            "energy_time_unit": "minute",
            "undelivered_rate": row["shortfall_rate"],
            "blocked_ev_charge_rate": (row["blocked_ev_charge"] / row["arrivals_A"]
                                       if row["arrivals_A"] else 0.0),
            "blocked_ev_park_rate": (row["blocked_ev_park"] / row["arrivals_A"]
                                     if row["arrivals_A"] else 0.0),
            "blocked_icev_rate": (row["blocked_icev"] / row["arrivals_A"]
                                  if row["arrivals_A"] else 0.0),
            "peak_concurrency": row["peak_concurrency"],
            "peak_power_kw": row["peak_power_kw"],
            "device_moves_executed": row["device_moves_executed"],
            "device_moves_cancelled": row["device_moves_cancelled"],
            "device_move_conflicts": row["device_move_conflicts"],
        })
    q_rows = v2_q_sensitivity(settings, cost_model, seed, designs)
    etp_points = evaluate.v2_etp_points(stats_rows["g"])
    g_structure = evaluate.v2_g_structure(stats_rows["g"])
    region_counts = {}
    for row in stats_rows["regions"]:
        region_counts[row["region"]] = region_counts.get(row["region"], 0) + 1
    return {"designs": rows, "best": best_rows, "decomposition": decomp,
            "timeline": timeline_rows, "service": service,
            "g": stats_rows["g"], "confidence": stats_rows["confidence"],
            "cvar": stats_rows["cvar"], "regions": stats_rows["regions"],
            "q_sensitivity": q_rows, "etp_points": etp_points,
            "g_structure": g_structure,
            "region_counts": region_counts, "extra_r_cells": extra_cells,
            "designs_count": len(designs)}


def archive_old_runs(config_dir, keep_names, archive_dir):
    """Move every run directory except keep_names into the archive folder."""
    moved = []
    keep = set(keep_names)
    if not os.path.isdir(config_dir):
        return moved
    for name in sorted(os.listdir(config_dir)):
        path = os.path.join(config_dir, name)
        if not os.path.isdir(path) or name in keep:
            continue
        io.ensure_dir(archive_dir)
        target = os.path.join(archive_dir, name)
        suffix = 1
        while os.path.exists(target):
            target = os.path.join(archive_dir, "%s-r%d" % (name, suffix))
            suffix += 1
        os.replace(path, target)
        moved.append(name)
    return moved


def canonicalize_outputs(out_root, config_name, run_dir, seed):
    """Keep exactly one canonical run per config; archive older directories."""
    config_dir = os.path.join(out_root, config_name)
    archive_dir = os.path.join(out_root, "_archive", config_name)
    canonical = os.path.join(config_dir, "canonical-seed%d" % int(seed))
    if os.path.exists(canonical):
        io.ensure_dir(archive_dir)
        target = os.path.join(archive_dir, "canonical-seed%d-%s" % (int(seed), io.run_id(seed)))
        base_target = target
        suffix = 1
        while os.path.exists(target):
            target = base_target + "-r%d" % suffix
            suffix += 1
        os.replace(canonical, target)
    moved = archive_old_runs(
        config_dir, (os.path.basename(canonical), os.path.basename(run_dir)),
        archive_dir)
    os.replace(run_dir, canonical)
    return canonical, moved


def manifest_metadata(argv, config_paths, timings):
    hashes = {}
    for path in config_paths:
        hashes[os.path.basename(path)] = (io.file_sha256(path)
                                          if os.path.exists(path) else None)
    return {
        "command": " ".join(argv),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "config_sha256": hashes,
        "timings": dict(timings),
    }
