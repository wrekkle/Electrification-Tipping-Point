"""双服务水平指标（R3-D）：停车服务与充电服务的可复算度量。

只读 simulation.Simulation.visits / export()["visits"] 的 dict 结构，不修改任何状态；
所有量都是事后结果计量，不使用 future arrivals 或隐藏意愿之外的输入。

口径
----
- 窗口：外生车辆 = 新到达时刻落在 [0, horizon_min) 的车辆。horizon_min 缺省时，
  若给出 config 则用 config.duration_hours * 60（与 Simulation.horizon 一致），
  否则视为无上界（全部到访均算外生）。
- 期初已在场车辆：由 initial_ids 显式声明，单列 initial_occupancy_n；
  其到访不计入外生分母（若它们出现在 visits 里，按 vehicle_id 排除），但仍计入删失。
- 停车服务：外生 EV / ICE 到访中被拒绝入园（admitted=False）的比例。
- 充电服务：
  * 容量未满足请求 = 外生 EV 充电请求中「被拒绝」或「已离场但充不满（缺电 > EPS）」的请求数；
    期末仍在场者不算失败，单列 pending；
  * 离场缺电能量比 = 已离场充电会话的缺电量 / 请求量（只算窗口内已离场；删失单列）。
- 期末仍在场（未离场或离场时刻超出窗口）的已入园会话为右删失（censored_sessions），
  不计入失败，也不进离场能量比。
- 零分母（或分母缺失）时比值一律 None，不写 0。

返回结构
----
{
  "numerators":   {capacity_unmet_requests, ev_parking_failures,
                   ice_parking_failures, departed_shortfall_kwh},
  "denominators": {exogenous_charge_requests, exogenous_ev_visits,
                   exogenous_ice_visits, departed_requested_kwh},
  "rates":        {capacity_unmet_rate, ev_parking_failure_rate,
                   ice_parking_failure_rate, departed_shortfall_energy_rate},
  "levels":       {pending_energy_kwh, pending_count,
                   initial_occupancy_n, censored_sessions},
  "missing":      [缺字段名，去重排序],
  "window":       {horizon_min, exogenous_only},
  "visit_count":  visits 长度,
  "policy":       config.policy（有 config 时），否则 None,
}
"""
from __future__ import annotations

import math

EPS = 1e-9

# 计算所依赖的 visit 字段（均为 Arrival.to_dict() + _arrive/_release 的公开结果字段）。
REQUIRED_FIELDS = (
    "vehicle_id", "time_min", "is_ev", "needs_charge", "admitted",
    "departed", "departure_min", "energy_kwh", "delivered_kwh",
)

METRIC_NAMES = (
    "capacity_unmet_requests", "ev_parking_failures", "ice_parking_failures",
    "departed_shortfall_kwh", "exogenous_charge_requests", "exogenous_ev_visits",
    "exogenous_ice_visits", "departed_requested_kwh", "pending_energy_kwh",
    "pending_count", "initial_occupancy_n", "censored_sessions",
)

RATE_NAMES = (
    "capacity_unmet_rate", "ev_parking_failure_rate",
    "ice_parking_failure_rate", "departed_shortfall_energy_rate",
)


def _ratio(numerator, denominator):
    """比值：分母缺失/非有限/<=EPS 一律 None（不写 0）。"""
    if numerator is None or denominator is None:
        return None
    if not isinstance(denominator, (int, float)) or isinstance(denominator, bool):
        return None
    if not math.isfinite(denominator) or denominator <= EPS:
        return None
    return numerator / denominator


def _field(visit, name, missing):
    """取字段；缺失/None 记入 missing 并返回 None。"""
    value = visit.get(name)
    if value is None:
        missing.add(name)
    return value


def _horizon(config, horizon_min):
    if horizon_min is not None:
        return float(horizon_min)
    hours = getattr(config, "duration_hours", None) if config is not None else None
    if hours is None:
        return None
    return float(hours) * 60.0


def _in_window(arrival, horizon):
    if arrival is None or isinstance(arrival, bool):
        return False
    if not isinstance(arrival, (int, float)) or not math.isfinite(arrival):
        return False
    if arrival < -EPS:
        return False
    return horizon is None or arrival < horizon - EPS


def _initial_ids(initial_ids):
    """initial_ids：None / 非负整数（只声明数量）/ 可迭代 id 集合。"""
    if initial_ids is None:
        return set(), 0
    if isinstance(initial_ids, bool):
        raise TypeError("initial_ids 不能是 bool")
    if isinstance(initial_ids, int):
        if initial_ids < 0:
            raise ValueError("initial_ids 数量不能为负")
        return set(), int(initial_ids)
    try:
        ids = set(initial_ids)
    except TypeError as exc:  # pragma: no cover - 明确报错优于静默忽略
        raise TypeError("initial_ids 需为 None、非负整数或 id 可迭代对象") from exc
    return ids, len(ids)


