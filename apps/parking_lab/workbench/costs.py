"""成本模型 v2：社会成本账本、占桩配对反事实与未知值传播。

唯一口径：docs/methods/COST-MODEL-V2.md（论文工作稿与后端共用词表）。
核心规则：
- 社会成本 = 用户资源成本 + 设施运营成本；收费/罚金/补贴是转移支付，单列 transfers；
  占桩影响是反事实归因，只进 attribution，不进 total。
- 参数缺失一律 None：某项所需参数为 None ⇒ 该项 None、total None、complete=False，
  并在 missing_parameters 列出参数名。禁止填 0、禁止套演示默认值。
- v1 的投诉处理成本（complaint handling）在 v2 删除；本模块不含任何投诉成本项，
  旧结果按 LEGACY_COST_MODEL_VERSION = "v1-legacy" 标注保留，不与 v2 混读。
- 时间对外统一小时（配置允许分钟输入，换算 /60）；金额币种由 currency 声明（默认 TWD）。
- 正常服务基准：目标停车场有可用车位、电车按额定功率充到所需电量、无额外搜索/绕行/步行；
  基准本身不计入增量。
- 设施成本只有 facility_cost() 一个权威入口：设备资本/维护按带枪设备位数×核算天数相乘，
  站级固定成本单列；调用方（账本、runner、分析脚本）不得再自行乘设备数或天数。
"""
from __future__ import annotations

import hashlib
import json
import math

COST_MODEL_VERSION = "v2-2026-10-30"
LEGACY_COST_MODEL_VERSION = "v1-legacy"

MINUTES_PER_HOUR = 60.0
MINUTES_PER_DAY = 1440.0
DAYS_PER_YEAR = 365.0
HOURS_PER_YEAR = 8760.0
EPS = 1e-9

# 事件层产出的成本行（单位见 COST-MODEL-V2 §1）；顺序固定，导出与界面共用。
COST_ITEMS = (
    "user_time", "ev_detour_energy", "ev_external", "ev_residual_trip_loss",
    "ice_vehicle_operating", "ice_external", "ice_activity_loss", "ev_activity_loss",
    "operator_capital_depreciation", "operator_energy", "operator_maintenance",
    "operator_facility_fixed",
)
ATTRIBUTION_ITEMS = ("occupancy_impact",)  # 不进 total
TRANSFER_ITEMS = ("parking_fee", "charging_fee", "fines", "subsidies")  # 不进 total

# 占带枪位的归因类别（不得合并）；R2-D2 起 no_charging_demand 仅指电车，油车单列。
OCCUPANCY_REASONS = (
    "no_charging_demand", "overstay_after_complete", "ice_blocking_connector",
    "dispatch_defer", "insufficient_power", "equipment_failure",
)
# 站级固定成本参数：facility_cost 的可选输入，有来源才可填；与设备成本分列。
FACILITY_FIXED_PARAMETER = "facility_fixed_cost_per_day"
FACILITY_COST_ITEMS = ("device_capital", "device_maintenance", "facility_fixed")
# 旧口径迁移映射（deprecated）：只用于读旧 JSON 对照，不得把旧值当成新字段复用。
DEPRECATED_OCCUPANCY_KEY_MAP = {
    "no_charging_demand": {
        "deprecated": True,
        "old_meaning": "旧口径把油车占带枪位也并入 no_charging_demand（EV+ICE 混口径）",
        "replacement": ("no_charging_demand", "ice_blocking_connector"),
        "migration": "旧 JSON 的 no_charging_demand ≈ 新 no_charging_demand + ice_blocking_connector；"
                     "新旧字段不得直接相减，旧值须按本条重算后再比较",
    },
}
# 释放的资源分三类独立建模，不得混为一谈
RELEASED_RESOURCES = ("power_released", "connector_released", "bay_released")
# 被拒绝车辆的合法去向：不得凭空消失
DISPOSITIONS = ("detour_exit", "alternate_bay", "give_up")

MISSING = "missing_parameters"
COMPLETE = "complete"

# 可配置成本参数：数值无来源一律 None；sources 记录来源槽位，metadata 记录币种/年份。
COST_PARAMETER_NAMES = (
    "vot_per_hour", "search_min", "detour_min", "walking_min", "detour_km_per_failure",
    "ev_kwh_per_km", "ev_energy_price_per_kwh", "alternative_charging_delta_per_kwh",
    "residual_trip_loss_per_kwh", "emission_cost_per_km", "fuel_l_per_km", "fuel_price_per_l",
    "activity_loss_per_failure", "electricity_price_per_kwh", "maintenance_per_kwh",
    "maintenance_per_bay_day", "depreciation_annual", "depreciation_capex",
    "depreciation_life_years", "facility_fixed_cost_per_day",
    "relocation_cost_per_move", "relocation_km_per_move",
    "parking_fee_per_hour", "charging_fee_per_kwh", "fine_per_event", "subsidy_per_session",
)
PROVENANCE_KINDS = ("unknown_not_calibrated", "illustrative_not_calibrated", "official_verified")


# --------------------------------------------------------------------------- #
# 时间与区间：搜索/绕行/步行区间取并集，重叠部分只计一次
# --------------------------------------------------------------------------- #
def _finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    return float(value)


def minutes_to_hours(minutes):
    """配置允许分钟输入；内部与论文公式统一用小时。"""
    return _finite(minutes, "分钟") / MINUTES_PER_HOUR


