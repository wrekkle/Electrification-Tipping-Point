"""阶段1/阶段2 入口：契约 -> 切分 -> 重采样 -> 仿真 -> E1–E7 机器输出 + manifest。

用法（仓库根目录，使用项目指定 Python）：
  python research/round8_20261031/engine/run_phase1.py --mode auto
  python research/round8_20261031/engine/run_phase1.py --mode synthetic --out research/round8_20261031/experiments/_phase1_smoke_synthetic
  python research/round8_20261031/engine/run_phase1.py --mode data --contract <processed 契约.json> --out research/round8_20261031/experiments

模式：
- synthetic：用 engine/synth.py 的合成 fixture 跑通全链路（输出显式标 synthetic_fixture，不是论文结果）；
- data：读 data/processed 契约，产出真实 E1–E7 输出；
- auto：有契约文件就走 data，否则写 missing_data 空壳（并可用 synthetic 自测）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = Path(__file__).resolve().parent
for _p in (str(_ROOT), str(_ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.parking_lab.workbench import publicdata
from apps.parking_lab.workbench.config import Config

import minimality
import offline_opt
import runner
import synth

FAMILIES = ("E1", "E2", "E3", "E4", "E5", "E6", "E7")
FAMILY_FILES = {
    "E1": ("coverage.csv", "fit_metrics.csv", "fit_params.json"),
    "E2": ("curve_E2.csv",),
    "E3": ("search_E3.csv", "classes.json"),
    "E4": ("test_E4.csv",),
    "E5": ("info_E5.csv",),
    "E6": ("energy_E6.csv",),
    "E7": ("traj_E7.csv", "meta_E7.json"),
}


# --------------------------------------------------------------------------- 自测
def selfcheck(seed=20261031):
    """离线枚举/最小性自测：max-flow 与穷举一致、可行解可构造核验、五分类各有归属。

    不依赖数据文件；失败即抛 AssertionError，并把细节打印出来。
    """
    import random
    checks = []

    def check(name, condition, detail=None):
        checks.append({"check": name, "passed": bool(condition), "detail": detail})
        if not condition:
            raise AssertionError("自测失败：%s；detail=%r" % (name, detail))

    rng = random.Random(seed)
    for trial in range(8):
        horizon = 8
        vehicles = []
        for index in range(rng.randrange(1, 4)):
            arrival = rng.randrange(0, 4)
            dwell = rng.randrange(2, max(3, horizon - arrival))
            needs = rng.random() < 0.7
            vehicles.append({"vehicle_id": "v%d" % index, "arrival_min": float(arrival),
                             "dwell_min": float(dwell),
                             "departure_min": float(arrival + dwell),
                             "is_ev": needs or rng.random() < 0.5,
                             "needs_charge": needs,
                             "energy_kwh": round(rng.uniform(0.1, 0.7), 2) if needs else 0.0})
        instance = {"instance_id": "tiny-%d" % trial, "n_spaces": 4, "charging_bays": 2,
                    "connectors": 2, "connector_kw": 7.0, "feeder_kw": None,
                    "horizon_min": horizon, "vehicles": vehicles}
        for k in (0, 1, 2):
            record = offline_opt.check_feasible(instance, k)
            brute = offline_opt.brute_force_feasible(instance, k)
            check("flow_vs_bruteforce_t%d_k%d" % (trial, k),
                  (record["status"] == "feasible") == brute,
                  {"flow": record["status"], "brute": brute})
            if record["status"] == "feasible":
                schedule = record["evidence"].get("schedule")
                if schedule is None:
                    check("no_charge_jobs_t%d_k%d" % (trial, k),
                          not offline_opt.charge_jobs(instance),
                          record["reason"])
                else:
                    verified = offline_opt.verify_schedule(instance, k, schedule)
                    check("schedule_witness_t%d_k%d" % (trial, k), verified["ok"],
                          verified["problems"])

    def search(per_k, k_min, cap, physical, stop):
        return {"instance_id": "synthetic-minimality", "per_k": per_k, "k_min": k_min,
                "k_max_searched": cap, "physical_bound": physical, "stop_reason": stop,
                "model": offline_opt.MODEL,
                "information": "offline_upper_bound_not_executable"}

    confirmed = minimality.classify(search(
        {0: {"status": "infeasible", "reason": "no_connector_with_charge_demand"},
         1: {"status": "infeasible", "reason": "insufficient_connector_minutes"},
         2: {"status": "feasible", "reason": "schedule_exists"}}, 2, 3, 3, "found_feasible"))
    check("class_confirmed_minimal", confirmed["class"] == "confirmed_minimal", confirmed)
    unconfirmed = minimality.classify(search(
        {0: {"status": "infeasible", "reason": "no_connector_with_charge_demand"},
         2: {"status": "feasible", "reason": "schedule_exists"}}, 2, 3, 3, "found_feasible"))
    check("class_minimality_unconfirmed",
          unconfirmed["class"] == "minimality_unconfirmed", unconfirmed)
    physical = minimality.classify(search(
        {0: {"status": "infeasible", "reason": "no_connector_with_charge_demand"},
         1: {"status": "infeasible", "reason": "insufficient_connector_minutes"},
         2: {"status": "infeasible", "reason": "insufficient_connector_minutes"}},
        None, 2, 2, "exhausted_physical_bound"))
    check("class_physically_infeasible", physical["class"] == "physically_infeasible", physical)
    budget = minimality.classify(search(
        {0: {"status": "infeasible", "reason": "no_connector_with_charge_demand"},
         1: {"status": "infeasible", "reason": "insufficient_connector_minutes"}},
        None, 1, 5, "budget_cap"))
    check("class_budget_not_covered", budget["class"] == "budget_not_covered", budget)
    missing = minimality.classify(search(
        {0: {"status": "missing_data", "reason": "缺 connector_kw"}}, None, 0, 3, "missing_data"))
    check("class_missing_data", missing["class"] == "missing_data", missing)
    counts = minimality.count_classes([confirmed, unconfirmed, physical, budget, missing])
    check("count_classes_all_five", all(value == 1 for value in counts.values()), counts)
    return checks


# --------------------------------------------------------------------------- 数据准备
def discover_contract(processed_dir=None):
    """在 data/processed 里找契约文件；找不到返回 (None, 候选列表)。"""
    directory = Path(processed_dir or publicdata.DEFAULT_PROCESSED_DIR)
    if not directory.exists():
        return None, []
    candidates = sorted(directory.glob("*.json"))
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("schema_version") in publicdata.SUPPORTED_SCHEMA_VERSIONS:
            return path, candidates
    return None, candidates


def load_blocks(contract_path):
    """读契约并在事件级坏行被计数剔除后建块（剔除数写入 QA，不静默丢失）。"""
    report = publicdata.load_contract(contract_path, strict=False)
    normalised = report.get("normalised")
    if normalised is None:
        raise publicdata.ContractError(
            "契约不可用（blocking=%s）：%s" % (report.get("blocking_errors"),
                                              report.get("errors", [])[:3]))
    blocks = publicdata.site_day_blocks(normalised)
    return normalised, blocks, report


# --------------------------------------------------------------------------- 输出
def write_missing_shell(out_dir, *, family, reason, required, command, status="missing_data"):
    directory = Path(out_dir) / family
    runner.write_json(directory / "missing_data.json", {
        "schema_version": "r8-family-shell/v1",
        "family": family,
        "status": status,
        "reason": reason,
        "required_inputs": required,
        "note": "数据不足时不伪造数字；此文件即为该族当前状态，补齐输入后重跑 run_phase1.py --mode data",
        "generated_utc": runner.utc_now(),
    })
    runner.write_manifest(directory, family=family, status=status, command=command,
                          seed=None, inputs=[],
                          outputs=[directory / "missing_data.json"],
                          notes=[reason])
    return directory / "missing_data.json"


def run_families(blocks, *, out_dir, seed, command, dataset_label, input_files,
                 k_max=None, coverage_meta=None, dataset_id=None):
    """E1–E7 全流程；返回摘要 dict（供命令行打印与 Lead 汇报）。"""
    out_dir = Path(out_dir)
    split = runner.build_dataset(blocks, seed=seed)
    calibration, test = split["calibration"], split["test"]
    solve = publicdata.select_solve_blocks(calibration)
    mode_label = "synthetic_fixture" if dataset_label == synth.DATASET_ID else "real_data"
    caps = runner.BUDGET_CAPS
    e2_test, budget_e2 = runner.sample_blocks(test, caps["E2_streams"], seed, salt=1)
    e4_test, budget_e4 = runner.sample_blocks(test, caps["E4_streams"], seed, salt=2)
    e5_test, budget_e5 = runner.sample_blocks(test, caps["E5_streams"], seed, salt=3)
    e6_test, budget_e6 = runner.sample_blocks(test, caps["E6_streams"], seed, salt=4)
    e7_test, budget_e7 = runner.sample_blocks(test, caps["E7_streams"], seed, salt=5)
    summary = {"dataset_label": dataset_label, "seed": seed, "mode": mode_label,
               "split": {key: split[key] for key in ("test_site_ids", "test_day_keys", "n",
                                                     "rule", "warnings")},
               "solve_blocks": ["%s:%s" % (b["site_id"], b["day_key"]) for b in solve],
               "families": {}}
    inputs = input_files
    summary["scenario_layer"] = {"label": runner.SCENARIO_LABEL,
                                  "forced_overrides": dict(runner.SCENARIO_FORCE),
                                 "declared_hardware_fields":
                                     sorted(runner.HARDWARE_SCENARIO_FIELDS),
                                 "parameters": {**runner.SCENARIO,
                                                **runner.SCENARIO_FORCE},
                                 "note": ("公开数据未观测到充电基础设施；充电位/枪数/功率/馈线"
                                          "按声明情景层推导，输出行带 capacity_source 与 "
                                          "scenario_label，不得当成实测值"),
                                 "dataset_id": dataset_label}
    summary["budget"] = {"E2": budget_e2, "E4": budget_e4, "E5": budget_e5,
                         "E6": budget_e6, "E7": budget_e7,
                         "note": "计算预算子样本（按 seed 抽样）；不是样本量，样本量=独立场站-日"}

    def manifest(directory, *, family, status="ok", outputs, notes=()):
        return runner.write_manifest(directory, family=family, status=status,
                                     command=command, seed=seed, inputs=inputs,
                                     outputs=outputs, notes=list(notes),
                                     extra={"mode": mode_label,
                                            "dataset_id": dataset_label,
                                            "scenario_label": runner.SCENARIO_LABEL})

    # E1 覆盖 + 拟合 + 留出误差
    e1, coverage = runner.e1_rows(calibration, test, coverage_meta=coverage_meta,
                                  dataset_id=dataset_id or dataset_label)
    e1_dir = out_dir / "E1"
    coverage_rows = [{"site_id": site_id, **{k: v for k, v in info.items()
                                             if k not in ("days", "complete_days_declared")}}
                     for site_id, info in coverage["per_site"].items()]
    e1_files = [runner.write_csv(e1_dir / "coverage.csv", coverage_rows),
                runner.write_csv(e1_dir / "fit_metrics.csv",
                                 [row for row in e1 if row.get("row_kind") != "coverage"]),
                runner.write_json(e1_dir / "fit_params.json", {
                    "unit": coverage["unit"], "dataset_id": coverage["dataset_id"],
                    "n_sites": coverage["n_sites"], "n_days": coverage["n_days"],
                    "n_site_days": coverage["n_site_days"], "n_events": coverage["n_events"],
                    "criteria": coverage["criteria"], "missing": coverage["missing"],
                    "dwell_summary_calibration":
                        publicdata.EmpiricalDwellModel.from_blocks(calibration).summary(),
                    "dwell_summary_test":
                        publicdata.EmpiricalDwellModel.from_blocks(test).summary(),
                    "note": "经验分布，无参数外推；单位=场站-日"})]
    manifest(e1_dir, family="E1", outputs=e1_files,
              notes=["经验重采样；样本量=独立场站-日数，不是 bootstrap 次数"])
    summary["families"]["E1"] = {"files": [str(p) for p in e1_files],
                                 "n_site_days": coverage["n_site_days"],
                                 "criteria": {c["id"]: c["status"] for c in coverage["criteria"]}}

    # 预注册 k：只用 calibration 块（测试块不参与），仿真全整数枚举取 max（风险裕度式选择）
    cal_eval, budget_cal = runner.sample_blocks(calibration, 10, seed, salt=6)
    prereg, prereg_detail, prereg_method = runner.preregistered_k(
        cal_eval, seed=seed, k_max=k_max, policy="A")
    summary["preregistered_k"] = prereg
    summary["preregistered_k_detail"] = prereg_detail
    summary["preregistered_k_method"] = prereg_method
    summary["budget"]["calibration"] = budget_cal

    # 小实例构造（E3/M3）：各场站训练块中"充电需求最大的连续 <=20 辆到达窗口"。
    # 显式声明为实例级子样本（不是完整场站-日），只用于离线完整枚举与最小性分类。
    def window_block(block, size=20):
        events = block["events"]
        if len(events) <= size:
            return dict(block, instance_construction="whole site-day (<=20 arrivals)")
        best_start, best_score = 0, -1
        for start in range(0, len(events) - size + 1):
            score = sum(1 for event in events[start:start + size]
                        if event["is_ev"] and event.get("needs_charge"))
            if score > best_score:
                best_start, best_score = start, score
        chunk = events[best_start:best_start + size]
        return {**block, "events": chunk, "n_events": len(chunk),
                "first_arrival_min": chunk[0]["arrival_min"],
                "instance_construction": ("max-charge-demand consecutive <=20-arrival "
                                          "window (declared subsample of the site-day)")}

    solve_instances = [window_block(block) for block in solve]
    summary["e3_instance_construction"] = {
        "rule": "per site: training site-day with highest charge demand; take the consecutive "
                "<=20-arrival window with the most needs_charge events",
        "note": "实例级子样本；容量/占用只按窗口内车辆算，不代表完整场站-日服务率",
        "instances": [{"site_id": b["site_id"], "day_key": b["day_key"],
                       "n_events": b["n_events"],
                       "construction": b.get("instance_construction")}
                      for b in solve_instances]}

    def k_for_block(block):
        bays = int(runner.site_capability(block["site"])["charging_bays"] or 0)
        if prereg is None:
            return None
        return min(int(prereg), bays)

    # E2 k—服务率曲线（A/D 规则；含 k=0）。固定流设计：只取 charging_bays>=8 的场站，
    # 24 条入选流在 k=0..8 上全部在场（n_streams 逐 k 恒定=24），避免高 k 处流集合漂移。
    e2_rows, e2_design = runner.e2_fixed_rows(test, seed=seed)
    e2_files = [runner.write_csv(out_dir / "E2" / "curve_E2.csv", e2_rows)]
    e2_summary_rows = runner.e2_summary(e2_rows)
    e2_summary_files = [runner.write_csv(out_dir / "E2" / "curve_E2_summary.csv",
                                         e2_summary_rows)]
    runner.write_json(out_dir / "E2" / "curve_E2_summary.json",
                      {"design": e2_design, "n_boot": 1000, "seed": seed,
                       "unit": "independent stream (site-day)",
                       "metrics": ["service_capacity_unmet_rate", "service_ev_parking_failure_rate",
                                   "service_ice_parking_failure_rate", "charging_access_rate",
                                   "energy_service_rate"],
                       "note": "固定流设计：每个 k 的 n_streams 相同；bootstrap 重采样单位=独立场站-日；"
                               "曲线为描述性，不作确认性比较；k 全整数枚举不二分"})
    manifest(out_dir / "E2", family="E2", outputs=e2_files + e2_summary_files,
              notes=["固定流设计：charging_bays>=8 的场站抽样 24 条流，k=0..8 全覆盖；"
                     "curve_E2.csv 含 n_streams_at_k 列",
                     "k 全枚举（无单调性证明不二分）；曲线含 A/D 规则",
                     "不确定性带由行级 bootstrap 生成（单位=场站-日）"])
    summary["families"]["E2"] = {"files": [str(p) for p in e2_files + e2_summary_files],
                                 "rows": len(e2_rows), "design": e2_design}
    summary["budget"]["E2"] = e2_design["budget"]

    # E3 离线最小 k + 五分类（只用 solve/calibration 块）
    e3_rows, e3_classified, e3_counts = runner.e3_rows(solve_instances, k_max=k_max)
    e3_dir = out_dir / "E3"
    e3_files = [runner.write_csv(e3_dir / "search_E3.csv", e3_rows),
                runner.write_json(e3_dir / "classes.json", {
                    "unit": "instance = site-day (offline, future information)",
                    "classes": e3_counts,
                    "class_definitions": minimality.CLASS_DEFINITIONS,
                    "instances": e3_classified,
                    "model": offline_opt.MODEL,
                    "information": "offline_upper_bound_not_executable",
                    "note": "confirmed_minimal 仅在本声明模型内成立；不是物理下界，也不在线可执行"})]
    manifest(e3_dir, family="E3", outputs=e3_files,
              notes=["完整枚举 0..K_max；未使用二分/跳点",
                     "confirmed_minimal 是声明模型内实测结论，不是物理下界"])
    summary["families"]["E3"] = {"files": [str(p) for p in e3_files],
                                 "class_counts": e3_counts,
                                 "instances": [item.get("instance_id") for item in e3_classified]}

    # E4 规则与基线留出测试（同流配对重放，k 来自训练集预注册）
    e4_rows = []
    if prereg is None:
        for block in e4_test:
            e4_rows.append({"family": "E4", "split": "test", "status": "missing_data",
                            "site_id": block["site_id"], "day_key": block["day_key"],
                            "reason": "训练集无法给出预注册 k（E3 离线最小 k 不可得）",
                            "unit": "site-day"})
    else:
        e4_rows = runner.holdout_rows(e4_test, runner.ALL_POLICIES, k_for_block=k_for_block,
                                      seed=seed)
        for row in e4_rows:
            row["family"] = "E4"
            row["k_source"] = "training_max_offline_min_k"
            row["k_clipped_to_charging_bays"] = bool(
                prereg is not None and row.get("k") is not None
                and row["k"] < int(prereg))
    e4_files = [runner.write_csv(out_dir / "E4" / "test_E4.csv", e4_rows)]
    manifest(out_dir / "E4", family="E4", outputs=e4_files,
              notes=["同流配对重放；k 由训练集预注册，测试集不调参",
                     "B2 literature_status=规则改编（见 baseline_meta 字段）",
                     "只评价留出场站/留出整日；information 标记逐行记录"])
    summary["families"]["E4"] = {"files": [str(p) for p in e4_files], "rows": len(e4_rows),
                                 "policies": list(runner.ALL_POLICIES)}

    # E5 逐独立流 Δk（探索性）
    e5_rows = runner.e5_rows(e5_test, k_max=k_max, seed=seed)
    e5_files = [runner.write_csv(out_dir / "E5" / "info_E5.csv", e5_rows)]
    manifest(out_dir / "E5", family="E5", outputs=e5_files,
              notes=["探索性：逐独立流的 Δk 方向与幅度；不作确认性结论"])
    summary["families"]["E5"] = {"files": [str(p) for p in e5_files], "rows": len(e5_rows)}

    # E6 能量约束 × 枪数 × 功率 × 馈线；功率/馈线由情景层决定
    e6_rows = []
    forced_kw = runner.SCENARIO_FORCE.get("connector_kw")
    forced_feeder = runner.SCENARIO_FORCE.get("feeder_kw_per_connector")
    if forced_kw is not None and forced_feeder is not None:
        power_values = (float(forced_kw),)
        feeder_shares = (float(forced_feeder) / float(forced_kw),)
        e6_mode = "regime_forced_power"
    else:
        power_values = (7.0, 11.0)
        feeder_shares = (1.0, 0.5)
        e6_mode = "power_sweep"
    if prereg is None:
        e6_rows.append({"family": "E6", "split": "test", "status": "missing_data",
                        "reason": "无预注册 k，无法做能量约束情景"})
    else:
        e6_rows = runner.e6_rows(e6_test, k_max=k_max, seed=seed,
                                 k_values=[prereg] if prereg is not None else None,
                                 power_values=power_values, feeder_shares=feeder_shares)
        for row in e6_rows:
            row["family"] = "E6"
            row["k_source"] = "preregistered_k"
            row["e6_mode"] = e6_mode
    e6_files = [runner.write_csv(out_dir / "E6" / "energy_E6.csv", e6_rows)]
    manifest(out_dir / "E6", family="E6", outputs=e6_files,
              notes=["能量服务条目含分子/分母/适用条件",
                     "不假设离场后免费补能；被拒请求计入缺口口径",
                     "被拒/初始/零需求/删失/缺失/非法分列在 energy_cat_* 列",
                     "E6 功率/馈线随情景层：forced=%r；power_values=%r；feeder_shares=%r"
                     % (bool(forced_kw), power_values, feeder_shares)])
    summary["families"]["E6"] = {"files": [str(p) for p in e6_files], "rows": len(e6_rows),
                                 "mode": e6_mode, "power_values": list(power_values),
                                 "feeder_shares": list(feeder_shares)}

    # E7 非单调事件轨迹（说明性）
    e7_rows, e7_meta = runner.e7_rows(e7_test, k_max=k_max, seed=seed)
    e7_dir = out_dir / "E7"
    e7_files = [runner.write_csv(e7_dir / "traj_E7.csv", e7_rows),
                runner.write_json(e7_dir / "meta_E7.json", e7_meta)]
    manifest(e7_dir, family="E7", status="ok" if e7_rows else "missing_data",
              outputs=e7_files,
              notes=["说明性单实例轨迹；找不到反例就写 missing_data，不伪造"])
    summary["families"]["E7"] = {"files": [str(p) for p in e7_files],
                                 "status": e7_meta.get("status")}

    # M1/M2/M3
    if prereg is None:
        m_rows = []
        m1 = []
    else:
        m1 = runner.m1_pairs(e5_test, k_max=k_max, seed=seed)
        m3 = runner.m3_pairs(solve_instances, k_max=k_max)
        summary["m3_pairs"] = m3
        m_rows = runner.m_summaries(m1_pairs_data=m1, e4_rows_data=e4_rows,
                                    m3_pairs_data=m3)
    m_dir = out_dir / "M"
    m_files = [runner.write_csv(m_dir / "m_summaries.csv", m_rows),
               runner.write_json(m_dir / "m_summaries.json",
                                 {"comparisons": m_rows, "m1_pairs": m1,
                                  "note": "M1–M3 预注册确认性比较；其余为探索性"})]
    manifest(m_dir, family="M", status="ok" if m_rows else "missing_data",
              outputs=m_files,
              notes=["bootstrap 单位=场站-日/独立流；bootstrap 次数不是样本量",
                     "不显著不等于无效；测试不达标如实报告"])
    summary["comparisons"] = m_rows
    summary["families"]["M"] = {"files": [str(p) for p in m_files]}

    runner.write_json(out_dir / "run_meta.json", summary)
    return summary


# --------------------------------------------------------------------------- CLI
def main(argv=None):
    parser = argparse.ArgumentParser(description="R8-B E1–E7 机器输出")
    parser.add_argument("--mode", choices=("auto", "synthetic", "data"), default="auto")
    parser.add_argument("--out", default=None)
    parser.add_argument("--contract", default=None, help="processed 契约 JSON 路径")
    parser.add_argument("--seed", type=int, default=20261031)
    parser.add_argument("--k-max", type=int, default=None)
    parser.add_argument("--connector-kw", type=float, default=None)
    parser.add_argument("--charging-bay-share", type=float, default=None)
    parser.add_argument("--max-connectors", type=float, default=None)
    parser.add_argument("--feeder-share", type=float, default=None)
    parser.add_argument("--skip-selfcheck", action="store_true")
    parser.add_argument("--scenario-label", default=None,
                        help="显式情景标签（写入行/清单，标明非观测值）")
    parser.add_argument("--force-connector-kw", type=float, default=None,
                        help="强制覆盖每个场站单枪功率（覆盖契约声明的硬件情景）")
    parser.add_argument("--feeder-kw-per-connector", type=float, default=None,
                        help="强制馈线容量 = 枪数 × 该值（kW）")
    args = parser.parse_args(argv)
    runner.set_scenario(connector_kw=args.connector_kw,
                        charging_bay_share=args.charging_bay_share,
                        max_connectors_per_site=args.max_connectors,
                        feeder_share=args.feeder_share)
    if args.scenario_label:
        runner.set_scenario_label(args.scenario_label)
    if args.force_connector_kw is not None or args.feeder_kw_per_connector is not None:
        runner.set_scenario_force(connector_kw=args.force_connector_kw,
                                  feeder_kw_per_connector=args.feeder_kw_per_connector)
    command = " ".join([Path(sys.argv[0]).name] + sys.argv[1:])
    checks = [] if args.skip_selfcheck else selfcheck()
    if checks:
        print(json.dumps({"selfcheck": {"passed": sum(1 for c in checks if c["passed"]),
                                        "failed": sum(1 for c in checks if not c["passed"]),
                                        "details": checks}}, ensure_ascii=False))
        if any(not c["passed"] for c in checks):
            raise SystemExit(1)

    contract = Path(args.contract) if args.contract else None
    candidates = []
    if contract is None and args.mode in ("auto", "data"):
        contract, candidates = discover_contract()
    out_dir = Path(args.out) if args.out else (Path(publicdata.DEFAULT_PROCESSED_DIR).parents[1]
                                               / "experiments")
    result = {"mode": args.mode, "out": str(out_dir), "contract": None if contract is None
              else str(contract)}
    if args.mode == "synthetic" or (args.mode == "auto" and contract is None):
        shells = []
        if args.mode == "auto":
            # 真实数据未到位：先给每族写 missing_data 空壳（不伪造数字），再做合成自测
            shell_reason = ("data/processed 中尚无 public_parking_events/v1 契约文件；"
                            "候选 JSON：%s"
                            % (", ".join(p.name for p in candidates) or "无"))
            for family in FAMILIES:
                shells.append(str(write_missing_shell(
                    out_dir, family=family, reason=shell_reason,
                    required=["schema_version", "sites", "events"], command=command)))
        payload = synth.build_payload()
        normalised = publicdata.normalise_contract(payload)
        blocks = publicdata.site_day_blocks(normalised)
        # 合成 fixture 一律写子目录：不与真实数据输出混放，避免被误当论文结果
        out = Path(out_dir) / "_phase1_smoke_synthetic"
        summary = run_families(blocks, out_dir=out, seed=args.seed, command=command,
                               dataset_label=synth.DATASET_ID, input_files=[],
                               k_max=args.k_max, coverage_meta=payload.get("coverage"),
                               dataset_id=synth.DATASET_ID)
        result.update({"status": "synthetic_fixture", "dataset": synth.DATASET_ID,
                       "blocks": len(blocks), "summary": summary, "out": str(out),
                       "shells": shells,
                       "note": "合成 fixture 自测运行：不是真实数据，也不是论文结果"})
        runner.write_json(out / "run_meta.json", summary)
        print(json.dumps(result, ensure_ascii=True, default=str))
        return result
    if contract is None:
        reason = ("data/processed 中尚无 public_parking_events/v1 契约文件；"
                  "候选 JSON：%s" % (", ".join(p.name for p in candidates) or "无"))
        produced = []
        for family in FAMILIES:
            produced.append(str(write_missing_shell(out_dir, family=family, reason=reason,
                                                    required=["schema_version",
                                                              "sites", "events"],
                                                    command=command)))
        runner.write_json(out_dir / "run_meta.json",
                          {"status": "missing_data", "reason": reason,
                           "families": produced, "candidates": [str(p) for p in candidates],
                           "generated_utc": runner.utc_now(), "seed": args.seed})
        result.update({"status": "missing_data", "reason": reason,
                       "candidates": [str(p) for p in candidates], "shells": produced})
        print(json.dumps(result, ensure_ascii=True, default=str))
        return result
    normalised, blocks, qa = load_blocks(contract)
    declared = ((normalised.get("provenance") or {}).get("scenario_fields") or {})
    if "hardware" in declared:
        runner.set_declared_hardware_fields(
            ("charging_bays", "connectors", "connector_kw", "feeder_kw"))
    summary = run_families(blocks, out_dir=out_dir, seed=args.seed, command=command,
                           dataset_label=normalised.get("dataset_id") or contract.name,
                           input_files=[{"path": str(contract),
                                         "sha256": publicdata.file_sha256(contract)}],
                           k_max=args.k_max,
                           coverage_meta=normalised.get("coverage"),
                           dataset_id=normalised.get("dataset_id") or contract.name)
    summary["input_qa"] = {"contract": str(contract),
                           "events_declared": qa["counts"]["events_declared"],
                           "events_accepted": qa["counts"]["events_accepted"],
                           "events_rejected": qa["counts"]["events_rejected"],
                           "missing_data_errors": sum(1 for e in qa["errors"]
                                                      if e["kind"] == "missing_data"),
                           "warnings": len(qa["warnings"]),
                           "note": "事件级坏行计数剔除；缺容量/缺充电设施字段按声明情景层处理"}
    runner.write_json(out_dir / "run_meta.json", summary)
    result.update({"status": "ok", "dataset": normalised.get("dataset_id"),
                   "blocks": len(blocks), "summary": summary})
    print(json.dumps({"mode": result["mode"], "status": "ok",
                      "out": result["out"], "dataset": result["dataset"],
                      "comparisons": summary.get("comparisons"),
                      "minimality": summary["families"]["E3"]["class_counts"],
                      "preregistered_k": summary.get("preregistered_k")},
                     ensure_ascii=True, default=str))
    return result


if __name__ == "__main__":
    main()
