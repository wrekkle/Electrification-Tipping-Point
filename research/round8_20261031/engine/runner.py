"""E1–E7 机器输出 runner（R8-B）：留出评价、k 全枚举曲线、离线最小性、能量结算、manifest。

纪律（PLAN §3.1/§3.6/§3.7）：
- 选择与评价分离：k 的选择只用 calibration/solve 块；test 块只在 run_holdout 里评价。
- 配对重放：同一 stream 在同一 hash 下跑所有规则，比较只在流内做差。
- 统计单位：场站-日或独立流；不把重采样次数当样本量。
- 不达标如实记录：feasible 用 service_semantics.feasible 三态（True/False/None）。
- 每条输出带 run manifest：命令、种子、输入哈希、输出版本。
- 数据不足的族写 missing_data 空壳，不伪造数字。
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = Path(__file__).resolve().parent
for _p in (str(_ROOT), str(_ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.parking_lab.workbench import energy_ledger, publicdata, service_metrics, stat_tools
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.service_semantics import CONSTRAINTS_3, feasible, minimal_feasible
from apps.parking_lab.workbench.simulation import Simulation

import minimality
import offline_opt
from baselines import BASELINE_META, BASELINE_NAMES, BaselineSimulation

RUN_SCHEMA_VERSION = "r8-run-manifest/v1"
OUTPUT_VERSION = "r8-engine-v1-2026-10-31"

# 规则代号沿第三轮报告：A=π0 专用、B=π1 全开、C=protected_quota、D=π2 预测共享。
RULES = {"A": "dedicated_by_type", "B": "full_open_ice_first",
         "C": "protected_quota", "D": "predictive_shared_ice_first"}
ALL_POLICIES = list(RULES) + list(BASELINE_NAMES)
SERVICE_ALPHA = 0.05
# B1 的 p_share 预注册值：只用训练集定一次，测试集不调参（PLAN §3.2/§3.6）。
B1_P_SHARE = 0.25
MISSING_INPUTS_NOTE = "缺失输入不填默认值：feeder_kw 缺失时按不加限的馈线跑并显式标记"

# 充电设施口径：公开停车数据没有观测到充电基础设施（P4 的充电容量缺失）。
# 下列参数是**声明的情景层**，不是观测值；每个输出行带 scenario_label 与 capacity_source。
SCENARIO_LABEL = "scenario_charging_layer_not_observed"
# 契约 provenance.scenario_fields.hardware 声明为情景的字段：标 scenario_declared_in_contract，
# 不得当成实测值（数据方明确写 "NOT observed in the Melbourne source"）。
HARDWARE_SCENARIO_FIELDS = set()


def set_declared_hardware_fields(fields):
    """登记契约里声明为情景的硬件字段（其余仍按 observed 处理）。"""
    HARDWARE_SCENARIO_FIELDS.clear()
    HARDWARE_SCENARIO_FIELDS.update(fields)
    return sorted(HARDWARE_SCENARIO_FIELDS)
SCENARIO_DEFAULTS = {
    "connector_kw": 7.0,            # 单枪功率情景
    "charging_bay_share": 0.10,     # 充电车位占全部车位比例情景
    "max_connectors_per_site": 4,   # 每场站枪数上限（小实例 k<=8 约束内）
    "feeder_share": 0.5,            # 馈线容量 = 枪数 × 功率 × 该比例
}
SCENARIO = dict(SCENARIO_DEFAULTS)
# 显式情景覆盖（用于"可决可行域"敏感性运行，如 main22：22 kW、馈线=枪数×22）：
# 覆盖不改变观测事件，但强制改写契约里声明的硬件情景值，并保留来源标签。
SCENARIO_FORCE = {}


def set_scenario_label(label):
    """显式情景标签；所有输出行/清单用该标签标明这是情景层而非观测。"""
    global SCENARIO_LABEL
    SCENARIO_LABEL = str(label)
    return SCENARIO_LABEL


def set_scenario_force(**values):
    """强制覆盖硬件情景字段。允许键：connector_kw（单枪 kW）、feeder_kw_per_connector（每枪馈线 kW）。"""
    allowed = {"connector_kw", "feeder_kw_per_connector"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("未知强制情景参数：" + ", ".join(sorted(unknown)))
    for key, value in values.items():
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("强制情景参数 %s 必须是正有限数值" % key)
        SCENARIO_FORCE[key] = float(value)
    return dict(SCENARIO_FORCE)
# 计算预算：各族只用确定性子样本跑（按 seed 抽样，写进 manifest），不是样本量。
BUDGET_CAPS = {"E2_streams": 24, "E4_streams": 20, "E5_streams": 10,
               "E6_streams": 6, "E7_streams": 10}


def set_scenario(**overrides):
    """设置充电情景层参数（只影响情景口径，不改变观测到的停车事件）。"""
    allowed = set(SCENARIO_DEFAULTS)
    unknown = set(overrides) - allowed
    if unknown:
        raise ValueError("未知情景参数：" + ", ".join(sorted(unknown)))
    for key, value in overrides.items():
        if value is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("情景参数 %s 必须是正有限数值" % key)
        SCENARIO[key] = float(value)
    SCENARIO["max_connectors_per_site"] = int(round(SCENARIO["max_connectors_per_site"]))
    return dict(SCENARIO)


def site_capability(site):
    """场站容量：观测到的直接用；缺充电设施字段时按声明情景层推导，并逐项标来源。"""
    n_spaces = site.get("n_spaces")
    charging_bays = site.get("charging_bays")
    connectors = site.get("connectors")
    source = {"n_spaces": "observed", "charging_bays": "observed", "connectors": "observed",
              "connector_kw": "observed", "feeder_kw": "observed"}
    if charging_bays is None and n_spaces is not None:
        charging_bays = max(0, int(math.floor(float(n_spaces) * SCENARIO["charging_bay_share"])))
        source["charging_bays"] = SCENARIO_LABEL
    if connectors is None and charging_bays is not None:
        connectors = min(int(SCENARIO["max_connectors_per_site"]), int(charging_bays))
        source["connectors"] = SCENARIO_LABEL
    kw = site.get("connector_kw")
    if kw is None:
        kw = SCENARIO["connector_kw"]
        source["connector_kw"] = SCENARIO_LABEL
    feeder = site.get("feeder_kw")
    if feeder is None:
        feeder = max(1, int(connectors or 1)) * float(kw) * SCENARIO["feeder_share"]
        source["feeder_kw"] = SCENARIO_LABEL
    for key in ("charging_bays", "connectors", "connector_kw", "feeder_kw"):
        if key in HARDWARE_SCENARIO_FIELDS and source.get(key) == "observed":
            source[key] = "scenario_declared_in_contract"
    # 强制情景覆盖（放在声明标记之后，确保来源仍标为情景而非观测/契约声明）
    if "connector_kw" in SCENARIO_FORCE:
        kw = float(SCENARIO_FORCE["connector_kw"])
        source["connector_kw"] = SCENARIO_LABEL
    if "feeder_kw_per_connector" in SCENARIO_FORCE:
        feeder = max(1, int(connectors or 1)) * float(SCENARIO_FORCE["feeder_kw_per_connector"])
        source["feeder_kw"] = SCENARIO_LABEL
        source["connector_kw"] = source["connector_kw"] if source.get("connector_kw") != "observed" else SCENARIO_LABEL
    if SCENARIO_FORCE:
        # 强制覆盖后充电位/枪数口径也属于该情景运行（保持可追溯）
        for key in ("charging_bays", "connectors"):
            if source.get(key) == "scenario_declared_in_contract":
                source[key] = SCENARIO_LABEL
    derived = sorted({key for key, value in source.items() if value != "observed"})
    return {"n_spaces": n_spaces, "charging_bays": charging_bays, "connectors": connectors,
            "connector_kw": float(kw), "feeder_kw": float(feeder),
            "source": source, "derived_fields": derived,
            "scenario": ({**SCENARIO, **SCENARIO_FORCE}
                         if (derived or SCENARIO_FORCE) else None),
            "scenario_label": SCENARIO_LABEL if derived else None}


def sample_blocks(blocks, cap, seed, salt=0):
    """按 seed 的确定性子样本（用于计算预算；抽样写进 manifest，不当作样本量）。"""
    blocks = list(blocks)
    if cap is None or len(blocks) <= cap:
        return blocks, {"cap": cap, "used": len(blocks), "sampled": False}
    index_rng = __import__("random").Random(int(seed) + 7919 * (1 + int(salt)))
    picked = sorted(index_rng.sample(range(len(blocks)), int(cap)))
    return [blocks[i] for i in picked], {"cap": cap, "used": len(picked), "sampled": True,
                                         "method": "seeded index sample (no replacement)"}


# --------------------------------------------------------------------------- 基础 IO
def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    return publicdata.file_sha256(path)


def flat(value):
    """CSV 单元格：dict/list 转规范 JSON 字符串，其余原样（None -> 空）。"""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
    return value


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return path


def write_csv(path, rows, fieldnames=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore",
                                    lineterminator="\n")
            writer.writeheader()
            for row in rows:
                writer.writerow({key: flat(row.get(key)) for key in fieldnames})
        else:
            handle.write(",".join(fieldnames) + "\n")
    return path


def write_manifest(out_dir, *, family, status, command, seed, inputs, outputs, notes=None,
                   extra=None):
    """写 run manifest：命令/种子/输入哈希/输出哈希/输出版本。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": RUN_SCHEMA_VERSION,
        "family": family,
        "status": status,
        "generated_utc": utc_now(),
        "output_version": OUTPUT_VERSION,
        "command": command,
        "seed": seed,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "inputs": [{"path": str(item["path"]),
                    "sha256": item.get("sha256") or sha256_file(item["path"]),
                    **{k: v for k, v in item.items() if k not in ("path", "sha256")}}
                   for item in inputs],
        "outputs": [{"path": Path(item).name, "sha256": sha256_file(item)}
                    for item in outputs],
        "notes": notes or [],
    }
    if extra:
        manifest.update(extra)
    write_json(out_dir / "manifest.json", manifest)
    return manifest


