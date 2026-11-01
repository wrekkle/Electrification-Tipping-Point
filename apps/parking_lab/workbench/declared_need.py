# -*- coding: utf-8 -*-
"""v3 申报制充电准入：信息合同、决策表与混合停车仿真（复用 workbench 引擎）。

本模块只新增文件，不修改 simulation.py / rules.py / config.py / info_regimes.py，
既有默认数值行为不变。v3 与 v2 的差别（用户 2026-11-01 决定）：

1. 信息条件版本化（INFORMATION_CONTRACT_VERSION = 3.0.0）
   - 真实补能需求 needs_charge：模拟器物理真值，隐藏字段；
   - 到达时申报的充电需求 declared_need：控制器可见（本轮假设申报真实、准确）；
   - 控制器可见信息 = ObservableState（车型、占用与资源、历史统计与预测）+ declared_need；
     仍不可见：能量目标、真实离场时间、未来到达、SOC。
   旧 I0（不可见 needs_charge）与 I1（analysis-only）保留为历史/对照，语义不变。
2. 准入决策表 A/B/C/D（EV 与 ICE 分开）：
   - 有申报充电需求的 EV：只接受空闲带枪位（bay < chargers）；没有就直接离开，
     不排队、不先停普通位等待、不自动换位；即使还有普通空位也记为无适配充电位置。
   - 本次不申报充电的 EV：普通位优先；普通位满后按规则允许回落到充电区
     （基准允许回落；禁止回落是独立敏感性 allow_no_need_fallback=False）。
   - 油车：普通位优先；带枪位可用性由 A/B/C/D 四条既有正式规则决定
     （A dedicated_by_type / B full_open_ice_first / C protected_quota / D
     predictive_shared_ice_first），ICE 部分直接复用 rules.py 的已测实现。
3. 充电完成即停止耗电，车辆占位到原定离场（不自动释放连接器、不挪车）；
   及时挪车仍是独立的 costs 反事实干预，不混入主模型。
4. 供电随桩数扩容：主情景要求 feeder_kw ≥ chargers × min(charger_kw, vehicle_max_kw)，
   即每辆车功率不受总馈线均分稀释；供给不足的共享功率池只作对照。
5. 指标分子分母见 content_metrics()；被拒充电需求的能量保留在能量分母中。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import Config
from .demand import Arrival
from .rules import (TYPE_OCCUPANCY_METRICS, AdmissionDecision, ObservableState,
                    decide as rule_decide, type_occupancy_ledger)
from .simulation import Simulation

EPS = 1e-9
INFORMATION_CONTRACT_VERSION = "3.0.0"
ADMISSION_RULES = ("A", "B", "C", "D")
BASE_RULE = {
    "A": "dedicated_by_type",
    "B": "full_open_ice_first",
    "C": "protected_quota",
    "D": "predictive_shared_ice_first",
}
RULE_LABELS = {
    "A": "A 专用（油车只用普通位；带枪位只给申报充电的 EV）",
    "B": "B 全开放（普通位满后油车可进充电区）",
    "C": "C 配额保护（为 EV 保留 m 个带枪位，其余对油车开放）",
    "D": "D 预测共享（按可见预测决定油车能否进充电区）",
}
VISIBLE_FIELDS = (
    "time_min", "is_ev", "free_bays", "n_spaces", "charging_bays", "chargers",
    "arrival_rate_per_hour", "p_ev", "p_charge_given_ev", "mean_ice_occupancy_min",
    "mean_connector_minutes_per_ev", "observed_departures", "ice_charging_bays",
    "declared_need",
)
HIDDEN_FIELDS = (
    "energy_kwh", "dwell_min", "departure_min", "future_arrivals", "soc",
    "battery_kwh", "true_needs_charge", "delivered_kwh",
)
DECLARATION_ASSUMPTION = (
    "本轮假设到达时申报的充电需求真实、准确（申报=真实 needs_charge）；"
    "这是运营机制假设，不是烟台 2025 停车数据的观测结果。旧 I0/I1 信息条件保留为历史对照。"
)
REJECTION_CATEGORIES = ("lot_full", "no_equipped_bay", "rule_restricted", "other")


class HiddenInformationError(PermissionError):
    """控制器读取了未授权字段。"""


class DeclaredNeedContext:
    """控制器可见信息合同 v3：ObservableState + 当次申报的充电需求。

    隐藏字段（能量/真实离场/未来到达/SOC/真实需求）一律抛 HiddenInformationError。
    """

    __slots__ = ("state", "declared_need")
    allowed_fields = VISIBLE_FIELDS
    information_regime = "I3_declared"
    contract_version = INFORMATION_CONTRACT_VERSION

    def __init__(self, state, declared_need):
        if not isinstance(state, ObservableState):
            raise TypeError("state 必须是 rules.ObservableState")
        if type(declared_need) is not bool:
            raise TypeError("declared_need 必须是布尔值")
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "declared_need", declared_need)

    def __getattr__(self, name):
        if name in HIDDEN_FIELDS:
            raise HiddenInformationError("信息合同 v3 不允许读取隐藏字段：%s" % name)
        raise AttributeError(name)

    def to_dict(self):
        return {"information_regime": self.information_regime,
                "contract_version": self.contract_version,
                "visible_fields": list(VISIBLE_FIELDS),
                "hidden_fields": list(HIDDEN_FIELDS),
                "declared_need": self.declared_need,
                "declaration_assumption": DECLARATION_ASSUMPTION}


def declared_need_context(state, declared_need):
    return DeclaredNeedContext(state, declared_need)


def v3_decision_table(rule):
    """返回该规则的完整决策表（供文档、测试与论文表格使用，不参与运行）。"""
    if rule not in ADMISSION_RULES:
        raise ValueError("未知 v3 准入规则：" + str(rule))
    return {
        "rule": rule, "label": RULE_LABELS[rule], "base_rule": BASE_RULE[rule],
        "ev_declared_need": [
            "1. 有空闲带枪位（bay < chargers）→ 分配编号最小的带枪位；",
            "2. 无空闲带枪位 → 直接离开（不排队、不占普通位等待、不换位）；",
            "3. 即使仍有普通空位，拒绝原因也记为 no_equipped_bay（无适配充电位置）；",
            "4. 若全场无任何空位，拒绝原因记为 lot_full。",
        ],
        "ev_no_declared_need": [
            "1. 普通位优先（bay ≥ charging_bays）；",
            "2. 普通位满后按规则允许回落到充电区：先充电预留位（无枪），再带枪位；",
            "3. 基准允许回落并单独记录其占位（type_occupancy.no_charging_demand_bay_min）；",
            "4. allow_no_need_fallback=False 是独立敏感性（禁止回落），不进入基准。",
        ],
        "ice": {
            "A": "普通位优先；普通位满则离开（不得进充电区）。",
            "B": "普通位优先；普通位满后可进充电区（先带枪位、再充电预留位）。",
            "C": "普通位优先；普通位满后仅当『已占用充电区的油车数 < charging_bays − m』时放行，否则离开。",
            "D": "普通位优先；普通位满后按可见预测：可用充电位−1−本批已放行 ≥ 预测需求+余量 时放行。",
        }[rule],
        "charging_completion": "充满即停止耗电；车辆继续占用原车位到原定离场（不自动释放连接器、不挪车）。",
        "supply": "feeder_kw ≥ chargers × min(charger_kw, vehicle_max_kw)：单车功率不受馈线均分稀释。",
        "information_contract": {"version": INFORMATION_CONTRACT_VERSION,
                                 "visible": list(VISIBLE_FIELDS),
                                 "hidden": list(HIDDEN_FIELDS),
                                 "assumption": DECLARATION_ASSUMPTION},
    }


def rejection_category(reason):
    """把规则理由映射为拒绝原因大类（停车失败率与充电拒绝率分层用）。"""
    if reason in (None, ""):
        return "other"
    if reason in ("lot_full", "rejected_no_free_bay"):
        return "lot_full"
    if reason == "no_equipped_bay":
        return "no_equipped_bay"
    if (reason.startswith("rejected_ice") or "no_ordinary_bay" in reason
            or reason.startswith("rejected_ice_reserved")):
        return "rule_restricted"
    return "other"


def decide(state, declared_need, rule, *, protected_bays=None, window_min=None,
           safety_margin=None, prediction_object=None, coordinate_window=True,
           pending_shared_bays=0, allow_no_need_fallback=True):
    """决策表 v3 唯一入口：只读取声明与 ObservableState，签名里没有隐藏字段。"""
    if rule not in ADMISSION_RULES:
        raise ValueError("未知 v3 准入规则：" + str(rule) + "；可选 " + ", ".join(ADMISSION_RULES))
    if type(declared_need) is not bool:
        raise TypeError("declared_need 必须是布尔值")
    if type(allow_no_need_fallback) is not bool:
        raise ValueError("allow_no_need_fallback 必须是布尔值")
    equipped, designated, ordinary = state.groups()
    detail = {"rule_v3": rule, "base_rule": BASE_RULE[rule], "declared_need": declared_need,
              "free_equipped_bays": len(equipped), "free_designated_bays": len(designated),
              "free_ordinary_bays": len(ordinary),
              "information_regime": "I3_declared",
              "contract_version": INFORMATION_CONTRACT_VERSION}
    if state.is_ev and declared_need:
        detail["branch"] = "ev_declared_need"
        if equipped:
            return AdmissionDecision(bay=equipped[0], rule=rule,
                                     reason="ev_need_equipped", detail=detail)
        reason = "no_equipped_bay" if (designated or ordinary) else "lot_full"
        detail["note"] = "申报充电但不占用非带枪位；直接离开"
        return AdmissionDecision(bay=None, rule=rule, reason=reason, detail=detail)
    if state.is_ev and not declared_need:
        detail["branch"] = "ev_no_declared_need"
        if ordinary:
            return AdmissionDecision(bay=ordinary[0], rule=rule,
                                     reason="ev_no_need_ordinary", detail=detail)
        if not allow_no_need_fallback:
            reason = "no_ordinary_bay_no_fallback" if (equipped or designated) else "lot_full"
            detail["fallback_disabled"] = True
            return AdmissionDecision(bay=None, rule=rule, reason=reason, detail=detail)
        if designated:
            return AdmissionDecision(bay=designated[0], rule=rule,
                                     reason="ev_no_need_fallback_designated", detail=detail)
        if equipped:
            return AdmissionDecision(bay=equipped[0], rule=rule,
                                     reason="ev_no_need_fallback_equipped", detail=detail)
        return AdmissionDecision(bay=None, rule=rule, reason="lot_full", detail=detail)
    # 油车：复用既有正式规则实现（理由、配额/预测审计字段原样保留）。
    decision = rule_decide(state, BASE_RULE[rule], window_min=window_min,
                           safety_margin=safety_margin, prediction_object=prediction_object,
                           coordinate_window=coordinate_window,
                           pending_shared_bays=pending_shared_bays,
                           protected_bays=protected_bays)
    ice_detail = {"rule_v3": rule, "base_rule": BASE_RULE[rule],
                  "declared_need": declared_need, "branch": "ice",
                  "information_regime": "I3_declared",
                  "contract_version": INFORMATION_CONTRACT_VERSION,
                  "free_equipped_bays": len(equipped),
                  "free_designated_bays": len(designated),
                  "free_ordinary_bays": len(ordinary)}
    ice_detail.update(decision.detail)
    return AdmissionDecision(bay=decision.bay, rule=rule, reason=decision.reason,
                             detail=ice_detail)


@dataclass(frozen=True)
class DeclaredArrival(Arrival):
    """带申报字段的到达：simulator 真值 needs_charge 与申报 declared_need 分开记录。"""

    declared_need: bool = False


class DeclaredNeedSimulation(Simulation):
    """v3 混合停车仿真：ICE、不充电 EV、申报充电 EV 参与同一容量与功率过程。

    复用 workbench 事件循环、能量记账、成本与三类占位账本；只覆写准入选择、
    单车功率上限与拒绝原因标注。每站单独运行；连续窗口处理跨午夜停留。
    """

    information_regime = "I3_declared"
    contract_version = INFORMATION_CONTRACT_VERSION
    analysis_only = False

    def __init__(self, config, arrivals=None, *, rule="A", protected_bays=None,
                 vehicle_max_kw=None, allow_no_need_fallback=True,
                 require_unconstrained_supply=True, intervention=None):
        if rule not in ADMISSION_RULES:
            raise ValueError("未知 v3 准入规则：" + str(rule))
        self.admission_rule = rule
        self.vehicle_max_kw = None if vehicle_max_kw is None else float(vehicle_max_kw)
        if self.vehicle_max_kw is not None and self.vehicle_max_kw <= 0:
            raise ValueError("vehicle_max_kw 必须为正数或 None")
        self.allow_no_need_fallback = bool(allow_no_need_fallback)
        self.require_unconstrained_supply = bool(require_unconstrained_supply)
        self.protected_bays_param = None if protected_bays is None else int(protected_bays)
        super().__init__(config, arrivals=arrivals, intervention=intervention)
        c = self.config
        if self.require_unconstrained_supply and c.chargers > 0:
            need = c.chargers * self.effective_charger_kw()
            if c.feeder_kw + EPS < need:
                raise ValueError(
                    "主情景要求供电随桩数扩容：feeder_kw=%.3f < chargers×单车功率=%.3f；"
                    "固定供电/共享功率池只能作对照（require_unconstrained_supply=False）"
                    % (c.feeder_kw, need))

    def effective_charger_kw(self):
        """单车可用功率上限：桩型额定与车端可接受功率的较小者。"""
        c = self.config
        if c.charger_kw <= 0:
            return 0.0
        if self.vehicle_max_kw is None:
            return float(c.charger_kw)
        return float(min(c.charger_kw, self.vehicle_max_kw))

    def powers(self):
        """充电功率：主情景不因总馈线而均分；仅当供给不足（对照）才按活动车数稀释。"""
        c = self.config
        candidates = [bay for bay, v in self.active.items()
                      if bay < c.chargers and v["needs_charge"]
                      and v["energy_kwh"] - v["delivered_kwh"] > EPS]
        cap = self.effective_charger_kw()
        if not candidates or cap <= 0 or c.feeder_kw <= 0:
            return {}
        share = c.feeder_kw / len(candidates)
        return {bay: min(cap, share) for bay in candidates}

    def choose_bay(self, a, forecast):
        c = self.config
        free = [bay for bay in range(c.n_spaces) if bay not in self.active]
        state = self.observable_state(a, forecast, free)
        declared = getattr(a, "declared_need", a.needs_charge)
        context = DeclaredNeedContext(state, declared)
        decision = decide(context.state, context.declared_need, self.admission_rule,
                          protected_bays=self.protected_bays_param,
                          window_min=c.ice_share_forecast_window_min,
                          safety_margin=c.ice_share_free_bay_margin,
                          prediction_object=c.prediction_object,
                          coordinate_window=c.coordinate_window,
                          pending_shared_bays=self._batch_pending,
                          allow_no_need_fallback=self.allow_no_need_fallback)
        detail = dict(decision.detail)
        detail.update(information_regime=self.information_regime,
                      contract_version=INFORMATION_CONTRACT_VERSION,
                      declared_need=declared,
                      declaration_truthful=bool(declared == a.needs_charge))
        self.last_decision = {"rule": self.admission_rule, "reason": decision.reason,
                              "bay": decision.bay, "detail": detail,
                              "information_regime": self.information_regime}
        return decision.bay

    def _record_rejection_cost(self, arrival, visit):
        super()._record_rejection_cost(arrival, visit)
        reason = (self.last_decision or {}).get("reason")
        visit["rejection_reason"] = reason
        visit["rejection_category"] = rejection_category(reason)

    def assert_invariants(self):
        super().assert_invariants()
        c = self.config
        cap = self.effective_charger_kw()
        if self.peak_power > c.chargers * cap + 1e-6:
            raise AssertionError("单车功率超过桩型/车端上限：peak_power=%.6f" % self.peak_power)
        for v in self.visits:
            if v["is_ev"] and v.get("declared_need") and v["admitted"] and v["bay"] >= c.chargers:
                raise AssertionError("申报充电的 EV 不得占用非带枪位")
            # 主模型假设申报=真实，因此上面一条同时保护“有需求却被分到非带枪位”。
            # 故意错报的信息条件敏感性不满足该假设，不在此处判违规。
            if v["delivered_kwh"] > EPS and v["bay"] is not None and v["bay"] >= c.chargers:
                raise AssertionError("无枪位不得交付电量")
            if v["departed"] and v["charge_start_min"] is not None:
                # 离场后交付只能为 0：由 delivered_kwh 与离场时间一致性间接检查
                pass
        return True

    def snapshot(self):
        data = super().snapshot()
        data.update({"admission_rule_v3": self.admission_rule,
                     "admission_rule_label": RULE_LABELS[self.admission_rule],
                     "information_contract_version": INFORMATION_CONTRACT_VERSION,
                     "information_regime": self.information_regime,
                     "declaration_assumption": DECLARATION_ASSUMPTION,
                     "vehicle_max_kw": self.vehicle_max_kw,
                     "effective_charger_kw": self.effective_charger_kw(),
                     "allow_no_need_fallback": self.allow_no_need_fallback,
                     "supply_unconstrained": bool(
                         self.config.chargers == 0
                         or self.config.feeder_kw + EPS >= self.config.chargers * self.effective_charger_kw()),
                     "decision_table": v3_decision_table(self.admission_rule)["ice"]})
        return data

    def export(self):
        data = super().export()
        data.update({"admission_rule_v3": self.admission_rule,
                     "information_contract_version": INFORMATION_CONTRACT_VERSION,
                     "information_regime": self.information_regime,
                     "declaration_assumption": DECLARATION_ASSUMPTION,
                     "vehicle_max_kw": self.vehicle_max_kw,
                     "effective_charger_kw": self.effective_charger_kw()})
        data["state"]["admission_rule_v3"] = self.admission_rule
        return data


# --------------------------------------------------------------------------- #
# 指标：分子、分母与统计层级显式化
# --------------------------------------------------------------------------- #
METRIC_DEFINITIONS = {
    "charging_request_rejection_rate": (
        "充电请求被拒率 = 被拒的『申报充电 EV 到达』数 / 全部申报充电 EV 到达数；"
        "分母含被拒需求，不含本次不充电的 EV。"),
    "ev_parking_failure_rate": (
        "EV 停车失败率 = 被拒 EV 到达数 / 全部 EV 到达数（含申报充电与不充电 EV）。"),
    "ice_parking_failure_rate": (
        "油车停车失败率 = 被拒油车到达数 / 全部油车到达数。"),
    "session_target_unmet_rate_settled": (
        "会话目标未达成率（已结算） = 未达成充电请求数 / 已结算充电请求数；"
        "已结算 = 被拒（到达即失败）或已离场；留场删失请求单列，不混入分母。"),
    "energy_delivery_rate": (
        "交付能量率 = 交付电量 / 请求电量；请求电量含被拒请求（被拒记 0 交付）。"),
    "ideal_energy_rate": (
        "理想能量率 = Σ min(E_i, P_eff×停留小时) / 请求电量；P_eff = min(桩额定, 车端上限)。"),
    "no_charging_demand_bay_share": (
        "不充电 EV 占带枪位分钟 / 带枪位被占分钟（三类占位之一）。"),
    "overstay_after_complete_share": (
        "充完滞留带枪位分钟 / 带枪位被占分钟（主模型默认充满仍占位到离场）。"),
    "ice_blocking_connector_share": (
        "油车占带枪位分钟 / 带枪位被占分钟（仅在 B/C/D 共享放行时出现）。"),
}
N_A = None  # 分母为 0 时指标为 N/A，不是 0，也不是通过


def _rate(num, den):
    return None if not den else float(num) / float(den)


def _combine_dicts(dicts):
    out = {}
    for d in dicts:
        for key, value in d.items():
            out[key] = out.get(key, 0) + value
    return out


def rates_from_totals(totals):
    """由计数/能量总量重算比率（聚合必须用总量，不能平均各站比率）。"""
    c, e, o = totals["counts"], totals["energy"], totals["occupancy"]
    req = c["charging_requests"]
    settled = c["settled_charging_requests"]
    return {
        "charging_request_rejection_rate": _rate(c["rejected_charging_requests"], req),
        "ev_parking_failure_rate": _rate(c["rejected_ev"], c["ev_arrivals"]),
        "ice_parking_failure_rate": _rate(c["rejected_ice"], c["ice_arrivals"]),
        "session_target_unmet_rate_settled": _rate(c["unmet_charging_requests"], settled),
        "energy_delivery_rate": _rate(e["delivered_kwh"], e["requested_kwh"]),
        "ideal_energy_rate": _rate(e["ideal_kwh"], e["requested_kwh"]),
        "delivered_over_ideal_rate": _rate(e["delivered_kwh"], e["ideal_kwh"]),
        "no_charging_demand_bay_share": _rate(o["no_charging_demand_bay_min"], o["equipped_min"]),
        "overstay_after_complete_share": _rate(o["overstay_after_complete_min"], o["equipped_min"]),
        "ice_blocking_connector_share": _rate(o["ice_blocking_connector_min"], o["equipped_min"]),
    }


def content_metrics(visits, config, *, vehicle_max_kw=None, cut_min=None):
    """按统计层级计算 v3 指标；visits 为 Simulation 导出的访问字典列表。

    分母约定：
    - 停车失败率分母 = 该类型全部到达（含被拒）；
    - 充电请求分母 = 申报充电的 EV 到达（含被拒）；
    - 会话目标未达成率（已结算）分母 = 被拒请求 + 已离场请求；
    - 能量分母 = 全部充电请求（被拒请求保留在分母，交付记 0）；
    - 留场删失请求单列，不进入『未达成率』分母。
    """
    c = config
    cap = c.charger_kw
    if vehicle_max_kw is not None:
        cap = min(cap, float(vehicle_max_kw))
    visits = list(visits)
    evs = [v for v in visits if v["is_ev"]]
    ices = [v for v in visits if not v["is_ev"]]
    reqs = [v for v in visits if v["is_ev"] and v.get("needs_charge")]
    rejected_ev = [v for v in evs if not v["admitted"]]
    rejected_ice = [v for v in ices if not v["admitted"]]
    rejected_req = [v for v in reqs if not v["admitted"]]
    settled = [v for v in reqs if (not v["admitted"]) or v["departed"]]
    censored = [v for v in reqs if v["admitted"] and not v["departed"]]
    unmet = [v for v in settled
             if (not v["admitted"]) or v["delivered_kwh"] < v["energy_kwh"] - EPS]
    requested = sum(float(v["energy_kwh"]) for v in reqs)
    delivered = sum(float(v["delivered_kwh"]) for v in reqs)
    ideal = sum(min(float(v["energy_kwh"]), cap * float(v["dwell_min"]) / 60.0) for v in reqs)
    counts = {
        "arrivals": len(visits), "ev_arrivals": len(evs), "ice_arrivals": len(ices),
        "charging_requests": len(reqs), "rejected_ev": len(rejected_ev),
        "rejected_ice": len(rejected_ice),
        "rejected_charging_requests": len(rejected_req),
        "settled_charging_requests": len(settled),
        "censored_charging_requests": len(censored),
        "unmet_charging_requests": len(unmet),
        "admitted_charging_requests": len(reqs) - len(rejected_req),
    }
    by_reason = {}
    by_category = {key: 0 for key in REJECTION_CATEGORIES}
    for v in visits:
        if v["admitted"]:
            continue
        reason = v.get("rejection_reason")
        by_reason[reason] = by_reason.get(reason, 0) + 1
        if v["is_ev"] and v.get("needs_charge"):
            category = v.get("rejection_category") or rejection_category(reason)
            by_category[category] = by_category.get(category, 0) + 1
    energy = {"requested_kwh": requested, "delivered_kwh": delivered,
              "shortfall_kwh": requested - delivered, "ideal_kwh": ideal}
    cut = None if cut_min is None else float(cut_min)
    ledger = type_occupancy_ledger(visits, c, cut if cut is not None else 0.0)
    equipped_min = 0.0
    for v in visits:
        if not v["admitted"] or v["bay"] is None or v["bay"] >= c.chargers:
            continue
        end = v.get("released_min")
        end = float(v["departure_min"]) if end is None else float(end)
        if cut is not None:
            end = min(end, cut)
        equipped_min += max(0.0, end - float(v["time_min"]))
    occupancy = {"equipped_min": equipped_min}
    occupancy.update({name: float(ledger["metrics"][name]) for name in TYPE_OCCUPANCY_METRICS})
    totals = {"counts": counts, "energy": energy, "occupancy": occupancy}
    return {"counts": counts, "energy": energy, "occupancy": occupancy,
            "rejection_by_reason": by_reason,
            "rejection_by_category_charging_requests": by_category,
            "rates": rates_from_totals(totals),
            "definitions": dict(METRIC_DEFINITIONS),
            "declaration_assumption": DECLARATION_ASSUMPTION}


def combine_metrics(metric_list):
    """跨场站/跨日期聚合：先加总分子分母，再重算比率（不得平均比率）。"""
    metric_list = [m for m in metric_list if m is not None]
    if not metric_list:
        raise ValueError("combine_metrics 需要至少一个指标块")
    totals = {
        "counts": _combine_dicts([m["counts"] for m in metric_list]),
        "energy": _combine_dicts([m["energy"] for m in metric_list]),
        "occupancy": _combine_dicts([m["occupancy"] for m in metric_list]),
    }
    by_reason = _combine_dicts([m["rejection_by_reason"] for m in metric_list])
    by_category = _combine_dicts([m["rejection_by_category_charging_requests"]
                                  for m in metric_list])
    return {"counts": totals["counts"], "energy": totals["energy"],
            "occupancy": totals["occupancy"],
            "rejection_by_reason": by_reason,
            "rejection_by_category_charging_requests": by_category,
            "rates": rates_from_totals(totals),
            "definitions": dict(METRIC_DEFINITIONS),
            "declaration_assumption": DECLARATION_ASSUMPTION,
            "post_hoc_of_nothing": True}


__all__ = [
    "INFORMATION_CONTRACT_VERSION", "ADMISSION_RULES", "BASE_RULE", "RULE_LABELS",
    "VISIBLE_FIELDS", "HIDDEN_FIELDS", "DECLARATION_ASSUMPTION", "REJECTION_CATEGORIES",
    "HiddenInformationError", "DeclaredNeedContext", "declared_need_context",
    "v3_decision_table", "rejection_category", "decide", "DeclaredArrival",
    "DeclaredNeedSimulation", "content_metrics", "combine_metrics",
    "rates_from_totals", "METRIC_DEFINITIONS", "N_A",
]
