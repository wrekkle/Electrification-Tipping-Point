"""阶段四按车型准入规则引擎：只接受可观测状态，绝不接受隐藏意愿。

可见信息（本模块的全部输入，见 ObservableState 字段）：
- 时钟 time_min；
- 车辆类型 is_ev（按车型判断，含本次不充电的电车）；
- 当前占用与资源：free_bays（空闲车位编号）、n_spaces/charging_bays/chargers；
- 历史统计与短期预测：arrival_rate_per_hour、p_ev、p_charge_given_ev
  （后者只由"已发生的充电开始"估计，见 prediction.Learner.observe_charging_start）。

不可见信息（本模块签名里没有这些字段，调用方传不进来，传了直接 TypeError）：
- needs_charge（本次是否要充电）、energy_kwh/SOC/电池容量、真实离场时间、未来到达车辆。

正式规则（CONTRACT §7；第三轮加入 protected_quota，C 基线）：
- dedicated_by_type（π0）：电车（含本次不充电）优先带枪位 → 充电预留位，无充电位时
  允许停普通位以保持总容量不变；油车只能用普通位，即使带枪位空着也不得进入。
- full_open_ice_first（π1）：油车优先普通位，普通位不足时可用充电区车位（先带枪位、
  再充电预留位）；电车同 π0。用于分离"共享本身"的收益。
- predictive_shared_ice_first（π2）：油车优先普通位；普通位不足时，用当时可得的电车
  到达/充电预测决定是否放行。第二轮（R2-E）：预测对象可配置为
  charge_arrivals（默认，窗口内预计开始充电的电车到达数）/ ev_arrivals（窗口内预计电车
  到达数）/ connector_load（Little 律的并发带枪位占用，需要已观察离场估计）；闸门先扣除
  本次将放行的这辆油车占用的 1 个充电位（再减调用方声明的本批已放行位数），
  保护窗口与已观察的油车平均占用时长协调（取两者较大值）。预测只来自历史观测与已发生的
  充电开始/离场，绝不读 needs_charge 或计划离场时间。
- protected_quota（π3，C 基线）：始终为电车保留 m 个充电车位（protected_bays，0≤m≤
  charging_bays）；油车仍优先普通位，只有普通位不足时才允许进入充电区，且"油车当前占用
  的充电车位数"必须严格小于 charging_bays − m。m=0 退化为 π1（油车不受配额限制）；
  m=charging_bays 时油车永不使用充电区，行为与 π0 的油车一致。油车占用计数
  （ice_charging_bays）是可观测状态：调用方由自己已放行的车辆类型与车位累计得到，不读
  needs_charge/能量/离场时间；未接线时该字段为 None，规则退回"放行后仍保留 m 个空闲充电位"
  的保守口径，detail 标注 quota_rule=free_bays_fallback。

legacy 四策略（strict/open/fixed/adaptive）不在本模块：strict 按隐藏意愿（needs_charge）
分区，只保留在 simulation.py 供历史复现，不得改名冒充 π0；正式对照必须走这里的正式规则。

签名约定：所有正式规则接受同一组关键字参数（window_min/safety_margin/prediction_object/
coordinate_window/pending_shared_bays/protected_bays），规则只用自己需要的；candidates/
decide 原样透传，因此预测选项保持纯函数可注入、不引入隐藏信息。
"""
from __future__ import annotations

from dataclasses import dataclass
import math

EPS = 1e-9

RULE_NAMES = ("dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first",
             "protected_quota")

# π2 默认参数；config.py 的同名字段默认值必须与此一致（配置可覆盖）。
DEFAULT_PREDICTION_WINDOW_MIN = 30.0
DEFAULT_FREE_BAY_MARGIN = 1.0