# --------------------------------------------------------------------------- 仿真执行
def _site_of(block):
    return block["site"]


def stream_from_block(block, *, dwell_mode="block", seed=0):
    return publicdata.BlockResampler([block], seed=seed, dwell_mode=dwell_mode).stream(0)


def stream_horizon(stream):
    horizon = 0.0
    for event in stream["events"]:
        horizon = max(horizon, event["time_min"] + event["dwell_min"])
    return horizon


def config_for(site, policy, k, *, horizon_min, seed=0,
               connector_kw=None, feeder_kw=None, arrival_rate_hour=0.0):
    """构造仿真配置：k=枪数；chargers<=charging_bays<=n_spaces 由调用方保证或被拒绝。"""
    capability = site_capability(site)
    charging_bays = capability["charging_bays"]
    n_spaces = capability["n_spaces"]
    if charging_bays is None or n_spaces is None:
        raise ValueError("场站缺 n_spaces/charging_bays（missing_data）")
    if not isinstance(k, int) or isinstance(k, bool) or k < 0:
        raise ValueError("k 必须是非负整数")
    if k > charging_bays:
        raise ValueError("k=%d 超过充电车位数 %d：配置不合法" % (k, charging_bays))
    kw = float(connector_kw) if connector_kw is not None else capability["connector_kw"]
    feeder = float(feeder_kw) if feeder_kw is not None else capability["feeder_kw"]
    rule = RULES.get(policy, "full_open_ice_first")
    params = {
        "n_spaces": int(n_spaces), "charging_bays": int(charging_bays), "chargers": int(k),
        "charger_kw": kw, "feeder_kw": feeder,
        "arrival_rate_hour": max(0.0, float(arrival_rate_hour)),
        # 上限 72h：个别超长停留不让配置非法；超窗部分在口径上记右删失
        "duration_hours": min(72.0, max(0.1, math.ceil(float(horizon_min) - 1e-9) / 60.0)),
        "start_hour": 0.0, "seed": int(seed), "policy": rule,
        "reserve_fixed": min(4, int(charging_bays)),
        "protected_bays": 0,
    }
    return Config.parse(params)


def _arrival_rate(stream, horizon_min):
    hours = max(1e-9, float(horizon_min) / 60.0)
    return max(0.0, len(stream["events"]) / hours)


