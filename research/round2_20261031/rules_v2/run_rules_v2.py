# -*- coding: utf-8 -*-
"""R2-E：π2 预测共享重设 × 饱和分层的规则对照实验（可复现运行脚本）。

用法（仓库根目录）：
    python research/round2_20261031/rules_v2/run_rules_v2.py

产物（research/round2_20261031/rules_v2/outputs/）：
- scenarios.json   情景定义、车流哈希、实测饱和分层与覆盖表、规则自检结果
- k_sweep.json     每条规则/情景/种子/ k 的指标曲线与 k_α（CONTRACT §3 口径）
- thresholds.json  π2 预测对象 × 保护窗口 × 安全余量 的训练集选择 + 验证集结果
- summary.json     汇总：固定 k、重选 k 分开报告；闸门触发计数与"不能证明预测有效"的情形

设计约束（对应任务书）：
1. 预测对象可配置 charge_arrivals（默认）/ ev_arrivals / connector_load；
2. 闸门扣除本次放行的油车占用（1 个充电位）并扣除调用方声明的本批已放行位数；
3. 保护窗口与已观察油车平均占用时长协调（取较大者）；
4. 阈值/窗口只在 training 情景上选择；validation 情景不重调；
5. 每条规则独立扫 k 重选 k_α；固定 k 与重选 k 的结果分开报告；
6. 情景按 observed_calibrated / amplified_calibrated / synthetic_range /
   synthetic_stress 分开标注；"闸门未触发 ⇒ 结果相同"不作为预测有效性的证据。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import (EPS, RULE_ORDER, PredictingSimulation, amplify_parameters,
                     call_service_level_k, load_fitted_parameters, resolve_traffic_gen,
                     run_metrics)

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import generate as generate_synthetic
from apps.parking_lab.workbench.rules import DEFAULT_PREDICTION_OBJECT, PREDICTION_OBJECTS
from apps.parking_lab.workbench.simulation import Simulation

HERE = Path(__file__).resolve().parent
OUTPUTS = HERE / "outputs"
TRAFFIC_PARAMS = ROOT / "research" / "traffic_generation_20261031" / "fitted_parameters.json"

VERSION_LABEL = "rules_v2-1.0.0"
SEEDS = (1031, 1032)
ALPHA = 0.05
ALPHA_SECONDARY = 0.10
KMAX_CAP = 48
K_STEP = 2
CHARGER_KW = 7.0
SYNTHETIC_N_SPACES = 60
WINDOW_GRID = (10.0, 30.0, 60.0, 120.0)
MARGIN_GRID = (0.0, 1.0, 2.0)
DEFAULT_WINDOW = 30.0
DEFAULT_MARGIN = 1.0
SELECTION_METRICS = ("unmet_no_connector_events", "ice_rejected_while_connector_idle")

# 情景定义。synthetic_range 用稳态强度 λ 设计普通位压力；amplification 同比放大到访与充电需求。
SCENARIOS = [
    # ---- training：阈值/窗口只在这里选 ----
    dict(scenario_id="train_syn_unsat_pe20", family="synthetic_range", split="train", kind="synthetic",
         lambda_base=10.0, ev_share=0.20, charge_probability=0.50, amplification=1.0),
    dict(scenario_id="train_syn_crit_pe20", family="synthetic_range", split="train", kind="synthetic",
         lambda_base=30.0, ev_share=0.20, charge_probability=0.50, amplification=1.0),
    dict(scenario_id="train_syn_unsat_pe40", family="synthetic_range", split="train", kind="synthetic",
         lambda_base=10.0, ev_share=0.40, charge_probability=0.65, amplification=1.0),
    dict(scenario_id="train_syn_crit_pe40", family="synthetic_range", split="train", kind="synthetic",
         lambda_base=30.0, ev_share=0.40, charge_probability=0.65, amplification=1.0),
    dict(scenario_id="train_obs_TPE0610", family="observed_calibrated", split="train", kind="observed",
         lot_id="TPE0610", arrival_factor=1.0, demand_scale=1.0, p_ev=0.30),
    dict(scenario_id="train_obs_TPE0008", family="observed_calibrated", split="train", kind="observed",
         lot_id="TPE0008", arrival_factor=1.0, demand_scale=1.0, p_ev=0.30),
    dict(scenario_id="train_amp_TPE0008_x2.0", family="amplified_calibrated", split="train", kind="observed",
         lot_id="TPE0008", arrival_factor=2.0, demand_scale=2.0, p_ev=0.30),
    # ---- validation：不重调阈值 ----
    dict(scenario_id="val_syn_high_pe20", family="synthetic_range", split="validation", kind="synthetic",
         lambda_base=50.0, ev_share=0.20, charge_probability=0.50, amplification=1.0),
    dict(scenario_id="val_syn_high_pe40", family="synthetic_range", split="validation", kind="synthetic",
         lambda_base=50.0, ev_share=0.40, charge_probability=0.65, amplification=1.0),
    dict(scenario_id="val_syn_lowev_pe08", family="synthetic_range", split="validation", kind="synthetic",
         lambda_base=30.0, ev_share=0.08, charge_probability=0.80, amplification=1.0),
    dict(scenario_id="val_syn_amp_crit_pe40", family="synthetic_range", split="validation", kind="synthetic",
         lambda_base=30.0, ev_share=0.40, charge_probability=0.65, amplification=1.75),
    dict(scenario_id="val_syn_lowev_amp_pe08", family="synthetic_range", split="validation", kind="synthetic",
         lambda_base=30.0, ev_share=0.08, charge_probability=0.80, amplification=1.75),
    dict(scenario_id="val_syn_stress_pe40", family="synthetic_stress", split="validation", kind="synthetic",
         lambda_base=80.0, ev_share=0.40, charge_probability=0.75, amplification=1.0),
    dict(scenario_id="val_obs_TPE0401", family="observed_calibrated", split="validation", kind="observed",
         lot_id="TPE0401", arrival_factor=1.0, demand_scale=1.0, p_ev=0.30),
    dict(scenario_id="val_obs_TPE1380", family="observed_calibrated", split="validation", kind="observed",
         lot_id="TPE1380", arrival_factor=1.0, demand_scale=1.0, p_ev=0.30),
    dict(scenario_id="val_amp_TPE0401_x1.5", family="amplified_calibrated", split="validation",
         kind="observed", lot_id="TPE0401", arrival_factor=1.5, demand_scale=2.0, p_ev=0.30),
    dict(scenario_id="val_amp_TPE1380_x1.3", family="amplified_calibrated", split="validation",
         kind="observed", lot_id="TPE1380", arrival_factor=1.3, demand_scale=2.0, p_ev=0.30),
    dict(scenario_id="val_amp_TPE0008_x3.0", family="amplified_calibrated", split="validation",
         kind="observed", lot_id="TPE0008", arrival_factor=3.0, demand_scale=2.0, p_ev=0.30),
]

VARIANTS = {
    "pi0": {"policy": "dedicated_by_type", "options": {}, "kind": "rule"},
    "pi1": {"policy": "full_open_ice_first", "options": {}, "kind": "rule"},
    "pi2_default": {"policy": "predictive_shared_ice_first",
                    "options": {"prediction_object": DEFAULT_PREDICTION_OBJECT,
                                "coordinate_window": True, "window_min": DEFAULT_WINDOW,
                                "safety_margin": DEFAULT_MARGIN}, "kind": "rule"},
}


def _options_key(options):
    return tuple(sorted((key, options[key]) for key in sorted(options)))


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dump(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, allow_nan=False)
        fh.write("\n")
    print("[write] %s (%.1f KB)" % (path.relative_to(ROOT), path.stat().st_size / 1024))


# ---- 场景运行时（车流只生成一次，所有规则/k 复用同一外生流） --------------------
def synthetic_runtime(spec, seed):
    config = Config.parse({
        "duration_hours": 24.0, "start_hour": 0.0, "scenario": "steady",
        "arrival_rate_hour": float(spec["lambda_base"]) * float(spec["amplification"]),
        "ev_share": float(spec["ev_share"]), "charge_probability": float(spec["charge_probability"]),
        "n_spaces": SYNTHETIC_N_SPACES, "charging_bays": 0, "chargers": 0,
        "charger_kw": CHARGER_KW, "feeder_kw": CHARGER_KW, "reserve_fixed": 0,
        "policy": "dedicated_by_type", "seed": int(seed)})
    arrivals = generate_synthetic(config)
    return {"kind": "synthetic", "n_spaces": SYNTHETIC_N_SPACES, "duration_hours": 24.0,
            "arrivals": arrivals, "n_initial": 0,
            "arrival_rate_hour": config.arrival_rate_hour,
            "ev_share": config.ev_share, "charge_probability": config.charge_probability,
            "stream_hash": _stream_hash(arrivals), "generator_version": "demand.generate"}


def observed_runtime(spec, seed, params, traffic_gen):
    document = params
    factor = float(spec.get("arrival_factor") or 1.0)
    if factor != 1.0:
        document = amplify_parameters(params, factor)
    arrivals, meta = traffic_gen.generate_for_lot(
        document, spec["lot_id"], int(seed), p_ev=spec.get("p_ev"),
        demand_scale=spec.get("demand_scale"))
    return {"kind": "observed", "n_spaces": int(meta["n_spaces"]),
            "duration_hours": float(meta["horizon_min"]) / 60.0,
            "arrivals": tuple(arrivals), "n_initial": int(meta.get("initial_occupancy_n") or 0),
            "arrival_factor": factor,
            "arrival_rate_hour": 0.0, "ev_share": 0.0, "charge_probability": 0.0,
            "stream_hash": meta["stream_hash"], "params_hash": meta.get("params_hash"),
            "generator_version": meta.get("generator_version"),
            "meta": {key: meta.get(key) for key in (
                "lot_id", "n_arrivals", "n_ev", "n_needs_charge", "observed_product_p_ev_q_need",
                "observed_sessions_per_day", "target_charge_arrivals", "demand_scale",
                "identification_conflict", "warm_start_method", "p_ev", "q_need")}}


def _stream_hash(arrivals):
    import hashlib
    payload = "|".join("%d,%.6f,%d,%d,%.6f,%.6f" % (a.vehicle_id, a.time_min, int(a.is_ev),
                                                    int(a.needs_charge), a.dwell_min, a.energy_kwh)
                       for a in arrivals)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_config(spec, runtime, k, seed, policy):
    return Config.parse({
        "duration_hours": runtime["duration_hours"], "start_hour": 0.0, "scenario": "steady",
        "arrival_rate_hour": runtime.get("arrival_rate_hour", 0.0),
        "ev_share": runtime.get("ev_share", 0.0),
        "charge_probability": runtime.get("charge_probability", 0.0),
        "n_spaces": int(runtime["n_spaces"]), "charging_bays": int(k), "chargers": int(k),
        "charger_kw": CHARGER_KW, "feeder_kw": max(CHARGER_KW * k, CHARGER_KW),
        "reserve_fixed": 0, "ice_share_forecast_window_min": DEFAULT_WINDOW,
        "ice_share_free_bay_margin": DEFAULT_MARGIN, "policy": policy, "seed": int(seed)})


def k_grid(scenario_id, runtime):
    kmax = min(KMAX_CAP, int(runtime["n_spaces"]))
    values = [0, 1] + list(range(2, kmax + 1, K_STEP))
    if kmax not in values:
        values.append(kmax)
    return kmax, sorted(set(values))


# ---- 运行器（带缓存） -------------------------------------------------------
class Runner:
    def __init__(self, params, traffic_gen, traffic_status):
        self.params = params
        self.traffic_gen = traffic_gen
        self.traffic_status = traffic_status
        self.runtime_cache = {}
        self.result_cache = {}
        self.rows = []

    def runtime(self, spec, seed):
        key = (spec["scenario_id"], seed)
        if key not in self.runtime_cache:
            if spec["kind"] == "synthetic":
                base = synthetic_runtime(spec, seed)
            else:
                if self.traffic_gen is None:
                    raise RuntimeError("traffic_gen 不可用：" + str(self.traffic_status))
                base = observed_runtime(spec, seed, self.params, self.traffic_gen)
            base["seed"] = seed
            base["spec"] = spec
            self.runtime_cache[key] = base
        return self.runtime_cache[key]

    def run(self, spec, k, seed, variant_id):
        return self.run_with_options(spec, k, seed, variant_id, VARIANTS[variant_id]["options"])

    def run_with_options(self, spec, k, seed, variant_id, options):
        key = (spec["scenario_id"], int(k), seed, variant_id, _options_key(options))
        if key in self.result_cache:
            return self.result_cache[key]
        runtime = self.runtime(spec, seed)
        variant = VARIANTS[variant_id]
        config = build_config(spec, runtime, k, seed, variant["policy"])
        sim = PredictingSimulation(config, runtime["arrivals"], **options)
        sim.run()
        metrics = run_metrics(sim, n_initial=runtime["n_initial"])
        row = {"scenario": spec["scenario_id"], "family": spec["family"], "split": spec["split"],
               "variant": variant_id, "policy": variant["policy"], "k": int(k), "seed": seed,
               "prediction_object": options.get("prediction_object"),
               "window_min": options.get("window_min"),
               "safety_margin": options.get("safety_margin"),
               "coordinate_window": options.get("coordinate_window"),
               "stream_hash": runtime["stream_hash"]}
        row.update(metrics)
        self.result_cache[key] = row
        self.rows.append(row)
        return row

    # k 扫：粗网格 + 在首过点附近补 ±1
    def sweep(self, spec, variant_id):
        runtime = self.runtime(spec, SEEDS[0])
        kmax, grid = k_grid(spec["scenario_id"], runtime)
        for k in grid:
            for seed in SEEDS:
                self.run(spec, k, seed, variant_id)
        result = {"scenario": spec["scenario_id"], "family": spec["family"], "split": spec["split"],
                  "variant": variant_id, "kmax": kmax, "grid": grid,
                  "k_alpha": {}, "k_alpha_alt": {}, "curves": {}, "refined_k": []}
        for metric in ("unmet_no_connector_events", "unmet_no_connector_energy_kwh"):
            by_k = self._curve(spec, variant_id, metric)
            result["curves"][metric] = by_k
            result["k_alpha"][metric] = call_service_level_k(by_k, alpha=ALPHA, metric=metric)
            result["k_alpha_alt"][metric] = call_service_level_k(
                by_k, alpha=ALPHA_SECONDARY, metric=metric)
        # 用 events 指标的首过点补 ±1（只在需要时补，避免无意义全扫）
        events = result["k_alpha"]["unmet_no_connector_events"]
        if events.get("status") == "achieved" and events.get("k") is not None:
            k_cross = int(events["k"])
            for k in (k_cross - 1, k_cross + 1):
                if 0 <= k <= kmax and k not in grid:
                    for seed in SEEDS:
                        self.run(spec, k, seed, variant_id)
                    result["refined_k"].append(k)
            if result["refined_k"]:
                for metric in ("unmet_no_connector_events", "unmet_no_connector_energy_kwh"):
                    by_k = self._curve(spec, variant_id, metric)
                    result["curves"][metric] = by_k
                    result["k_alpha"][metric] = call_service_level_k(by_k, alpha=ALPHA, metric=metric)
                    result["k_alpha_alt"][metric] = call_service_level_k(
                        by_k, alpha=ALPHA_SECONDARY, metric=metric)
        # 每个种子的 k_α（用于观察种子稳定性）
        per_seed = {}
        for seed in SEEDS:
            seed_rows = [alt for alt in self._rows_for(spec, variant_id) if alt["seed"] == seed]
            by_k = {}
            for row in seed_rows:
                by_k.setdefault(row["k"], []).append(row["unmet_no_connector_events"])
            by_k = {k: sum(v) / len(v) for k, v in by_k.items()}
            per_seed[seed] = call_service_level_k(by_k, alpha=ALPHA,
                                                 metric="unmet_no_connector_events")
        result["k_alpha_per_seed"] = per_seed
        return result

    def _rows_for(self, spec, variant_id):
        return [row for row in self.rows
                if row["scenario"] == spec["scenario_id"] and row["variant"] == variant_id]

    def _curve(self, spec, variant_id, metric):
        by_k = {}
        for row in self._rows_for(spec, variant_id):
            by_k.setdefault(row["k"], []).append(row[metric] / 1.0)
        return {k: sum(v) / len(v) for k, v in sorted(by_k.items())}

    def metrics_at(self, spec, variant_id, k):
        rows = [row for row in self._rows_for(spec, variant_id) if row["k"] == int(k)]
        if not rows:
            return None
        summable = [key for key, value in rows[0].items() if isinstance(value, (int, float))
                    and key not in ("k", "seed")]
        result = {"k": int(k), "seeds": sorted(row["seed"] for row in rows), "n_runs": len(rows)}
        for key in summable:
            result[key] = sum(row[key] for row in rows) / len(rows)
        for key in ("stream_hash", "family", "split"):
            result[key] = rows[0][key]
        return result


def reference_k(pi0_sweep):
    """参考布局 k：π0 的 α=0.05 服务 k；不可行时退 α=0.10；仍不可行取实测 unmet 最小的 k。

    参考 k 只用于"固定 k"对照，不是阈值调参；选择依据写入产物，避免把 fallback 当成服务达标。
    """
    primary = pi0_sweep["k_alpha"]["unmet_no_connector_events"]
    if primary.get("k") is not None:
        return int(primary["k"]), "pi0_k_alpha_0.05"
    secondary = pi0_sweep["k_alpha_alt"]["unmet_no_connector_events"]
    if secondary.get("k") is not None:
        return int(secondary["k"]), "pi0_k_alpha_0.10(fallback)"
    curve = pi0_sweep["curves"]["unmet_no_connector_events"]
    best = min(curve, key=lambda k: (curve[k], k))
    return int(best), "argmin_unmet(fallback)"


# ---- 主流程 -----------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="只跑 2 个情景做冒烟（不写正式产物）")
    args = parser.parse_args()
    started = time.time()
    params = load_fitted_parameters(TRAFFIC_PARAMS) if TRAFFIC_PARAMS.exists() else {}
    traffic_gen, traffic_status = resolve_traffic_gen()
    if traffic_gen is not None and params:
        try:
            traffic_gen.load_params(TRAFFIC_PARAMS)
            traffic_status["params_file_ok"] = True
        except Exception as exc:                              # noqa: BLE001
            traffic_status["params_file_ok"] = False
            traffic_status["params_error"] = "%s: %s" % (type(exc).__name__, exc)
    runner = Runner(params, traffic_gen, traffic_status)
    scenarios = list(SCENARIOS)
    if args.quick:
        scenarios = scenarios[:2]
    if traffic_gen is None:
        scenarios = [s for s in scenarios if s["kind"] == "synthetic"]
        print("[warn] traffic_gen 不可用，实测/放大情景全部跳过：", traffic_status)

    meta = {
        "version_label": VERSION_LABEL,
        "command": "python research/round2_20261031/rules_v2/run_rules_v2.py",
        "generated_utc": utc_now(),
        "seeds": list(SEEDS), "alpha": ALPHA, "k_policy": {
            "kmax_cap": KMAX_CAP, "coarse_step": K_STEP, "refinement": "首过点 ±1"},
        "threshold_grid": {"window_min": list(WINDOW_GRID), "safety_margin": list(MARGIN_GRID)},
        "selection_objective": "mean(unmet_no_connector_events) + mean(ice_rejected_while_connector_idle)，等权",
        "source_sha256": {
            "apps/parking_lab/workbench/rules.py": file_sha256(ROOT / "apps/parking_lab/workbench/rules.py"),
            "apps/parking_lab/workbench/prediction.py": file_sha256(ROOT / "apps/parking_lab/workbench/prediction.py"),
            "research/round2_20261031/rules_v2/harness.py": file_sha256(HERE / "harness.py"),
            "research/round2_20261031/rules_v2/run_rules_v2.py": file_sha256(HERE / "run_rules_v2.py"),
            "apps/parking_lab/workbench/tests/test_type_rules.py": file_sha256(
                ROOT / "apps/parking_lab/workbench/tests/test_type_rules.py"),
        },
        "traffic_parameters": {"path": str(TRAFFIC_PARAMS.relative_to(ROOT)),
                              "sha256": file_sha256(TRAFFIC_PARAMS) if TRAFFIC_PARAMS.exists() else None},
        "traffic_gen": traffic_status,
        "allowed_claims": "规则对照结论只在本次情景与参数网格内成立；实测情景的充电需求来自 "
                          "p_EV 假设（未识别），不得当成观测到的充电意愿。",
    }

    # 规则自检：默认选项下 PredictingSimulation 必须与 Simulation 逐字节一致。
    parity = {"status": "not_run"}
    if scenarios:
        spec = next(s for s in scenarios if s["kind"] == "synthetic")
        runtime = runner.runtime(spec, SEEDS[0])
        k = min(6, int(runtime["n_spaces"]))
        config = build_config(spec, runtime, k, SEEDS[0], "predictive_shared_ice_first")
        base = Simulation(config, runtime["arrivals"]); base.run()
        probe = PredictingSimulation(config, runtime["arrivals"],
                                     prediction_object=DEFAULT_PREDICTION_OBJECT,
                                     coordinate_window=False, window_min=DEFAULT_WINDOW,
                                     safety_margin=DEFAULT_MARGIN)
        probe.run()

        def behavior(sim):
            # 行为 = 逐车决策 + 交付/充电开始 + 快照指标；审计 detail 允许不同：
            # 生产仿真不注入离场估计（故 coordinate_window 记录为 True 但未生效），
            # 实验子类注入估计，detail 会多出占用统计，但不得改变任何决策。
            return {
                "decisions": [(v["vehicle_id"], v["bay"], v["admitted"],
                               v["admission"]["reason"]) for v in sim.visits],
                "delivery": [(v["vehicle_id"], round(v["delivered_kwh"], 12),
                              v["charge_start_min"], v["completion_min"],
                              v["departed"]) for v in sim.visits],
                "metrics": sim.snapshot()["metrics"],
                "traffic_hash": sim.traffic_hash,
            }

        base_behavior, probe_behavior = behavior(base), behavior(probe)
        parity = {"status": ("identical_behavior" if base_behavior == probe_behavior
                             else "MISMATCH"),
                  "scenario": spec["scenario_id"], "k": k,
                  "detail_note": "行为（决策/交付/指标）必须一致；admission.detail 允许差异："
                                 "生产仿真无离场估计，实验子类注入了可见离场统计。",
                  "audit_detail_differs": base.export() != probe.export()}
        if parity["status"] != "identical_behavior":
            raise AssertionError("实验子类默认路径与 Simulation 行为不一致：不能用于结论")
    print("[check]", parity)

    # ---- 阶段 A：每条规则独立粗扫 k + 首过点细化 ----
    print("[stage A] k sweep ...")
    sweeps = []
    for spec in scenarios:
        for variant_id in ("pi0", "pi1", "pi2_default"):
            result = runner.sweep(spec, variant_id)
            sweeps.append(result)
            status = result["k_alpha"]["unmet_no_connector_events"]
            print("  %-28s %-12s k_alpha=%s status=%s" % (
                spec["scenario_id"], variant_id, status.get("k"), status.get("status")))

    # ---- 情景分层（用 π0 在 k_α 处的实测普通位利用率） ----
    scenario_meta = {}
    coverage = {}
    for spec in scenarios:
        sid = spec["scenario_id"]
        runtime = runner.runtime(spec, SEEDS[0])
        pi0 = next(item for item in sweeps
                   if item["scenario"] == sid and item["variant"] == "pi0")
        k_ref, k_ref_basis = reference_k(pi0)
        k_ref_status = pi0["k_alpha"]["unmet_no_connector_events"].get("status")
        reference = runner.metrics_at(spec, "pi0", k_ref)
        ordinary = reference["ordinary_utilization"] if reference else None
        if ordinary is None:
            stratum = "no_ordinary_bays"
        elif ordinary < 0.60:
            stratum = "unsaturated"
        elif ordinary < 0.85:
            stratum = "critical"
        else:
            stratum = "high_saturation"
        coverage.setdefault(spec["family"], {}).setdefault(stratum, []).append(sid)
        scenario_meta[sid] = {
            "scenario_id": sid, "family": spec["family"], "split": spec["split"],
            "kind": spec["kind"], "n_spaces": runtime["n_spaces"],
            "duration_hours": runtime["duration_hours"],
            "n_initial": runtime["n_initial"], "n_arrivals": len(runtime["arrivals"]),
            "stream_hash": runtime["stream_hash"],
            "generator_version": runtime.get("generator_version"),
            "observed_meta": runtime.get("meta"),
            "design": {key: spec.get(key) for key in
                       ("lambda_base", "ev_share", "charge_probability", "amplification",
                        "lot_id", "arrival_factor", "demand_scale", "p_ev")},
            "reference_k_pi0": k_ref, "reference_k_status": k_ref_status,
            "reference_k_basis": k_ref_basis,
            "measured_at_reference_k": reference,
            "measured_ordinary_utilization": ordinary,
            "measured_stratum": stratum,
            "measured_charge_requests": reference["charge_requests"] if reference else None,
        }
    # 车流一致性：同一情景/种子跨规则、跨 k 必须同一外生流
    hash_check = {}
    for row in runner.rows:
        key = (row["scenario"], row["seed"])
        hash_check.setdefault(key, set()).add(row["stream_hash"])
    violations = [{"scenario": key[0], "seed": key[1], "hashes": sorted(value)}
                  for key, value in hash_check.items() if len(value) > 1]
    scenario_payload = {"meta": {**meta, "stage": "scenarios"}, "scenarios": scenario_meta,
                        "coverage": coverage, "traffic_hash_violations": violations,
                        "parity_check": parity}
    _, traffic_status_now = resolve_traffic_gen()
    scenario_payload["traffic_gen_runtime"] = traffic_status_now
    dump(OUTPUTS / "scenarios.json", scenario_payload)
    if violations:
        raise AssertionError("同一情景出现多个 traffic_hash：外生流不一致")

    # ---- 阶段 B：π2 预测对象 × 窗口 × 余量，只在 training 情景上选 ----
    print("[stage B] threshold selection (train only) ...")
    train_specs = [spec for spec in scenarios if spec["split"] == "train"]
    selection_rows = []
    for obj in PREDICTION_OBJECTS:
        variant_id = "select_%s" % obj
        VARIANTS[variant_id] = {"policy": "predictive_shared_ice_first", "kind": "selection",
                                "options": {"prediction_object": obj, "coordinate_window": True}}
        for window in WINDOW_GRID:
            for margin in MARGIN_GRID:
                for spec in train_specs:
                    pi0 = next(item for item in sweeps
                               if item["scenario"] == spec["scenario_id"] and item["variant"] == "pi0")
                    k_ref, _ = reference_k(pi0)
                    for seed in SEEDS:
                        options = dict(VARIANTS[variant_id]["options"],
                                       window_min=float(window), safety_margin=float(margin))
                        VARIANTS[variant_id]["options"] = options
                        row = runner.run_with_options(spec, int(k_ref), seed, variant_id, options)
                        score = row["unmet_no_connector_events"] + row["ice_rejected_while_connector_idle"]
                        row["selection_score"] = score
                        row["k_reference"] = int(k_ref)
                        selection_rows.append(row)
        VARIANTS[variant_id]["options"]["window_min"] = DEFAULT_WINDOW
        VARIANTS[variant_id]["options"]["safety_margin"] = DEFAULT_MARGIN
    selected = {}
    selection_summary = {}
    for obj in PREDICTION_OBJECTS:
        variant_id = "select_%s" % obj
        rows = [row for row in selection_rows if row["variant"] == variant_id]
        cells = {}
        for row in rows:
            key = (row["window_min"], row["safety_margin"])
            cells.setdefault(key, []).append(row["selection_score"])
        surface = []
        for (window, margin), values in cells.items():
            surface.append({"window_min": window, "safety_margin": margin,
                            "mean_score": sum(values) / len(values),
                            "mean_unmet": sum(r["unmet_no_connector_events"] for r in rows
                                              if r["window_min"] == window
                                              and r["safety_margin"] == margin) / len(values),
                            "mean_idle_rejections": sum(
                                r["ice_rejected_while_connector_idle"] for r in rows
                                if r["window_min"] == window and r["safety_margin"] == margin) / len(values),
                            "n_runs": len(values)})
        selected_cell = sorted(surface, key=lambda item: (item["mean_score"],
                                                          item["window_min"],
                                                          item["safety_margin"]))[0]
        selected[obj] = {"window_min": selected_cell["window_min"],
                         "safety_margin": selected_cell["safety_margin"],
                         "mean_score": selected_cell["mean_score"],
                         "mean_unmet": selected_cell["mean_unmet"],
                         "mean_idle_rejections": selected_cell["mean_idle_rejections"]}
        selection_summary[obj] = {"surface": sorted(surface, key=lambda item: item["mean_score"])}
        print("  selected %-16s window=%.0f margin=%.1f score=%.3f" % (
            obj, selected[obj]["window_min"], selected[obj]["safety_margin"],
            selected[obj]["mean_score"]))
    thresholds_payload = {"meta": {**meta, "stage": "thresholds", "split_used": "train only"},
                          "grid": {"window_min": list(WINDOW_GRID), "safety_margin": list(MARGIN_GRID)},
                          "selected": selected, "surfaces": selection_summary,
                          "rows": selection_rows}
    dump(OUTPUTS / "thresholds.json", thresholds_payload)

    # ---- 阶段 C：验证集固定 k（k_ref = π0 的 k_α）下的规则差异 ----
    print("[stage C] validation at fixed reference k ...")
    val_specs = [spec for spec in scenarios if spec["split"] == "validation"]
    val_variants = ["pi0", "pi1", "pi2_default"]
    for obj in PREDICTION_OBJECTS:
        vid = "selected_%s" % obj
        VARIANTS[vid] = {"policy": "predictive_shared_ice_first", "kind": "selected",
                         "options": {"prediction_object": obj, "coordinate_window": True,
                                     "window_min": selected[obj]["window_min"],
                                     "safety_margin": selected[obj]["safety_margin"]}}
        val_variants.append(vid)
    fixed_k_rows = []
    for spec in val_specs:
        pi0 = next(item for item in sweeps
                   if item["scenario"] == spec["scenario_id"] and item["variant"] == "pi0")
        k_ref, _ = reference_k(pi0)
        for variant_id in val_variants:
            for seed in SEEDS:
                if variant_id in ("pi0", "pi1", "pi2_default"):
                    row = runner.run(spec, int(k_ref), seed, variant_id)
                else:
                    row = runner.run_with_options(spec, int(k_ref), seed, variant_id,
                                                  VARIANTS[variant_id]["options"])
                row = dict(row)
                row["k_fixed"] = int(k_ref)
                fixed_k_rows.append(row)
    fixed_k_summary = _summarize_pairs(fixed_k_rows, "k_fixed")
    dump(OUTPUTS / "fixed_k_validation.json",
         {"meta": {**meta, "stage": "fixed_k_validation"}, "rows": fixed_k_rows,
          "summary": fixed_k_summary})

    # ---- 阶段 D：每条 π2 变体独立扫 k 重选 k_α ----
    print("[stage D] reselect k per rule ...")
    reselect_variants = ["pi2_default"] + ["selected_%s" % obj for obj in PREDICTION_OBJECTS]
    reselect_rows = []
    for spec in val_specs:
        sid = spec["scenario_id"]
        k_ref = scenario_meta[sid]["reference_k_pi0"]
        pi0_ref = runner.metrics_at(spec, "pi0", k_ref)
        for variant_id in reselect_variants:
            options = VARIANTS[variant_id]["options"]
            result = _sweep_with_options(runner, spec, variant_id, options)
            status = result["k_alpha"]["unmet_no_connector_events"]
            k_alpha = status.get("k")
            metrics_alpha = (runner.metrics_at(spec, variant_id, k_alpha)
                             if k_alpha is not None else None)
            metrics_ref = runner.metrics_at(spec, variant_id, k_ref)
            reselect_rows.append({
                "scenario": sid, "family": spec["family"], "split": spec["split"],
                "variant": variant_id,
                "prediction_object": options.get("prediction_object"),
                "window_min": options.get("window_min"),
                "safety_margin": options.get("safety_margin"),
                "k_reference_pi0": k_ref,
                "k_alpha": k_alpha,
                "delta_k_vs_pi0": (None if k_alpha is None or k_ref is None
                                   else k_alpha - k_ref),
                "status": status.get("status"),
                "curve": result["curves"]["unmet_no_connector_events"],
                "k_alpha_energy": result["k_alpha"]["unmet_no_connector_energy_kwh"].get("k"),
                "k_alpha_per_seed": result["k_alpha_per_seed"],
                "metrics_at_k_alpha": metrics_alpha,
                "metrics_at_k_reference": metrics_ref,
                "pi0_at_k_reference": pi0_ref,
            })
            print("  %-28s %-22s k_ref=%s k_alpha=%s (%s)" % (
                sid, variant_id, k_ref, k_alpha, status.get("status")))
    reselect_summary = _summarize_reselected(reselect_rows, scenario_meta)
    dump(OUTPUTS / "reselect_k_validation.json",
         {"meta": {**meta, "stage": "reselect_k_validation"}, "rows": reselect_rows,
          "summary": reselect_summary})

    # ---- 阶段 A 产物（曲线 + k_α） ----
    k_sweep_payload = {"meta": {**meta, "stage": "k_sweep"},
                       "sweeps": sweeps, "rows": runner.rows,
                       "k_alpha_source": "CONTRACT §3：最小 k 使 mean(metric) ≤ α×mean(metric@k=0)"}
    dump(OUTPUTS / "k_sweep.json", k_sweep_payload)

    # ---- 汇总 ----
    summary = {
        "meta": {**meta, "stage": "summary", "elapsed_s": round(time.time() - started, 2),
                 "n_runs": len(runner.rows)},
        "parity_check": parity,
        "coverage": coverage,
        "scenarios": {sid: {"family": item["family"], "split": item["split"],
                            "measured_stratum": item["measured_stratum"],
                            "ordinary_utilization": item["measured_ordinary_utilization"],
                            "reference_k_pi0": item["reference_k_pi0"],
                            "reference_k_basis": item["reference_k_basis"]}
                      for sid, item in scenario_meta.items()},
        "k_alpha": [{"scenario": item["scenario"], "split": item["split"],
                     "variant": item["variant"],
                     "status": item["k_alpha"]["unmet_no_connector_events"].get("status"),
                     "k": item["k_alpha"]["unmet_no_connector_events"].get("k"),
                     "baseline_unmet": item["k_alpha"]["unmet_no_connector_events"].get("baseline"),
                     "target": item["k_alpha"]["unmet_no_connector_events"].get("target"),
                     "status_alpha_0.10": item["k_alpha_alt"]["unmet_no_connector_events"].get("status"),
                     "k_alpha_0.10": item["k_alpha_alt"]["unmet_no_connector_events"].get("k"),
                     "k_alpha_per_seed": item["k_alpha_per_seed"],
                     "refined_k": item["refined_k"]}
                    for item in sweeps],
        "thresholds": {"selected": selected,
                       "objective": meta["selection_objective"],
                       "note": "窗口/余量只在 training 情景上选；validation 未重调"},
        "fixed_k_validation": fixed_k_summary,
        "reselect_k_validation": reselect_summary,
        "gate_evidence_caveat": "闸门未触发（ice_shared_by_forecast=0 且 "
                                "ice_rejected_by_forecast=0）的情景中 π2 与 π0/π1 相同，"
                                "只能说明该情景没有检验到预测机制，不得作为预测有效的证据。",
    }
    dump(OUTPUTS / "summary.json", summary)
    print("[done] %.1fs, %d runs" % (time.time() - started, len(runner.rows)))


def _sweep_with_options(runner, spec, variant_id, options):
    """对带窗口/余量选项的 π2 变体扫 k（与 Runner.sweep 同口径）。"""
    runtime = runner.runtime(spec, SEEDS[0])
    kmax, grid = k_grid(spec["scenario_id"], runtime)
    original = VARIANTS[variant_id]["options"]
    VARIANTS[variant_id]["options"] = options
    try:
        result = runner.sweep(spec, variant_id)
        return result
    finally:
        VARIANTS[variant_id]["options"] = original


def sweeps_by_variant(sweeps):
    return {item["variant"] for item in sweeps}


def _summarize_pairs(rows, k_key):
    """验证集固定 k：相对 π0 的配对差异（同情景同种子同 k）。"""
    grouped = {}
    for row in rows:
        grouped.setdefault((row["scenario"], row["seed"]), {})[row["variant"]] = row
    pairs = {}
    reference = "pi0"
    for (scenario, seed), by_variant in grouped.items():
        if reference not in by_variant:
            continue
        base = by_variant[reference]
        for variant_id, row in by_variant.items():
            if variant_id == reference:
                continue
            entry = pairs.setdefault(variant_id, {})
            for metric in ("unmet_no_connector_events", "unmet_no_connector_energy_kwh",
                           "delivered_energy_kwh", "ice_rejected_while_connector_idle",
                           "ice_shared_by_forecast", "ice_rejected_by_forecast",
                           "rejected_total", "ev_rejected", "charge_requests"):
                entry.setdefault(metric, {}).setdefault(scenario, []).append(
                    row[metric] - base[metric])
    summary = {}
    for variant_id, metrics in pairs.items():
        summary[variant_id] = {}
        for metric, by_scenario in metrics.items():
            values = [value for scenario_values in by_scenario.values() for value in scenario_values]
            summary[variant_id][metric] = {
                "mean_delta": sum(values) / len(values),
                "n": len(values),
                "by_scenario": {scenario: sum(vals) / len(vals)
                                for scenario, vals in by_scenario.items()},
            }
    return summary


def _summarize_reselected(rows, scenario_meta):
    """每条规则独立重选 k 的结果：Δk、重选后指标、与固定 k 的差异（分离容量效应）。"""
    metric_keys = ("unmet_no_connector_events", "unmet_no_connector_energy_kwh",
                   "ice_rejected_while_connector_idle", "ice_shared_by_forecast",
                   "ice_rejected_by_forecast", "delivered_energy_kwh", "rejected_total")
    summary = {"by_variant": {}, "notes": []}
    for row in rows:
        variant_id = row["variant"]
        entry = summary["by_variant"].setdefault(variant_id, {
            "delta_k": {}, "k_alpha": {}, "k_reference_pi0": {},
            "delta_vs_pi0_at_fixed_k": {}, "delta_vs_same_rule_at_fixed_k": {},
            "status": {}, "k_alpha_per_seed": {}})
        sid = row["scenario"]
        entry["delta_k"][sid] = row["delta_k_vs_pi0"]
        entry["k_alpha"][sid] = row["k_alpha"]
        entry["k_reference_pi0"][sid] = row["k_reference_pi0"]
        entry["status"][sid] = row["status"]
        entry["k_alpha_per_seed"][sid] = row["k_alpha_per_seed"]
        alpha = row.get("metrics_at_k_alpha")
        fixed = row.get("pi0_at_k_reference")
        same = row.get("metrics_at_k_reference")
        if alpha is None or fixed is None or same is None:
            continue
        for metric in metric_keys:
            entry["delta_vs_pi0_at_fixed_k"].setdefault(metric, {})[sid] = (
                alpha[metric] - fixed[metric])
            entry["delta_vs_same_rule_at_fixed_k"].setdefault(metric, {})[sid] = (
                alpha[metric] - same[metric])
    for variant_id, entry in summary["by_variant"].items():
        values = [value for value in entry["delta_k"].values() if value is not None]
        entry["mean_delta_k"] = sum(values) / len(values) if values else None
        entry["n_scenarios"] = len(entry["delta_k"])
        entry["mean_delta_k_per_seed"] = {}
        for metric, mapping in entry["delta_vs_pi0_at_fixed_k"].items():
            entry["mean_delta_vs_pi0_at_fixed_k_" + metric] = (
                sum(mapping.values()) / len(mapping) if mapping else None)
        for metric, mapping in entry["delta_vs_same_rule_at_fixed_k"].items():
            entry["mean_delta_vs_same_rule_at_fixed_k_" + metric] = (
                sum(mapping.values()) / len(mapping) if mapping else None)
    summary["notes"].append("k_α 按 CONTRACT §3 每条规则独立重选；固定 k 结果见 fixed_k_validation.json。")
    summary["notes"].append("重选 k 后不同规则使用不同普通位容量（n_spaces 固定、charging_bays=k），"
                            "因此重选 k 的指标差异同时包含规则效应与容量效应。"
                            "delta_vs_same_rule_at_fixed_k 是同一规则在 k_α 与 k_ref 之间的容量效应；"
                            "delta_vs_pi0_at_fixed_k 是重选 k 后相对 π0 的总差异。")
    return summary


if __name__ == "__main__":
    main()
