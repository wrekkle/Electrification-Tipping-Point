#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定 k 的三条正式准入规则同车流对比（阶段四规则部分）。

生成命令（本文件同时是生成物来源，输出 JSON 首屏带同一命令）：
    python research/sim_rules_20261031/run_rule_comparison.py

数据：workbench.demand.generate 的合成车流（synthetic，未对任何真实停车场校准）。
同 seed 只生成一次车流，三条规则与不同 k 复用同一 arrivals，并核对 traffic_hash / demand_hash。
成本：默认成本参数全为 null（缺参不填 0、不套演示值）⇒ 成本分项为 null 并列出 missing_parameters；
另跑一组 config.ILLUSTRATIVE_COST 的合成算术演示，显式标注 illustrative_not_calibrated，
只用于展示"可计算分项长什么样"，不是现实成本、也不是最优性证据。
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.parking_lab.workbench import VERSION                      # noqa: E402
from apps.parking_lab.workbench.config import ILLUSTRATIVE_COST, RULE_POLICIES, Config  # noqa: E402
from apps.parking_lab.workbench.costs import (COST_MODEL_VERSION, MISSING, OCCUPANCY_REASONS,  # noqa: E402
                                               cost_report, traffic_hash)
from apps.parking_lab.workbench.demand import generate              # noqa: E402
from apps.parking_lab.workbench.metrics import calculate            # noqa: E402
from apps.parking_lab.workbench.rules import TYPE_OCCUPANCY_METRICS  # noqa: E402
from apps.parking_lab.workbench.simulation import Simulation        # noqa: E402

COMMAND = "python research/sim_rules_20261031/run_rule_comparison.py"
SEEDS = [11, 12, 13]
OUTPUT = ROOT / "research" / "sim_rules_20261031" / "outputs" / "rule_comparison.json"

# 固定 k：充电车位 charging_bays 与带枪位 chargers 固定，三规则只改准入规则。
FIXED_K = {"n_spaces": 60, "charging_bays": 18, "chargers": 12}
BASE = {
    "scenario": "peaks", "duration_hours": 12.0, "start_hour": 7.0,
    "arrival_rate_hour": 35.0, "ev_share": 0.4, "charge_probability": 0.65,
    "charger_kw": 7.0, "feeder_kw": 60.0, **FIXED_K,
    "cost": {"provenance": "unknown_not_calibrated", "currency": "TWD", "price_year": None},
}
ILLUSTRATIVE_BASE = {**BASE, "cost": {"provenance": "illustrative_not_calibrated",
                                      "currency": "TWD", "price_year": None, **ILLUSTRATIVE_COST}}


def rounded(value, places=6):
    return None if value is None else round(float(value), places)


def cost_block(report):
    """成本分项：null 原样保留（缺参不是 0），并列出 missing_parameters 与 complete。"""
    return {
        "cost_model_version": report["cost_model_version"],
        "unit": report["unit"], "currency": report["currency"],
        "price_year": report["price_year"], "accounting_period": report["accounting_period"],
        "items": {key: rounded(value) for key, value in report["items"].items()},
        "total": rounded(report["total"]), "complete": report["complete"],
        "missing_parameters": list(report[MISSING]),
        "relocation_cost": rounded(report["relocation_cost"]),
    }