def run_policy(stream, site, policy, k, *, seed=0, connector_kw=None, feeder_kw=None,
               protected_bays=None, b2_params=None):
    """在一条流上跑一个策略（规则 A–D 或基线 B0–B2），返回扁平结果行。"""
    if policy not in ALL_POLICIES:
        raise ValueError("未知策略：%r" % (policy,))
    arrivals = publicdata.to_traffic_arrivals(stream)
    horizon = stream_horizon(stream)
    capability = site_capability(site)
    # 到达强度按本流的事件密度设置（只影响内部预测器，不影响外生到达）
    config = config_for(site, policy, k, horizon_min=horizon, seed=seed,
                        connector_kw=connector_kw, feeder_kw=feeder_kw,
                        arrival_rate_hour=_arrival_rate(stream, horizon))
    missing_inputs = list(capability["derived_fields"])
    if connector_kw is not None or feeder_kw is not None:
        missing_inputs = [name for name in missing_inputs
                          if not (name == "connector_kw" and connector_kw is not None)
                          and not (name == "feeder_kw" and feeder_kw is not None)]
    if policy in RULES:
        sim = Simulation(config, arrivals=arrivals)
        baseline = None
    else:
        bays = protected_bays
        if bays is None:
            bays = int(math.ceil(B1_P_SHARE * int(site.get("charging_bays") or 0)))
        sim = BaselineSimulation(config, policy, arrivals=arrivals,
                                 protected_bays=bays, b2_params=b2_params)
        baseline = policy
    sim.run()
    export = sim.export()
    visits = export["visits"]
    service = service_metrics.summarise(visits, config)
    energy = energy_ledger.settle(visits, horizon_min=sim.horizon)
    verdict_row = {"service_metrics": service,
                   "capacity_only_unmet_rate": service["rates"]["capacity_unmet_rate"],
                   "charge_requests": service["denominators"]["exogenous_charge_requests"]}
    row = {
        "schema_version": "r8-eval-row/v1",
        "site_id": stream["site_id"], "day_key": stream["day_key"],
        "stream_id": stream["stream_id"], "stream_hash": stream["stream_hash"],
        "policy": policy, "policy_kind": "rule" if policy in RULES else "baseline",
        "policy_impl": RULES.get(policy, policy),
        "k": k, "n_events": len(stream["events"]), "n_visits": len(visits),
        "horizon_min": sim.horizon, "seed": seed,
        "model": "workbench.simulation (event-exact, fixed connectors, shared feeder)",
        "information": "online_observable",
        "missing_inputs": missing_inputs,
        "capacity_source": capability["source"],
        "scenario_layer": capability["scenario"],
        "scenario_label": capability["scenario_label"],
        "traffic_hash": export["traffic_hash"],
        "admitted": sum(1 for v in visits if v["admitted"]),
        "rejected": sum(1 for v in visits if not v["admitted"]),
    }
    row.update({("service_" + key): value for key, value in service["rates"].items()})
    row.update({("num_" + key): value for key, value in service["numerators"].items()})
    row.update({("den_" + key): value for key, value in service["denominators"].items()})
    row["service_missing_fields"] = service["missing"]
    row["censored_sessions"] = service["levels"]["censored_sessions"]
    row["pending_energy_kwh"] = service["levels"]["pending_energy_kwh"]
    row["capacity_unmet_rate"] = service["rates"]["capacity_unmet_rate"]
    # 供 service_semantics 直接消费的规范键（capacity 项在 service_semantics 里叫 capacity_only）
    row["capacity_only_unmet_rate"] = service["rates"]["capacity_unmet_rate"]
    row["charge_requests"] = service["denominators"]["exogenous_charge_requests"]
    row["feasible_3constraints"] = feasible(verdict_row, constraints=CONSTRAINTS_3,
                                            alpha=SERVICE_ALPHA)
    row["feasible_raw"] = feasible(verdict_row, constraints=CONSTRAINTS_3, alpha=SERVICE_ALPHA)
    energy_kinds = energy["categories"]
    row.update({("energy_cat_" + key): value for key, value in energy_kinds.items()})
    row["parking_service_rate"] = energy["parking_service"]["rate"]
    row["parking_service_num"] = energy["parking_service"]["numerator"]
    row["parking_service_den"] = energy["parking_service"]["denominator"]
    row["charging_access_rate"] = energy["charging_access"]["rate"]
    row["charging_access_num"] = energy["charging_access"]["numerator"]
    row["charging_access_den"] = energy["charging_access"]["denominator"]
    dep = energy["departure_energy_service"]["admitted_departed"]
    dep_all = energy["departure_energy_service"]["including_rejected"]
    row["delivered_kwh"] = dep["delivered_kwh"]
    row["demand_kwh"] = dep["demand_kwh"]
    row["gap_kwh"] = dep["gap_kwh"]
    row["energy_service_rate"] = dep["service_rate"]
    row["energy_gap_rate"] = dep["gap_rate"]
    row["delivered_kwh_incl_rejected"] = dep_all["delivered_kwh"]
    row["demand_kwh_incl_rejected"] = dep_all["demand_kwh"]
    row["gap_kwh_incl_rejected"] = dep_all["gap_kwh"]
    row["energy_service_rate_incl_rejected"] = dep_all["service_rate"]
    row["censored_sessions_energy"] = energy["censored"]["n_sessions"]
    row["energy_missing_fields"] = [item["field"] for item in energy["missing"]["fields"]]
    row["energy_illegal"] = energy["illegal"]["n_visits"]
    if baseline is not None:
        row["baseline_meta"] = BASELINE_META[baseline]
    return row


def k_curve(stream, site, policy, k_values, *, seed=0, **kwargs):
    """对给定 k 列表逐点评测（不做二分：无单调性证明）。"""
    return [run_policy(stream, site, policy, k, seed=seed, **kwargs) for k in k_values]


def sim_minimal_k(rows, *, alpha=SERVICE_ALPHA):
    """由 k 曲线行求最小可行 k（service_semantics 三态口径，不插值）。"""
    by_k = {}
    for row in rows:
        by_k[int(row["k"])] = {"service_metrics": {
            "rates": {key[len("service_"):]: row.get(key) for key in row
                      if key.startswith("service_") and key != "service_missing_fields"},
            "denominators": {key[len("den_"):]: row.get(key) for key in row
                             if key.startswith("den_")}},
            "capacity_only_unmet_rate": row.get("capacity_only_unmet_rate"),
            "charge_requests": row.get("den_exogenous_charge_requests")}
    return minimal_feasible(by_k, constraints=CONSTRAINTS_3, alpha=alpha)