def dedupe_intervals(intervals):
    """合并重叠（含相接）区间，返回按起点排序的并集。

    用于 Δt搜索 / Δt绕行 / Δt步行：若有重叠区间只能计一次，不允许相加。
    """
    items = []
    for interval in intervals:
        if len(interval) != 2:
            raise ValueError("时间区间必须是 (start_min, end_min)")
        start, end = _finite(interval[0], "区间起点"), _finite(interval[1], "区间终点")
        if end < start - EPS:
            raise ValueError("时间区间终点早于起点")
        if end - start > EPS:
            items.append((start, end))
    items.sort()
    merged = []
    for start, end in items:
        if merged and start <= merged[-1][1] + EPS:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def union_minutes(intervals):
    """区间并集总长度（分钟）。重叠与相接部分只算一次。"""
    return math.fsum(end - start for start, end in dedupe_intervals(intervals))


# --------------------------------------------------------------------------- #
# 车流哈希：只设相同 seed 不算证据
# --------------------------------------------------------------------------- #
def traffic_hash(exogenous_events, until_min=None):
    """对外生事件流（干预点之前）做规范化 JSON 的 SHA-256。

    exogenous_events 接受 Arrival 等带 to_dict() 的对象或 dict；until_min 给定时
    只取 time_min <= until_min 的事件，即"干预点之前"的部分。
    """
    rows = []
    for event in exogenous_events:
        row = event.to_dict() if hasattr(event, "to_dict") else dict(event)
        if until_min is not None:
            when = row.get("time_min")
            if when is None or float(when) > float(until_min) + EPS:
                continue
        rows.append(row)
    raw = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 缺参传播的算术原语：None 表示未知，0 表示确实为零
# --------------------------------------------------------------------------- #
def _param(params, name):
    value = params.get(name)
    if value is None:
        return None, (name,)
    return float(value), ()


def _mul(*terms):
    missing, unknown, product, zero = [], False, 1.0, False
    for value, names in terms:
        missing.extend(names)
        if value is None:
            unknown = True
        else:
            product *= value
            if abs(value) <= EPS:
                zero = True
    if zero:  # 0 × 未知 = 0：该项确实不触发
        return 0.0, ()
    if unknown:
        return None, tuple(missing)
    return product, ()


def _add(*terms):
    missing, unknown, total = [], False, 0.0
    for value, names in terms:
        missing.extend(names)
        if value is None:
            unknown = True
        else:
            total += value
    if unknown:
        return None, tuple(missing)
    return total, ()


def _quantity(quantity):
    value = _finite(quantity, "数量")
    if value < -EPS:
        raise ValueError("数量不能为负")
    return max(0.0, value)


# 该次行程的绕行距离没有观测：不得回退到通用参数 detour_km_per_failure 当作已知。
UNKNOWN_DETOUR = object()


def _distance(params, detour_km):
    if detour_km is UNKNOWN_DETOUR:
        return None, ("detour_km_per_failure",)
    if detour_km is None:
        return _param(params, "detour_km_per_failure")
    return _finite(detour_km, "绕行距离"), ()


def _term(params, name, quantity):
    """quantity × 参数；数量为 0 时该项确实为零，不因参数未知而变 null。"""
    count = _quantity(quantity)
    if count <= EPS:
        return 0.0, ()
    return _mul((count, ()), _param(params, name))


def failure_hours(intervals=None, time_missing=()):
    """失败耗时的区间并集（小时）。intervals=None 表示区间本身不可知 ⇒ None。"""
    if intervals is None:
        names = tuple(time_missing) or ("search_min", "detour_min", "walking_min")
        return None, names
    return union_minutes(intervals) / MINUTES_PER_HOUR, ()


def _clean_missing(names):
    return tuple(sorted({name for name in names if name}))


# --------------------------------------------------------------------------- #
# 分项公式（COST-MODEL-V2 §2、§3）
# --------------------------------------------------------------------------- #
def ev_failure_cost(params, *, intervals=None, time_missing=(), shortfall_kwh=0.0, detour_km=None,
                    activity_loss_applies=False):
    """电车无法停车/无法获得所需充电服务：
    c_i^EV = v_iΔt + ΔC行驶补能 + ΔC外部 + L剩余行程 (+ L活动损失，仅放弃活动时)。

    detour_km=None 表示使用参数 detour_km_per_failure；显式给 0 表示该次失败没有绕行
    （例如已接纳但功率不足），不得借参数凭空加一段绕行能耗。
    缺电本身的损失用 ev_residual_trip_loss；放弃活动的机会损失单列 ev_activity_loss，
    两者概念不同，不得互相替代，也不得对同一损失重复计。
    activity_loss_per_failure 缺参时该项为 null（并入 missing_parameters），不得计 0。
    """
    hours, hours_missing = failure_hours(intervals, time_missing)
    user_time = _mul((hours, hours_missing), _param(params, "vot_per_hour"))
    distance = _distance(params, detour_km)
    # 额外行驶能耗：绕行公里 × 每公里电耗 × 电价
    detour_energy = _mul(distance, _param(params, "ev_kwh_per_km"),
                         _param(params, "ev_energy_price_per_kwh"))
    # 替代补能（含替代桩价差）：缺电量 × 价差
    alternative = _term(params, "alternative_charging_delta_per_kwh", shortfall_kwh)
    ev_detour_energy = _add(detour_energy, alternative)
    ev_external = _mul(distance, _param(params, "emission_cost_per_km"))
    # 缺电损失不得直接用售电价代替，必须单列参数
    residual = _term(params, "residual_trip_loss_per_kwh", shortfall_kwh)
    # 与油车共用 activity_loss_per_failure：只有"放弃活动"才触发；未触发时确实为 0。
    activity = _term(params, "activity_loss_per_failure", 1.0 if activity_loss_applies else 0.0)
    items = {"user_time": user_time[0], "ev_detour_energy": ev_detour_energy[0],
             "ev_external": ev_external[0], "ev_residual_trip_loss": residual[0],
             "ev_activity_loss": activity[0]}
    missing = _clean_missing(user_time[1] + ev_detour_energy[1] + ev_external[1]
                             + residual[1] + activity[1])
    return {"kind": "EV", "items": items, "missing_parameters": list(missing)}