# π2 预测对象（R2-E）。默认 charge_arrivals 保持阶段四现状口径；三种对象回答的保护问题不同，
# 不得当成同一系数的替换：charge_arrivals 保护"会充电的电车"、ev_arrivals 保护"所有电车到访"、
# connector_load 保护"带枪位的并发占用"（Little 律，需离场估计）。
PREDICTION_OBJECTS = ("charge_arrivals", "ev_arrivals", "connector_load")
DEFAULT_PREDICTION_OBJECT = "charge_arrivals"

# 三类占位分钟指标（阶段四计量口径，进 snapshot/export/metrics，逐车/逐事件可导出）。
TYPE_OCCUPANCY_METRICS = (
    "no_charging_demand_bay_min",     # 无充电需求的电车占带枪位分钟
    "overstay_after_complete_min",    # 充电完成仍占带枪位分钟
    "ice_blocking_connector_min",     # 油车占带枪位分钟
)

TYPE_OCCUPANCY_DEFINITIONS = {
    "no_charging_demand_bay_min": "无充电需求的电车（is_ev 且 needs_charge=False）占用带枪位"
                                   "（bay < chargers）的分钟，实时累计到统计截止时刻",
    "overstay_after_complete_min": "电车充满后仍占用带枪位的分钟：从 completion_min 起算，"
                                    "到释放（released_min）或离场（departure_min）为止；"
                                    "与 costs.occupancy_minutes 的 overstay_after_complete 同口径",
    "ice_blocking_connector_min": "油车占用带枪位（bay < chargers）的分钟；按规则 π0 不应出现，"
                                   "π1/π2 共享放行时出现",
    "measurement_only": "这三项是用隐藏真值做的结果计量，只用于研究与成本归因；"
                        "不得反馈进任何准入决策（决策只看 ObservableState）",
}


def _finite(name, value, *, minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    if minimum is not None and value < minimum - EPS:
        raise ValueError(f"{name} 必须 ≥ {minimum}")
    return float(value)


def _integer(name, value, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} 必须是 ≥ {minimum} 的整数")
    return value


@dataclass(frozen=True)
class ObservableState:
    """控制器在决策时刻唯一能看到的输入。不含 needs_charge/能量/真实离场时间/未来到达。"""

    time_min: float
    is_ev: bool
    free_bays: tuple[int, ...]
    n_spaces: int
    charging_bays: int
    chargers: int
    arrival_rate_per_hour: float
    p_ev: float
    p_charge_given_ev: float
    # 已观察离场的统计（prediction.ObservableOccupancy）：在场/删失样本不计入；None=样本不足。
    mean_ice_occupancy_min: float | None = None
    mean_connector_minutes_per_ev: float | None = None
    observed_departures: int = 0
    # 油车当前占用的充电车位数（可观测：由调用方根据已放行车辆的类型与车位累计，不读隐藏意愿）。
    # None = 调用方未提供（仿真尚未接线），protected_quota 退回"保留 m 个空闲充电位"的保守口径。
    ice_charging_bays: int | None = None

    def __post_init__(self):
        object.__setattr__(self, "time_min", _finite("time_min", self.time_min, minimum=0))
        if type(self.is_ev) is not bool:
            raise ValueError("is_ev 必须是布尔值")
        n_spaces = _integer("n_spaces", self.n_spaces)
        charging_bays = _integer("charging_bays", self.charging_bays)
        chargers = _integer("chargers", self.chargers)
        if not chargers <= charging_bays <= n_spaces:
            raise ValueError("必须满足 chargers ≤ charging_bays ≤ n_spaces")
        bays = tuple(self.free_bays)
        if any(type(bay) is not int or not 0 <= bay < n_spaces for bay in bays):
            raise ValueError("free_bays 必须是 [0, n_spaces) 内的整数车位编号")
        if len(set(bays)) != len(bays):
            raise ValueError("free_bays 不能重复")
        object.__setattr__(self, "free_bays", tuple(sorted(bays)))
        object.__setattr__(self, "arrival_rate_per_hour", _finite("arrival_rate_per_hour", self.arrival_rate_per_hour, minimum=0))
        for name, value in (("p_ev", self.p_ev), ("p_charge_given_ev", self.p_charge_given_ev)):
            value = _finite(name, value)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} 必须在 [0, 1] 内")
            object.__setattr__(self, name, value)
        for name in ("mean_ice_occupancy_min", "mean_connector_minutes_per_ev"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _finite(name, value, minimum=0))
        object.__setattr__(self, "observed_departures",
                           _integer("observed_departures", self.observed_departures))
        if self.ice_charging_bays is not None:
            occupied = _integer("ice_charging_bays", self.ice_charging_bays)
            if occupied > charging_bays:
                raise ValueError("ice_charging_bays 不能超过 charging_bays")
            object.__setattr__(self, "ice_charging_bays", occupied)

    def groups(self):
        """按物理资源分组返回空闲车位：带枪位、充电预留位、普通位。"""
        equipped = tuple(bay for bay in self.free_bays if bay < self.chargers)
        designated = tuple(bay for bay in self.free_bays if self.chargers <= bay < self.charging_bays)
        ordinary = tuple(bay for bay in self.free_bays if bay >= self.charging_bays)
        return equipped, designated, ordinary

    def free_charging_bays(self):
        equipped, designated, _ = self.groups()
        return len(equipped) + len(designated)


