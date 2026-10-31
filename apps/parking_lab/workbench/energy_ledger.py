"""能量服务结算（R8-B）：停车服务、充电接入、离场能量服务，逐条目写清分子/分母/适用条件。

口径（PLAN §3.5 与 DESIGN_MATRIX.energy_accounting）：
- 固定到达窗口：外生车辆 = 到达时刻在 [0, horizon_min) 的车辆。窗口结束停止新增车辆，
  已入园车辆继续跟踪到离场（或观察上限），仍删失者单列（censored），不计失败也不进缺口分母。
- 拒绝车辆计入分母，不从分母消失。
- 分列统计：初始在场（initial_vehicles）、零需求（zero_demand）、仍删失（censored）、
  缺失（missing）、非法（illegal）；五类互不吞并。
- 不假设离场后免费补能：被拒请求与离场仍缺电的需求都记为缺口；给两个口径
  （仅已入园离场会话 / 含被拒请求），不得只看后者或只写"补能后已满足"。
- 不假设损失为 0：缺字段记 missing 并排除出该条目的分子分母，不填 0。
- 不把峰值×均值×安全系数当已证明上界（本模块不做任何上界推断）。

输入：visit dict 序列（Simulation.export()["visits"] 或经适配层构造的等价结构）。
必需字段 vehicle_id, time_min, is_ev, needs_charge, admitted；
离场能量条目另需 departed, departure_min, energy_kwh, delivered_kwh。
"""
from __future__ import annotations

import math

SCHEMA_VERSION = "energy_service_ledger/v1"
EPS = 1e-9

REQUIRED_FIELDS = ("vehicle_id", "time_min", "is_ev", "admitted")
ENERGY_FIELDS = ("departed", "departure_min", "energy_kwh", "delivered_kwh")


def _finite(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value))


def _ratio(numerator, denominator):
    """比值；分母 <= EPS 或缺失时返回 None（不写 0，避免"零分母=零失败"的误读）。"""
    if denominator is None or numerator is None:
        return None
    if not _finite(denominator) or denominator <= EPS:
        return None
    return numerator / denominator


def _initial_set(initial_ids):
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
    except TypeError as exc:  # pragma: no cover
        raise TypeError("initial_ids 需为 None、非负整数或 id 可迭代对象") from exc
    return ids, len(ids)