def ice_failure_cost(params, *, intervals=None, time_missing=(), activity_loss_applies=False, detour_km=None):
    """油车无法停车：c_i^ICE = v_i(Δt搜索+Δt绕行+Δt步行) + ΔC车辆运行 + ΔC外部 + L活动损失。

    Δt 三项先取区间并集再乘时间价值，重叠区间不重复相加；电车无充电需求时也只计停车失败，
    不产生充电失败损失。
    """
    hours, hours_missing = failure_hours(intervals, time_missing)
    user_time = _mul((hours, hours_missing), _param(params, "vot_per_hour"))
    distance = _distance(params, detour_km)
    operating = _mul(distance, _param(params, "fuel_l_per_km"), _param(params, "fuel_price_per_l"))
    external = _mul(distance, _param(params, "emission_cost_per_km"))
    activity = _term(params, "activity_loss_per_failure", 1.0 if activity_loss_applies else 0.0)
    items = {"user_time": user_time[0], "ice_vehicle_operating": operating[0],
             "ice_external": external[0], "ice_activity_loss": activity[0]}
    missing = _clean_missing(user_time[1] + operating[1] + external[1] + activity[1])
    return {"kind": "ICE", "items": items, "missing_parameters": list(missing)}


def depreciation_daily(params):
    """设备折旧按日分摊：年金/365；或 capex / 寿命年 / 365。两者只能取其一。"""
    annual, capex = params.get("depreciation_annual"), params.get("depreciation_capex")
    if annual is not None and capex is not None:
        raise ValueError("设备投入与折旧分摊只能取其一：不能同时给出 depreciation_annual 与 depreciation_capex")
    if annual is not None:
        return float(annual) / DAYS_PER_YEAR, ()
    if capex is not None:
        life, life_missing = _param(params, "depreciation_life_years")
        if life is None:
            return None, life_missing
        return float(capex) / life / DAYS_PER_YEAR, ()
    return None, ("depreciation_annual",)


def facility_cost(k, cost_params, *, days):
    """设施成本唯一权威入口：设备资本 + 设备维护 + 站级固定成本（COST-MODEL-V2 §6）。

    口径：
    - device_capital = k × (depreciation_capex / depreciation_life_years) × days；
      以 depreciation_annual 给出时 = k × (depreciation_annual / 365) × days（两者互斥）。
    - device_maintenance = k × maintenance_per_bay_day × days。
    - facility_fixed = facility_fixed_cost_per_day × days；站级成本与设备数无关、单列。
    返回 {"value", "items", "missing", "not_applicable"}：
    - k=0：设备资本与维护为 0.0 并进 not_applicable（零设备没有资本/维护，不是缺参）；
    - 设备参数缺失（None 或未给出）⇒ 该项 None、value None，参数名进 missing；禁止补 0；
    - 未提供 facility_fixed_cost_per_day 键 = 本次核算不含站级固定成本（旧成本曲线口径），
      items["facility_fixed"]=0.0 且不进 missing；显式传 None 才表示"未知"。
    设备数与天数只在本函数内相乘一次；调用方不得再乘，避免重复相乘。
    """
    if isinstance(k, bool) or type(k) is not int or k < 0:
        raise ValueError("k 必须是 >= 0 的整数（带枪设备位数）")
    days = _finite(days, "核算天数")
    if days < 0:
        raise ValueError("核算天数不能为负")
    params = dict(cost_params or {})
    items, not_applicable, missing = {}, [], []
    if k == 0:
        items["device_capital"] = 0.0
        items["device_maintenance"] = 0.0
        not_applicable.extend(("device_capital", "device_maintenance"))
    else:
        daily, daily_missing = depreciation_daily(params)
        if daily is None:
            items["device_capital"] = None
            missing.extend(daily_missing)
        else:
            items["device_capital"] = daily * k * days
        maintenance, maintenance_missing = _param(params, "maintenance_per_bay_day")
        if maintenance is None:
            items["device_maintenance"] = None
            missing.extend(maintenance_missing)
        else:
            items["device_maintenance"] = maintenance * k * days
    if FACILITY_FIXED_PARAMETER in params:
        fixed = params[FACILITY_FIXED_PARAMETER]
        if fixed is None:
            items["facility_fixed"] = None
            missing.append(FACILITY_FIXED_PARAMETER)
        else:
            fixed = _finite(fixed, FACILITY_FIXED_PARAMETER)
            if fixed < 0:
                raise ValueError("站级固定成本不能为负")
            items["facility_fixed"] = fixed * days
    else:
        items["facility_fixed"] = 0.0
    missing = _clean_missing(missing)
    value = None if any(item is None for item in items.values()) else math.fsum(items.values())
    return {"value": value, "items": items, "missing": list(missing),
            "not_applicable": list(not_applicable)}


def legacy_no_charging_demand(minutes):
    """deprecated 迁移映射（读旧 JSON 专用）：旧口径 no_charging_demand 含油车占带枪位。

    新口径下旧值 ≈ no_charging_demand（仅 EV）+ ice_blocking_connector。不得把旧值直接当新
    字段使用，也不得把两键相加后写回新口径字段；见 DEPRECATED_OCCUPANCY_KEY_MAP。
    """
    values = []
    for name in ("no_charging_demand", "ice_blocking_connector"):
        value = (minutes or {}).get(name) or 0.0
        values.append(_finite(value, name))
    return math.fsum(values)


