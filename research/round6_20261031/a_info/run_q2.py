# -*- coding: utf-8 -*-
"""第六轮 A / Q2：信息条件 I0 vs I1 的固定 k 小实验（算法比较，不是全局最优）。

轨迹：TPE0008/TPE0401（可 --lots 扩展），seeds 1–2，规则 A/B，k=0..40 完整枚举，
p_EV=0.10、q_need=0.36、7 kW、feeder 336 kW、1440 min、start 11.5。
每个 (lot, seed, rule) 只生成一次外生车流，同一车流重放 I0 与 I1；
I0 走未修改的 Simulation；I1 走 info_regimes.RegimeSimulation（analysis_only）。
所有率按 service_semantics 五态判定；censored/missing/illegal 不判成功。

命令示例（默认解释器）：
  C:/anaconda/python.exe research/round6_20261031/a_info/run_q2.py --workers 8 \
      --out research/round6_20261031/a_info/q2_info_regimes.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research", "integer_allocation_20261031"))

import run_cost_curve as RC  # noqa: E402
from apps.parking_lab.workbench import info_regimes as R  # noqa: E402
from apps.parking_lab.workbench import service_semantics as S  # noqa: E402
from apps.parking_lab.workbench import traffic_gen  # noqa: E402
from apps.parking_lab.workbench.service_metrics import summarise as summarise_service  # noqa: E402
from apps.parking_lab.workbench.simulation import Simulation  # noqa: E402

PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
DEFAULT_LOTS = "TPE0008,TPE0401"
DEFAULT_SEEDS = "1,2"
DEFAULT_RULES = "A,B"
RULES = {"A": "dedicated_by_type", "B": "full_open_ice_first"}
K_MAX = 40
ALPHA = 0.05
P_EV = 0.10
Q_NEED = 0.36
CHARGER_KW = 7.0
FEEDER_KW = 336.0
DURATION_HOURS = 24.0
START_HOUR = 11.5
HORIZON_MIN = DURATION_HOURS * 60.0
COMMAND = ("C:/anaconda/python.exe research/round6_20261031/a_info/run_q2.py "
           "--workers %s --out research/round6_20261031/a_info/q2_info_regimes.json")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def demand_hash(arrivals):
    payload = [[a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min,
                a.energy_kwh] for a in arrivals]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def config_for(n_spaces, k, rule, seed):
    return {
        "n_spaces": int(n_spaces), "charging_bays": int(k), "chargers": int(k),
        "charger_kw": CHARGER_KW, "feeder_kw": FEEDER_KW,
        "duration_hours": DURATION_HOURS, "start_hour": START_HOUR,
        "interval_level": 0.9, "arrival_rate_hour": 0.0, "ev_share": 0.0,
        "charge_probability": 0.0, "policy": rule, "seed": int(seed),
        "reserve_fixed": 0,
    }


def measure(sim, meta_n0, row_meta):
    extra = RC._visit_metrics(sim, meta_n0)
    service = summarise_service(sim.visits, horizon_min=sim.horizon,
                                initial_ids=range(meta_n0))
    charge_requests = int(extra.get("charge_requests") or 0)
    capacity = int(extra.get("unmet_no_connector_events") or 0)
    rate = (capacity / charge_requests) if charge_requests else None
    row = dict(row_meta)
    row.update({
        "charge_requests": charge_requests,
        "capacity_only_unmet_requests": capacity,
        "capacity_only_unmet_rate": rate,
        "service_metrics": service,
        "arrivals": int(extra["arrivals"]),
        "ev_arrivals": int(extra["ev_arrivals"]),
        "ev_rejected": int(extra["ev_rejected"]),
        "ice_rejected": int(extra["ice_rejected"]),
        "charge_requests_rejected": int(extra["charge_requests_rejected"]),
        "pending_charge_at_window_end": int(extra["charge_pending_at_window_end"]),
        "admitted_total": int(extra["arrivals"] - extra["rejected_total"]),
        "demand_hash": sim.demand_hash,
        "traffic_hash": sim.traffic_hash,
    })
    verdict = S.judge(row, constraints=S.CONSTRAINTS_3, alpha=ALPHA, na_policy="skip")
    row["constraints"] = {name: S.constraint_status(name, row)
                          for name in S.CONSTRAINTS_3}
    row["judgement"] = verdict
    row["feasibility"] = S.feasible(row)
    return row


def run_task(task):
    lot_id, seed, rule_label, k_values, n_spaces = task
    started = time.perf_counter()
    try:
        with open(PARAMS, encoding="utf-8") as handle:
            params = json.load(handle)
        arrivals, meta = traffic_gen.generate_for_lot(
            params, lot_id, seed, horizon_min=HORIZON_MIN, p_ev=P_EV, q_need=Q_NEED,
            scenario_model="independent", strict=True, charge_provenance=None,
            dwell_scale=1.0)
        arrivals = tuple(arrivals)
        n0 = int(meta.get("initial_occupancy_n") or 0)
        rule = RULES[rule_label]
        rows, failures = [], []
        for k in k_values:
            config = config_for(n_spaces, k, rule, seed)
            base_meta = {"lot_id": lot_id, "seed": int(seed), "k": int(k),
                         "rule": rule, "rule_label": rule_label,
                         "information_regime": R.I0, "analysis_only": False,
                         "policy_kind": "real_rule", "n_spaces": int(n_spaces),
                         "initial_occupancy_n": n0,
                         "demand_hash": demand_hash(arrivals)}
            try:
                sim = Simulation(config, arrivals=arrivals)
                sim.run()
                rows.append(measure(sim, n0, base_meta))
            except Exception as error:  # noqa: BLE001
                failures.append({**{k2: base_meta[k2] for k2 in
                                    ("lot_id", "seed", "k", "rule", "information_regime")},
                                 "error": "%s: %s" % (type(error).__name__, error),
                                 "traceback": traceback.format_exc()[-1500:]})
            analysis_meta = dict(base_meta)
            analysis_meta.update({"information_regime": R.I1, "analysis_only": True,
                                  "policy_kind": "analysis_heuristic"})
            try:
                sim = R.RegimeSimulation(config, arrivals=arrivals,
                                         policy=R.AnalysisHeuristicPolicy(rule))
                sim.run()
                rows.append(measure(sim, n0, analysis_meta))
            except Exception as error:  # noqa: BLE001
                failures.append({**{k2: analysis_meta[k2] for k2 in
                                    ("lot_id", "seed", "k", "rule", "information_regime")},
                                 "error": "%s: %s" % (type(error).__name__, error),
                                 "traceback": traceback.format_exc()[-1500:]})
        return {"lot_id": lot_id, "seed": int(seed), "rule": rule_label,
                "n_spaces": int(n_spaces), "k_grid": [min(k_values), max(k_values)],
                "ok": True, "rows": rows, "failures": failures,
                "demand_hash": demand_hash(arrivals),
                "traffic_hash": rows[0]["traffic_hash"] if rows else None,
                "elapsed_s": round(time.perf_counter() - started, 3),
                "meta": {key: meta.get(key) for key in
                         ("p_ev", "q_need", "initial_occupancy_n", "scenario_model")}}
    except Exception as error:  # noqa: BLE001 - 任务失败必须留痕
        return {"lot_id": lot_id, "seed": int(seed), "rule": rule_label, "ok": False,
                "error": "%s: %s" % (type(error).__name__, error),
                "traceback": traceback.format_exc()[-2000:],
                "elapsed_s": round(time.perf_counter() - started, 3)}


def feasible_sets(rows):
    grouped = {}
    for row in rows:
        key = (row["lot_id"], row["seed"], row["rule_label"],
               row["information_regime"])
        grouped.setdefault(key, {})[row["k"]] = row
    out = []
    for key in sorted(grouped):
        by_k = grouped[key]
        shape = S.minimal_feasible(by_k, constraints=S.CONSTRAINTS_3, alpha=ALPHA,
                                   k_max=max(by_k))
        out.append({"lot_id": key[0], "seed": key[1], "rule": key[2],
                    "information_regime": key[3], **shape,
                    "n_feasible": len(shape["feasible"]),
                    "n_infeasible": len(shape["infeasible_ks"]),
                    "n_undecidable": len(shape["undecidable_ks"])})
    return out


def delta_k_info(feasible):
    """Δk_info = 最小已知可行 k(I1) − 最小已知可行 k(I0)，按 (lot,seed,rule) 配对。"""
    lookup = {(item["lot_id"], item["seed"], item["rule"], item["information_regime"]):
              item["min_known_feasible"] for item in feasible}
    units = sorted({(item["lot_id"], item["seed"], item["rule"]) for item in feasible})
    pairs = []
    for key in units:
        k0 = lookup.get((key[0], key[1], key[2], R.I0))
        k1 = lookup.get((key[0], key[1], key[2], R.I1))
        pairs.append({"lot_id": key[0], "seed": key[1], "rule": key[2],
                      "k_I0": k0, "k_I1": k1,
                      "delta_k_info": (k1 - k0) if (k0 is not None and k1 is not None) else None})
    return pairs


def four_categories(rows):
    by_k = {}
    for row in rows:
        key = (row["lot_id"], row["seed"], row["rule_label"], row["k"])
        by_k.setdefault(key, {})[row["information_regime"]] = row
    counts = {"both": 0, "only_I0": 0, "only_I1": 0, "neither": 0, "undecidable": 0}
    cells = []
    for key in sorted(by_k):
        f0 = by_k[key][R.I0]["feasibility"]
        f1 = by_k[key][R.I1]["feasibility"]
        if f0 is True and f1 is True:
            label = "both"
        elif f0 is True and f1 is False:
            label = "only_I0"
        elif f0 is False and f1 is True:
            label = "only_I1"
        elif f0 is False and f1 is False:
            label = "neither"
        else:
            label = "undecidable"
        counts[label] += 1
        cells.append({"lot_id": key[0], "seed": key[1], "rule": key[2], "k": key[3],
                      "feasible_I0": f0, "feasible_I1": f1, "category": label})
    return {"counts": counts, "cells": cells}


def category_at(k_ref, rows):
    by_k = {}
    for row in rows:
        by_k.setdefault((row["lot_id"], row["seed"], row["rule_label"], row["k"]),
                        {})[row["information_regime"]] = row
    out = []
    for (lot, seed, rule, k), cell in sorted(by_k.items()):
        if k != k_ref.get((lot, seed, rule)):
            continue
        f0, f1 = cell[R.I0]["feasibility"], cell[R.I1]["feasibility"]
        label = ("both" if f0 is True and f1 is True else
                 "only_I0" if f0 is True and f1 is False else
                 "only_I1" if f0 is False and f1 is True else
                 "neither" if f0 is False and f1 is False else "undecidable")
        out.append({"lot_id": lot, "seed": seed, "rule": rule, "k_ref": k,
                    "feasible_I0": f0, "feasible_I1": f1, "category": label})
    return out


def fixed_k_comparison(rows, feasible):
    by_unit = {}
    for row in rows:
        key = (row["lot_id"], row["seed"], row["rule_label"])
        by_unit.setdefault(key, {}).setdefault(row["k"], {})[row["information_regime"]] = row
    lookup = {(item["lot_id"], item["seed"], item["rule"], item["information_regime"]):
              item["min_known_feasible"] for item in feasible}
    out = []
    for key in sorted(by_unit):
        by_k = by_unit[key]
        k0 = lookup.get((key[0], key[1], key[2], R.I0))
        k1 = lookup.get((key[0], key[1], key[2], R.I1))
        k_ref = k0 if k0 is not None else k1
        if k_ref is None or k_ref not in by_k:
            out.append({"lot_id": key[0], "seed": key[1], "rule": key[2], "k_ref": None})
            continue
        cell = by_k[k_ref]
        record = {"lot_id": key[0], "seed": key[1], "rule": key[2], "k_ref": int(k_ref)}
        for regime in (R.I0, R.I1):
            row = cell.get(regime)
            if row is None:
                record[regime] = None
                continue
            record[regime] = {
                "charge_requests": row["charge_requests"],
                "capacity_only_unmet_requests": row["capacity_only_unmet_requests"],
                "capacity_only_unmet_rate": row["capacity_only_unmet_rate"],
                "ev_parking_failure_rate": row["service_metrics"]["rates"]["ev_parking_failure_rate"],
                "ice_parking_failure_rate": row["service_metrics"]["rates"]["ice_parking_failure_rate"],
                "departed_shortfall_energy_rate": row["service_metrics"]["rates"]["departed_shortfall_energy_rate"],
                "censored_sessions": row["service_metrics"]["levels"]["censored_sessions"],
                "feasibility": row["feasibility"],
                "constraints": {name: row["constraints"][name]["status"]
                                for name in S.CONSTRAINTS_3},
            }
        out.append(record)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="Q2 信息条件 I0/I1 小实验")
    parser.add_argument("--lots", default=DEFAULT_LOTS)
    parser.add_argument("--seeds", default=DEFAULT_SEEDS)
    parser.add_argument("--rules", default=DEFAULT_RULES)
    parser.add_argument("--k-max", type=int, default=K_MAX)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      "q2_info_regimes.json"))
    parser.add_argument("--quick", action="store_true", help="冒烟：只跑 k=0..2 并少打印")
    args = parser.parse_args(argv)

    with open(PARAMS, encoding="utf-8") as handle:
        params = json.load(handle)
    lots = [lot.strip() for lot in args.lots.split(",") if lot.strip()]
    seeds = [int(seed) for seed in args.seeds.split(",") if seed.strip()]
    rules = [rule.strip() for rule in args.rules.split(",") if rule.strip()]
    for rule in rules:
        if rule not in RULES:
            parser.error("未知规则标签：%s（可选 %s）" % (rule, sorted(RULES)))
    tasks = []
    grids = {}
    for lot_id in lots:
        info = RC.lot_meta(params, lot_id)
        n_spaces = int(info["n_spaces"])
        k_max = max(0, min(int(args.k_max), n_spaces))
        k_values = list(range(0, k_max + 1))
        grids[lot_id] = {"n_spaces": n_spaces, "k_values": k_values}
        for seed in seeds:
            for rule in rules:
                tasks.append((lot_id, seed, rule, k_values, n_spaces))

    started = time.perf_counter()
    results = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(run_task, task): task for task in tasks}
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(json.dumps({"done": [result.get("lot_id"), result.get("seed"),
                                           result.get("rule")], "ok": result.get("ok"),
                                  "rows": len(result.get("rows") or []),
                                  "elapsed_s": result.get("elapsed_s")}), flush=True)
    else:
        for task in tasks:
            result = run_task(task)
            results.append(result)
            print(json.dumps({"done": [result.get("lot_id"), result.get("seed"),
                                       result.get("rule")], "ok": result.get("ok"),
                              "rows": len(result.get("rows") or [])}), flush=True)

    rows, failures = [], []
    for result in results:
        if result.get("ok"):
            rows.extend(result["rows"])
            failures.extend(result.get("failures") or [])
        else:
            failures.append({key: result.get(key) for key in
                             ("lot_id", "seed", "rule", "error", "traceback")})
    rows.sort(key=lambda row: (row["lot_id"], row["seed"], row["rule_label"],
                               row["k"], row["information_regime"]))
    feasible = feasible_sets(rows)
    delta = delta_k_info(feasible)
    categories = four_categories(rows)
    fixed = fixed_k_comparison(rows, feasible)

    k0_rows = [row for row in rows if row["k"] == 0]
    def _range(key):
        values = [(row["service_metrics"]["rates"][key] or 0.0) for row in k0_rows]
        return [min(values), max(values)] if values else None

    hand = {
        "prediction": "k=0 无带枪位：有充电请求时 capacity_only_unmet_rate=1.0>α，"
                      "I0/I1 均应不可行；EV/ICE 停车失败率由总车位 N 是否够用决定，"
                      "不能由 k=0 的充电条件直接推零。",
        "k0_rows": len(k0_rows),
        "k0_capacity_rate_all_one": all(abs((row["capacity_only_unmet_rate"] or 0.0) - 1.0) < 1e-12
                                        for row in k0_rows),
        "k0_infeasible_both": all(row["feasibility"] is False for row in k0_rows),
        "k0_ev_failure_rate_range": _range("ev_parking_failure_rate"),
        "k0_ice_failure_rate_range": _range("ice_parking_failure_rate"),
    }
    delta_values = [item["delta_k_info"] for item in delta if item["delta_k_info"] is not None]
    delta_summary = {
        "n_units": len(delta),
        "n_pairs": len(delta_values),
        "n_undecidable_or_empty": len(delta) - len(delta_values),
        "positive": sum(1 for v in delta_values if v > 0),
        "zero": sum(1 for v in delta_values if v == 0),
        "negative": sum(1 for v in delta_values if v < 0),
        "min": min(delta_values) if delta_values else None,
        "max": max(delta_values) if delta_values else None,
        "median": statistics.median(delta_values) if delta_values else None,
    }
    elapsed = time.perf_counter() - started
    document = {
        "schema": "round6/a_info/q2_info_regimes/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Q2 信息条件 I0/I1 算法比较（有限策略；非全局最优）",
        "command": COMMAND % args.workers,
        "argv": list(sys.argv),
        "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
        "exit_code": 0 if not failures else 1,
        "workers": args.workers,
        "elapsed_s": round(elapsed, 2),
        "scope": {
            "lots": lots, "seeds": seeds, "rules": {rule: RULES[rule] for rule in rules},
            "k_grid": {lot: grids[lot]["k_values"] for lot in lots},
            "k_max": int(args.k_max),
            "alpha": ALPHA, "p_ev": P_EV, "q_need": Q_NEED,
            "charger_kw": CHARGER_KW, "feeder_kw": FEEDER_KW,
            "horizon_min": HORIZON_MIN, "start_hour": START_HOUR,
            "simulations": len(rows),
            "note": "每个 (lot,seed,rule) 同一外生车流重放 I0/I1；只改决策可用信息与分配。",
        },
        "information_regime": {
            R.I0: R.metadata(R.I0),
            R.I1: R.metadata(R.I1, R.AnalysisHeuristicPolicy("dedicated_by_type")),
        },
        "analysis_only": {R.I0: False, R.I1: True},
        "policy_kind": {R.I0: "real_rule", R.I1: "analysis_heuristic"},
        "can_mimic_I0": {R.I0: True,
                         R.I1: "supported_by_MimicI0Policy (validated in test_round6_info)"},
        "authorization": {
            "grant": "info_regimes.ANALYSIS_GRANT",
            "analysis_only_fields": list(R.ANALYSIS_ONLY_FIELDS),
            "forbidden_fields": list(R.FORBIDDEN_FIELDS),
            "real_rule_context_has_needs_charge": False,
            "i1_context_extra_fields": list(R.ANALYSIS_ONLY_FIELDS),
            "unauthorized_access": "PermissionError",
        },
        "hand_check": hand,
        "feasible_sets": feasible,
        "delta_k_info": {"units": delta, "summary": delta_summary},
        "four_categories": categories,
        "four_categories_at_fixed_k": category_at(
            {(item["lot_id"], item["seed"], item["rule"]): item["k_ref"]
             for item in fixed}, rows),
        "fixed_k_comparison": fixed,
        "input_sha256": {
            "research/traffic_generation_20261031/fitted_parameters.json": sha256_file(PARAMS),
        },
        "source_sha256": {
            path: sha256_file(os.path.join(ROOT, path)) for path in (
                "apps/parking_lab/workbench/service_semantics.py",
                "apps/parking_lab/workbench/info_regimes.py",
                "apps/parking_lab/workbench/simulation.py",
                "apps/parking_lab/workbench/rules.py",
                "apps/parking_lab/workbench/traffic_gen.py",
                "research/round6_20261031/a_info/run_q2.py")
        },
        "demand_hash_by_lot_seed": {("%s|%s" % (result.get("lot_id"), result.get("seed"))):
                                    result.get("demand_hash")
                                    for result in results if result.get("ok")},
        "task_elapsed_s": {("%s|%s|%s" % (result.get("lot_id"), result.get("seed"),
                                          result.get("rule"))): result.get("elapsed_s")
                           for result in results},
        "rows": rows,
        "failures": failures,
        "limits": [
            "I1 只实现一种 needs_charge 启发式，属算法比较/信息上界示例，不是全局最优。",
            "I1 改变分配次序后，后续准入可能因占用结构变化而改变；所有到访仍显式记录决策。",
            "可行集合只在 k=0..%d 网格内；k_max 处可行标 truncated_at_kmax。" % args.k_max,
            "零需求 N/A 记录并跳过；censored/missing/illegal 不判成功。",
        ],
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"out": args.out, "rows": len(rows), "failures": len(failures),
                      "feasible_sets": len(feasible), "delta": delta_summary,
                      "categories": categories["counts"], "hand": hand,
                      "elapsed_s": round(elapsed, 2)}, ensure_ascii=False), flush=True)
    return document["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
