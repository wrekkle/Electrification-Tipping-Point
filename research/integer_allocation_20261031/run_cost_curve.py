"""逐场站整数配桩成本曲线：枚举 k（带枪车位数），同一外生车流重放，输出物理与成本账本。

口径：research/integer_allocation_20261031/DESIGN.md；数据契约 CONTRACT.md §6-§8。
缺参：成本分项 None 不补 0；完整成本 complete=False 时 total 为 null，并给 missing_parameters。
工程关系：1 桩 = 1 枪 = 1 带枪车位（本脚本），charging_bays=chargers=k；总车位 N 固定。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.parking_lab.workbench.config import ALL_POLICIES, Config  # noqa: E402
from apps.parking_lab.workbench import charge_sources  # noqa: E402
from apps.parking_lab.workbench.rules import type_occupancy_ledger  # noqa: E402
from apps.parking_lab.workbench.service_metrics import summarise as summarise_service  # noqa: E402
from apps.parking_lab.workbench.simulation import Simulation  # noqa: E402

EPS = 1e-9
FACILITY_KEYS = ("depreciation_capex", "depreciation_life_years", "maintenance_per_bay_day",
                 "depreciation_annual")


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def facility_cost_per_period(k, cost_params, accounting_period="per_day", duration_hours=24.0):
    """设施成本走 costs.facility_cost（唯一权威入口）；days = duration_hours/24（窗口口径）。

    设备数只在该函数内乘一次。返回 {"value","items","missing_parameters","not_applicable",
    "days","source","accounting_period"}；k=0 的设备资本/维护为 0.0 并进 not_applicable。
    accounting_period 仅作报告标注，不改变数值口径（一律按实际窗口天数换算）。
    """
    from apps.parking_lab.workbench import costs
    days = float(duration_hours) / 24.0
    result = costs.facility_cost(int(k), cost_params, days=days)
    return {"value": result["value"], "items": result["items"],
            "missing_parameters": result["missing"], "not_applicable": result["not_applicable"],
            "days": days, "source": "costs.facility_cost", "accounting_period": accounting_period}


def _visit_metrics(sim, n_initial=0):
    # 期初在场车辆（暖启动）不参与「窗口内新到达」的容量指标：它们是否拿到枪由窗口前状态决定，
    # 本实验不构造窗口前轨迹。占用/交付总量仍含它们。
    visits = [v for v in sim.visits if v["vehicle_id"] >= n_initial]
    needs = [v for v in visits if v["needs_charge"]]
    admitted_needs = [v for v in needs if v["admitted"]]
    rejected_charge = [v for v in needs if not v["admitted"]]
    departed_short = [v for v in admitted_needs if v["departed"] and v["energy_kwh"] - v["delivered_kwh"] > EPS]
    pending_charge = [v for v in admitted_needs if not v["departed"] and v["energy_kwh"] - v["delivered_kwh"] > EPS]
    no_connector = [v for v in admitted_needs if v.get("charge_start_min") is None]
    plugged = [v for v in admitted_needs if v.get("charge_start_min") is not None]
    dwell_short = [v for v in plugged if v["departed"] and v["energy_kwh"] - v["delivered_kwh"] > EPS]
    ev_fail = [v for v in visits if v["is_ev"] and not v["admitted"]]
    ice_fail = [v for v in visits if (not v["is_ev"]) and not v["admitted"]]
    # 未满足充电服务事件：被拒的充电请求 + 离场仍缺电；窗口末仍在场的单列为 pending，不算最终失败。
    unserved_events = len(rejected_charge) + len(departed_short)
    unserved_energy = sum(v["energy_kwh"] for v in rejected_charge) + sum(
        max(0.0, v["energy_kwh"] - v["delivered_kwh"]) for v in departed_short)
    pending_energy = sum(max(0.0, v["energy_kwh"] - v["delivered_kwh"]) for v in pending_charge)
    return {
        "arrivals": len(visits),
        "ev_arrivals": sum(1 for v in visits if v["is_ev"]),
        "charge_requests": len(needs),
        "ev_rejected": len(ev_fail), "ice_rejected": len(ice_fail),
        "rejected_total": len(ev_fail) + len(ice_fail),
        "charge_requests_rejected": len(rejected_charge),
        "charge_shortfall_at_departure": len(departed_short),
        "charge_pending_at_window_end": len(pending_charge),
        "unserved_charge_events": unserved_events,
        "unserved_charge_energy_kwh": unserved_energy,
        # 容量驱动（没拿到枪：被拒或停在普通位）与功率/停留驱动（插上了但离场仍缺电）分开。',
        "unmet_no_connector_events": len(rejected_charge) + len(no_connector),
        "unmet_no_connector_energy_kwh": sum(v["energy_kwh"] for v in rejected_charge) + sum(v["energy_kwh"] for v in no_connector),
        "power_dwell_shortfall_events": len(dwell_short),
        "power_dwell_shortfall_kwh": sum(max(0.0, v["energy_kwh"] - v["delivered_kwh"]) for v in dwell_short),
        "pending_charge_energy_kwh": pending_energy,
        "delivered_energy_kwh": sum(v["delivered_kwh"] for v in visits),
        "ev_activity_loss_applies": len(ev_fail),
    }


def _dwell_components(lot_info):
    dist = lot_info.get("dwell_dist") or {}
    comps = dist.get("components")
    if comps:
        return [(float(c["weight"]), float(c["params"][0]), float(c["params"][1])) for c in comps]
    params = dist.get("params")
    if params:
        return [(1.0, float(params[0]), float(params[1]))]
    mean_min = float(dist.get("mean_min") or 60.0)
    return [(1.0, math.log(max(mean_min, 1.0)), 0.5)]


def warm_start_arrivals(lot_info, arrivals, meta, seed, p_ev=None, q_need=None):
    """兼容旧调用：期初车辆一律交给 traffic_gen.warm_start_arrivals（平稳长度偏置）。

    旧实现用 U(0,D) 残余停留，会把 E[remaining] 低估成 E[D]/2=2.5min（正确 4.1min），
    已删除；此处只是保留旧返回形状 (arrivals, n_initial) 的薄包装，不再有第二套公式。
    """
    from apps.parking_lab.workbench.demand import Arrival
    n_existing = int(meta.get("initial_occupancy_n") or meta.get("n_initial") or 0)
    overridden = p_ev is not None or q_need is not None
    if overridden:
        if n_existing <= 0:
            n_existing = int(round(float(lot_info.get("mean_occupancy_vehicles") or 0.0)))
        return tuple(arrivals), n_existing
    if n_existing > 0:
        return arrivals, n_existing
    n0 = int(round(float(lot_info.get("mean_occupancy_vehicles") or 0.0)))
    if n0 <= 0:
        return arrivals, 0
    rng = random.Random((int(seed) << 16) + 0x5EED)
    p_ev = float(meta.get("p_ev") if meta.get("p_ev") is not None else 0.30)
    q_need = float(meta.get("q_need") if meta.get("q_need") is not None else 1.0)
    mean_energy = float(meta.get("mean_energy_kwh") or 0.0)
    comps = _dwell_components(lot_info)
    initial = []
    for index in range(n0):
        pick, acc = rng.random(), 0.0
        chosen = comps[-1]
        for comp in comps:
            acc += comp[0]
            if pick <= acc:
                chosen = comp
                break
        dwell = math.exp(rng.gauss(chosen[1], chosen[2]))
        residual = rng.random() * dwell
        residual = min(max(residual, 0.1), 7 * 1440)
        is_ev = rng.random() < p_ev
        needs = bool(is_ev and rng.random() < q_need and mean_energy > 0)
        initial.append(Arrival(index, 0.0, is_ev, needs, residual, mean_energy if needs else 0.0))
    shifted = [Arrival(a.vehicle_id + n0, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh)
               for a in arrivals]
    return tuple(initial) + tuple(shifted), n0


def run_lot_seed(task):
    """一个 (场站, seed) 任务：同一车流下跑全部 k，保证重放同流与哈希一致。"""
    lot_id, params_path, seed, k_values, base, rule, cost_params, accounting = task
    try:
        from apps.parking_lab.workbench import traffic_gen
        with open(params_path, encoding="utf-8") as handle:
            params = json.load(handle)
        p_ev_override = base.get("p_ev_override")
        q_need_override = base.get("q_need_override")
        demand_scale = base.get("demand_scale_override")
        scenario_model = base.get("scenario_model", "legacy_product")
        charge_provenance = base.get("charge_provenance")
        dwell_scale = base.get("dwell_scale", 1.0)
        lot_info = lot_meta(params, lot_id)
        observed_ratio = float(lot_info.get("observed_p_ev_times_q_need") or 0.0)
        if scenario_model == "legacy_product":
            if p_ev_override is not None and observed_ratio > 0 and float(p_ev_override) < observed_ratio - 1e-12:
                # legacy 固定乘积情景：p_EV < z 时 q=z/p_EV>1，必须拒绝而不是截断成 1。
                raise ValueError("incompatible_scenario: p_EV=%r < observed_ratio z=%r -> q>1"
                                 % (p_ev_override, observed_ratio))
            arrivals, meta = traffic_gen.generate_for_lot(
                params, lot_id, seed, horizon_min=float(base["duration_hours"]) * 60.0,
                p_ev=p_ev_override, q_need=q_need_override, demand_scale=demand_scale,
                scenario_model="legacy_product", charge_provenance=charge_provenance,
                dwell_scale=dwell_scale)
        else:
            # 正式模式：p_EV 与 q_need 独立指定，严格校验，不因 p_EV<z 拒绝。
            if p_ev_override is None or q_need_override is None:
                raise ValueError("independent 模式必须同时给出 --p-ev 与 --q-need")
            arrivals, meta = traffic_gen.generate_for_lot(
                params, lot_id, seed, horizon_min=float(base["duration_hours"]) * 60.0,
                p_ev=p_ev_override, q_need=q_need_override, demand_scale=demand_scale,
                scenario_model="independent", strict=True, charge_provenance=charge_provenance,
                dwell_scale=dwell_scale)
        arrivals = tuple(arrivals)
        n_initial = int(meta.get("initial_occupancy_n") or 0)
        demand_hash = hashlib.sha256(json.dumps(
            [[a.vehicle_id, a.time_min, a.is_ev, a.needs_charge, a.dwell_min, a.energy_kwh]
             for a in arrivals], sort_keys=True).encode()).hexdigest()
        demand_energy_total = sum(a.energy_kwh for a in arrivals)
        theoretical_service_min_total = float(meta.get("theoretical_service_min_total") or 0.0)
        rows = []
        traffic_hash = None
        for k in k_values:
            config = {key: value for key, value in base.items()
                      if key not in ("p_ev_override", "q_need_override",
                                     "demand_scale_override", "scenario_model",
                                     "prediction_object", "coordinate_window", "protected_bays",
                                     "charge_provenance", "dwell_scale")}
            config["n_spaces"] = int(base["n_spaces"])
            config["charging_bays"] = int(k)
            config["chargers"] = int(k)
            config["policy"] = rule
            config["prediction_object"] = base.get("prediction_object", "charge_arrivals")
            config["coordinate_window"] = bool(base.get("coordinate_window", True))
            config["protected_bays"] = min(int(base.get("protected_bays", 0)), int(k))
            config["reserve_fixed"] = 0  # 仅 legacy fixed 策略使用；k=0 时必须为 0 才能通过校验
            config["seed"] = int(seed)
            config["cost"] = dict(cost_params)
            sim = Simulation(config, arrivals=arrivals)
            sim.run()
            snapshot = sim.snapshot()
            metrics = snapshot["metrics"]
            traffic_hash = sim.traffic_hash
            extra = _visit_metrics(sim, n_initial)
            extra["initial_occupancy_vehicles"] = n_initial
            # 双服务水平：容量型只看"被拒/从未拿到枪"，离场缺电单列为能量型；期初按 id 声明。
            service = summarise_service(sim.visits, horizon_min=sim.horizon,
                                        initial_ids=range(n_initial))
            extra["service_metrics"] = service
            charge_requests = extra.get("charge_requests") or 0
            capacity_only = extra.get("unmet_no_connector_events") or 0
            extra["capacity_only_unmet_requests"] = capacity_only
            extra["capacity_only_unmet_rate"] = (capacity_only / charge_requests) if charge_requests else None
            extra["new_arrivals"] = sum(1 for v in sim.visits if v["vehicle_id"] >= n_initial)
            ledger = type_occupancy_ledger(sim.visits, sim.config, sim.horizon)
            facility = facility_cost_per_period(k, cost_params, accounting, base["duration_hours"])
            row = {
                "lot_id": lot_id, "seed": int(seed), "k": int(k), "rule": rule,
                "n_spaces": int(base["n_spaces"]),
                "traffic_hash": traffic_hash,
                "duration_hours": float(base["duration_hours"]),
                "facility_cost": facility["value"],
                "facility_cost_missing": facility["missing_parameters"],
                "facility_cost_per_day": (facility["value"] / facility["days"]
                                          if facility["value"] is not None and facility["days"] > 0 else None),
                "facility_items": facility["items"],
                "facility_not_applicable": facility["not_applicable"],
                "facility_source": facility["source"],
                "facility_days": facility["days"],
                "demand_hash": demand_hash,
                "demand_energy_kwh_total": demand_energy_total,
                "theoretical_service_min_total": theoretical_service_min_total,
                "initial_occupancy_n": n_initial,
                "warm_start_method": meta.get("warm_start_method"),
                "p_ev_used": meta.get("p_ev"),
                "q_need_used": meta.get("q_need"),
                "observed_ratio_z": meta.get("observed_product_p_ev_q_need"),
                "identification_conflict": meta.get("identification_conflict"),
                "scenario_model": meta.get("scenario_model", base.get("scenario_model")),
                "product_coupled": meta.get("product_coupled"),
                "q_need_clipped": meta.get("q_need_clipped"),
                "p_ev_source": meta.get("p_ev_source"),
                "q_need_source": meta.get("q_need_source"),
                "charge_scenario_id": (charge_provenance or {}).get("scenario_id"),
                "charge_provenance": charge_provenance,
                "demand_calibration_status": meta.get("demand_calibration_status"),
                "expected_warm_residual_mean_min": meta.get("expected_warm_residual_mean_min"),
                "cost_total": metrics.get("total_cost"),
                "cost_complete": metrics.get("cost_complete"),
                "cost_items": metrics.get("cost_items"),
                "cost_missing_parameters": metrics.get("cost_missing_parameters"),
                "occupancy_minutes_by_reason": metrics.get("occupancy_minutes"),
                "type_occupancy": {key: (ledger.get("metrics") or {}).get(key)
                                    for key in ("no_charging_demand_bay_min", "overstay_after_complete_min",
                                                "ice_blocking_connector_min")},
                "peak_power_kw": metrics.get("peak_power_kw"),
                "peak_charging": metrics.get("peak_charging"),
                "mean_occupancy_rate": metrics.get("mean_occupancy_rate"),
                "charge_completion_rate_all": metrics.get("charge_completion_rate_all"),
                "energy_requested_kwh": metrics.get("energy_requested_all_kwh"),
            }
            row.update(extra)
            rows.append(row)
        return {"lot_id": lot_id, "seed": int(seed), "ok": True, "rows": rows, "meta": meta}
    except Exception as error:  # noqa: BLE001 - 任务失败要留痕，不静默跳过
        return {"lot_id": lot_id, "seed": int(seed), "ok": False,
                "error": "%s: %s" % (type(error).__name__, error),
                "traceback": traceback.format_exc()[-2000:]}


def build_base(n_spaces, duration_hours, start_hour, charger_kw, feeder_kw, interval_level=0.9):
    return {"n_spaces": int(n_spaces), "charging_bays": 0, "chargers": 0,
            "charger_kw": float(charger_kw), "feeder_kw": float(feeder_kw),
            "duration_hours": float(duration_hours), "start_hour": float(start_hour),
            "interval_level": float(interval_level),
            "arrival_rate_hour": 0.0, "ev_share": 0.0, "charge_probability": 0.0}


def lot_meta(params, lot_id):
    for row in params.get("per_lot") or []:
        if row.get("lot_id") == lot_id:
            return row
    raise KeyError("场站不存在：" + lot_id)


def main(argv=None):
    parser = argparse.ArgumentParser(description="逐场站整数配桩成本曲线")
    parser.add_argument("--params", required=True)
    parser.add_argument("--lots", required=True, help="逗号分隔场站 id")
    parser.add_argument("--seeds", default="1")
    parser.add_argument("--k-max", type=int, default=None)
    parser.add_argument("--rule", default="dedicated_by_type", choices=sorted(ALL_POLICIES))
    parser.add_argument("--charger-kw", type=float, default=7.0)
    parser.add_argument("--feeder-kw", type=float, default=120.0,
                        help="充电可用馈线功率（情景参数；未知时按情景标注）")
    parser.add_argument("--start-hour", type=float, default=11.5)
    parser.add_argument("--horizon-min", type=float, default=None,
                        help="窗口时长（分钟）；默认用拟合 generator.horizon_min（1440）")
    parser.add_argument("--demand-scale", type=float, default=None,
                        help="充电需求增长情景倍数（默认 1；>1 为情景外推，须标注）")
    parser.add_argument("--cost-file", default=None, help="成本参数 JSON（cost 块）")
    parser.add_argument("--accounting", default="per_day", choices=("per_day", "per_hour"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--p-ev", type=float, default=None,
                        help="情景覆盖：在场车辆中电车占比（识别缺口参数，默认用生成器 meta）")
    parser.add_argument("--q-need", type=float, default=None,
                        help="情景覆盖：电车本次需充电概率；independent 模式必填")
    parser.add_argument("--scenario-model", default="legacy_product",
                        choices=("legacy_product", "independent"),
                        help="legacy_product=固定乘积情景（历史对照）；independent=独立 p_EV/q_need（正式）")
    parser.add_argument("--prediction-object", default="charge_arrivals",
                        choices=("charge_arrivals", "ev_arrivals", "connector_load"),
                        help="π2 预测对象（正式配置项）")
    parser.add_argument("--coordinate-window", default="1", choices=("0", "1"),
                        help="π2 是否让保护窗口覆盖已观察油车占用")
    parser.add_argument("--protected-bays", type=int, default=0,
                        help="规则 C protected_quota 保留的带枪位数（按 k 截断）")
    parser.add_argument("--charge-catalog", default=None,
                        help="带来源元数据的充电概率情景目录（charge_sources.py）")
    parser.add_argument("--charge-scenario", default=None,
                        help="来源情景 id；给出后自动以 independent 模式覆盖 p_ev/q_need")
    parser.add_argument("--fixed-k", type=int, default=None,
                        help="只评估该 k（固定 k 独立评价用），优先于 k-max")
    parser.add_argument("--dwell-scale", type=float, default=1.0,
                        help="停留时长情景倍数（1=观测拟合；≠1 为情景敏感性，meta 标注）")
    parser.add_argument("--k-step", type=int, default=1,
                        help="k 网格步长；调参粗扫用 2，最终确认必须 1")
    parser.add_argument("--prediction-window-min", type=float, default=30.0,
                        help="π2 预测窗口（分钟），仅正式规则 π2 使用")
    parser.add_argument("--prediction-margin", type=float, default=1.0,
                        help="π2 预测余量（车位），仅正式规则 π2 使用")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    with open(args.params, encoding="utf-8") as handle:
        params = json.load(handle)
    cost_params = {}
    if args.cost_file:
        with open(args.cost_file, encoding="utf-8") as handle:
            cost_doc = json.load(handle)
        cost_params = cost_doc.get("cost", cost_doc)
    cost_params = {key: value for key, value in cost_params.items()
                   if value is not None or key in FACILITY_KEYS}

    charge_payload = None
    if args.charge_scenario:
        if not args.charge_catalog:
            parser.error("--charge-scenario 需要 --charge-catalog")
        if args.p_ev is not None or args.q_need is not None:
            parser.error("--charge-scenario 与 --p-ev/--q-need 不可同时给出（避免两套口径）")
        charge_payload = charge_sources.resolve(args.charge_catalog, args.charge_scenario)
        args.p_ev = charge_payload["p_ev"]
        args.q_need = charge_payload["q_need"]
        args.scenario_model = "independent"
    lots = [lot.strip() for lot in args.lots.split(",") if lot.strip()]
    seeds = [int(seed) for seed in args.seeds.split(",") if seed.strip()]
    tasks, meta_rows = [], []
    for lot_id in lots:
        info = lot_meta(params, lot_id)
        n_spaces = int(info["n_spaces"])
        horizon = float(args.horizon_min if args.horizon_min is not None
                        else params.get("generator", {}).get("horizon_min", 1440))
        k_max = args.k_max if args.k_max is not None else n_spaces
        k_max = max(0, min(int(k_max), n_spaces))
        step = max(1, int(args.k_step))
        if args.fixed_k is not None:
            fixed = int(args.fixed_k)
            if fixed < 0 or fixed > n_spaces:
                raise SystemExit("--fixed-k 必须在 0..n_spaces，收到 %d（n_spaces=%d）" % (fixed, n_spaces))
            k_values = [fixed]
        else:
            k_values = list(range(0, k_max + 1, step))
            if k_values[-1] != k_max:
                k_values.append(k_max)
        base = build_base(n_spaces, horizon / 60.0, args.start_hour, args.charger_kw, args.feeder_kw)
        base["p_ev_override"] = args.p_ev
        base["q_need_override"] = args.q_need
        base["demand_scale_override"] = args.demand_scale
        base["scenario_model"] = args.scenario_model
        base["prediction_object"] = args.prediction_object
        base["coordinate_window"] = args.coordinate_window == "1"
        base["protected_bays"] = args.protected_bays
        base["charge_provenance"] = charge_payload["provenance"] if charge_payload else None
        base["dwell_scale"] = args.dwell_scale
        base["ice_share_forecast_window_min"] = args.prediction_window_min
        base["ice_share_free_bay_margin"] = args.prediction_margin
        meta_rows.append({"lot_id": lot_id, "n_spaces": n_spaces, "k_values": k_values,
                          "horizon_min": horizon, "fit_split": info.get("fit_split")})
        for seed in seeds:
            tasks.append((lot_id, args.params, seed, k_values, base, args.rule, cost_params, args.accounting))

    results = []
    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for result in pool.map(run_lot_seed, tasks):
                results.append(result)
    else:
        for task in tasks:
            results.append(run_lot_seed(task))

    rows = []
    failures = []
    for result in results:
        if result.get("ok"):
            rows.extend(result["rows"])
        else:
            failures.append({key: result.get(key) for key in ("lot_id", "seed", "error", "traceback")})
    rows.sort(key=lambda row: (row["lot_id"], row["seed"], row["k"]))
    document = {
        "schema": "integer_allocation_cost_curve/v1",
        "meta": {
            "params_path": args.params, "params_sha256": sha256_file(args.params),
            "cost_file": args.cost_file,
            "cost_source": "cost-file" if args.cost_file else "none",
            "p_ev_override": args.p_ev, "q_need_override": args.q_need,
            "charge_catalog": args.charge_catalog,
            "charge_scenario": charge_payload["provenance"] if charge_payload else None,
            "fixed_k": args.fixed_k, "dwell_scale": args.dwell_scale,
            "demand_scale": args.demand_scale, "scenario_model": args.scenario_model,
            "prediction_object": args.prediction_object,
            "coordinate_window": args.coordinate_window == "1",
            "protected_bays": args.protected_bays,
            "prediction_window_min": args.prediction_window_min,
            "prediction_margin": args.prediction_margin,
            "horizon_min": meta_rows[0]["horizon_min"] if meta_rows else None,
            "facility_cost_source": "costs.facility_cost",
            "source_sha256": {path: sha256_file(path) for path in (
                "apps/parking_lab/workbench/costs.py",
                "apps/parking_lab/workbench/traffic_gen.py",
                "apps/parking_lab/workbench/allocation.py",
                "apps/parking_lab/workbench/rules.py",
                "apps/parking_lab/workbench/simulation.py",
                "apps/parking_lab/workbench/config.py",
                "apps/parking_lab/workbench/demand.py",
                "research/integer_allocation_20261031/run_cost_curve.py")},
            "rule": args.rule, "seeds": seeds, "lots": meta_rows,
            "charger_kw": args.charger_kw, "feeder_kw": args.feeder_kw,
            "k_step": max(1, int(args.k_step)),
            "start_hour": args.start_hour, "accounting_period": args.accounting,
            "engineering": "1 桩 = 1 枪 = 1 带枪车位；charging_bays=chargers=k；总车位 N 固定",
            "traffic_hash_by_lot_seed": {"%s|%s" % (row["lot_id"], row["seed"]): row["traffic_hash"]
                                         for row in rows},
        },
        "rows": rows,
        "failures": failures,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"out": args.out, "rows": len(rows), "failures": len(failures)}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