@dataclass(frozen=True)
class AdmissionDecision:
    """一次准入决策：分到哪个车位（None=被拒）及规则理由；detail 供审计/导出。"""

    bay: int | None
    rule: str
    reason: str
    detail: dict

    def to_dict(self):
        return {"bay": self.bay, "rule": self.rule, "reason": self.reason,
                "detail": dict(self.detail)}


def predicted_charging_arrivals(state, window_min):
    """窗口内预计开始充电的电车到达数（只由可见历史统计得出）。

    到达率 × EV 份额 × EV 到达后开始充电的比例（充电开始比例只由已发生事件估计）。
    """
    window = _finite("window_min", window_min, minimum=0)
    return state.arrival_rate_per_hour / 60.0 * state.p_ev * state.p_charge_given_ev * window


def predicted_demand_bays(state, prediction_object=None, window_min=None):
    """按预测对象给出"需要保护的充电位需求"；返回 (值, 审计明细)。

    三种对象不是同一系数的替换，单位与含义不同（detail["unit"] 显式记录）：
    - charge_arrivals（默认）：窗口内预计"会真正开始充电"的电车到达数（events_in_window）；
    - ev_arrivals：窗口内预计电车到达数（events_in_window，不分是否充电）；
    - connector_load：Little 律预计的并发占用带枪位电车数（concurrent_connector_bays）
      = 到达强度 × p_ev × 已观察到的"每个 EV 到达平均占带枪位分钟数"；缺离场估计时
      退回 charge_arrivals 并在 detail 标注 fallback（不伪造占用估计）。
    只用可见统计：arrival_rate_per_hour / p_ev / p_charge_given_ev / 已观察离场均值。
    """
    obj = DEFAULT_PREDICTION_OBJECT if prediction_object is None else prediction_object
    if obj not in PREDICTION_OBJECTS:
        raise ValueError("未知预测对象：" + str(prediction_object) + "；可选 " + ", ".join(PREDICTION_OBJECTS))
    window = DEFAULT_PREDICTION_WINDOW_MIN if window_min is None else _finite("window_min", window_min, minimum=0)
    rate_min = state.arrival_rate_per_hour / 60.0
    detail = {"prediction_object": obj, "window_min": window,
              "arrival_rate_per_hour": state.arrival_rate_per_hour,
              "p_ev": state.p_ev, "p_charge_given_ev": state.p_charge_given_ev,
              "mean_connector_minutes_per_ev": state.mean_connector_minutes_per_ev,
              "observed_departures": state.observed_departures}
    if obj == "charge_arrivals":
        value = rate_min * state.p_ev * state.p_charge_given_ev * window
        detail.update(unit="events_in_window", fallback=None)
    elif obj == "ev_arrivals":
        value = rate_min * state.p_ev * window
        detail.update(unit="events_in_window", fallback=None)
    else:
        estimate = state.mean_connector_minutes_per_ev
        if estimate is None:
            value = rate_min * state.p_ev * state.p_charge_given_ev * window
            detail.update(unit="events_in_window", fallback="charge_arrivals",
                          fallback_reason="缺少已观察离场占用估计（在场样本右删失不可用）")
        else:
            value = rate_min * state.p_ev * estimate
            detail.update(unit="concurrent_connector_bays",
                          formula="arrival_rate_per_hour/60 × p_ev × mean_connector_minutes_per_ev",
                          fallback=None)
    detail["value"] = value
    return value, detail


