"""第二轮独立验收（Lead）：12 项，不依赖被验收实现的内部结论函数。

用法：python research/round2_20261031/verify_round2.py [--curve outputs/...json]
输出：research/round2_20261031/verify_round2_report.json + 控制台 PASS/FAIL/SKIP。
每项检查独立 try/except；缺依赖记为 SKIP 并写原因，不用“跳过”冒充通过。
"""
from __future__ import annotations
import argparse, json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER_DIR = os.path.join(ROOT, "research", "integer_allocation_20261031")
for entry in (ROOT, RUNNER_DIR):
    if entry not in sys.path:
        sys.path.insert(0, entry)

RESULTS = []


def run(name, fn):
    try:
        payload = fn() or {}
        status = payload.get("status", "PASS" if payload.get("pass") else "FAIL")
        RESULTS.append({"check": name, "status": status, "detail": payload})
    except Exception as error:  # noqa: BLE001
        RESULTS.append({"check": name, "status": "FAIL",
                        "detail": {"error": "%s: %s" % (type(error).__name__, error)}})


def load_json(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return json.load(handle)


def config_dict(**overrides):
    base = {"n_spaces": 6, "charging_bays": 1, "chargers": 1, "charger_kw": 7.0, "feeder_kw": 120.0,
            "duration_hours": 4.0, "start_hour": 11.5, "interval_level": 0.9,
            "arrival_rate_hour": 0.0, "ev_share": 0.0, "charge_probability": 0.0,
            "policy": "dedicated_by_type", "reserve_fixed": 0, "seed": 1}
    base.update(overrides)
    return base


def arrival(vehicle_id, time_min, is_ev, needs, dwell_min, energy_kwh):
    from apps.parking_lab.workbench.demand import Arrival
    return Arrival(vehicle_id, time_min, is_ev, needs, dwell_min, energy_kwh)


def run_sim(arrivals, **overrides):
    from apps.parking_lab.workbench.simulation import Simulation
    sim = Simulation(config_dict(**overrides), arrivals=tuple(arrivals))
    sim.run()
    return sim


# 1 设备成本与窗口换算
def check_device_cost():
    from apps.parking_lab.workbench import costs
    params = {"depreciation_capex": 116792.62, "depreciation_life_years": 10.0,
              "maintenance_per_bay_day": 43.29969863013699, "facility_fixed_cost_per_day": 12.5}
    if not hasattr(costs, "facility_cost"):
        return {"pass": False, "status": "FAIL", "error": "costs.facility_cost 不存在（R2-A 未完成）"}
    daily = costs.facility_cost(2, params, days=1.0)
    half = costs.facility_cost(2, params, days=0.5)
    zero = costs.facility_cost(0, params, days=1.0)
    expect_dev = 2 * (116792.62 / 10.0 / 365.0) + 2 * 43.29969863013699
    missing = costs.facility_cost(1, {"depreciation_capex": 116792.62}, days=1.0)
    detail = {"daily": daily, "half": half, "zero": zero,
              "expect_device_daily": expect_dev,
              "missing_value": (missing or {}).get("value")}
    ok = (abs(zero["items"]["device_capital"]) < 1e-12 and abs(zero["items"]["device_maintenance"]) < 1e-12
          and abs(daily["items"]["device_capital"] + daily["items"]["device_maintenance"] - expect_dev) < 1e-6
          and abs(half["value"] - (daily["value"]) / 2.0) < 1e-9
          and missing.get("value") is None)
    detail["pass"] = ok
    return detail


# 2 真实需求 14kWh / 7kW / 60min 的缺口
def check_demand_gap():
    sim = run_sim([arrival(0, 10.0, True, True, 60.0, 14.0)], n_spaces=2, chargers=1, charger_kw=7.0, feeder_kw=7.0)
    visit = sim.visits[0]
    delivered = float(visit.get("delivered_kwh") or 0.0)
    gap = float(visit["energy_kwh"]) - delivered
    detail = {"energy_kwh": visit["energy_kwh"], "delivered_kwh": delivered, "gap_kwh": gap,
              "dwell_min": visit["dwell_min"]}
    detail["pass"] = (abs(visit["energy_kwh"] - 14.0) < 1e-9 and 6.0 <= delivered <= 7.0 and 7.0 <= gap <= 8.0)
    return detail


# 3 两点/对数正态停留的平稳剩余寿命
def check_stationary_residual():
    import random
    from apps.parking_lab.workbench import traffic_gen
    # 黑盒：单成分对数正态，平稳剩余均值闭式 = exp(mu+1.5*sigma^2)/2
    mu, sigma = 3.0, 0.5
    expected = math.exp(mu + 1.5 * sigma * sigma) / 2.0
    import copy
    with open(os.path.join(ROOT, "research/traffic_generation_20261031/fitted_parameters.json"), encoding="utf-8") as handle:
        params = json.load(handle)
    params = copy.deepcopy(params)
    real = params["per_lot"][0]
    synthetic = dict(real)
    synthetic.update({"lot_id": "SYN", "n_spaces": 200.0, "mean_occupancy_vehicles": 150.0,
                      "lambda_bar_veh_per_hour": 0.0,
                      "lambda_hour_by_bin": [0.0] * len(real["lambda_hour_by_bin"]),
                      "charge_session_rate_hour_by_bin": [0.0] * len(real["charge_session_rate_hour_by_bin"]),
                      "dwell_dist": {"family": "single_component_mean_matched",
                                     "components": [{"name": "single", "weight": 1.0,
                                                    "family": "lognormal_scenario",
                                                    "params": [mu, sigma],
                                                    "mean_min": math.exp(mu + sigma * sigma / 2.0),
                                                    "is_scenario": True}]},
                      "usable": True, "fit_split": "train"})
    params["per_lot"] = [synthetic]
    params["split"] = {"train_lots": ["SYN"], "validation_lots": [], "unusable_lots": []}
    try:
        arrivals, meta = traffic_gen.generate_for_lot(params, "SYN", 7, split=None)
    except TypeError:
        arrivals, meta = traffic_gen.generate_for_lot(params, "SYN", 7)
    n_initial = int(meta.get("initial_occupancy_n") or 0)
    if n_initial <= 0:
        return {"pass": False, "status": "FAIL", "error": "生成器未提供期初在场（无暖启动）"}
    initial = [a for a in arrivals if a.vehicle_id < n_initial]
    # 期初车辆 dwell_min 即剩余停留（生成器口径：time_min=0 的期初车）
    remain = [float(a.dwell_min) for a in initial if a.time_min == 0.0]
    mean_remain = sum(remain) / len(remain) if remain else None
    detail = {"expected": expected, "observed": mean_remain, "n_initial": len(remain),
              "warm_start_method": meta.get("warm_start_method")}
    detail["pass"] = (mean_remain is not None and abs(mean_remain / expected - 1.0) < 0.15)
    return detail


# 4 p_EV 可行域与不相容组合拒绝
def check_pev_feasible():
    candidates = ["research/calibration/charging_probability_20261030/model_20261031_v2.json",
                  "research/calibration/charging_probability_20261030/model_20261031.json"]
    path = next((rel for rel in candidates if os.path.exists(os.path.join(ROOT, rel))), None)
    if path is None:
        return {"pass": False, "status": "FAIL", "error": "模型文件缺失"}
    model = load_json(path)
    text = json.dumps(model, ensure_ascii=False)
    renamed = model.get("renamed_identified_quantity") or {}
    feasible = model.get("feasible_region") or {}
    detail = {"path": path, "z": renamed.get("value"),
              "identification_status": model.get("identification_status"),
              "renamed_status": renamed.get("status"),
              "has_usage_proxy_name": "observed_charging_session_ratio" in text,
              "pass": False}
    rows, violations = [], []
    def walk(node):
        if isinstance(node, dict):
            if "p_ev" in node and ("q_need" in node or "q" in node):
                rows.append(node)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(model)
    zz = renamed.get("value") or 0.03636583089107938
    for row in rows:
        try:
            p_ev = float(row["p_ev"])
            q = float(row["q_need"] if "q_need" in row else row["q"])
        except (TypeError, ValueError):
            continue
        status = str(row.get("status") or row.get("compatibility") or "")
        compatible = row.get("incompatible") is True
        if q > 1.0 + 1e-12 and not (compatible or "incompatible" in status):
            violations.append({"p_ev": p_ev, "q_need": q, "violation": "q>1 未标 incompatible（可能被截断）"})
        if p_ev < zz - 1e-12 and not (compatible or "incompatible" in status):
            violations.append({"p_ev": p_ev, "q_need": q, "violation": "p_ev<z 未标 incompatible"})
    detail["rows_checked"] = len(rows)
    detail["violations"] = violations[:5]
    detail["pass"] = (path.endswith("_v2.json")
                      and model.get("identification_status") == "unidentified"
                      and renamed.get("status") == "usage_proxy"
                      and detail["has_usage_proxy_name"] and not violations)
    return detail


# 5 整数搜索状态（未达标不得返回伪推荐）
def check_search_status():
    from apps.parking_lab.workbench import allocation
    cases = []
    def attempt(label, by_k, **kwargs):
        try:
            result = allocation.service_level_k(by_k, 0.05, **kwargs)
        except TypeError:
            result = allocation.service_level_k(by_k, 0.05)
        cases.append({"case": label, "result": result})
        return result
    infeasible = attempt("all_unmet", {0: 10.0, 1: 9.8, 2: 9.5})
    achieved = attempt("achieved", {0: 10.0, 1: 9.0, 2: 9.0, 3: 0.4})
    no_demand = attempt("no_demand", {0: 0.0, 1: 0.0})
    missing = attempt("missing_k0", {1: 5.0, 2: 1.0})
    def status_of(item):
        return item.get("status") if isinstance(item, dict) else "legacy_return"
    detail = {"cases": cases, "pass": False}
    ok = (status_of(infeasible) == "infeasible_upper_bound" and infeasible.get("k") is None
          and status_of(achieved) == "achieved" and achieved.get("k") == 3
          and status_of(no_demand) == "no_demand"
          and status_of(missing) == "missing_data")
    detail["pass"] = ok
    detail["note"] = "legacy_return 说明 R2-C 未完成"
    return detail


# 6 Erlang 闭式、同 α、占位负荷口径
def erlang_closed_form(load, servers):
    from math import factorial
    numerator = load ** servers / factorial(servers)
    denominator = sum(load ** n / factorial(n) for n in range(0, servers + 1))
    return numerator / denominator


def check_erlang_and_occupancy():
    from apps.parking_lab.workbench import allocation
    hand_values = {(0.5, 1): 1.0 / 3.0, (1.0, 1): 0.5, (2.0, 2): 0.4}
    cases = [(load, servers) for load, servers in ((0.5, 1), (1.0, 1), (2.0, 2), (5.0, 3))]
    rows = []
    ok = True
    for load, servers in cases:
        got = allocation.erlang_b(load, servers)
        mine = erlang_closed_form(load, servers)
        expected = hand_values.get((load, servers), mine)
        rows.append({"load": load, "servers": servers, "expected": expected, "module": got,
                     "closed_form": mine})
        ok = ok and abs(got - mine) < 1e-9 and abs(got - expected) < 1e-9
    load = allocation.mean_connector_load(1.0, 0.3, 0.45, 148.5, 952.0)
    dwell_model = load.get("mean_connector_minutes")
    detail = {"erlang": rows, "mean_connector_minutes": dwell_model, "pass": False}
    ok = ok and abs(float(dwell_model) - 952.0) < 1e-6
    report_rel = "docs/reports/2026-10-31-整数配桩规则与仿真验证.md"
    if os.path.exists(os.path.join(ROOT, report_rel)):
        text = open(os.path.join(ROOT, report_rel), encoding="utf-8").read()
        detail["report_wrong_b11_claim_removed"] = "B(a=1,c=1)=1/3" not in text
        ok = ok and detail["report_wrong_b11_claim_removed"]
    detail["pass"] = ok
    return detail


# 7 分母：零需求、期末删失、期初在场
def check_denominators():
    import run_cost_curve as runner
    base = {"n_spaces": 6, "chargers": 1, "charging_bays": 1, "charger_kw": 7.0, "feeder_kw": 7.0,
            "duration_hours": 2.0, "start_hour": 11.5, "interval_level": 0.9, "arrival_rate_hour": 0.0,
            "ev_share": 0.0, "charge_probability": 0.0, "policy": "dedicated_by_type", "reserve_fixed": 0, "seed": 1}
    from apps.parking_lab.workbench.simulation import Simulation
    # 零需求
    ice_only = [arrival(0, 10.0, False, False, 30.0, 0.0)]
    sim = Simulation(dict(base), arrivals=tuple(ice_only)); sim.run()
    metrics = runner._visit_metrics(sim, 0)
    # 期末删失：车辆最后才到、窗口末仍在场
    pending = [arrival(0, 100.0, True, True, 600.0, 30.0)]
    sim2 = Simulation(dict(base), arrivals=tuple(pending)); sim2.run()
    metrics2 = runner._visit_metrics(sim2, 0)
    detail = {"no_demand_charge_requests": metrics["charge_requests"],
              "pending_at_end": metrics2["charge_pending_at_window_end"],
              "pending_events_counted_as_failure": metrics2["charge_shortfall_at_departure"],
              "pending_energy": metrics2.get("pending_charge_energy_kwh"), "pass": False}
    detail["pass"] = (metrics["charge_requests"] == 0 and metrics2["charge_pending_at_window_end"] == 1
                      and metrics2["charge_shortfall_at_departure"] == 0)
    return detail


# 8 三类占位与资源守恒
def check_occupancy_conservation():
    from apps.parking_lab.workbench import costs as costs_module
    from apps.parking_lab.workbench.rules import type_occupancy_ledger
    sim = run_sim([arrival(0, 10.0, False, False, 60.0, 0.0),
                   arrival(1, 20.0, True, True, 90.0, 10.0)],
                  n_spaces=3, chargers=1, charging_bays=1, policy="full_open_ice_first")
    ledger = type_occupancy_ledger(sim.visits, sim.config, sim.horizon)["metrics"]
    total_bay_min = 0.0
    for visit in sim.visits:
        if not visit["admitted"] or visit["bay"] is None:
            continue
        end = min(visit["departure_min"] if visit["departure_min"] is not None else sim.horizon, sim.horizon)
        total_bay_min += max(0.0, end - visit["time_min"])
    three = sum(v for v in ledger.values())
    occ = costs_module.occupancy_minutes(sim, until_min=sim.horizon)
    detail = {"ledger": ledger, "three_class_sum": three, "total_bay_minutes": total_bay_min,
              "costs_occupancy_keys": sorted(occ.keys()), "pass": False}
    detail["costs_no_charging"] = occ.get("no_charging_demand")
    detail["pass"] = (three <= total_bay_min + 1e-6)
    return detail


# 9 隐藏信息：可观测前缀相同 -> 决策相同
def check_hidden_info():
    def decisions(needs_flags):
        arrivals = []
        for index, needs in enumerate(needs_flags):
            arrivals.append(arrival(index, 5.0 * index, True, needs, 60.0, 20.0 if needs else 0.0))
        sim = run_sim(arrivals, n_spaces=4, chargers=2, charging_bays=2, policy="dedicated_by_type")
        return [(round(v["time_min"], 6), v["is_ev"], v["admitted"], v["bay"]) for v in sim.visits]
    a = decisions([True, False, True, True, False])
    b = decisions([False, True, True, False, True])
    detail = {"same": a == b, "first": a[:3], "second": b[:3], "pass": a == b}
    return detail


# 10 跨 k / 功率的外生车流与需求不变
def check_exogenous_invariance():
    arrivals = [arrival(0, 10.0, True, True, 120.0, 14.0), arrival(1, 30.0, True, True, 60.0, 7.0),
                arrival(2, 50.0, False, False, 40.0, 0.0)]
    import hashlib
    def demand_hash(items):
        payload = [[a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh] for a in items]
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    base_hash = demand_hash(arrivals)
    hashes = {}
    for label, overrides in {"k1": {"charging_bays": 1, "chargers": 1},
                             "k3": {"charging_bays": 3, "chargers": 3},
                             "kw11": {"charger_kw": 11.0}, "feeder60": {"feeder_kw": 60.0}}.items():
        sim = run_sim(arrivals, **overrides)
        hashes[label] = sim.traffic_hash
        if demand_hash(tuple(arrivals)) != base_hash:
            return {"pass": False, "error": "输入需求被修改"}
    detail = {"traffic_hash": hashes, "unique": len(set(hashes.values())), "pass": len(set(hashes.values())) == 1}
    return detail


# 11 完整成本与代理目标分账、缺参传播
def check_cost_split():
    from apps.parking_lab.workbench import costs
    scenario = load_json("research/integer_allocation_20261031/cost_scenario.json")["cost"]
    params = dict(scenario)
    params.pop("parking_fee_rate", None)
    params = {key: value for key, value in params.items() if value is not None}
    sim = run_sim([arrival(0, 10.0, True, True, 90.0, 10.0)], n_spaces=2, chargers=1,
                  duration_hours=4.0)
    sim.ledger = costs.CostLedger(params)
    detail = {"pass": False}
    report = costs.cost_report(sim)
    detail["total"] = report.get("total")
    detail["complete"] = report.get("complete")
    detail["missing"] = report.get("missing_parameters")
    detail["pass"] = report.get("complete") is False and report.get("total") is None
    return detail
def check_enumeration_and_oos(curve_path, analysis_path=None):
    if not curve_path or not os.path.exists(curve_path):
        return {"pass": False, "status": "SKIP", "error": "新曲线未生成：" + str(curve_path)}
    curve = json.load(open(curve_path, encoding="utf-8"))
    groups = {}
    for row in curve["rows"]:
        groups.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    reference = None
    if analysis_path and os.path.exists(analysis_path):
        doc = json.load(open(analysis_path, encoding="utf-8"))
        reference = (doc.get("curves") or {}).get("pi0_pev030")
        if reference is None and doc.get("curves"):
            reference = next(iter(doc["curves"].values()))
    mismatches, checked = [], 0
    if reference:
        for lot, seed in (("TPE0008", "1"), ("TPE0610", "1"), ("TPE1171", "1")):
            rec = (reference.get("lots") or {}).get(lot, {}).get(seed)
            by_k = groups.get((lot, int(seed)))
            if not rec or not by_k:
                continue
            scores = {k: row["facility_cost"] + 100.0 * row["unmet_no_connector_events"]
                      for k, row in by_k.items()
                      if row.get("facility_cost") is not None and row.get("unmet_no_connector_events") is not None}
            best = min(scores, key=lambda k: (scores[k], k))
            checked += 1
            if rec.get("k_star_loss_100.0") != best:
                mismatches.append({"lot": lot, "seed": seed,
                                   "reported": rec.get("k_star_loss_100.0"), "recomputed": best})
    fits = (reference or {}).get("fits") or {}
    model_fit = fits.get("model_load") or {}
    excluded = len(fits.get("excluded") or [])
    oos = {"train_mae": model_fit.get("train_mae"), "n_train": model_fit.get("n_train"),
           "validation_mae": model_fit.get("validation_mae"),
           "n_validation": model_fit.get("n_validation")}
    ok = (checked >= 2 and not mismatches and oos["validation_mae"] is not None
          and oos["n_validation"] >= 1 and excluded >= 1)
    return {"lots_checked": checked, "loss": 100.0, "mismatches": mismatches,
            "oos": oos, "excluded_points": excluded, "pass": ok}
    detail = {"lots": len(mean), "enumeration_rows": len(mismatches), "pass": len(mean) > 0}
    detail["sample"] = mismatches[:3]
    return detail


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--curve", default=None)
    parser.add_argument("--analysis", default="research/round2_20261031/results/analysis_v2_all.json")
    args = parser.parse_args(argv)
    run("1_device_cost_window", check_device_cost)
    run("2_demand_gap_14kwh", check_demand_gap)
    run("3_stationary_residual", check_stationary_residual)
    run("4_pev_feasible", check_pev_feasible)
    run("5_search_status", check_search_status)
    run("6_erlang_occupancy", check_erlang_and_occupancy)
    run("7_denominators", check_denominators)
    run("8_occupancy_conservation", check_occupancy_conservation)
    run("9_hidden_info", check_hidden_info)
    run("10_exogenous_invariance", check_exogenous_invariance)
    run("11_cost_split", check_cost_split)
    run("12_enumeration", lambda: check_enumeration_and_oos(args.curve, args.analysis))
    passed = sum(1 for item in RESULTS if item["status"] == "PASS")
    payload = {"schema": "round2_verification/v1", "passed": passed, "total": len(RESULTS), "results": RESULTS}
    path = os.path.join(HERE, "verify_round2_report.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"passed": passed, "total": len(RESULTS)}, ensure_ascii=False))
    for item in RESULTS:
        print(item["status"], item["check"], json.dumps(item["detail"], ensure_ascii=False)[:240])
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