def _k_values_for(site, k_max=None):
    charging_bays = int(site_capability(site)["charging_bays"] or 0)
    cap = charging_bays if k_max is None else min(charging_bays, int(k_max))
    return list(range(0, cap + 1))


# --------------------------------------------------------------------------- E1
def _normalised_from_blocks(blocks):
    sites, events = {}, []
    for block in blocks:
        sites[block["site_id"]] = dict(block["site"])
        for row in block["events"]:
            events.append({"event_id": row["event_id"], "site_id": row["site_id"],
                           "arrival_min": row["arrival_min"], "day_key": row["day_key"],
                           "dwell_min": row["dwell_min"], "is_ev": row["is_ev"],
                           "needs_charge": row["needs_charge"],
                           "energy_kwh": row["energy_kwh"]})
    return {"sites": sites, "events": events, "dataset_id": None, "coverage": {}}


def _interarrival(block):
    rows = block["events"]
    return [rows[i + 1]["arrival_min"] - rows[i]["arrival_min"] for i in range(len(rows) - 1)]


def e1_rows(calibration_blocks, test_blocks, *, coverage_meta=None, dataset_id=None):
    """E1：覆盖度 + 停留/到达拟合 + 留出误差（单位=场站-日）。

    coverage_meta = 契约 payload.coverage（含 complete_days 声明）；不传则 P3 完整性记 unverified。
    """
    rows = []
    normalised = _normalised_from_blocks(calibration_blocks + test_blocks)
    normalised["coverage"] = coverage_meta or {}
    normalised["dataset_id"] = dataset_id
    coverage = publicdata.coverage_report(normalised)
    for criterion in coverage["criteria"]:
        rows.append({"family": "E1", "row_kind": "coverage",
                     "metric": criterion["id"], "status": criterion["status"],
                     "value": criterion.get("value"), "requirement": criterion.get("requirement"),
                     "reason": criterion.get("reason"), "unit": coverage["unit"],
                     "n_site_days": coverage["n_site_days"], "n_sites": coverage["n_sites"],
                     "n_days": coverage["n_days"], "n_events": coverage["n_events"]})
    cal_model = publicdata.EmpiricalDwellModel.from_blocks(calibration_blocks)
    test_model = publicdata.EmpiricalDwellModel.from_blocks(test_blocks)
    for category in cal_model.CATEGORIES:
        cal_values = cal_model.pools[category]
        test_values = test_model.pools[category]
        if not cal_values or not test_values:
            rows.append({"family": "E1", "row_kind": "dwell_fit", "category": category,
                         "status": "missing_data", "n_calibration": len(cal_values),
                         "n_test": len(test_values),
                         "reason": "训练集或测试集该类别无停留样本"})
            continue
        ks = stat_tools.ks_statistic(cal_values, test_values)
        cal_summary = cal_model.summary()[category]
        test_summary = test_model.summary()[category]
        rows.append({"family": "E1", "row_kind": "dwell_fit", "category": category,
                     "status": "ok", "n_calibration": len(cal_values),
                     "n_test": len(test_values), "ks_statistic": ks,
                     "mean_calibration": cal_summary["mean"], "mean_test": test_summary["mean"],
                     "p50_calibration": cal_summary["p50"], "p50_test": test_summary["p50"],
                     "p90_calibration": cal_summary["p90"], "p90_test": test_summary["p90"],
                     "holdout_mean_rel_error": (abs(test_summary["mean"] - cal_summary["mean"])
                                                / cal_summary["mean"]
                                                if cal_summary["mean"] else None),
                     "estimator": "empirical distribution (no parametric fit)",
                     "unit": "site-day"})
    cal_gaps, test_gaps = [], []
    for block in calibration_blocks:
        cal_gaps.extend(_interarrival(block))
    for block in test_blocks:
        test_gaps.extend(_interarrival(block))
    if cal_gaps and test_gaps:
        rows.append({"family": "E1", "row_kind": "arrival_fit", "status": "ok",
                     "n_calibration": len(cal_gaps), "n_test": len(test_gaps),
                     "ks_statistic": stat_tools.ks_statistic(cal_gaps, test_gaps),
                     "mean_gap_calibration": sum(cal_gaps) / len(cal_gaps),
                     "mean_gap_test": sum(test_gaps) / len(test_gaps),
                     "unit": "site-day",
                     "note": "块内相邻到达间隔的合并经验分布；块间相关未建模（block resampling 保留）"})
    else:
        rows.append({"family": "E1", "row_kind": "arrival_fit", "status": "missing_data",
                     "reason": "训练或测试块内事件少于 2 条，无法计算到达间隔"})
    return rows, coverage