def _ev_decision(state, rule):
    """电车候选顺序（三条规则统一）：带枪位 → 充电预留位 → 普通位（保总容量）。"""
    equipped, designated, ordinary = state.groups()
    ordered = list(equipped) + list(designated) + list(ordinary)
    reason = "ev_charging_bays_first" if ordered else "rejected_no_free_bay"
    return ordered, reason, _detail(state, rule=rule)


def _detail(state, **extra):
    equipped, designated, ordinary = state.groups()
    info = {"free_equipped_bays": len(equipped), "free_designated_bays": len(designated),
            "free_charging_bays": len(equipped) + len(designated),
            "free_ordinary_bays": len(ordinary)}
    info.update(extra)
    return info


def dedicated_by_type(state, *, window_min=None, safety_margin=None, prediction_object=None,
                       coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """π0：电车可用带枪位/充电预留位（无充电位可退普通位）；油车只能普通位。

    预测相关参数对 π0 无效，只为三条规则统一调用签名（candidates/decide 透传）。
    """
    if state.is_ev:
        return _ev_decision(state, "dedicated_by_type")
    _, _, ordinary = state.groups()
    reason = "ice_ordinary_only" if ordinary else "rejected_no_ordinary_bay"
    return list(ordinary), reason, _detail(state, rule="dedicated_by_type")


def full_open_ice_first(state, *, window_min=None, safety_margin=None, prediction_object=None,
                        coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """π1：油车优先普通位，普通位不足时可用充电区车位；电车同 π0。

    预测相关参数对 π1 无效，只为三条规则统一调用签名（candidates/decide 透传）。
    """
    if state.is_ev:
        return _ev_decision(state, "full_open_ice_first")
    equipped, designated, ordinary = state.groups()
    if ordinary:
        return (list(ordinary) + list(equipped) + list(designated),
                "ice_ordinary_first", _detail(state, rule="full_open_ice_first"))
    ordered = list(equipped) + list(designated)
    reason = "ice_shared_charging_bays" if ordered else "rejected_no_free_bay"
    return ordered, reason, _detail(state, rule="full_open_ice_first")


def predictive_shared_ice_first(state, *, window_min=None, safety_margin=None, prediction_object=None,
                                coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """π2：油车优先普通位；普通位不足时按可见预测决定是否放行到充电区。

    放行条件（R2-E）：
      可用 = 当前空闲充电位 − 1（本次将放行的这辆油车）− pending_shared_bays（本批已放行数）
      需求 = predicted_demand_bays(预测对象, 有效窗口)
      可用 − 需求 ≥ safety_margin 且 当前至少 1 个空闲充电位 ⇒ 放行

    - 扣除本次油车占用是硬要求：不能拿"放行前的空闲位数"去和预测需求比较。
    - pending_shared_bays 由调用方声明"同一决策批次内已放行的油车数"，缺省 0；
      逐车决策的仿真器每次只放行一辆，故默认 0 即准确。
    - 有效窗口 = max(window_min, 已观察油车平均占用分钟)（coordinate_window 且估计可用时）：
      油车占位多久，保护窗口就至少覆盖多久。
    """
    if state.is_ev:
        return _ev_decision(state, "predictive_shared_ice_first")
    window = DEFAULT_PREDICTION_WINDOW_MIN if window_min is None else _finite("window_min", window_min, minimum=0)
    margin = DEFAULT_FREE_BAY_MARGIN if safety_margin is None else _finite("safety_margin", safety_margin, minimum=0)
    pending = _integer("pending_shared_bays", pending_shared_bays)
    if type(coordinate_window) is not bool:
        raise ValueError("coordinate_window 必须是布尔值")
    ice_hold = state.mean_ice_occupancy_min
    coordinated = bool(coordinate_window and ice_hold is not None and ice_hold > window + EPS)
    effective_window = float(ice_hold) if coordinated else window
    expected, pdetail = predicted_demand_bays(state, prediction_object, effective_window)
    equipped, designated, ordinary = state.groups()
    info = _detail(state, rule="predictive_shared_ice_first", window_min=window,
                   effective_window_min=effective_window, safety_margin=margin,
                   coordinate_window=coordinate_window, window_coordinated=coordinated,
                   mean_ice_occupancy_min=ice_hold, pending_shared_bays=pending,
                   prediction_object=pdetail["prediction_object"],
                   predicted_demand=expected, prediction_unit=pdetail["unit"],
                   prediction_fallback=pdetail.get("fallback"),
                   prediction_detail=pdetail)
    if ordinary:
        return (list(ordinary) + list(equipped) + list(designated),
                "ice_ordinary_first", info)
    free_charging = len(equipped) + len(designated)
    usable = free_charging - 1 - pending
    slack = usable - expected
    info.update(free_charging_bays=free_charging, usable_after_this_ice=usable,
                forecast_slack_bays=slack)
    if free_charging > 0 and slack >= margin - EPS:
        return list(equipped) + list(designated), "ice_shared_by_forecast", info
    reason = "rejected_ice_reserved_for_ev_forecast" if free_charging > 0 else "rejected_no_free_bay"
    return [], reason, info


def _protected_quota_bays(value, charging_bays):
    """protected_quota 的 m 校验：必须是 0 ≤ m ≤ charging_bays 的整数。"""
    if value is None:
        raise ValueError("protected_quota 需要 protected_bays 参数（0 ≤ m ≤ charging_bays）")
    bays = _integer("protected_bays", value, minimum=0)
    if bays > charging_bays:
        raise ValueError("protected_bays 不能超过 charging_bays（m ≤ k）")
    return bays


def protected_quota(state, *, window_min=None, safety_margin=None, prediction_object=None,
                    coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """π3（C 基线）：固定保留 m 个充电车位给电车，油车仅普通位不足时按配额进入充电区。

    - 电车行为与 π0/π1/π2 相同：带枪位 → 充电预留位 → 普通位。
    - 油车：优先普通位；普通位不足时，只有"当前油车占用的充电车位数"严格小于
      charging_bays − m 才允许进入充电区（先带枪位、再充电预留位），否则拒绝。
    - m=0 退化为 π1（无配额约束）；m=charging_bays 时油车永不进入充电区，行为同 π0。
    - 油车占位计数必须由调用方按可见历史提供（ice_charging_bays）。未提供（None）时
      退回可见口径"放行这辆油车后仍保留 m 个空闲充电位"等价于 free_charging_bays − 1 ≥ m，
      detail 标注 quota_rule=free_bays_fallback；该口径在仿真接线前是保守近似，不是隐藏信息。
    - prediction_object 等预测参数对 π3 无效，只为统一签名接受。
    """
    if state.is_ev:
        return _ev_decision(state, "protected_quota")
    m = _protected_quota_bays(protected_bays, state.charging_bays)
    equipped, designated, ordinary = state.groups()
    quota = max(0, state.charging_bays - m)
    occupied = state.ice_charging_bays
    info = _detail(state, rule="protected_quota", protected_bays=m,
                   charging_bays=state.charging_bays, ice_charging_bays=occupied,
                   ice_charging_quota=quota)
    if ordinary:
        return (list(ordinary) + list(equipped) + list(designated),
                "ice_ordinary_first", info)
    free_charging = len(equipped) + len(designated)
    info["free_charging_bays"] = free_charging
    if free_charging <= 0:
        return [], "rejected_no_free_bay", info
    if occupied is None:
        allowed = free_charging - 1 >= m
        info.update(quota_rule="free_bays_fallback", quota_known=False,
                    fallback_condition="free_charging_bays - 1 >= protected_bays")
    else:
        allowed = occupied < quota
        info.update(quota_rule="observed_ice_occupancy", quota_known=True)
    info["quota_allows_this_ice"] = allowed
    if allowed:
        return list(equipped) + list(designated), "ice_shared_quota", info
    return [], "rejected_ice_quota", info


_RULES = {
    "dedicated_by_type": dedicated_by_type,
    "full_open_ice_first": full_open_ice_first,
    "predictive_shared_ice_first": predictive_shared_ice_first,
    "protected_quota": protected_quota,
}


def candidates(state, rule, *, window_min=None, safety_margin=None, prediction_object=None,
               coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """返回 (按优先次序的候选车位列表, 理由, 审计明细)；列表为空表示被拒。

    参数统一透传：各规则只读自己需要的字段，其余参数无副作用（纯函数、可注入）。
    π0/π1 忽略预测相关参数；只有 protected_quota 使用 protected_bays。
    """
    if rule not in _RULES:
        raise ValueError("未知正式规则：" + str(rule) + "；可选 " + ", ".join(RULE_NAMES))
    return _RULES[rule](state, window_min=window_min, safety_margin=safety_margin,
                        prediction_object=prediction_object,
                        coordinate_window=coordinate_window,
                        pending_shared_bays=pending_shared_bays,
                        protected_bays=protected_bays)


def decide(state, rule, *, window_min=None, safety_margin=None, prediction_object=None,
           coordinate_window=True, pending_shared_bays=0, protected_bays=None):
    """按规则给出准入决策；只读取 ObservableState 的可见字段。"""
    ordered, reason, detail = candidates(state, rule, window_min=window_min,
                                         safety_margin=safety_margin,
                                         prediction_object=prediction_object,
                                         coordinate_window=coordinate_window,
                                         pending_shared_bays=pending_shared_bays,
                                         protected_bays=protected_bays)
    return AdmissionDecision(bay=ordered[0] if ordered else None, rule=rule,
                             reason=reason, detail=detail)


def reserved_charging_bays(rule, *, charging_bays, arrival_rate_per_hour=0.0, p_ev=0.0,
                           p_charge_given_ev=0.0, window_min=None, safety_margin=None,
                           protected_bays=None):
    """各规则下"预留/保留给电车的充电位数"（展示用，不参与准入计算）。

    展示口径固定为 charge_arrivals（默认预测对象），不随 π2 可选预测对象改变；
    准入计算见 predictive_shared_ice_first / protected_quota。"""
    if rule not in _RULES:
        raise ValueError("未知正式规则：" + str(rule))
    bays = _integer("charging_bays", charging_bays)
    if rule == "dedicated_by_type":
        return bays
    if rule == "full_open_ice_first":
        return 0
    if rule == "protected_quota":
        return min(bays, _protected_quota_bays(protected_bays, bays))
    state = ObservableState(time_min=0.0, is_ev=True, free_bays=tuple(range(bays)),
                            n_spaces=bays, charging_bays=bays, chargers=bays,
                            arrival_rate_per_hour=arrival_rate_per_hour, p_ev=p_ev,
                            p_charge_given_ev=p_charge_given_ev)
    window = DEFAULT_PREDICTION_WINDOW_MIN if window_min is None else window_min
    margin = DEFAULT_FREE_BAY_MARGIN if safety_margin is None else safety_margin
    return min(bays, max(0, math.ceil(predicted_charging_arrivals(state, window) + margin)))


def _segment(visit):
    """一次已接纳访问在统计截止时刻内的占用区间（分钟）；未接纳返回 None。"""
    if not visit["admitted"] or visit["bay"] is None:
        return None
    start = float(visit["time_min"])
    released = visit.get("released_min")
    end = float(released) if released is not None else float(visit["departure_min"])
    return start, end


def type_occupancy_ledger(visits, config, cut_min):
    """三类占位分钟：汇总 + 逐车 + 逐事件区间（用隐藏真值做结果计量，不反馈进决策）。

    实时口径：只累计到 cut_min（通常取 sim.time）；在场车辆与期末删失不计未发生的未来停留。
    只有占用带枪位（bay < chargers）的访问进入这三项指标；其他车位分组在 definitions 说明。
    """
    cut = _finite("cut_min", cut_min, minimum=0)
    chargers = config.chargers
    metrics = {name: 0.0 for name in TYPE_OCCUPANCY_METRICS}
    reasons = {"no_charging_demand": "no_charging_demand_bay_min",
               "overstay_after_complete": "overstay_after_complete_min",
               "ice_blocking_connector": "ice_blocking_connector_min"}
    events, by_visit = [], []
    for visit in visits:
        per = {name: 0.0 for name in TYPE_OCCUPANCY_METRICS}
        span = _segment(visit)
        bay = visit["bay"]
        reason, span_start = None, None
        if span is not None:
            start, end = span
            end = min(end, cut)
            stay = max(0.0, end - start)
            if stay > EPS and bay < chargers:
                if not visit["is_ev"]:
                    reason, span_start = "ice_blocking_connector", start
                elif not visit["needs_charge"]:
                    reason, span_start = "no_charging_demand", start
                elif visit.get("completed") and visit.get("completion_min") is not None:
                    span_start = max(start, float(visit["completion_min"]))
                    if end - span_start > EPS:
                        reason = "overstay_after_complete"
                if reason is not None:
                    per[reasons[reason]] = end - span_start
                    events.append({"vehicle_id": visit["vehicle_id"], "reason": reason,
                                   "bay": bay, "is_ev": visit["is_ev"],
                                   "needs_charge": visit["needs_charge"],
                                   "start_min": round(span_start, 6), "end_min": round(end, 6),
                                   "minutes": round(per[reasons[reason]], 6)})
        for name in TYPE_OCCUPANCY_METRICS:
            metrics[name] += per[name]
        by_visit.append({"vehicle_id": visit["vehicle_id"], "is_ev": visit["is_ev"],
                         "needs_charge": visit["needs_charge"], "admitted": visit["admitted"],
                         "bay": bay,
                         "connector_bay": bool(visit["admitted"] and bay is not None and bay < chargers),
                         **{name: round(per[name], 6) for name in TYPE_OCCUPANCY_METRICS}})
    return {"cutoff_min": cut,
            "metrics": {name: round(metrics[name], 6) for name in TYPE_OCCUPANCY_METRICS},
            "events": events, "by_visit": by_visit,
            "definitions": dict(TYPE_OCCUPANCY_DEFINITIONS), "synthetic": True}


__all__ = [
    "RULE_NAMES", "DEFAULT_PREDICTION_WINDOW_MIN", "DEFAULT_FREE_BAY_MARGIN",
    "TYPE_OCCUPANCY_METRICS", "TYPE_OCCUPANCY_DEFINITIONS",
    "ObservableState", "AdmissionDecision", "predicted_charging_arrivals",
    "candidates", "decide", "reserved_charging_bays", "type_occupancy_ledger",
    "dedicated_by_type", "full_open_ice_first", "predictive_shared_ice_first",
]