CHARGING_FAILURE_SOURCES = {
    "insufficient_power": "功率不足或无可用枪口（馈线均分受限/枪数不足）",
    "equipment_failure": "设备故障（本仿真未注入故障事件，恒为 0）",
    "dispatch_defer": "智能调度主动暂缓供电（本仿真未实现该策略，恒为 0）",
}


def classify_charging_failure(visit, config):
    """充电失败原因分类：零功率/功率不足与设备故障、主动暂缓分开记。

    本仿真没有设备故障注入、也没有调度暂缓策略，可识别的只有功率/枪口不足；
    另外两类在归因表里恒为 0，不得混入同一项。
    """
    if config.charger_kw <= 0 or config.feeder_kw <= 0 or config.chargers <= 0:
        return "insufficient_power"
    bay = visit.get("bay")
    if bay is None or bay >= config.chargers:
        return "insufficient_power"
    return "insufficient_power"


def transfer_amounts(params, visits, delivered_kwh, until_min=None):
    """转移支付（停车费/充电费/罚金/补贴）：单列，不进社会总成本。

    实时口径：until_min 给定时只累计到该时刻，在场车辆不得按计划停留时长或完整窗口
    收费（未发生的停车时间不能已经记账）。until_min=None 表示按计划离场时间算到窗口末，
    这只用于 projected 预计字段，不能写回实际口径。
    """
    cut = math.inf if until_min is None else max(0.0, _finite(until_min, "统计截止分钟"))
    hours = []
    for visit in visits:
        if not visit["admitted"]:
            continue
        start = visit["time_min"]
        end = min(visit["departure_min"], cut)
        if end > start:
            hours.append(end - start)
    parked_hours = math.fsum(hours) / MINUTES_PER_HOUR
    values, missing = {}, []
    for item, name, quantity in (
        ("parking_fee", "parking_fee_per_hour", parked_hours),
        ("charging_fee", "charging_fee_per_kwh", delivered_kwh),
        ("fines", "fine_per_event", 0.0),
        ("subsidies", "subsidy_per_session", 0.0),
    ):
        value, names = _term(params, name, quantity)
        values[item] = value
        missing.extend(names)
    return values, _clean_missing(missing)


def occupancy_minutes(sim, until_min=None):
    """按归因类别统计带枪位占用分钟（归因展示，不进 total）。

    三类严格分列（R2-D2，2026-10-31 迁移）：
    - no_charging_demand：仅 is_ev=True 且 needs_charge=False 的电车占带枪位；
    - overstay_after_complete：电车充满后仍占带枪位的分钟；
    - ice_blocking_connector：油车（is_ev=False）占带枪位，π1/π2 共享放行时才出现。

    迁移说明（旧键 deprecated）：旧口径 no_charging_demand = 无充电需求电车 + 占用带枪位的
    油车，旧 JSON 不能直接与新版比较；须用 legacy_no_charging_demand(minutes) 或
    DEPRECATED_OCCUPANCY_KEY_MAP 还原后比较。新口径下油车分钟单列 ice_blocking_connector。

    实时口径：until_min 缺省取 sim.time，在场车辆只累计到当前时刻——不得把未来计划
    停留时长或完整窗口算进"当前占用"。预计最终值由 cost_report["projected"] 单列。
    """
    c = sim.config
    now = max(0.0, _finite(sim.time, "当前仿真分钟"))
    if until_min is None:
        cut = now
    else:
        cut = min(max(0.0, _finite(until_min, "统计截止分钟")), sim.horizon)
    minutes = {reason: 0.0 for reason in OCCUPANCY_REASONS}
    for visit in sim.visits:
        if not visit["admitted"] or visit["bay"] is None:
            continue
        start = visit["time_min"]
        if visit.get("released_min") is not None:
            # 反事实 B：充满后挪到普通位，带枪位占用在释放时刻结束（车辆本身没有消失）
            end = visit["released_min"]
        elif visit["departed"]:
            end = visit["departure_min"]
        else:
            end = visit["departure_min"]
        end = min(end, cut)
        stay = max(0.0, end - start)
        if visit["needs_charge"]:
            if visit["completed"] and visit["completion_min"] is not None:
                minutes["overstay_after_complete"] += max(0.0, end - max(start, visit["completion_min"]))
            elif visit["delivered_kwh"] <= EPS and visit["bay"] < c.chargers:
                # 持有枪口却零交付：功率不足/设备不可用，归因单列（不冒充排队等待）
                minutes["insufficient_power"] += stay
        elif not visit["is_ev"]:
            # 油车占带枪位：旧口径混进 no_charging_demand，现单列（rules.type_occupancy 同口径）
            if visit["bay"] < c.chargers:
                minutes["ice_blocking_connector"] += stay
        elif visit["bay"] < c.chargers:
            minutes["no_charging_demand"] += stay
    return minutes


