"""信息条件接口（第六轮 A）：I0 现实规则 / I1 analysis_only。

契约（CONTRACT §2）
-------------------
- I0：正式规则可见信息与现有实现完全一致（车型、当前占用/资源、历史统计与预测；
  不见 needs_charge、能量、真实离场、未来到达）。I0 直接使用未修改的 Simulation
  与 rules.py，数值行为不变。
- I1：analysis_only=True，仅额外把“当次到访车辆的充电意愿 needs_charge”暴露给
  标记为 analysis-only 的决策策略；不暴露能量、真实离场时间、未来到达。
- 所有车辆仍停车；原始到达、停留、需求、能量保持一致；信息只改变决策可用信息与分配。
- 输出元数据顶层必须含 information_regime / analysis_only / policy_kind / can_mimic_I0。

本模块不修改 simulation.py / rules.py / config.py：I1 用 Simulation 子类
(RegimeSimulation) 覆写 choose_bay，I0 走原类，因此默认数值逐字节不变。

I1 若只实现启发式（本模块的 AnalysisHeuristicPolicy），报告只能写“算法比较/信息
上界示例”，不得写“全局最优”。
"""
from __future__ import annotations

from dataclasses import dataclass

from .rules import ObservableState, candidates as rule_candidates
from .simulation import Simulation

I0 = "I0"
I1 = "I1"
REGIMES = (I0, I1)

# I1 唯一额外可见字段；不得增加（能量/离场时间/未来到达都属越权）。
ANALYSIS_ONLY_FIELDS = ("needs_charge",)
FORBIDDEN_FIELDS = ("energy_kwh", "departure_min", "dwell_min", "future_arrivals",
                    "delivered_kwh", "soc", "battery_kwh")

POLICY_KINDS = ("real_rule", "analysis_heuristic")


@dataclass(frozen=True)
class AnalysisGrant:
    """analysis_only 授权凭证：只允许 needs_charge 一个字段，不接受扩展。"""

    analysis_only: bool = True
    fields: tuple = ANALYSIS_ONLY_FIELDS

    def __post_init__(self):
        if self.analysis_only is not True:
            raise PermissionError("analysis-only 授权必须显式 analysis_only=True")
        if tuple(self.fields) != ANALYSIS_ONLY_FIELDS:
            raise PermissionError("analysis-only 授权字段只能是 %r，收到 %r"
                                  % (ANALYSIS_ONLY_FIELDS, tuple(self.fields)))


ANALYSIS_GRANT = AnalysisGrant()


class RealRuleContext:
    """I0 现实规则上下文：只有 ObservableState；needs_charge 等隐藏字段不可读。"""

    __slots__ = ("state",)
    allowed_fields = ()

    def __init__(self, state):
        if not isinstance(state, ObservableState):
            raise TypeError("state 必须是 rules.ObservableState")
        object.__setattr__(self, "state", state)

    def __getattr__(self, name):
        if name in ANALYSIS_ONLY_FIELDS or name in FORBIDDEN_FIELDS:
            raise PermissionError("现实规则上下文不可见字段：%s" % name)
        raise AttributeError(name)

    def to_dict(self):
        return {"information_regime": I0, "analysis_only": False,
                "allowed_fields": list(self.allowed_fields)}


class AnalysisContext(RealRuleContext):
    """I1 analysis-only 上下文：在现实规则上下文上仅增加 needs_charge。"""

    __slots__ = ("needs_charge",)
    allowed_fields = ANALYSIS_ONLY_FIELDS

    def __init__(self, state, needs_charge, grant=None):
        super().__init__(state)
        if grant is not ANALYSIS_GRANT:
            raise PermissionError("analysis-only 上下文必须持有 ANALYSIS_GRANT 授权（同一凭证）")
        if type(needs_charge) is not bool:
            raise TypeError("needs_charge 必须是布尔值")
        object.__setattr__(self, "needs_charge", needs_charge)

    def to_dict(self):
        return {"information_regime": I1, "analysis_only": True,
                "allowed_fields": list(self.allowed_fields),
                "needs_charge": self.needs_charge}