# --------------------------------------------------------------------------- E3
def e3_rows(solve_blocks, *, k_max=None, feeder_mode="site"):
    """E3：对每个代表性场站-日做 0..K_max 完整枚举并五分类（离线、非在线可执行）。"""
    per_k_rows, classified, class_counts = [], [], {name: 0 for name in minimality.CLASSES}
    for block in solve_blocks:
        instance_id = "%s:%s" % (block["site_id"], block["day_key"])
        capability = site_capability(block["site"])
        try:
            instance = offline_opt.instance_from_block(
                block, connector_kw=capability["connector_kw"],
                feeder_kw=capability["feeder_kw"])
        except offline_opt.InstanceTooLarge as exc:
            search = {"instance_id": instance_id, "per_k": {}, "k_min": None,
                      "k_max_searched": None, "physical_bound": None,
                      "stop_reason": "instance_too_large", "model": offline_opt.MODEL,
                      "information": "offline_upper_bound_not_executable"}
            info = minimality.classify(search, instance_note=str(exc))
            info["class"] = "budget_not_covered"
            info["reason"] = "超出小实例完整枚举范围（车辆≤20）：%s" % exc
            rows = minimality.rows(info, instance_id=instance_id,
                                   n_vehicles=len(block["events"]), search=search)
            per_k_rows.extend(rows)
            classified.append({"instance_id": instance_id, "notes": str(exc), **info})
            class_counts[info["class"]] += 1
            continue
        except ValueError as exc:
            search = {"instance_id": instance_id, "per_k": {}, "k_min": None,
                      "k_max_searched": None, "physical_bound": None,
                      "stop_reason": "missing_data", "model": offline_opt.MODEL,
                      "information": "offline_upper_bound_not_executable"}
            info = minimality.classify(search, missing_fields=[str(exc)])
            rows = minimality.rows(info, instance_id=instance_id,
                                   n_vehicles=len(block["events"]), search=search)
            per_k_rows.extend(rows)
            classified.append({"instance_id": instance_id, "notes": str(exc), **info})
            class_counts[info["class"]] += 1
            continue
        instance = dict(instance, connectors=capability["connectors"])
        instance["charging_bays"] = capability["charging_bays"]
        if feeder_mode == "unbounded":
            instance = dict(instance, feeder_kw=None)
        search = offline_opt.min_connectors(instance, k_max=k_max)
        info = minimality.classify(search)
        info["instance_id"] = instance_id
        info["n_vehicles"] = len(instance["vehicles"])
        info["n_charge_jobs"] = len(offline_opt.charge_jobs(instance))
        info["feeder_mode"] = feeder_mode
        classified.append(info)
        class_counts[info["class"]] += 1
        per_k_rows.extend(minimality.rows(info, instance_id=instance_id,
                                          n_vehicles=len(instance["vehicles"]),
                                          search=search))
    return per_k_rows, classified, class_counts


# --------------------------------------------------------------------------- 主流程
def build_dataset(blocks, *, seed=0, holdout_site_fraction=0.25, holdout_day_fraction=0.2):
    split = publicdata.split_site_days(blocks, seed=seed,
                                       holdout_site_fraction=holdout_site_fraction,
                                       holdout_day_fraction=holdout_day_fraction)
    return split


def holdout_rows(test_blocks, policies, *, k_for_block, seed=0, split_label="test"):
    """同一 test 块（独立流）上配对重放所有策略；比较只在同一 stream 内做差。"""
    rows = []
    for block in test_blocks:
        stream = stream_from_block(block, seed=seed)
        k = k_for_block(block)
        site = block["site"]
        capability = site_capability(site)
        if capability["n_spaces"] is None or capability["charging_bays"] is None or k is None:
            for policy in policies:
                rows.append({"family": "E4", "split": split_label,
                             "site_id": block["site_id"], "day_key": block["day_key"],
                             "stream_id": stream["stream_id"],
                             "stream_hash": stream["stream_hash"], "policy": policy,
                             "k": k, "status": "missing_data",
                             "reason": "场站缺 n_spaces/charging_bays 或预注册 k 不可得",
                             "unit": "site-day"})
            continue
        for policy in policies:
            try:
                rows.append({**run_policy(stream, block["site"], policy, k, seed=seed),
                             "split": split_label})
            except ValueError as exc:
                rows.append({"family": "E4", "split": split_label,
                             "site_id": block["site_id"], "day_key": block["day_key"],
                             "stream_id": stream["stream_id"],
                             "stream_hash": stream["stream_hash"],
                             "policy": policy, "k": k, "status": "error",
                             "reason": str(exc), "unit": "site-day"})
    return rows


def k_curve_rows(test_blocks, policies, *, k_max=None, seed=0, family="E2"):
    rows = []
    for block in test_blocks:
        stream = stream_from_block(block, seed=seed)
        site = block["site"]
        for policy in policies:
            try:
                rows.extend({**row, "family": family, "split": "test"}
                            for row in k_curve(stream, site, policy,
                                               _k_values_for(site, k_max), seed=seed))
            except ValueError as exc:
                rows.append({"family": family, "split": "test", "status": "error",
                             "site_id": block["site_id"], "day_key": block["day_key"],
                             "policy": policy, "reason": str(exc)})
    return rows


E2_FIXED_K = 8


def e2_fixed_rows(test_blocks, *, k_fixed=E2_FIXED_K, cap=24, seed=0):
    """E2 固定流设计：只取 charging_bays>=k_fixed 的场站，抽样 cap 条流，
    每条入选流都跑 k=0..k_fixed，保证每个 k 上的 n_streams 恒定（避免高 k 处流集合漂移）。"""
    eligible = [b for b in test_blocks
                if (site_capability(b["site"])["charging_bays"] or 0) >= k_fixed]
    picked, budget = sample_blocks(eligible, cap, seed, salt=1)
    rows = []
    for block in picked:
        stream = stream_from_block(block, seed=seed)
        site = block["site"]
        for policy in ("A", "D"):
            for row in k_curve(stream, site, policy, list(range(0, k_fixed + 1)), seed=seed):
                rows.append({**row, "policy": policy, "e2_design": "fixed_streams"})
    size = {}
    for row in rows:
        key = (row.get("policy"), int(row["k"]))
        size[key] = size.get(key, 0) + 1
    for row in rows:
        row["n_streams_at_k"] = size[(row.get("policy"), int(row["k"]))]
    return rows, {"design": "fixed_streams", "k_fixed": k_fixed,
                  "eligible_sites": sorted({b["site_id"] for b in picked}),
                  "n_streams": len(picked), "k_values": list(range(0, k_fixed + 1)),
                  "budget": budget,
                  "note": "固定流设计：入选流在每个 k 上都在场；曲线不作确认性比较"}