def settle(visits, *, horizon_min=None, initial_ids=None, eps=EPS):
    """结算三类服务；返回可逐条目复算的账本 dict（含分子、分母、比值与适用条件）。

    horizon_min=None 表示无上界（全部到访都算外生，仍保留删失分列）。
    """
    if eps <= 0 or not _finite(eps):
        raise ValueError("eps 必须是正的有限数值")
    horizon = None if horizon_min is None else float(horizon_min)
    if horizon is not None and (not _finite(horizon) or horizon <= 0):
        raise ValueError("horizon_min 必须是正的有限数值或 None")
    initial_set, initial_count = _initial_set(initial_ids)

    categories = {"visits_total": 0, "exogenous_visits": 0, "initial_vehicles": 0,
                  "zero_demand": 0, "censored": 0, "missing": 0, "illegal": 0,
                  "rejected": 0, "charge_requests": 0}
    missing_fields = {}
    illegal = []
    parking = {"numerator": 0, "denominator": 0,
               "by_type": {"ev": {"numerator": 0, "denominator": 0},
                           "ice": {"numerator": 0, "denominator": 0}}}
    access = {"numerator": 0, "denominator": 0,
              "subcounts": {"rejected_no_bay": 0, "admitted_no_delivery": 0,
                            "admitted_started": 0, "started_censored": 0}}
    dep_admitted = {"n_sessions": 0, "n_full": 0, "n_short": 0,
                    "demand_kwh": 0.0, "delivered_kwh": 0.0}
    dep_all = {"n_requests": 0, "demand_kwh": 0.0, "delivered_kwh": 0.0}
    censored = {"n_sessions": 0, "pending_demand_kwh": 0.0, "delivered_so_far_kwh": 0.0}
    initial_energy = {"demand_kwh": 0.0, "delivered_kwh": 0.0, "n_sessions": 0}

    def add_missing(name):
        missing_fields[name] = missing_fields.get(name, 0) + 1

    for index, visit in enumerate(visits):
        categories["visits_total"] += 1
        if not isinstance(visit, dict):
            categories["illegal"] += 1
            illegal.append({"index": index, "reason": "visit 不是对象"})
            continue
        # ---- 字段读取与非法判定
        if any(visit.get(name) is None for name in REQUIRED_FIELDS):
            for name in REQUIRED_FIELDS:
                if visit.get(name) is None:
                    add_missing(name)
            categories["missing"] += 1
            continue
        vehicle_id = visit["vehicle_id"]
        arrival = visit["time_min"]
        if not _finite(arrival) or arrival < -eps:
            categories["illegal"] += 1
            illegal.append({"index": index, "vehicle_id": vehicle_id,
                            "reason": "time_min 非有限或为负：%r" % (arrival,)})
            continue
        try:
            is_ev = bool(visit["is_ev"])
            admitted = bool(visit["admitted"])
        except (TypeError, ValueError):
            categories["illegal"] += 1
            illegal.append({"index": index, "vehicle_id": vehicle_id,
                            "reason": "is_ev/admitted 不可转布尔"})
            continue
        needs_raw = visit.get("needs_charge")
        if needs_raw is None:
            add_missing("needs_charge")
        elif not isinstance(needs_raw, bool):
            categories["illegal"] += 1
            illegal.append({"index": index, "vehicle_id": vehicle_id,
                            "reason": "needs_charge 不是布尔值"})
            continue
        energy_raw = visit.get("energy_kwh")
        delivered_raw = visit.get("delivered_kwh")
        if energy_raw is None:
            add_missing("energy_kwh")
        elif not _finite(energy_raw) or energy_raw < -eps:
            categories["illegal"] += 1
            illegal.append({"index": index, "vehicle_id": vehicle_id,
                            "reason": "energy_kwh 非有限或为负"})
            continue
        if delivered_raw is not None:
            if not _finite(delivered_raw) or delivered_raw < -eps:
                categories["illegal"] += 1
                illegal.append({"index": index, "vehicle_id": vehicle_id,
                                "reason": "delivered_kwh 非有限或为负"})
                continue
            if energy_raw is not None and float(delivered_raw) > float(energy_raw) + eps:
                categories["illegal"] += 1
                illegal.append({"index": index, "vehicle_id": vehicle_id,
                                "reason": "delivered_kwh 超过 energy_kwh（能量不守恒）"})
                continue
        departed_raw = visit.get("departed")
        departed = bool(departed_raw) if departed_raw is not None else False
        departure = visit.get("departure_min")
        if departed and departure is None:
            add_missing("departure_min")
        elif departure is not None and not _finite(departure):
            categories["illegal"] += 1
            illegal.append({"index": index, "vehicle_id": vehicle_id,
                            "reason": "departure_min 非有限"})
            continue

        is_initial = vehicle_id in initial_set
        in_window = (arrival < horizon - eps) if horizon is not None else True
        exogenous = in_window and not is_initial
        if is_initial:
            categories["initial_vehicles"] += 1
        if exogenous:
            categories["exogenous_visits"] += 1
        # ---- 停车服务：拒绝计入分子与分母（外生车辆）
        if exogenous:
            parking["denominator"] += 1
            key = "ev" if is_ev else "ice"
            parking["by_type"][key]["denominator"] += 1
            if not admitted:
                parking["numerator"] += 1
                parking["by_type"][key]["numerator"] += 1
                categories["rejected"] += 1
        # ---- 充电需求分类（零需求/缺失/请求）
        energy = float(energy_raw) if energy_raw is not None else None
        delivered = float(delivered_raw) if delivered_raw is not None else None
        zero_demand = (needs_raw is False) or (energy is not None and energy <= eps)
        if is_ev and zero_demand:
            # 零需求单列：电车明确不充电，或充电需求为 0；不进充电接入/能量服务分母，也不当失败
            categories["zero_demand"] += 1
        charge_request = (is_ev and needs_raw is True and energy is not None and energy > eps)
        if not charge_request:
            if needs_raw is True and energy is None:
                add_missing("energy_kwh")
            continue
        # ---- 仍删失：已入园但窗口内未离场
        if exogenous:
            categories["charge_requests"] += 1
            access["denominator"] += 1
        censored_here = False
        if exogenous or is_initial:
            # 只跟踪到达窗口内（或期初在场）的会话；窗口外到访不冒充删失样本
            censored_here = _track_censored(visit, departed, departure, horizon, censored, eps)
        if is_initial:
            if admitted:
                initial_energy["n_sessions"] += 1
                initial_energy["demand_kwh"] += energy
                initial_energy["delivered_kwh"] += delivered or 0.0
            continue
        if not exogenous:
            continue
        # 外生充电请求
        if not admitted:
            # 被拒请求：分母与缺口都保留，不假设离场后在别处免费补能
            dep_all["n_requests"] += 1
            dep_all["demand_kwh"] += energy
            access["subcounts"]["rejected_no_bay"] += 1
            continue
        if delivered is None:
            add_missing("delivered_kwh")
            dep_all["n_requests"] += 1
            dep_all["demand_kwh"] += energy
            continue
        # 充电接入：只要实际交付过电量就算接入成功（删失只影响离场能量条目，不否定已发生的接入）
        if delivered > eps:
            access["numerator"] += 1
            access["subcounts"]["admitted_started"] += 1
        else:
            access["subcounts"]["admitted_no_delivery"] += 1
        if censored_here:
            access["subcounts"]["started_censored"] += 1
            dep_all["n_requests"] += 1
            dep_all["demand_kwh"] += energy
            dep_all["delivered_kwh"] += delivered
            continue
        dep_all["n_requests"] += 1
        dep_all["demand_kwh"] += energy
        dep_all["delivered_kwh"] += delivered
        dep_admitted["n_sessions"] += 1
        dep_admitted["demand_kwh"] += energy
        dep_admitted["delivered_kwh"] += delivered
        gap = max(0.0, energy - delivered)
        if gap <= eps:
            dep_admitted["n_full"] += 1
        else:
            dep_admitted["n_short"] += 1

    categories["censored"] = censored["n_sessions"]
    dep_admitted["gap_kwh"] = max(0.0, dep_admitted["demand_kwh"] - dep_admitted["delivered_kwh"])
    dep_admitted["gap_rate"] = _ratio(dep_admitted["gap_kwh"], dep_admitted["demand_kwh"])
    dep_all["gap_kwh"] = max(0.0, dep_all["demand_kwh"] - dep_all["delivered_kwh"])
    dep_all["gap_rate"] = _ratio(dep_all["gap_kwh"], dep_all["demand_kwh"])
    for block in (dep_admitted, dep_all):
        block["service_rate"] = _ratio(block["delivered_kwh"], block["demand_kwh"])
    result = {
        "schema_version": SCHEMA_VERSION,
        "window": {"horizon_min": horizon, "exogenous_only": True,
                   "censoring": "观察窗口内未离场的已入园会话右删失，单列不计失败"},
        "categories": categories,
        "parking_service": {
            "numerator": parking["numerator"], "denominator": parking["denominator"],
            "rate": _ratio(parking["numerator"], parking["denominator"]),
            "by_type": {key: {**value, "rate": _ratio(value["numerator"], value["denominator"])}
                        for key, value in parking["by_type"].items()},
            "condition": "外生到访（到达在 [0, horizon) 且非期初在场）中被拒绝入园的比例",
        },
        "charging_access": {
            "numerator": access["numerator"], "denominator": access["denominator"],
            "rate": _ratio(access["numerator"], access["denominator"]),
            "subcounts": access["subcounts"],
            "condition": ("外生充电请求（is_ev 且 needs_charge 且 energy_kwh>0）中"
                          "实际交付过电量（delivered_kwh>eps）的比例；被拒请求在分母内"),
        },
        "departure_energy_service": {
            "admitted_departed": {
                **dep_admitted,
                "condition": ("仅已入园且窗口内已离场的充电会话；缺口=需求-交付；"
                              "不假设离场后补能，不假设缺口成本为 0"),
            },
            "including_rejected": {
                **dep_all,
                "condition": ("外生充电请求全体（含被拒、含仍删失的已交付部分）；"
                              "被拒请求按 delivered=0 计入缺口，不假设别处免费补能"),
            },
        },
        "censored": {**censored,
                     "condition": "窗口末仍在场（未离场或离场时刻超出窗口）的已入园充电会话"},
        "initial_vehicles": {**initial_energy,
                             "condition": "期初已在场车辆单列，不进外生分母"},
        "missing": {"n_visits": categories["missing"],
                    "fields": [{"field": k, "count": v} for k, v in sorted(missing_fields.items())]},
        "illegal": {"n_visits": categories["illegal"], "detail": illegal},
        "notes": [
            "分母=0 时比值记 None，不写 0。",
            "重采样次数不是样本量；统计单位须是独立场站-日或独立流。",
            "本条目不提供任何已证明的容量上界；k 上界只能来自完整枚举（见 engine/offline_opt.py）。",
        ],
    }
    return result