def run_one(config, arrivals):
    sim = Simulation(config, arrivals)
    sim.run()
    metrics = calculate(sim)
    report = cost_report(sim)
    ledger = sim.type_occupancy()
    admission_reasons, rejected_reasons = {}, {}
    for visit in sim.visits:
        bucket = admission_reasons if visit["admitted"] else rejected_reasons
        reason = (visit["admission"] or {}).get("reason") or "unknown"
        bucket[reason] = bucket.get(reason, 0) + 1
    missing_causes = {}
    for line in sim.ledger.lines:
        cause = line.get("disposition") or "unknown"
        missing_causes.setdefault(cause, set()).update(line["missing_parameters"])
    return {
        "policy": config.policy, "policy_name": RULE_POLICIES[config.policy],
        "seed": config.seed,
        "traffic_hash": sim.traffic_hash, "demand_hash": sim.demand_hash,
        "traffic_hash_matches_arrivals": sim.traffic_hash == traffic_hash(arrivals),
        "arrivals": metrics["arrivals"], "admitted": metrics["admitted"], "rejected": metrics["rejected"],
        "ev_arrivals": metrics["ev_arrivals"], "ice_arrivals": metrics["ice_arrivals"],
        "rejected_ev": metrics["rejected_ev"], "rejected_ice": metrics["rejected_ice"],
        "rejection_rate": rounded(metrics["rejection_rate"]),
        "rejected_charge_requests": sum(1 for visit in sim.visits
                                        if visit["needs_charge"] and not visit["admitted"]),
        "charge_requests": metrics["charge_requests"], "charge_completed": metrics["charge_completed"],
        "charge_completion_rate_all": rounded(metrics["charge_completion_rate_all"]),
        "energy_requested_kwh": rounded(metrics["energy_requested_all_kwh"]),
        "energy_delivered_kwh": rounded(metrics["energy_delivered_kwh"]),
        "energy_not_served_kwh": rounded(metrics["window_undelivered_kwh"]),
        "rejected_energy_kwh": rounded(metrics["rejected_energy_kwh"]),
        "departed_shortfall_kwh": rounded(metrics["departed_shortfall_kwh"]),
        "pending_energy_kwh": rounded(metrics["pending_energy_kwh"]),
        "mean_occupancy_rate": rounded(metrics["mean_occupancy_rate"]),
        "peak_occupancy": metrics["peak_occupancy"], "peak_charging": metrics["peak_charging"],
        "type_occupancy_minutes": ledger["metrics"],
        "occupancy_minutes_by_reason": {name: rounded(value) for name, value in
                                        report["attribution"]["occupancy_minutes_by_reason"].items()},
        "resource_minutes": {key: rounded(value) for key, value in
                             (report["attribution"].get("resource_minutes") or {}).items()},
        "admission_reason_counts": admission_reasons,
        "rejection_reason_counts": rejected_reasons,
        "cost": cost_block(report),
        "cost_missing_by_disposition": {cause: sorted(names) for cause, names in missing_causes.items()},
    }


def mean_of(rows, key):
    values = [row[key] for row in rows if row.get(key) is not None]
    return rounded(sum(values) / len(values)) if values else None


def aggregate(runs):
    by_rule = {}
    for policy, label in RULE_POLICIES.items():
        rows = [run for run in runs if run["policy"] == policy]
        aggregate_row = {
            "policy": policy, "policy_name": label, "seeds": len(rows),
            "arrivals": mean_of(rows, "arrivals"), "admitted": mean_of(rows, "admitted"),
            "rejected": mean_of(rows, "rejected"), "rejection_rate": mean_of(rows, "rejection_rate"),
            "rejected_ev": mean_of(rows, "rejected_ev"), "rejected_ice": mean_of(rows, "rejected_ice"),
            "rejected_charge_requests": mean_of(rows, "rejected_charge_requests"),
            "charge_requests": mean_of(rows, "charge_requests"),
            "charge_completed": mean_of(rows, "charge_completed"),
            "charge_completion_rate_all": mean_of(rows, "charge_completion_rate_all"),
            "energy_delivered_kwh": mean_of(rows, "energy_delivered_kwh"),
            "energy_not_served_kwh": mean_of(rows, "energy_not_served_kwh"),
            "departed_shortfall_kwh": mean_of(rows, "departed_shortfall_kwh"),
            "pending_energy_kwh": mean_of(rows, "pending_energy_kwh"),
            "mean_occupancy_rate": mean_of(rows, "mean_occupancy_rate"),
            "cost_complete_runs": sum(1 for row in rows if row["cost"]["complete"]),
            "type_occupancy_minutes": {name: rounded(sum(row["type_occupancy_minutes"][name] for row in rows)
                                                     / len(rows)) for name in TYPE_OCCUPANCY_METRICS},
            "occupancy_minutes_by_reason": {name: rounded(sum(
                row["occupancy_minutes_by_reason"].get(name) or 0.0 for row in rows) / len(rows))
                for name in OCCUPANCY_REASONS},
        }
        base = {run["seed"]: run for run in runs if run["policy"] == "dedicated_by_type"}
        deltas = []
        for row in rows:
            left, right = row["type_occupancy_minutes"], base[row["seed"]]["type_occupancy_minutes"]
            deltas.append({name: rounded(left[name] - right[name]) for name in TYPE_OCCUPANCY_METRICS})
        aggregate_row["paired_delta_vs_pi0_type_minutes"] = {
            name: rounded(sum(delta[name] for delta in deltas) / len(deltas))
            for name in TYPE_OCCUPANCY_METRICS}
        counts = {}
        for row in rows:
            for reason, count in row["admission_reason_counts"].items():
                counts["admitted:" + reason] = counts.get("admitted:" + reason, 0) + count
            for reason, count in row["rejection_reason_counts"].items():
                counts["rejected:" + reason] = counts.get("rejected:" + reason, 0) + count
        aggregate_row["admission_and_rejection_reason_counts"] = counts
        by_rule[policy] = aggregate_row
    return by_rule