def real_rule_context(state):
    return RealRuleContext(state)


def analysis_context(state, needs_charge, grant=None):
    return AnalysisContext(state, needs_charge, ANALYSIS_GRANT if grant is None else grant)


class Policy:
    """分析用决策策略基类：只接受自己的授权上下文。"""

    name = "base"
    policy_kind = "analysis_heuristic"
    information_regime = I1
    analysis_only = True
    can_mimic_I0 = False
    context_type = AnalysisContext

    def __init__(self, base_rule="dedicated_by_type"):
        if base_rule not in ("dedicated_by_type", "full_open_ice_first",
                             "predictive_shared_ice_first", "protected_quota"):
            raise ValueError("未知基础规则：" + str(base_rule))
        self.base_rule = base_rule

    def require_context(self, context):
        if not isinstance(context, self.context_type):
            raise PermissionError(
                "%s 只接受 %s（analysis_only=True）；收到 %s"
                % (self.name, self.context_type.__name__, type(context).__name__))
        if context.state is None:  # pragma: no cover - 防御
            raise ValueError("上下文缺少 state")
        return context

    def choose(self, context):  # pragma: no cover - 抽象
        raise NotImplementedError

    def metadata(self):
        return {"information_regime": self.information_regime,
                "analysis_only": self.analysis_only,
                "policy_kind": self.policy_kind,
                "policy_name": self.name,
                "base_rule": self.base_rule,
                "can_mimic_I0": self.can_mimic_I0}


class MimicI0Policy(Policy):
    """I1 的“模仿 I0”策略：决策规则与 base_rule 完全相同，只用可见状态。"""

    name = "mimic_i0"
    can_mimic_I0 = True
    policy_kind = "analysis_heuristic"

    def choose(self, context):
        context = self.require_context(context)
        ordered, reason, detail = rule_candidates(context.state, self.base_rule)
        detail = dict(detail)
        detail.update(analysis_only=True, information_regime=I1,
                      policy_name=self.name, needs_charge_visible=True,
                      needs_charge_used=False,
                      note="授权可见 needs_charge 但本策略不读取，用于验证与 I0 完全一致")
        return ordered, reason, detail


class AnalysisHeuristicPolicy(Policy):
    """I1 启发式：用当次到访的充电意愿调整电车车位次序。

    - 需要充电的电车：带枪位 → 充电预留位 → 普通位（与 π0/π1 相同）；
    - 不需要充电的电车：普通位 → 带枪位 → 充电预留位（把连接器留给要充电的车）；
    - 油车：完全沿用 base_rule（π0 只能普通位；π1 普通位不足时可进充电区）。
    仍是启发式算法比较，不是全局最优；所有车辆仍停车，只改分配次序。
    """

    name = "needs_charge_priority"
    can_mimic_I0 = False

    def choose(self, context):
        context = self.require_context(context)
        state = context.state
        if not state.is_ev:
            ordered, reason, detail = rule_candidates(state, self.base_rule)
            detail = dict(detail)
            detail.update(analysis_only=True, information_regime=I1,
                          policy_name=self.name, needs_charge_visible=True,
                          needs_charge_used=False, info_branch="ice_delegate_base_rule")
            return ordered, reason, detail
        equipped, designated, ordinary = state.groups()
        if context.needs_charge:
            ordered = list(equipped) + list(designated) + list(ordinary)
            reason = "ev_charge_intent_connector_first"
            branch = "ev_needs_charge"
        else:
            ordered = list(ordinary) + list(equipped) + list(designated)
            reason = "ev_no_charge_intent_ordinary_first"
            branch = "ev_no_charge_intent"
        detail = {"rule": self.base_rule, "analysis_only": True,
                  "information_regime": I1, "policy_name": self.name,
                  "needs_charge_visible": True, "needs_charge_used": True,
                  "info_branch": branch, "needs_charge": context.needs_charge,
                  "free_equipped_bays": len(equipped),
                  "free_designated_bays": len(designated),
                  "free_ordinary_bays": len(ordinary)}
        return ordered, reason, detail