def resource_minutes(sim, until_min=None):
    """四类占用资源分别记账（分钟）：功率/枪口/带枪位/普通位，不得合并成一个"释放"。

    connector_min：占用带枪车位的分钟；charged_bay_min：占用充电车位的分钟；
    ordinary_bay_min：占用普通车位的分钟；power_kw_min：实际充电功率积分（kW·min，
    由 power_segments 累计，只统计到 until 为止）。挪车后车辆继续占普通位直到原定离场。
    实时口径同 occupancy_minutes：until_min 缺省取 sim.time。
    """
    c = sim.config
    now = max(0.0, _finite(sim.time, "当前仿真分钟"))
    if until_min is None:
        cut = now
    else:
        cut = min(max(0.0, _finite(until_min, "统计截止分钟")), sim.horizon)
    result = {"power_kw_min": 0.0, "connector_min": 0.0,
              "charged_bay_min": 0.0, "ordinary_bay_min": 0.0,
              "relocation_moves": 0}
    power = []
    for segment in sim.power_segments:
        start, end = segment["start_min"], min(segment["end_min"], cut)
        if end > start:
            power.append((end - start) * segment["power_kw"])
    result["power_kw_min"] = math.fsum(power)
    for visit in sim.visits:
        if not visit["admitted"]:
            continue
        start = min(visit["time_min"], cut)
        end = min(visit["departure_min"], cut)
        if end <= start:
            continue
        relocated_min = visit.get("relocated_min")
        if relocated_min is not None:
            result["relocation_moves"] += 1
            charger_end = min(end, max(relocated_min, start))
            bay = visit.get("relocated_from_bay")
            current = visit.get("relocated_to_bay")
        else:
            charger_end = end
            bay = visit["bay"]
            current = visit["bay"]
        if bay is not None and bay < c.chargers:
            result["connector_min"] += max(0.0, charger_end - start)
        if bay is not None and bay < c.charging_bays:
            result["charged_bay_min"] += max(0.0, charger_end - start)
        if current is not None and current >= c.charging_bays:
            ordinary_start = start if relocated_min is None else max(start, min(relocated_min, cut))
            result["ordinary_bay_min"] += max(0.0, end - ordinary_start)
    return result


# --------------------------------------------------------------------------- #
# 账本
# --------------------------------------------------------------------------- #
class DuplicateCostLineError(ValueError):
    """同一用户同一时段出现第二条失败成本行：拒绝入账（防止重复计费）。"""


class CostLedger:
    def __init__(self, params=None, *, currency="TWD", price_year=None, accounting_period="per_day"):
        self.params = dict(params or {})
        self.currency = currency
        self.price_year = price_year
        self.accounting_period = accounting_period
        self.lines = []
        self.occupancy_impact = None
        self.relocations = []
        self._failures = {}
        self._missing = []

    def add_failure(self, user_id, kind, *, intervals=None, time_missing=(), shortfall_kwh=0.0,
                    activity_loss_applies=False, detour_km=None, reason=None, disposition=None):
        """记录一条失败成本行。同一用户只允许一条（重复计费直接拒绝）。"""
        if kind not in ("EV", "ICE"):
            raise ValueError("失败成本类型必须是 EV 或 ICE")
        prior = self._failures.get(user_id)
        if prior is not None:
            raise DuplicateCostLineError(
                f"用户 {user_id} 已有失败成本行（{prior['kind']}），同一用户同一时段只允许一条")
        if kind == "EV":
            result = ev_failure_cost(self.params, intervals=intervals, time_missing=time_missing,
                                     shortfall_kwh=shortfall_kwh, detour_km=detour_km,
                                     activity_loss_applies=activity_loss_applies)
        else:
            result = ice_failure_cost(self.params, intervals=intervals, time_missing=time_missing,
                                      activity_loss_applies=activity_loss_applies, detour_km=detour_km)
        period = None
        if intervals is not None and len(intervals):
            merged = dedupe_intervals(intervals)
            period = (merged[0][0], merged[-1][1])
        line = {"user_id": user_id, "kind": kind, "reason": reason, "disposition": disposition,
                "period_min": period, "items": result["items"],
                "missing_parameters": result["missing_parameters"]}
        self._failures[user_id] = line
        self.lines.append(line)
        self._missing.extend(result["missing_parameters"])
        return line

    def add_relocation(self, user_id, *, from_bay, to_bay, time_min):
        """挪车事件（充满后释放带枪位）：只挪到普通位，车辆保留原定离场时间。

        挪车代价按次计（relocation_cost_per_move）；参数未知时成本为 null 并进
        missing_parameters，不得假设零成本。
        """
        event = {"user_id": user_id, "from_bay": from_bay, "to_bay": to_bay,
                 "time_min": _finite(time_min, "挪车时间")}
        self.relocations.append(event)
        return event

    def relocation_count(self):
        return len(self.relocations)

    def has_failure(self, user_id):
        return user_id in self._failures

    def failure_count(self):
        return len(self.lines)

    def set_occupancy_impact(self, value, *, traffic_hash_value=None):
        """占桩影响只作归因展示；不进入 total。"""
        if value is not None:
            value = _finite(value, "占桩影响")
        self.occupancy_impact = value
        self.occupancy_traffic_hash = traffic_hash_value

    def summary(self, *, elapsed_min=0.0, delivered_kwh=0.0, chargers=None, transfers=None,
                occupancy_minutes_by_reason=None, resource_minutes=None, projected=None):
        if chargers is None:
            raise ValueError("summary 需要 chargers（带枪车位/设备数）：按位维护成本必须乘以设备数量")
        equipped_bays = max(0, int(chargers))
        elapsed = max(0.0, _finite(elapsed_min, "已运行分钟"))
        days = elapsed / MINUTES_PER_DAY
        missing = set(self._missing)
        items = {}
        for item in COST_ITEMS:
            values = [line["items"][item] for line in self.lines if item in line["items"]]
            if not values:
                items[item] = 0.0
            elif any(value is None for value in values):
                items[item] = None
            else:
                items[item] = math.fsum(values)
        # 设施成本（设备资本+维护+站级固定）统一由 facility_cost 计算：设备数只乘一次，
        # 窗口天数按 elapsed_min/1440 精确换算；这里不得再乘 chargers 或 days。
        facility = facility_cost(equipped_bays, self.params, days=days)
        items["operator_capital_depreciation"] = facility["items"]["device_capital"]
        items["operator_facility_fixed"] = facility["items"]["facility_fixed"]
        missing.update(facility["missing"])
        value, names = _term(self.params, "electricity_price_per_kwh", delivered_kwh)
        items["operator_energy"] = value
        missing.update(names)
        per_kwh = _term(self.params, "maintenance_per_kwh", delivered_kwh)
        value, names = _add(per_kwh, (facility["items"]["device_maintenance"], ()))
        items["operator_maintenance"] = value
        missing.update(names)
        # 挪车成本：按挪车次数计，参数未知 ⇒ null（不假设免费挪车）
        relocation_cost, relocation_missing = _term(
            self.params, "relocation_cost_per_move", float(self.relocation_count()))
        missing.update(relocation_missing)
        total = None if (any(value is None for value in items.values())
                         or relocation_cost is None) else math.fsum(items.values()) + relocation_cost
        if transfers is None:
            transfers, transfer_missing = ({item: None for item in TRANSFER_ITEMS}, ())
        else:
            transfer_missing = ()
        attribution = {"occupancy_impact": self.occupancy_impact,
                       "occupancy_minutes_by_reason": dict(occupancy_minutes_by_reason or {}),
                       "resource_minutes": dict(resource_minutes or {}),
                       "relocated_vehicles": [dict(event) for event in self.relocations]}
        # 折算日口径：窗口值 = 折算日值 × elapsed_days；设备数（chargers）只在折算日值里乘一次。
        daily_capital, _ = depreciation_daily(self.params)
        maintenance_rate, _ = _param(self.params, "maintenance_per_bay_day")
        if equipped_bays == 0:
            per_day_capital = 0.0
            per_day_maintenance = 0.0
        else:
            per_day_capital = None if daily_capital is None else daily_capital * equipped_bays
            per_day_maintenance = (None if maintenance_rate is None
                                   else maintenance_rate * equipped_bays)
        if FACILITY_FIXED_PARAMETER in self.params:
            raw_fixed = self.params[FACILITY_FIXED_PARAMETER]
            per_day_fixed = None if raw_fixed is None else _finite(raw_fixed, FACILITY_FIXED_PARAMETER)
            fixed_included = raw_fixed is not None
        else:
            per_day_fixed = 0.0
            fixed_included = False
        daily_equivalent = {
            "note": "窗口值 = 折算日值 × elapsed_days；设备数只在折算日值里乘一次，不得重复相乘",
            "elapsed_min": elapsed,
            "elapsed_days": days,
            "operator_capital_depreciation_per_day": per_day_capital,
            "operator_maintenance_per_day": per_day_maintenance,
            "operator_facility_fixed_per_day": per_day_fixed,
        }
        return {
            "cost_model_version": COST_MODEL_VERSION,
            "currency": self.currency, "price_year": self.price_year,
            "accounting_period": self.accounting_period,
            "unit": f"{self.currency} / 仿真窗口（{self.accounting_period} 口径）",
            "items": items, "total": total, COMPLETE: total is not None,
            "relocation_cost": relocation_cost,
            "relocation_count": self.relocation_count(),
            MISSING: sorted(missing),
            "attribution": attribution,
            "projected": dict(projected or {}),
            "transfers": dict(transfers),
            "transfers_missing_parameters": list(transfer_missing),
            "conversions": {"minutes_per_hour": MINUTES_PER_HOUR, "minutes_per_day": MINUTES_PER_DAY,
                            "days_per_year": DAYS_PER_YEAR, "hours_per_year": HOURS_PER_YEAR,
                            "elapsed_min": elapsed, "elapsed_days": days},
            "daily_equivalent": daily_equivalent,
            "facility_cost": {"source": "costs.facility_cost", "k": equipped_bays, "days": days,
                              "items": dict(facility["items"]),
                              "missing": list(facility["missing"]),
                              "not_applicable": list(facility["not_applicable"]),
                              "facility_fixed_included": fixed_included},
            "elapsed_min": elapsed,
            "synthetic": True,
        }