def main():
    config = Config.parse({**BASE, "policy": "dedicated_by_type"})
    illustrative = Config.parse({**ILLUSTRATIVE_BASE, "policy": "dedicated_by_type"})
    flows, runs, illustrative_runs = {}, [], []
    for seed in SEEDS:
        seeded = replace(config, seed=seed)
        arrivals = generate(seeded)
        flows[seed] = {"demand_hash": traffic_hash(arrivals), "arrivals": len(arrivals)}
        hashes = set()
        for policy in RULE_POLICIES:
            run = run_one(replace(seeded, policy=policy), arrivals)
            run["k"] = dict(FIXED_K)
            runs.append(run)
            hashes.add(run["traffic_hash"])
            illustrative_runs.append({**run_one(replace(illustrative, seed=seed, policy=policy), arrivals),
                                      "note": "ILLUSTRATIVE 合成成本参数，仅供算术演示，不是现实成本"})
        if len(hashes) != 1:
            raise SystemExit(f"seed {seed} 的 traffic_hash 不一致，拒绝出对比：{sorted(hashes)}")

    by_rule = aggregate(runs)

    # π2 阈值/窗口敏感性：同样是合成同流对比，只改 π2 的两个可配置参数。
    sensitivity = []
    for window_min, margin in ((30.0, 1.0), (10.0, 0.0), (60.0, 0.0), (10.0, 2.0)):
        rows = []
        for seed in SEEDS:
            tuned = replace(config, seed=seed, policy="predictive_shared_ice_first",
                            ice_share_forecast_window_min=window_min,
                            ice_share_free_bay_margin=margin)
            rows.append(run_one(tuned, generate(replace(config, seed=seed))))
        sensitivity.append({
            "window_min": window_min, "safety_margin": margin,
            "rejected": mean_of(rows, "rejected"),
            "rejected_ice": mean_of(rows, "rejected_ice"),
            "admitted_ice_shared_by_forecast": sum(
                row["admission_reason_counts"].get("ice_shared_by_forecast", 0) for row in rows),
            "energy_not_served_kwh": mean_of(rows, "energy_not_served_kwh"),
            "ice_blocking_connector_min": mean_of(
                [{name: row["type_occupancy_minutes"][name] for name in TYPE_OCCUPANCY_METRICS}
                 for row in rows], "ice_blocking_connector_min"),
            "note": "同 seed 同车流；只改 π2 的可配置窗口/余量，用于展示参数影响，不是最优参数搜索",
        })
    payload = {
        "生成命令": COMMAND,
        "meta": {
            "kind": "rule_comparison_fixed_k", "synthetic": True,
            "data_source": "workbench.demand.generate 合成车流；未对任何真实停车场校准",
            "model_version": VERSION, "cost_model_version": COST_MODEL_VERSION,
            "seeds": SEEDS, "fixed_k": dict(FIXED_K),
            "base_config": json.loads(json.dumps({key: value for key, value in BASE.items()})),
            "rules": dict(RULE_POLICIES),
            "legacy_note": "旧 strict（按 needs_charge 隐藏意愿分区）不在本对比中，只作 legacy 历史复现",
            "traffic_hash_rule": "同 seed 三条规则复用同一 arrivals；每 seed 断言 traffic_hash 全等",
        },
        "flows": {str(seed): row for seed, row in flows.items()},
        "by_rule": by_rule,
        "predictive_sensitivity": sensitivity,
        "runs": runs,
        "cost_default_null": {
            "note": "默认成本参数全为 null：分项与 total 为 null、complete=false，不填 0、不套演示值",
            "cost_complete_runs": sum(1 for run in runs if run["cost"]["complete"]),
            "missing_parameters": sorted({name for run in runs for name in run["cost"]["missing_parameters"]}),
            "items_sample": runs[0]["cost"]["items"],
        },
        "computable_indicators": {
            "note": "不依赖缺失成本参数的物理/服务指标（确定可算）；货币成本与缺参见 cost_default_null，"
                    "不得把 null 成本当 0 或编造罚价",
            "by_rule": {policy: {key: by_rule[policy][key] for key in (
                "arrivals", "admitted", "rejected", "rejection_rate", "rejected_ev", "rejected_ice",
                "rejected_charge_requests", "charge_requests", "charge_completed",
                "charge_completion_rate_all", "energy_delivered_kwh", "energy_not_served_kwh",
                "departed_shortfall_kwh", "pending_energy_kwh", "mean_occupancy_rate")}
                | {"type_occupancy_minutes": by_rule[policy]["type_occupancy_minutes"],
                   "occupancy_minutes_by_reason": by_rule[policy]["occupancy_minutes_by_reason"]}
                for policy in RULE_POLICIES},
        },
        "cost_illustrative_synthetic": {
            "note": "config.ILLUSTRATIVE_COST：合成演示值 illustrative_not_calibrated，仅展示算术与缺参口径，"
                    "不是现实成本、不用于结论；仍有运行因离场缺电的后续时间未知而 total=null，"
                    "不得把 null 当 0 参与比较",
            "runs": illustrative_runs,
            "by_rule": {policy: {
                "cost_complete_runs": sum(1 for run in illustrative_runs
                                          if run["policy"] == policy and run["cost"]["complete"]),
                "cost_total_mean_complete_runs": (
                    rounded(sum(run["cost"]["total"] for run in illustrative_runs
                                if run["policy"] == policy and run["cost"]["total"] is not None)
                            / max(1, sum(1 for run in illustrative_runs
                                          if run["policy"] == policy and run["cost"]["total"] is not None)))
                    if any(run["cost"]["total"] is not None for run in illustrative_runs
                           if run["policy"] == policy) else None),
                "missing_parameters": sorted({name for run in illustrative_runs
                                              if run["policy"] == policy
                                              for name in run["cost"]["missing_parameters"]}),
            } for policy in RULE_POLICIES},
        },
        "limitations": [
            "synthetic 车流：参数未对台北/任何真实停车场校准，数值只用于规则行为对比。",
            "q_need 未识别：needs_charge 是生成器真值，只用于结算与计量，不进入控制器。",
            "占桩分钟是逐车结果计量（用隐藏真值），只用于研究与成本归因，不反馈进准入决策。",
            "缺参成本为 null：不得据此比较社会成本优劣，也不得据此定 k*。",
            "三条规则在同一 k 与同一车流下比较，不构成 k 与规则的联合最优性证明。",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("written", OUTPUT)
    for policy, row in by_rule.items():
        print(policy, "rejected", row["rejected"], "unserved_kwh", row["energy_not_served_kwh"],
              "type", row["type_occupancy_minutes"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