def make_policy(kind="needs_charge_priority", base_rule="dedicated_by_type"):
    if kind in ("heuristic", AnalysisHeuristicPolicy.name):
        return AnalysisHeuristicPolicy(base_rule)
    if kind in ("mimic_i0", "mimic", "MimicI0Policy"):
        return MimicI0Policy(base_rule)
    raise ValueError("未知 I1 策略：" + str(kind))


def metadata(regime, policy=None):
    """输出顶层元数据（JSON 可直接使用）。"""
    if regime not in REGIMES:
        raise ValueError("未知信息条件：" + str(regime))
    if regime == I0:
        return {"information_regime": I0, "analysis_only": False,
                "policy_kind": "real_rule", "policy_name": "real_rules",
                "can_mimic_I0": True,
                "visible_fields": ["is_ev", "free_bays", "n_spaces", "charging_bays",
                                   "chargers", "arrival_rate_per_hour", "p_ev",
                                   "p_charge_given_ev", "observed_departures"],
                "hidden_fields": list(ANALYSIS_ONLY_FIELDS) + list(FORBIDDEN_FIELDS)}
    if policy is None:
        raise ValueError("I1 需要显式策略实例")
    if not isinstance(policy, Policy):
        raise TypeError("I1 策略必须是 info_regimes.Policy")
    if policy.information_regime != I1 or policy.analysis_only is not True:
        raise PermissionError("I1 策略必须标记 information_regime=I1 / analysis_only=True")
    data = policy.metadata()
    data["hidden_fields"] = list(FORBIDDEN_FIELDS)
    data["visible_fields"] = ["is_ev", "free_bays", "n_spaces", "charging_bays",
                              "chargers", "arrival_rate_per_hour", "p_ev",
                              "p_charge_given_ev", "observed_departures", "needs_charge"]
    return data


class RegimeSimulation(Simulation):
    """I1 仿真：只在选择车位时读取 analysis-only 上下文；其余事件逻辑继承不变。"""

    def __init__(self, config, arrivals=None, policy=None, intervention=None):
        super().__init__(config, arrivals=arrivals, intervention=intervention)
        if policy is None:
            raise ValueError("RegimeSimulation 需要 I1 策略")
        if not isinstance(policy, Policy):
            raise TypeError("policy 必须是 info_regimes.Policy")
        if policy.analysis_only is not True:
            raise PermissionError("RegimeSimulation 只接受 analysis_only=True 的策略")
        self.info_policy = policy
        self.information_regime = I1
        self.analysis_only = True
        self.policy_kind = policy.policy_kind
        self.can_mimic_I0 = bool(policy.can_mimic_I0)

    def choose_bay(self, a, forecast):
        c = self.config
        free = [bay for bay in range(c.n_spaces) if bay not in self.active]
        state = self.observable_state(a, forecast, free)
        context = AnalysisContext(state, a.needs_charge, ANALYSIS_GRANT)
        ordered, reason, detail = self.info_policy.choose(context)
        detail = dict(detail)
        detail.update(information_regime=I1, analysis_only=True,
                      policy_kind=self.policy_kind, policy_name=self.info_policy.name)
        bay = ordered[0] if ordered else None
        self.last_decision = {"rule": self.info_policy.base_rule, "reason": reason,
                              "bay": bay, "detail": detail,
                              "information_regime": I1, "analysis_only": True}
        return bay

    def export(self):
        payload = super().export()
        payload["state"].update(metadata(I1, self.info_policy))
        payload["information_regime"] = I1
        payload["analysis_only"] = True
        payload["policy_kind"] = self.policy_kind
        payload["can_mimic_I0"] = self.can_mimic_I0
        return payload