# --------------------------------------------------------------------------- #
# 运行级成本报告（metrics 与导出共用，保证一致）
# --------------------------------------------------------------------------- #
def cost_report(sim):
    c = sim.config
    now = max(0.0, _finite(sim.time, "当前仿真分钟"))
    delivered = math.fsum(v["delivered_kwh"] for v in sim.visits)
    # 实时口径：停车费与占桩分钟只累计到当前时刻；预计最终值单列在 projected。
    transfers, transfer_missing = transfer_amounts(sim.ledger.params, sim.visits, delivered,
                                                   until_min=now)
    report = sim.ledger.summary(elapsed_min=now, delivered_kwh=delivered, chargers=c.chargers,
                                transfers=transfers,
                                occupancy_minutes_by_reason=occupancy_minutes(sim),
                                resource_minutes=resource_minutes(sim),
                                projected={})
    report["transfers_missing_parameters"] = list(transfer_missing)
    report["relocation_blocked"] = sum(
        1 for visit in sim.visits
        if visit.get("relocation_status") == "blocked_no_ordinary_bay")
    projected_transfers, projected_missing = transfer_amounts(
        sim.ledger.params, sim.visits, delivered, until_min=sim.horizon)
    report["projected"] = {
        "note": "预计最终值：按计划离场时间算到窗口末，不是当前实时累计；不得与实时字段混用",
        "transfers": projected_transfers,
        "transfers_missing_parameters": list(projected_missing),
        "occupancy_minutes_by_reason": occupancy_minutes(sim, sim.horizon),
        "resource_minutes": resource_minutes(sim, sim.horizon),
    }
    report["assumptions"] = {
        "normal_service_baseline": "目标场有可用车位、电车按额定功率充到所需电量、无额外搜索/绕行/步行",
        "rejected_disposition": c.cost.rejected_disposition,
        "queue_and_relocation": "本仿真无排队、无插枪切换；只有占桩反事实干预才挪车，挪车必须有普通空位并保留原定离场时间，无普通位则不释放",
        "realtime_accounting": "occupancy_minutes/transfers 只累计到 sim.time；预计最终值另列 projected",
        "departed_shortfall_followup": "离场仍缺电的后续额外时间与绕行距离在本仿真无观测，保持 null 并进 missing_parameters",
        "maintenance_per_bay_day": "按带枪设备位（chargers）数量逐日相乘，不是全场总额",
        "facility_cost_entry": "设备资本/维护/站级固定成本统一由 costs.facility_cost(k=chargers, "
                               "days=elapsed_min/1440) 计算；调用方不得再乘设备数或天数",
        "facility_fixed_cost_per_day": "站级固定成本有来源才填；未提供时不纳入核算（成本情景仍为设备口径），"
                                       "不得把未提供当成已核实为 0",
        "occupancy_attribution": "三类严格分列：no_charging_demand（仅电车无充电需求）、"
                                 "overstay_after_complete、ice_blocking_connector；旧键混口径见 "
                                 "DEPRECATED_OCCUPANCY_KEY_MAP 迁移映射",
        "occupancy_impact": "需要配对反事实运行（traffic_hash 相等）才能填入 attribution.occupancy_impact",
        "complaint_handling_cost": "v2 已删除，不属于任何成本项",
    }
    return report