def _track_censored(visit, departed, departure, horizon, censored, eps):
    """记录右删失并返回是否删失。已入园、未在窗口内离场 = 删失。"""
    if not visit.get("admitted"):
        return False
    if not departed:
        censored["n_sessions"] += 1
        energy = visit.get("energy_kwh")
        delivered = visit.get("delivered_kwh")
        if _finite(energy):
            censored["pending_demand_kwh"] += float(energy)
        if _finite(delivered):
            censored["delivered_so_far_kwh"] += float(delivered)
        return True
    if horizon is not None and _finite(departure) and float(departure) > horizon + eps:
        censored["n_sessions"] += 1
        energy = visit.get("energy_kwh")
        delivered = visit.get("delivered_kwh")
        if _finite(energy):
            censored["pending_demand_kwh"] += float(energy)
        if _finite(delivered):
            censored["delivered_so_far_kwh"] += float(delivered)
        return True
    return False


def settle_export(export, *, initial_ids=None):
    """直接接收 Simulation.export()：窗口取 state.horizon_min，车辆取 visits。"""
    if not isinstance(export, dict) or "visits" not in export:
        raise ValueError("export 必须是 Simulation.export() 的 dict（含 visits）")
    state = export.get("state") or {}
    horizon = state.get("horizon_min")
    return settle(export["visits"], horizon_min=horizon, initial_ids=initial_ids)