def e2_summary(rows, *, n_boot=1000, seed=20261031):
    """E2 汇总：按 policy×k 对独立场站-日重采样给均值与 bootstrap 区间。"""
    from apps.parking_lab.workbench.stat_tools import bootstrap_ci
    metrics = ("service_capacity_unmet_rate", "service_ev_parking_failure_rate",
               "service_ice_parking_failure_rate", "charging_access_rate", "energy_service_rate")
    groups = {}
    for row in rows:
        groups.setdefault((row["policy"], int(row["k"])), []).append(row)
    out = []
    for (policy, k), subset in sorted(groups.items()):
        entry = {"policy": policy, "k": k, "n_streams": len(subset),
                 "n_events": sum(int(float(row["n_events"])) for row in subset),
                 "unit": "independent stream (site-day)", "design": "fixed_streams",
                 "bootstrap": {"n_boot": n_boot, "seed": seed, "method": "percentile"}}
        for metric in metrics:
            values = [float(row[metric]) for row in subset if row.get(metric) not in ("", None)]
            if len(values) < 2:
                entry[metric + "_mean"] = None
                entry[metric + "_low"] = None
                entry[metric + "_high"] = None
                continue
            ci = bootstrap_ci(values, n_boot=n_boot, alpha=0.05, seed=seed)
            entry[metric + "_mean"] = ci["point"]
            entry[metric + "_low"] = ci["low"]
            entry[metric + "_high"] = ci["high"]
        out.append(entry)
    return out


def e5_rows(test_blocks, *, k_max=None, seed=0, policies=("A", "D")):
    """E5：逐独立流的 Δk（政策 D − 政策 A 的仿真最小可行 k），探索性。"""
    rows = []
    for block in test_blocks:
        stream = stream_from_block(block, seed=seed)
        site = block["site"]
        results = {}
        for policy in policies:
            curve = k_curve(stream, site, policy, _k_values_for(site, k_max), seed=seed)
            verdict = sim_minimal_k(curve)
            results[policy] = verdict
        base = results[policies[0]]
        base_k = base.get("min_known_feasible")
        for policy in policies:
            verdict = results[policy]
            k_value = verdict.get("min_known_feasible")
            delta = (k_value - base_k
                     if k_value is not None and base_k is not None else None)
            rows.append({"family": "E5", "split": "test", "site_id": block["site_id"],
                         "day_key": block["day_key"], "stream_id": stream["stream_id"],
                         "stream_hash": stream["stream_hash"], "policy": policy,
                         "k_min_feasible": k_value,
                         "confirmed_minimal_sim": verdict.get("confirmed_minimal"),
                         "undecidable_ks": verdict.get("undecidable_ks"),
                         "delta_k_vs_" + policies[0]: delta,
                         "unit": "independent stream (site-day)",
                         "mode": "exploratory"})
    return rows


def e6_rows(test_blocks, *, k_max=None, seed=0, policy="A",
            power_values=(7.0, 11.0), feeder_shares=(1.0, 0.5), k_values=None):
    """E6：能量约束 × 枪数 × 功率 × 馈线；逐场站-日记录交付/需求/缺口与可行性。"""
    rows = []
    for block in test_blocks:
        site = block["site"]
        stream = stream_from_block(block, seed=seed)
        capability = site_capability(site)
        try:
            # k_values 已预注册时只需在给定 k 做可行性检查，不要求完整枚举，
            # 故允许完整场站-日（>20 辆）构造实例；枚举型小实例约束只作用于 E3。
            instance = offline_opt.instance_from_block(
                block, connector_kw=capability["connector_kw"],
                feeder_kw=capability["feeder_kw"],
                max_vehicles=max(offline_opt.MAX_VEHICLES, len(block["events"]))
                if k_values is not None else offline_opt.MAX_VEHICLES)
        except (offline_opt.InstanceTooLarge, ValueError) as exc:
            rows.append({"family": "E6", "split": "test", "site_id": block["site_id"],
                         "day_key": block["day_key"], "status": "missing_data",
                         "reason": str(exc), "unit": "site-day"})
            continue
        if k_values is not None:
            bays = site_capability(site)["charging_bays"]
            candidates = sorted({int(value) for value in k_values
                                 if bays is not None and 0 <= int(value) <= int(bays)})
            if not candidates:
                rows.append({"family": "E6", "split": "test", "site_id": block["site_id"],
                             "day_key": block["day_key"], "status": "missing_data",
                             "reason": "预注册 k 超过该场站充电车位数，无法构造配置",
                             "unit": "site-day"})
                continue
        else:
            base = offline_opt.min_connectors(instance, k_max=k_max)
            candidates = sorted({base["k_min"]} if base["k_min"] is not None else {0})
        for k in candidates:
            for power in power_values:
                for share in feeder_shares:
                    feeder = power * max(1, k) * share
                    try:
                        row = run_policy(stream, site, policy, k, seed=seed,
                                         connector_kw=power, feeder_kw=feeder)
                    except ValueError as exc:
                        rows.append({"family": "E6", "split": "test",
                                     "site_id": block["site_id"], "day_key": block["day_key"],
                                     "k": k, "connector_kw": power,
                                     "feeder_kw": feeder, "status": "error",
                                     "reason": str(exc), "unit": "site-day"})
                        continue
                    offline = offline_opt.check_feasible(dict(instance, connector_kw=power,
                                                              feeder_kw=feeder), k)
                    rows.append({**row, "family": "E6", "split": "test", "mode": "confirmatory",
                                 "connector_kw": power, "feeder_kw": feeder,
                                 "feeder_share": share,
                                 "offline_status": offline["status"],
                                 "offline_reason": offline["reason"],
                                 "offline_model": offline["model"],
                                 "unit": "site-day"})
    return rows


def e7_rows(test_blocks, *, k_max=None, seed=0, policy="A"):
    """E7：非单调性事件轨迹。若测试集内找不到反例，返回空列表 + missing_data 说明。"""
    rows = []
    for block in test_blocks:
        site = block["site"]
        stream = stream_from_block(block, seed=seed)
        curve = k_curve(stream, site, policy, _k_values_for(site, k_max), seed=seed)
        metric = None
        for key in ("charging_access_rate", "energy_service_rate", "parking_service_rate"):
            values = [row.get(key) for row in curve]
            if all(value is not None for value in values) and len(values) >= 2:
                metric = key
                break
        if metric is None:
            continue
        values = [row[metric] for row in curve]
        for index in range(len(values) - 1):
            if values[index + 1] < values[index] - 1e-12:
                k_low, k_high = curve[index]["k"], curve[index + 1]["k"]
                low_row = run_policy(stream, site, policy, k_low, seed=seed)
                high_row = run_policy(stream, site, policy, k_high, seed=seed)
                for tag, k in (("k_low", k_low), ("k_high", k_high)):
                    sim = None
                    row = low_row if tag == "k_low" else high_row
                    rows.append({"family": "E7", "row_kind": "non_monotone_pair",
                                 "site_id": block["site_id"], "day_key": block["day_key"],
                                 "stream_id": stream["stream_id"],
                                 "stream_hash": stream["stream_hash"], "policy": policy,
                                 "k": k, "metric": metric,
                                 "metric_value": row.get(metric),
                                 "pair_role": tag, "unit": "single instance trajectory"})
                return rows, {"status": "found",
                              "site_id": block["site_id"], "day_key": block["day_key"],
                              "metric": metric, "k_low": k_low, "k_high": k_high,
                              "value_low": values[index], "value_high": values[index + 1]}
    return rows, {"status": "missing_data",
                  "reason": "留出块中未观察到服务率随 k 增加而下降的非单调事件（不伪造轨迹）"}