def counterfactual_run(sim, *, until_min=None, reason_costs=None, resources=None):
    """构造配对反事实的一侧输入：车流哈希 + 社会总成本 + 三类释放资源。"""
    report = cost_report(sim)
    return {"traffic_hash": traffic_hash(sim.arrivals, until_min=until_min),
            "cost_total": report["total"], COMPLETE: report[COMPLETE],
            MISSING: report[MISSING],
            "reason_costs": dict(reason_costs or {}),
            "resources": {name: (resources or {}).get(name) for name in RELEASED_RESOURCES}}


def _run_hash(run):
    for key in ("traffic_hash",):
        if run.get(key):
            return run[key]
    for key in ("state", "metrics"):
        nested = run.get(key) or {}
        if nested.get("traffic_hash"):
            return nested["traffic_hash"]
    return None


def _run_total(run):
    if "cost_total" in run:
        return run["cost_total"]
    cost = run.get("cost") or (run.get("metrics") or {}).get("cost") or {}
    if "total" in cost:
        return cost["total"]
    return run.get("total", run.get("total_cost"))


def paired_occupancy_counterfactual(base_run, interrupt):
    """ΔC占桩影响 = C(允许该段占位) - C(及时释放充电资源)。

    两次运行必须使用完全相同的外生到达序列（traffic_hash 相等）；哈希不等即拒绝出结果。
    结果只作归因展示，不进 total；释放的 power/connector/bay 三类资源分开返回。
    """
    base_hash, interrupt_hash = _run_hash(base_run), _run_hash(interrupt)
    if not base_hash or not interrupt_hash:
        raise ValueError("缺少 traffic_hash，不能做占桩配对反事实")
    if base_hash != interrupt_hash:
        raise ValueError("traffic_hash 不一致：两次运行的外生车流不同（相同 seed 不算证据），拒绝输出占位反事实")
    base_total, interrupt_total = _run_total(base_run), _run_total(interrupt)
    missing = sorted(set(base_run.get(MISSING) or ()) | set(interrupt.get(MISSING) or ()))
    resources = {name: (interrupt.get("resources") or {}).get(name) for name in RELEASED_RESOURCES}
    reasons = dict(interrupt.get("reason_costs") or {})
    if base_total is None or interrupt_total is None:
        return {"occupancy_impact": None, COMPLETE: False, MISSING: missing,
                "traffic_hash": base_hash, "resources": resources, "reasons": reasons,
                "note": "占桩影响只作归因展示，不进入 total"}
    return {"occupancy_impact": _finite(base_total, "总成本") - _finite(interrupt_total, "总成本"),
            COMPLETE: True, MISSING: missing, "traffic_hash": base_hash,
            "resources": resources, "reasons": reasons,
            "note": "占桩影响只作归因展示，不进入 total"}


INTERVENTIONS = {
    "overstay_after_complete": {"release_after_complete": True},
    "no_charging_demand": {"exclude_no_charging_demand": True},
}
_INTERVENTION_FLAGS = {"release_after_complete", "exclude_no_charging_demand"}


def intervention_spec(intervention):
    """把干预类型名或规格对象规范化为 (reason, flags)。"""
    if isinstance(intervention, str):
        if intervention not in INTERVENTIONS:
            raise ValueError("未知占桩干预类型：" + intervention + "；可选 " + ", ".join(INTERVENTIONS))
        return intervention, dict(INTERVENTIONS[intervention])
    if isinstance(intervention, dict):
        reason = intervention.get("reason") or "custom"
        flags = {key: value for key, value in intervention.items() if key != "reason"}
        unknown = set(flags) - _INTERVENTION_FLAGS
        if unknown:
            raise ValueError("未知干预开关：" + ", ".join(sorted(unknown)))
        if not flags:
            raise ValueError("干预规格为空")
        return reason, flags
    raise ValueError("干预规格必须是类型名或对象")