def summarise(visits, config=None, horizon_min=None, initial_ids=None):
    """汇总双服务水平六项指标；visits 为 dict 序列（可来自 Simulation.export()）。

    缺字段逐条容忍：不可判定的部分跳过并记入 missing；分母为 0 时比值返回 None。
    无副作用，不修改入参。horizon_min 缺省且无 config 时窗口无上界。
    """
    horizon = _horizon(config, horizon_min)
    initial_set, initial_count = _initial_ids(initial_ids)
    missing = set()

    numerators = {name: 0 for name in (
        "capacity_unmet_requests", "ev_parking_failures",
        "ice_parking_failures", "departed_shortfall_kwh")}
    denominators = {name: 0 for name in (
        "exogenous_charge_requests", "exogenous_ev_visits",
        "exogenous_ice_visits", "departed_requested_kwh")}
    levels = {"pending_energy_kwh": 0.0, "pending_count": 0,
              "initial_occupancy_n": int(initial_count), "censored_sessions": 0}

    for visit in visits:
        if not isinstance(visit, dict):
            missing.add("visit")
            continue
        vehicle_id = visit.get("vehicle_id")
        arrival = _field(visit, "time_min", missing)
        is_ev = _field(visit, "is_ev", missing)
        needs_charge = _field(visit, "needs_charge", missing)
        admitted = _field(visit, "admitted", missing)
        if is_ev is None or needs_charge is None or admitted is None:
            continue  # 车型/意愿/是否入园不可判定：整条跳过
        is_ev, needs_charge, admitted = bool(is_ev), bool(needs_charge), bool(admitted)

        departed_raw = _field(visit, "departed", missing)
        departed = bool(departed_raw)
        departure = _field(visit, "departure_min", missing)
        departed_in_window = departed and (
            departure is None or horizon is None
            or (isinstance(departure, (int, float)) and not isinstance(departure, bool)
                and math.isfinite(departure) and departure <= horizon + EPS))
        is_initial = vehicle_id is not None and vehicle_id in initial_set
        in_window = _in_window(arrival, horizon)
        session_in_scope = in_window or is_initial

        # 右删失与期末挂起：只统计窗口内（或期初已在场）的已入园会话。
        if admitted and session_in_scope and not departed_in_window:
            levels["censored_sessions"] += 1
            if is_ev and needs_charge:
                levels["pending_count"] += 1
                energy = _field(visit, "energy_kwh", missing)
                delivered = _field(visit, "delivered_kwh", missing)
                if energy is not None and delivered is not None:
                    levels["pending_energy_kwh"] += max(0.0, float(energy) - float(delivered))

        if is_initial or not in_window:
            continue  # 期初车辆与窗口外到访不进外生分母

        if is_ev:
            denominators["exogenous_ev_visits"] += 1
            if not admitted:
                numerators["ev_parking_failures"] += 1
        else:
            denominators["exogenous_ice_visits"] += 1
            if not admitted:
                numerators["ice_parking_failures"] += 1

        if not (is_ev and needs_charge):
            continue
        denominators["exogenous_charge_requests"] += 1
        if not admitted:
            numerators["capacity_unmet_requests"] += 1  # 充电请求被拒入园
            continue
        if not departed_in_window:
            continue  # 期末仍在场：pending，不算未满足
        energy = _field(visit, "energy_kwh", missing)
        delivered = _field(visit, "delivered_kwh", missing)
        if energy is None or delivered is None:
            continue  # 能量不可判定：分子分母同口径跳过
        requested = float(energy)
        shortfall = max(0.0, requested - float(delivered))
        denominators["departed_requested_kwh"] += requested
        numerators["departed_shortfall_kwh"] += shortfall
        if shortfall > EPS:
            numerators["capacity_unmet_requests"] += 1

    rates = {
        "capacity_unmet_rate": _ratio(numerators["capacity_unmet_requests"],
                                      denominators["exogenous_charge_requests"]),
        "ev_parking_failure_rate": _ratio(numerators["ev_parking_failures"],
                                          denominators["exogenous_ev_visits"]),
        "ice_parking_failure_rate": _ratio(numerators["ice_parking_failures"],
                                           denominators["exogenous_ice_visits"]),
        "departed_shortfall_energy_rate": _ratio(numerators["departed_shortfall_kwh"],
                                                 denominators["departed_requested_kwh"]),
    }
    numerators["departed_shortfall_kwh"] = float(numerators["departed_shortfall_kwh"])
    denominators["departed_requested_kwh"] = float(denominators["departed_requested_kwh"])
    levels["pending_energy_kwh"] = float(levels["pending_energy_kwh"])
    return {
        "numerators": numerators,
        "denominators": denominators,
        "rates": rates,
        "levels": levels,
        "missing": sorted(missing),
        "window": {"horizon_min": horizon, "exogenous_only": True},
        "visit_count": len(visits),
        "policy": getattr(config, "policy", None) if config is not None else None,
    }