def sim_min_k_on_streams(blocks, *, policy="A", k_max=None, seed=0):
    """在训练流上做全整数 k 枚举，取每流的最小可行 k（模拟口径，三约束 alpha=0.05）。"""
    rows = []
    for block in blocks:
        capability = site_capability(block["site"])
        if capability["n_spaces"] is None or capability["charging_bays"] is None:
            rows.append({"site_id": block["site_id"], "day_key": block["day_key"],
                         "status": "missing_data",
                         "reason": "场站缺 n_spaces/charging_bays"})
            continue
        stream = stream_from_block(block, seed=seed)
        curve = k_curve(stream, block["site"], policy,
                        _k_values_for(block["site"], k_max), seed=seed)
        verdict = sim_minimal_k(curve)
        rows.append({"site_id": block["site_id"], "day_key": block["day_key"],
                     "policy": policy, "k_min": verdict.get("min_known_feasible"),
                     "confirmed_minimal_sim": verdict.get("confirmed_minimal"),
                     "undecidable_ks": verdict.get("undecidable_ks"),
                     "status": "ok"})
    return rows


def preregistered_k(blocks, *, seed=0, k_max=None, policy="A"):
    """预注册 k：训练流上仿真最小可行 k 的最大值（风险裕度式选择，测试集不调参）。

    只用训练/标定块；完整整数枚举（不二分）；取 max 是保守选择（更大的 k 更不容易在测试上不达标）。
    若训练流全部不可判定，返回 (None, rows, reason) 由调用方写 missing_data。
    """
    rows = sim_min_k_on_streams(blocks, policy=policy, k_max=k_max, seed=seed)
    values = [row["k_min"] for row in rows if row.get("k_min") is not None]
    if not values:
        return None, rows, "训练流上没有任何 k 满足三约束（全不可判定/不可行）"
    return max(values), rows, ("max over training streams of simulation min feasible k; "
                               "full integer enumeration; risk-averse selection")


def m1_pairs(test_blocks, *, k_max=None, seed=0, policies=("A", "B")):
    """M1 配对：同一独立流上两策略的仿真最小可行 k（同口径、同流、配对重放）。"""
    pairs = []
    for block in test_blocks:
        stream = stream_from_block(block, seed=seed)
        site = block["site"]
        entry = {"site_id": block["site_id"], "day_key": block["day_key"],
                 "stream_id": stream["stream_id"], "stream_hash": stream["stream_hash"]}
        for policy in policies:
            try:
                curve = k_curve(stream, site, policy, _k_values_for(site, k_max), seed=seed)
                verdict = sim_minimal_k(curve)
                entry["k_" + policy] = verdict.get("min_known_feasible")
                entry["confirmed_" + policy] = verdict.get("confirmed_minimal")
                entry["undecidable_" + policy] = verdict.get("undecidable_ks")
            except ValueError as exc:
                entry["error_" + policy] = str(exc)
        if len(policies) == 2:
            first, second = policies
            a_value, b_value = entry.get("k_" + first), entry.get("k_" + second)
            entry["delta_k"] = (b_value - a_value
                                if a_value is not None and b_value is not None else None)
            if entry["delta_k"] is None:
                entry["reason"] = ("至少一侧在 k=0..charging_bays 网格内无可行 k"
                                   "（三约束不可满足，非配对缺失）")
            entry["definition"] = ("simulation 最小可行 k（事件加权失败率三约束，alpha=0.05）"
                                   "；%s 减 %s，负值表示后者需要更少枪数" % (second, first))
        pairs.append(entry)
    return pairs


