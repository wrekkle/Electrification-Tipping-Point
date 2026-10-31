# -*- coding: utf-8 -*-
"""run_all

Single entry point of the PREI reproduction package.

    python run_all.py --mode all --seed 42 [--config configs/baseline.yaml] [--out outputs]

Not the original MATLAB code: this is an independent Python re-implementation.

拆分后仅保留 HERE, load_settings, load_v2, main；其余实现由下列模块提供并在此重新导出（公共导入面不变）。
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

from run_blocks import REQUIRED, CHOICES, static_block, static_stats, sensitivity_block, v2_stats_rows, v2_q_sensitivity, v2_block, archive_old_runs, canonicalize_outputs, manifest_metadata



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
        io.write_csv(os.path.join(run_dir, "v2_g_structure.csv"), v2["g_structure"])
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
        results["v2_g_structure"] = v2["g_structure"]
        results["v2_region_counts"] = v2["region_counts"]
        results["v2_extra_r_cells"] = v2["extra_r_cells"]
        results["v2_interval_scope"] = {
            "per_r": "pointwise marginal interval at each r",
            "joint_across_r": False,
            "region_labels": ("inherit the per-r interval status; see the "
                              "region_confidence column of v2_g_curve.csv / "
                              "v2_regions.csv"),
            "etp": ("point-estimate sign pattern on the discrete r grid; no "
                    "joint coverage across r and no finite-sample ETP guarantee"),
        }

    runtime = time.time() - t0
    summary = io.summary_payload(
        args.seed, run_label, runtime, counts, results,
        notes=[
            "independent Python re-implementation; not the authors' MATLAB code",
            "baseline event_cost_scale=36 is an assumption (see README and report)",
            "confidence sets approximate Martinoli et al. (2026), not their theorem",
            "v2 g intervals are per-r pointwise; three-region labels, dominant "
            "windows and ETP keep that pointwise scope and carry no joint "
            "coverage across r; block_len>1 intervals are diagnostic only "
            "(see v2_g_curve.csv g_nominal_coverage/region_confidence)",
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
        "v2_g_structure.csv": "占优窗口 vs 持续 ETP 后缀，以及规则是否同时改变",
        "v2_regions.csv": "v2 三区标签（full_dominant/partial_dominant/undetermined），Fig. 8/Table 11",
        "v2_cvar.csv": "v2 CVaR_0.95（tail_samples 与 aux 两条值），Table 11",
        "v2_q_sensitivity.csv": "q 敏感性（q=0.3/0.9，100 天）对最优规则/模式的影响",
        "decomposition.csv": "式 (12) 的路径 A/B 分解与路径依赖",
    }
    manifest = [{"file": name, "sha256": io.file_sha256(os.path.join(run_dir, name)),
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
