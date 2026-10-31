# -*- coding: utf-8 -*-
"""R2-E 规则实验框架（研究用；不属于生产代码路径）。

为什么需要子类而不改 simulation.py：本轮写权限只覆盖 rules.py / prediction.py /
tests / 本目录。实验需要两件生产路径暂未接线的东西：
(a) 把"已观察离场"统计注入 ObservableState（mean_ice_occupancy_min 等）；
(b) 指定 π2 预测对象与窗口协调开关。
规则判定本身全部仍由 rules.py 完成；本子类只负责提供可见状态与选项。

隐藏信息边界：离场估计器只接收"已发生离场"事件（到达/离场时刻、车型、是否曾占带枪位、
是否曾开始充电）。仍在场车辆是右删失样本，不计入均值；不使用计划离场时间、needs_charge、
能量或未来到达。默认选项（prediction_object=charge_arrivals, coordinate_window=False）
下本子类的轨迹与 Simulation 逐字节一致——run_rules_v2.py 里对此有显式自检。
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from pathlib import Path

from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.prediction import ObservableOccupancy
from apps.parking_lab.workbench.rules import (DEFAULT_PREDICTION_OBJECT, PREDICTION_OBJECTS,
                                              candidates as rule_candidates)
from apps.parking_lab.workbench.simulation import Simulation

EPS = 1e-8

RULE_ORDER = ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first")

FAMILIES = ("observed_calibrated", "amplified_calibrated", "synthetic_range", "synthetic_stress")


class PredictingSimulation(Simulation):
    """带可见离场估计与 π2 预测对象选项的仿真（研究用）。"""

    def __init__(self, config, arrivals=None, *, prediction_object=DEFAULT_PREDICTION_OBJECT,
                 coordinate_window=False, window_min=None, safety_margin=None,
                 intervention=None):
        super().__init__(config, arrivals, intervention)
        if self.rule is None:
            raise ValueError("预测实验只用于正式规则 π0/π1/π2")
        if prediction_object not in PREDICTION_OBJECTS:
            raise ValueError("未知预测对象：" + str(prediction_object))
        self.prediction_object = prediction_object
        self.coordinate_window = bool(coordinate_window)
        self.window_min = (float(config.ice_share_forecast_window_min)
                           if window_min is None else float(window_min))
        self.safety_margin = (float(config.ice_share_free_bay_margin)
                              if safety_margin is None else float(safety_margin))
        self.occupancy = ObservableOccupancy()
        self._pending_departures = []

    # ---- 可见离场观测（只由离场事件驱动） -------------------------------------
    def _refresh_observed_departures(self):
        if not self._pending_departures:
            return
        remaining = []
        for visit in self._pending_departures:
            if not visit["departed"]:
                remaining.append(visit)
                continue
            start = float(visit["time_min"])
            departure = float(visit["departure_min"])
            released = visit.get("released_min")
            connector = 0.0
            if visit["bay"] is not None and visit["bay"] < self.config.chargers:
                connector_end = float(released) if released is not None else departure
                connector = max(0.0, connector_end - start)
            self.occupancy.observe_departure(
                is_ev=visit["is_ev"], duration_min=max(0.0, departure - start),
                connector_minutes=connector,
                charging_started=visit["charge_start_min"] is not None)
        self._pending_departures = remaining

    def _arrive(self, a):
        super()._arrive(a)
        visit = self.visits[-1]
        if visit["admitted"]:
            self._pending_departures.append(visit)

    def observable_state(self, a, forecast, free):
        self._refresh_observed_departures()
        state = super().observable_state(a, forecast, free)
        estimate = self.occupancy.estimate()
        return replace(state,
                       mean_ice_occupancy_min=estimate["mean_ice_occupancy_min"],
                       mean_connector_minutes_per_ev=estimate["mean_connector_minutes_per_ev"],
                       observed_departures=estimate["observed_departures"])

    def choose_bay(self, a, forecast):
        c = self.config
        free = [bay for bay in range(c.n_spaces) if bay not in self.active]
        state = self.observable_state(a, forecast, free)
        ordered, reason, detail = rule_candidates(
            state, self.rule, window_min=self.window_min, safety_margin=self.safety_margin,
            prediction_object=self.prediction_object,
            coordinate_window=self.coordinate_window)
        detail = dict(detail)
        if self.intervention.get("exclude_no_charging_demand") and not a.needs_charge:
            ordered = [bay for bay in ordered if bay >= c.chargers]
            detail["counterfactual"] = "exclude_no_charging_demand"
        bay = ordered[0] if ordered else None
        self.last_decision = {"rule": self.rule, "reason": reason, "bay": bay,
                              "detail": detail, "legacy": False}
        return bay


# ---- 指标（口径与 research/integer_allocation_20261031/run_cost_curve.py 一致） ----
def visit_metrics(sim, n_initial=0):
    """窗口需求指标：期初在场车辆（id < n_initial）不计入，避免把暖启动当新需求。"""
    visits = [v for v in sim.visits if v["vehicle_id"] >= n_initial]
    needs = [v for v in visits if v["needs_charge"]]
    admitted_needs = [v for v in needs if v["admitted"]]
    rejected_charge = [v for v in needs if not v["admitted"]]
    no_connector = [v for v in admitted_needs if v.get("charge_start_min") is None]
    plugged = [v for v in admitted_needs if v.get("charge_start_min") is not None]
    departed_short = [v for v in admitted_needs if v["departed"]
                      and v["energy_kwh"] - v["delivered_kwh"] > EPS]
    pending_charge = [v for v in admitted_needs if not v["departed"]
                      and v["energy_kwh"] - v["delivered_kwh"] > EPS]
    ev_fail = [v for v in visits if v["is_ev"] and not v["admitted"]]
    ice_fail = [v for v in visits if (not v["is_ev"]) and not v["admitted"]]
    return {
        "arrivals": len(visits),
        "ev_arrivals": sum(1 for v in visits if v["is_ev"]),
        "charge_requests": len(needs),
        "ev_rejected": len(ev_fail),
        "ice_rejected": len(ice_fail),
        "rejected_total": len(ev_fail) + len(ice_fail),
        "charge_requests_rejected": len(rejected_charge),
        "unmet_no_connector_events": len(rejected_charge) + len(no_connector),
        "unmet_no_connector_energy_kwh": (sum(v["energy_kwh"] for v in rejected_charge)
                                          + sum(v["energy_kwh"] for v in no_connector)),
        "admitted_no_connector": len(no_connector),
        "charging_started": len(plugged),
        "departed_shortfall_events": len(departed_short),
        "pending_charge_events": len(pending_charge),
        "delivered_energy_kwh": sum(v["delivered_kwh"] for v in visits),
        "ice_shared_by_forecast": 0,
        "ice_rejected_by_forecast": 0,
        "ice_rejected_while_connector_idle": 0,
        "gate_evaluations": 0,
    }


def bay_utilization(sim):
    """普通位/充电区按占用分钟计的利用率（物理占用，含期初车辆）。"""
    c = sim.config
    horizon = sim.horizon
    ordinary_minutes = charging_minutes = 0.0
    for v in sim.visits:
        if not v["admitted"]:
            continue
        minutes = max(0.0, min(float(v["departure_min"]), horizon) - float(v["time_min"]))
        if v["bay"] < c.charging_bays:
            charging_minutes += minutes
        else:
            ordinary_minutes += minutes
    ordinary_bays = c.n_spaces - c.charging_bays
    return {
        "ordinary_bays": ordinary_bays,
        "charging_bays": c.charging_bays,
        "ordinary_utilization": (ordinary_minutes / (ordinary_bays * horizon)
                                 if ordinary_bays > 0 else None),
        "charging_utilization": (charging_minutes / (c.charging_bays * horizon)
                                 if c.charging_bays > 0 else None),
    }


def run_metrics(sim, n_initial=0):
    metrics = visit_metrics(sim, n_initial=n_initial)
    metrics.update(bay_utilization(sim))
    shared = rejected = idle = evaluated = 0
    for v in sim.visits:
        reason = v["admission"].get("reason")
        detail = v["admission"].get("detail") or {}
        if "predicted_demand" in detail:
            evaluated += 1
        if reason == "ice_shared_by_forecast":
            shared += 1
        elif reason == "rejected_ice_reserved_for_ev_forecast":
            rejected += 1
            if detail.get("free_charging_bays", 0) > 0:
                idle += 1
    metrics["ice_shared_by_forecast"] = shared
    metrics["ice_rejected_by_forecast"] = rejected
    metrics["ice_rejected_while_connector_idle"] = idle
    metrics["gate_evaluations"] = evaluated
    metrics["traffic_hash"] = sim.traffic_hash
    metrics["demand_hash"] = sim.demand_hash
    return metrics


# ---- k 选择（CONTRACT §3 语义） --------------------------------------------
def service_level_k(by_k, alpha=0.05, metric="unmet_no_connector_events"):
    """最小 k：mean_metric(k) ≤ alpha × mean_metric(k=0)。

    by_k: {k: 该 k 的指标均值（跨种子）}。与阶段四契约一致；缺失 k=0 或基线为 0 时
    分别返回 missing_data / no_demand。用 ceil 语义的自然推广（直接比较实数阈值）。
    """
    if 0 not in by_k:
        return {"status": "missing_data", "k": None, "alpha": alpha, "metric": metric}
    baseline = float(by_k[0])
    if baseline <= 0:
        return {"status": "no_demand", "k": 0, "alpha": alpha, "metric": metric,
                "baseline": 0.0, "target": 0.0, "metric_mean": 0.0}
    target = alpha * baseline
    for k in sorted(by_k):
        value = float(by_k[k])
        if value <= target + 1e-12:
            return {"status": "achieved", "k": int(k), "alpha": alpha, "metric": metric,
                    "baseline": baseline, "target": target, "metric_mean": value}
    best = float(by_k[max(by_k)])
    return {"status": "infeasible_upper_bound", "k": None, "alpha": alpha, "metric": metric,
            "baseline": baseline, "target": target, "max_k": max(by_k),
            "metric_mean_at_max_k": best}


def resolve_service_level_k():
    """优先用 allocation.service_level_k（task-3 产出），不可用/签名不符则用本模块实现。

    返回 (callable, implementation_label)。外部实现按契约签名调用；任何异常都退回本地
    实现并在 label 里记录原因（不静默换口径）。
    """
    try:
        from apps.parking_lab.workbench.allocation import service_level_k as external
    except Exception as exc:                                  # noqa: BLE001
        return service_level_k, "local_fallback(import_failed:%s)" % type(exc).__name__
    if not callable(external):
        return service_level_k, "local_fallback(not_callable)"

    def adapter(by_k, alpha=0.05, metric="unmet_no_connector_events"):
        try:
            result = external({int(k): float(v) for k, v in by_k.items()},
                              alpha=alpha, metric=metric)
        except Exception as exc:                              # noqa: BLE001
            raise RuntimeError("external service_level_k failed: %s" % exc)
        if not isinstance(result, dict) or "status" not in result:
            raise RuntimeError("external service_level_k returned unexpected payload")
        return result

    return adapter, "apps.parking_lab.workbench.allocation.service_level_k"


def call_service_level_k(by_k, alpha=0.05, metric="unmet_no_connector_events"):
    impl, label = resolve_service_level_k()
    try:
        result = impl(by_k, alpha=alpha, metric=metric)
        source = label
    except Exception as exc:                                  # noqa: BLE001
        result = service_level_k(by_k, alpha=alpha, metric=metric)
        source = "local_fallback(%s: %s)" % (type(exc).__name__, exc)
    result = dict(result)
    result.setdefault("alpha", alpha)
    result.setdefault("metric", metric)
    result["implementation"] = source
    return result


# ---- 实测流量（traffic_gen 公开 API） --------------------------------------
def load_fitted_parameters(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def amplify_parameters(params, arrival_factor, *, warm_cap_fraction=0.95):
    """需求放大：到访率、充电会话率与暖启动占用同比放大，保持 p_EV×q_need 乘积不变。

    只复制参数后调用公开 generate_for_lot；不改动拟合文件。任何未知结构保持原样
    （traffic-eng 可能继续改 traffic_gen；这里只碰 schema v1 的公开字段）。
    """
    factor = float(arrival_factor)
    if factor <= 0:
        raise ValueError("arrival_factor 必须为正")
    out = copy.deepcopy(params)
    for entry in out.get("per_lot") or []:
        for key in ("lambda_hour_by_bin", "charge_session_rate_hour_by_bin"):
            bins = entry.get(key)
            if isinstance(bins, list):
                entry[key] = [float(x) * factor for x in bins]
        for key in ("lambda_bar_veh_per_hour", "charge_session_rate_mean_hour"):
            value = entry.get(key)
            if isinstance(value, (int, float)):
                entry[key] = float(value) * factor
        occupancy = entry.get("mean_occupancy_vehicles")
        if isinstance(occupancy, (int, float)):
            cap = warm_cap_fraction * float(entry.get("n_spaces") or occupancy)
            entry["mean_occupancy_vehicles"] = min(float(occupancy) * factor, cap)
    out.setdefault("generator", {})["r2e_amplification"] = {
        "arrival_factor": factor,
        "applied_to": "lambda_hour_by_bin, charge_session_rate_*, mean_occupancy_vehicles",
        "warm_cap_fraction": warm_cap_fraction,
    }
    return out


def resolve_traffic_gen():
    """traffic_gen 可能被 traffic-eng 并发修改：导入失败时记录并允许退化到纯合成情景。"""
    try:
        from apps.parking_lab.workbench import traffic_gen
        version = getattr(traffic_gen, "GENERATOR_VERSION", "unknown")
        for name in ("generate_for_lot", "generate", "stream_hash", "params_hash"):
            if not hasattr(traffic_gen, name):
                raise AttributeError("traffic_gen 缺少公开函数 " + name)
        return traffic_gen, {"available": True, "generator_version": version}
    except Exception as exc:                                  # noqa: BLE001
        return None, {"available": False, "error": "%s: %s" % (type(exc).__name__, exc)}