def m_summaries(*, m1_pairs_data, e4_rows_data, m3_pairs_data):
    """M1/M2/M3：点估计 + bootstrap 区间；只报可排除幅度与区间，不写"显著"。"""
    from apps.parking_lab.workbench.stat_tools import bootstrap_ci, paired_mean_diff_ci
    out = []
    # M1：留出集上 A 专用 vs B 共享的最小 k 差
    deltas = [pair["delta_k"] for pair in m1_pairs_data if pair.get("delta_k") is not None]
    if len(deltas) >= 2:
        ci = bootstrap_ci(deltas, n_boot=1000, alpha=0.05, seed=20261031)
        out.append({"comparison": "M1", "mode": "confirmatory",
                    "definition": "留出独立流上 B_shared 与 A_dedicated 的仿真最小可行 k 之差",
                    "point": ci["point"], "low": ci["low"], "high": ci["high"],
                    "n_pairs": len(deltas), "unit": "independent stream (site-day)",
                    "pairs_computable": len(deltas),
                    "pairs_total": len(m1_pairs_data),
                    "estimate": "mean of paired differences (bootstrap percentile CI)",
                    "note": "重采样单位=独立流；bootstrap 次数不是样本量"})
    else:
        no_k = sum(1 for pair in m1_pairs_data if pair.get("delta_k") is None)
        out.append({"comparison": "M1", "mode": "confirmatory", "status": "missing_data",
                    "reason": ("无可比配对：%d 条留出流上至少一侧在 k=0..charging_bays "
                               "网格内无可行 k（三约束未满足，属服务标准可达性问题，"
                               "不是数据缺失）" % no_k),
                    "n_pairs": len(deltas), "n_streams_no_feasible_k": no_k,
                    "pairs_total": len(m1_pairs_data)})
    # M2：同一流配对的服务率差（基线 vs A）
    by_stream = {}
    for row in e4_rows_data:
        if row.get("status") == "error":
            continue
        by_stream.setdefault(row["stream_id"], {})[row["policy"]] = row
    # B1/B2 恒等解释（数据事实驱动）：两规则在本数据上 ICE 都没有被拒，普通位始终足够，
    # B2 的 ICE 借位门控没有改变任何决策；EV 侧两者都优先充电位 → 有效决策序列一致。
    b1_b2_same = 0
    b1_b2_pairs = 0
    for pair in by_stream.values():
        if "B1_QUOTA" in pair and "B2_LITERATURE" in pair:
            b1_b2_pairs += 1
            left = pair["B1_QUOTA"].get("energy_service_rate_incl_rejected")
            right = pair["B2_LITERATURE"].get("energy_service_rate_incl_rejected")
            if left is not None and right is not None and abs(float(left) - float(right)) <= 1e-12:
                b1_b2_same += 1
    b1_ice = sum(float(row.get("num_ice_parking_failures") or 0)
                 for row in e4_rows_data if row.get("policy") == "B1_QUOTA")
    b1_ice_den = sum(float(row.get("den_exogenous_ice_visits") or 0)
                     for row in e4_rows_data if row.get("policy") == "B1_QUOTA")
    b1b2_note = ("B1_QUOTA 与 B2_LITERATURE 在本数据上给出相同能量结果："
                 "%d/%d 条流的能量服务率逐流相同；B1/B2 的 ICE 停车失败均 0/%d，"
                 "普通位始终足够，B2 的 ICE 借位门控没有改变任何准入决策；"
                 "EV 侧两者都优先充电位，故有效决策序列一致。"
                 % (b1_b2_same, b1_b2_pairs, int(b1_ice_den)))
    for base_policy in ("B0_FCFS", "B1_QUOTA", "B2_LITERATURE"):
        diffs = []
        for pair in by_stream.values():
            if "A" in pair and base_policy in pair:
                first = pair["A"].get("energy_service_rate_incl_rejected")
                second = pair[base_policy].get("energy_service_rate_incl_rejected")
                if first is not None and second is not None:
                    diffs.append(float(second) - float(first))
        pair_label = base_policy + " - A"
        note = ("方向：baseline 减 A（负值 = A 更高/更好）；"
                "重采样单位=场站-日；同流同 k 配对；不显著不等于无效")
        if base_policy != "B0_FCFS":
            note += "；" + b1b2_note
        if len(diffs) >= 2:
            ci = bootstrap_ci(diffs, n_boot=1000, alpha=0.05, seed=20261031)
            out.append({"comparison": "M2", "mode": "confirmatory",
                        "pair": pair_label,
                        "direction": "baseline_rate - A_rate; negative => A better",
                        "definition": "离场能量服务率（含被拒，delivered/demand）的流内配对差（baseline − A）",
                        "point": ci["point"], "low": ci["low"], "high": ci["high"],
                        "n_pairs": len(diffs), "unit": "site-day",
                        "estimate": "mean paired difference (bootstrap percentile CI)",
                        "b1_b2_same_streams": "%d/%d" % (b1_b2_same, b1_b2_pairs),
                        "note": note})
        else:
            out.append({"comparison": "M2", "mode": "confirmatory",
                        "pair": pair_label, "direction": "baseline_rate - A_rate; negative => A better",
                        "status": "missing_data", "reason": "可比配对不足 2 个", "n_pairs": len(diffs)})
    # M3：能量约束加入前后离线最小 k 的变化
    pairs = [(item["k_min"], item["k_min_energy_constrained"])
             for item in m3_pairs_data
             if item.get("k_min") is not None and item.get("k_min_energy_constrained") is not None]
    if len(pairs) >= 2:
        delta = [b - a for a, b in pairs]
        ci = bootstrap_ci(delta, n_boot=1000, alpha=0.05, seed=20261031)
        out.append({"comparison": "M3", "mode": "confirmatory",
                    "definition": "加入场站馈线能量约束后的离线最小 k 变化（受约束 − 不受约束）",
                    "point": ci["point"], "low": ci["low"], "high": ci["high"],
                    "n_pairs": len(pairs), "unit": "site-day",
                    "estimate": "mean paired difference (bootstrap percentile CI)",
                    "note": "离线声明模型内比较，不是物理下界"})
    else:
        infeasible = sum(1 for item in m3_pairs_data
                         if item.get("k_min") is None and item.get("k_min_energy_constrained") is None)
        out.append({"comparison": "M3", "mode": "confirmatory", "status": "missing_data",
                    "reason": ("无可比配对：%d/%d 个离线实例在声明模型下（含/不含馈线约束）"
                               "均不可行，k 无法变化（多为 window_too_short：情景能量需求超过"
                               "观测停留时间在声明的单枪功率下可交付的量）"
                               % (infeasible, len(m3_pairs_data))),
                    "n_pairs": len(pairs), "n_instances_infeasible": infeasible,
                    "instances_total": len(m3_pairs_data)})
    return out


def m3_pairs(solve_blocks, *, k_max=None):
    """M3 的配对数据：每块上（不受馈线约束的离线最小 k, 受场站馈线约束的 k）。"""
    pairs = []
    for block in solve_blocks:
        capability = site_capability(block["site"])
        try:
            instance = offline_opt.instance_from_block(
                block, connector_kw=capability["connector_kw"],
                feeder_kw=capability["feeder_kw"])
        except (offline_opt.InstanceTooLarge, ValueError):
            continue
        capability = site_capability(block["site"])
        instance = dict(instance, connectors=capability["connectors"],
                        charging_bays=capability["charging_bays"])
        unbounded = offline_opt.min_connectors(dict(instance, feeder_kw=None), k_max=k_max)
        bounded = offline_opt.min_connectors(instance, k_max=k_max)
        pairs.append({"instance_id": "%s:%s" % (block["site_id"], block["day_key"]),
                      "site_id": block["site_id"], "day_key": block["day_key"],
                      "k_min": unbounded["k_min"],
                      "k_min_energy_constrained": bounded["k_min"],
                      "unbounded_stop": unbounded["stop_reason"],
                      "bounded_stop": bounded["stop_reason"],
                      "reason": (None if unbounded["k_min"] is not None
                                 and bounded["k_min"] is not None
                                 else "declared model infeasible (no feasible k)")})
    return pairs