def run_paired_occupancy_counterfactual(config, intervention, *, arrivals=None, arrivals_b=None):
    """可运行的占桩配对反事实：A=允许该段占位（基准），B=及时释放充电资源（干预）。

    - 两侧使用完全相同的外生到达流：不传 arrivals 时按 config 只生成一次并复用；
      arrivals_b 仅用于校验"哈希不等即拒绝"。
    - 返回 delta_total = C_A - C_B，只作归因展示，不进入任何 total；两侧各自 total 是
      完整社会成本（含各自产生的用户失败成本），不做二次计账。
    - traffic_hash 不等 ⇒ accepted=False、delta_total=None，绝不返回差值。
    """
    from .config import Config
    from .demand import generate
    from .simulation import Simulation

    c = config if isinstance(config, Config) else Config.parse(config)
    reason, flags = intervention_spec(intervention)
    left = tuple(generate(c)) if arrivals is None else tuple(arrivals)
    right = left if arrivals_b is None else tuple(arrivals_b)
    base = Simulation(c, left)
    base.run()
    interrupt = Simulation(c, right, intervention=flags)
    interrupt.run()
    hash_a, hash_b = traffic_hash(base.arrivals), traffic_hash(interrupt.arrivals)
    if hash_a != hash_b:
        return {"accepted": False, "hashes_equal": False,
                "traffic_hash_a": hash_a, "traffic_hash_b": hash_b,
                "cost_a": None, "cost_b": None, "delta_total": None,
                COMPLETE: False, MISSING: [],
                "attribution": {"occupancy_impact": None, "reason": reason},
                "note": "traffic_hash 不一致：两次运行的外生车流不同（相同 seed 不算证据），拒绝输出占位反事实"}
    report_a, report_b = cost_report(base), cost_report(interrupt)
    missing = sorted(set(report_a[MISSING]) | set(report_b[MISSING]))
    complete = report_a[COMPLETE] and report_b[COMPLETE]
    delta = None if not complete else report_a["total"] - report_b["total"]
    # 无普通空位时挪车干预未执行：不得把"未发生"报成 delta=0，标明无法计算。
    blocked_b = report_b.get("relocation_blocked", 0) or 0
    not_implemented = None
    note = "delta_total 只作归因展示，不进入任何 total；两侧 total 各自为完整社会成本"
    if flags.get("release_after_complete") and blocked_b and not report_b["relocation_count"]:
        delta, complete = None, False
        not_implemented = "no_ordinary_bay"
        note = ("无普通空位：挪车干预无法执行（不得让车辆凭空消失），不输出差值；"
                "delta_total=null 表示无法计算，不是 0")
    minutes_a = report_a["attribution"]["occupancy_minutes_by_reason"]
    minutes_b = report_b["attribution"]["occupancy_minutes_by_reason"]
    minutes_a = {name: minutes_a.get(name, 0.0) for name in OCCUPANCY_REASONS}
    minutes_b = {name: minutes_b.get(name, 0.0) for name in OCCUPANCY_REASONS}
    released = {name: minutes_a[name] - minutes_b[name] for name in OCCUPANCY_REASONS}
    ressources_a = report_a["attribution"].get("resource_minutes") or {}
    ressources_b = report_b["attribution"].get("resource_minutes") or {}

    def _delta(name):
        if name not in ressources_a or name not in ressources_b:
            return None
        return ressources_a[name] - ressources_b[name]

    return {"accepted": True, "hashes_equal": True,
            "traffic_hash_a": hash_a, "traffic_hash_b": hash_b,
            "cost_a": report_a["total"], "cost_b": report_b["total"],
            "delta_total": delta, COMPLETE: complete, MISSING: missing,
            "attribution": {"occupancy_impact": delta, "reason": reason,
                            "occupancy_minutes_a": minutes_a, "occupancy_minutes_b": minutes_b,
                            "released_minutes_by_reason": released,
                            "resource_minutes_a": dict(ressources_a),
                            "resource_minutes_b": dict(ressources_b)},
            "resources": {"power_released_kw_min": None,
                          "connector_released_min": _delta("connector_min"),
                          "charged_bay_released_min": _delta("charged_bay_min"),
                          "bay_released_min": _delta("charged_bay_min"),
                          "ordinary_bay_minutes_delta": _delta("ordinary_bay_min"),
                          "relocation_moves_b": ressources_b.get("relocation_moves"),
                          "relocation_blocked_b": blocked_b,
                          "note": "枪口/带枪位/普通位分别按分钟数比较；功率释放量在充满后自动释放，反事实不额外改变，需按充电曲线另行建模（null）"},
            "not_implemented": not_implemented,
            "note": note}


def annotate_legacy(payload, *, note=None):
    """给历史 v1 结果打版本标记，不改写其字段（历史证据只读）。"""
    marked = dict(payload)
    marked["cost_model_version"] = LEGACY_COST_MODEL_VERSION
    marked["legacy_note"] = note or "v1 结果保留原字段（含投诉成本项），口径与 v2 不可混读"
    return marked


__all__ = [
    "COST_MODEL_VERSION", "LEGACY_COST_MODEL_VERSION", "COST_ITEMS", "ATTRIBUTION_ITEMS",
    "TRANSFER_ITEMS", "OCCUPANCY_REASONS", "RELEASED_RESOURCES", "DISPOSITIONS", "MISSING", "COMPLETE",
    "COST_PARAMETER_NAMES", "PROVENANCE_KINDS",
    "minutes_to_hours", "dedupe_intervals", "union_minutes", "traffic_hash", "UNKNOWN_DETOUR",
    "failure_hours", "ev_failure_cost", "ice_failure_cost", "depreciation_daily", "facility_cost",
    "FACILITY_FIXED_PARAMETER", "FACILITY_COST_ITEMS", "DEPRECATED_OCCUPANCY_KEY_MAP",
    "legacy_no_charging_demand",
    "transfer_amounts", "occupancy_minutes", "resource_minutes", "CostLedger", "DuplicateCostLineError",
    "cost_report", "counterfactual_run", "paired_occupancy_counterfactual",
    "run_paired_occupancy_counterfactual", "intervention_spec", "INTERVENTIONS", "annotate_legacy",
]