def ledger_rows(result):
    """账本 -> 扁平 CSV 行：每条含 section/metric/numerator/denominator/rate/condition。

    用途：E6 机器输出与 SI 表格；一行一条目，分子分母和适用条件同时落盘，避免只给比值。
    """
    rows = []

    def add(section, metric, numerator=None, denominator=None, rate=None, condition=None, extra=None):
        row = {"section": section, "metric": metric, "numerator": numerator,
               "denominator": denominator, "rate": rate, "condition": condition}
        if extra:
            row.update(extra)
        rows.append(row)

    categories = result["categories"]
    for name in ("visits_total", "exogenous_visits", "initial_vehicles", "zero_demand",
                 "censored", "missing", "illegal", "rejected", "charge_requests"):
        add("categories", name, numerator=categories[name],
            condition="分列计数（不是比值）")
    parking = result["parking_service"]
    add("parking_service", "rejected_over_exogenous", parking["numerator"],
        parking["denominator"], parking["rate"], parking["condition"])
    for key, block in parking["by_type"].items():
        add("parking_service", "rejected_over_exogenous_%s" % key, block["numerator"],
            block["denominator"], block["rate"], parking["condition"])
    access = result["charging_access"]
    add("charging_access", "delivered_any_over_charge_requests", access["numerator"],
        access["denominator"], access["rate"], access["condition"])
    dep = result["departure_energy_service"]["admitted_departed"]
    add("departure_energy_service", "delivered_kwh_over_demand_kwh_admitted_departed",
        dep["delivered_kwh"], dep["demand_kwh"], dep["service_rate"], dep["condition"])
    add("departure_energy_service", "gap_kwh_over_demand_kwh_admitted_departed",
        dep["gap_kwh"], dep["demand_kwh"], dep["gap_rate"], dep["condition"])
    dep_all = result["departure_energy_service"]["including_rejected"]
    add("departure_energy_service", "delivered_kwh_over_demand_kwh_including_rejected",
        dep_all["delivered_kwh"], dep_all["demand_kwh"], dep_all["service_rate"],
        dep_all["condition"])
    add("departure_energy_service", "gap_kwh_over_demand_kwh_including_rejected",
        dep_all["gap_kwh"], dep_all["demand_kwh"], dep_all["gap_rate"], dep_all["condition"])
    censored = result["censored"]
    add("censored", "pending_demand_kwh", censored["pending_demand_kwh"],
        denominator=None, rate=None, condition=censored["condition"])
    add("missing", "n_visits", result["missing"]["n_visits"],
        denominator=categories["visits_total"], rate=None,
        condition="必需字段缺失的访次数；缺失既不当 0 也不进对应分母")
    add("illegal", "n_visits", result["illegal"]["n_visits"],
        denominator=categories["visits_total"], rate=None,
        condition="非法访次数（负值/不守恒/类型错误），单列不吞并")
    return rows
