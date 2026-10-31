# -*- coding: utf-8 -*-
"""Single entry point of the PREI reproduction package.

    python run_all.py --mode all --seed 42 [--config configs/baseline.yaml] [--out outputs]

Not the original MATLAB code: this is an independent Python re-implementation.
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


def load_settings(config_path, seed):
    cfg = cfgmod.load_config(config_path)
    cfg.validate(required=REQUIRED, source_check=True)
    settings = cfg.resolved()
    settings["seed"] = int(seed)
    modes = cfgmod.load_config(os.path.join(HERE, "configs", "modes.yaml")).resolved()
    settings["modes"] = modes["modes"]
    if not isinstance(settings["run"]["r_grid"], list):
        raise cfgmod.ConfigError("run.r_grid must be a list")
    return cfg, settings


def load_v2(settings):
    raw = cfgmod.load_config(os.path.join(HERE, "configs", "v2.yaml")).resolved()
    v2 = raw["v2"]
    merged = copy.deepcopy(settings)
    merged["v2"] = v2
    merged["demand"] = dict(merged["demand"])
    for key, val in v2["demand"].items():
        merged["demand"][key] = val
    merged["cost"] = dict(merged["cost"])
    for key, val in v2.get("cost", {}).items():
        merged["cost"][key] = val
    return merged


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
            "energy_delivered_kwh": row["energy_delivered_kwh"],
            "undelivered_rate": row["shortfall_rate"],
            "blocked_ev_charge_rate": (row["blocked_ev_charge"] / row["arrivals_A"]
                                       if row["arrivals_A"] else 0.0),
            "blocked_ev_park_rate": (row["blocked_ev_park"] / row["arrivals_A"]
                                     if row["arrivals_A"] else 0.0),
            "blocked_icev_rate": (row["blocked_icev"] / row["arrivals_A"]
                                  if row["arrivals_A"] else 0.0),
            "peak_concurrency": row["peak_concurrency"],
            "peak_power_kw": row["peak_power_kw"],
        })
    q_rows = v2_q_sensitivity(settings, cost_model, seed, designs)
    etp_points = evaluate.v2_etp_points(stats_rows["g"])
    region_counts = {}
    for row in stats_rows["regions"]:
        region_counts[row["region"]] = region_counts.get(row["region"], 0) + 1
    return {"designs": rows, "best": best_rows, "decomposition": decomp,
            "timeline": timeline_rows, "service": service,
            "g": stats_rows["g"], "confidence": stats_rows["confidence"],
            "cvar": stats_rows["cvar"], "regions": stats_rows["regions"],
            "q_sensitivity": q_rows, "etp_points": etp_points,
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
        hashes[os.path.basename(path)] = (io.content_hash(path)
                                          if os.path.exists(path) else None)
    return {
        "command": " ".join(argv),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "config_sha256": hashes,
        "timings": dict(timings),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="PREI reproduction backend")
    ap.add_argument("--config", default=os.path.join(HERE, "configs", "baseline.yaml"))
    ap.add_argument("--mode", default="all", choices=["static", "v2", "all"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=os.path.join(HERE, "outputs"))
    ap.add_argument("--no-canonical", action="store_true",
                    help="keep the timestamped run directory instead of "
                         "renaming it to canonical-seed<seed>")
    args = ap.parse_args(argv)

    t0 = time.time()
    cfg, settings = load_settings(args.config, args.seed)
    cost_model = costs.CostModel(settings, args.seed)
    config_name = str(cfg.resolved()["meta"]["name"])
    run_dir = os.path.join(args.out, config_name, io.run_id(args.seed))
    suffix = 1
    while os.path.exists(run_dir):
        run_dir = os.path.join(args.out, config_name,
                               io.run_id(args.seed) + "-r%d" % suffix)
        suffix += 1
    io.ensure_dir(run_dir)
    canonical = not args.no_canonical
    run_label = ("canonical-seed%d" % args.seed) if canonical else os.path.basename(run_dir)
    counts = {}
    results = {}
    timings = {}

    io.write_json(os.path.join(run_dir, "params.json"), io.params_snapshot(
        cfg, settings, args.seed, run_label))
    io.write_csv(os.path.join(run_dir, "rule_matrix.csv"), rules.compatibility_matrix(
        theta=0.4))

    if args.mode in ("static", "all"):
        st = time.time()
        block = static_block(settings, args.seed, cost_model)
        counts["static_curves"] = len(block["curves"])
        counts["static_optimum"] = len(block["optimum"])
        counts["scenarios"] = int(settings["run"]["scenario_count"])
        counts["candidates"] = len(block["ms"])
        io.write_csv(os.path.join(run_dir, "static_curves.csv"), block["curves"])
        io.write_csv(os.path.join(run_dir, "static_optimum.csv"), block["optimum"])
        io.write_csv(os.path.join(run_dir, "integer_check.csv"), block["integer"])
        io.write_csv(os.path.join(run_dir, "modes.csv"), block["modes"])
        io.write_csv(os.path.join(run_dir, "etp.csv"), block["etp"])
        sens = cfgmod.load_config(os.path.join(HERE, "configs", "sensitivity.yaml"))
        sens_rows = sensitivity_block(cfg, settings, args.seed, sens.resolved())
        io.write_csv(os.path.join(run_dir, "sensitivity.csv"), sens_rows)
        counts["sensitivity_rows"] = len(sens_rows)
        stx = static_stats(settings, cost_model, args.seed,
                           int(settings["run"]["block_days"]), block)
        io.write_csv(os.path.join(run_dir, "confidence_sets.csv"), stx["confidence"])
        io.write_csv(os.path.join(run_dir, "g_curve.csv"), stx["g"])
        io.write_csv(os.path.join(run_dir, "cvar.csv"), stx["cvar"])
        io.write_json(os.path.join(run_dir, "etp_points.json"), stx["etp_point"])
        saa = evaluate.saa_rows(settings, cost_model, args.seed, reps=10)
        io.write_csv(os.path.join(run_dir, "saa_error.csv"), saa)
        counts["saa_rows"] = len(saa)
        feasibility = evaluate.feasibility_rows(settings, args.seed)
        io.write_csv(os.path.join(run_dir, "feasibility_costs.csv"), feasibility)
        counts["feasibility_rows"] = len(feasibility)
        fig8 = evaluate.fig8_rows(
            settings, cost_model, args.seed,
            n_boot=int(settings["run"].get("bootstrap_reps", 1000)))
        io.write_csv(os.path.join(run_dir, "fig8_regions.csv"), fig8)
        counts["fig8_rows"] = len(fig8)
        timings["static_seconds"] = round(time.time() - st, 3)
        results["etp_points"] = stx["etp_point"]
        results["static_optima"] = {
            "%s|%s|%.1f" % (row["lot_type"], row["ev_mode"], row["r"]): row
            for row in block["optimum"] if row["mode"] == "partition"}
        results["psc_increase_pct_range"] = [
            min(r["psc_increase_pct"] for r in block["optimum"]
                if r["mode"] == "partition" and "psc_increase_pct" in r),
            max(r["psc_increase_pct"] for r in block["optimum"]
                if r["mode"] == "partition" and "psc_increase_pct" in r),
        ]

    if args.mode in ("v2", "all"):
        st = time.time()
        v2_settings = load_v2(settings)
        v2_cost = costs.CostModel(v2_settings, args.seed)
        v2 = v2_block(v2_settings, args.seed, v2_cost)
        io.write_csv(os.path.join(run_dir, "v2_designs.csv"), [
            {k: v for k, v in row.items()} for row in v2["designs"]])
        io.write_csv(os.path.join(run_dir, "v2_best.csv"), v2["best"])
        io.write_csv(os.path.join(run_dir, "v2_service_accounting.csv"), v2["service"])
        io.write_csv(os.path.join(run_dir, "v2_timeline_sample.csv"), v2["timeline"])
        io.write_csv(os.path.join(run_dir, "decomposition.csv"), v2["decomposition"])
        io.write_csv(os.path.join(run_dir, "v2_confidence_sets.csv"), v2["confidence"])
        io.write_csv(os.path.join(run_dir, "v2_g_curve.csv"), v2["g"])
        io.write_csv(os.path.join(run_dir, "v2_regions.csv"), v2["regions"])
        io.write_csv(os.path.join(run_dir, "v2_cvar.csv"), v2["cvar"])
        io.write_csv(os.path.join(run_dir, "v2_q_sensitivity.csv"), v2["q_sensitivity"])
        counts["v2_designs"] = len(v2["designs"])
        counts["v2_days"] = int(v2_settings["v2"]["scenario_count"])
        counts["v2_stat_cells"] = len(v2["g"])
        counts["v2_q_rows"] = len(v2["q_sensitivity"])
        timings["v2_seconds"] = round(time.time() - st, 3)
        results["v2_best"] = [
            {"lot_type": row["lot_type"], "ev_mode": row["ev_mode"],
             "r": row["r"], "q": row["q"],
             "mode": row["mode"], "rule": row["rule"], "theta": row["theta"],
             "ppr": row["ppr"], "v_rmb": row["v_rmb"]}
            for row in v2["best"]]
        results["decomposition"] = v2["decomposition"]
        results["v2_etp_points"] = v2["etp_points"]
        results["v2_region_counts"] = v2["region_counts"]
        results["v2_extra_r_cells"] = v2["extra_r_cells"]

    runtime = time.time() - t0
    summary = io.summary_payload(
        args.seed, run_label, runtime, counts, results,
        notes=[
            "independent Python re-implementation; not the authors' MATLAB code",
            "baseline event_cost_scale=36 is an assumption (see README and report)",
            "confidence sets approximate Martinoli et al. (2026), not their theorem",
        ])
    notes = {
        "params.json": "运行参数快照：每个叶子带 value 与 source（manuscript/assumption/sensitivity）",
        "summary.json": "运行摘要：计数、关键结果、耗时",
        "rule_matrix.csv": "pi_S/pi_F/pi_theta 与三类需求的兼容矩阵（18 行）",
        "static_curves.csv": "静态 PSC 曲线，对应论文图 2 的曲线数据",
        "static_optimum.csv": "各 r 的最优 PPR、被动装桩对照与 PSC 增幅，对应图 2 标记",
        "integer_check.csv": "网格枚举与整数枚举的差",
        "modes.csv": "四种运营模式的最优 PPR 与相对分区的降幅，对应共享/移动充电比较图",
        "etp.csv": "式 (8)(9) 的全安装增量成本与净效益，ETP 判定输入",
        "sensitivity.csv": "单因素 ±20% 与极端值敏感性，对应论文敏感性图",
        "confidence_sets.csv": "静态层候选集/置信集（支撑 Table 11 的静态对照）",
        "g_curve.csv": "静态层 g(r) 与三区域判定（不作 v2 Fig. 7，见 v2_g_curve.csv）",
        "cvar.csv": "静态层 CVaR_0.95；full_install_evaluated 与 zero_reason 消除零值歧义",
        "etp_points.json": "各场地/构成口径下的 ETP 汇总（静态层）",
        "saa_error.csv": "同种子重复 10 次的 SAA 误差：argmin 命中率与 PSC 标准差",
        "feasibility_costs.csv": "event_cost_scale x horizon 网格：最优 PPR 是否落在 (0,1)",
        "fig8_regions.csv": "Fig. 8 的三区地图数据（r, scarcity, g 与置信区间）",
        "v2_designs.csv": "事件层全设计评估（规则 x 设备数 x 模式），Table 10/11 的输入",
        "v2_best.csv": "各 r x q 的最优 v2 设计",
        "v2_service_accounting.csv": "资源-服务台账（Table 10）：可达车位、并发、功率、能量、拒绝率",
        "v2_timeline_sample.csv": "事件时间轴样本（t_a/t_c/t_d/t_r），对应 v2 稿 Fig. 6",
        "v2_confidence_sets.csv": "v2 置信集合（block bootstrap + max-t/holm），Table 11",
        "v2_g_curve.csv": "v2 的 g(r) 与置信区间，Fig. 7",
        "v2_regions.csv": "v2 三区标签（full_dominant/partial_dominant/undetermined），Fig. 8/Table 11",
        "v2_cvar.csv": "v2 CVaR_0.95（tail_samples 与 aux 两条值），Table 11",
        "v2_q_sensitivity.csv": "q 敏感性（q=0.3/0.9，100 天）对最优规则/模式的影响",
        "decomposition.csv": "式 (12) 的路径 A/B 分解与路径依赖",
    }
    manifest = [{"file": name, "sha256": io.content_hash(os.path.join(run_dir, name)),
                 "note": notes.get(name, "")}
                for name in sorted(os.listdir(run_dir)) if not name.startswith("manifest")]
    config_paths = [args.config,
                    os.path.join(HERE, "configs", "modes.yaml"),
                    os.path.join(HERE, "configs", "sensitivity.yaml"),
                    os.path.join(HERE, "configs", "v2.yaml")]
    io.write_json(os.path.join(run_dir, "manifest.json"),
                  dict(manifest_metadata(sys.argv, config_paths, timings),
                       run_id=summary["run_id"], files=manifest))
    summary["timings"] = dict(timings, total_seconds=round(runtime, 3))
    io.write_json(os.path.join(run_dir, "summary.json"), summary)
    if canonical:
        final_dir, archived = canonicalize_outputs(args.out, config_name, run_dir, args.seed)
        run_dir = final_dir
        print("archived_runs:", archived)
    print("run_dir:", run_dir)
    print("runtime_seconds: %.2f" % runtime)
    print("counts:", counts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
