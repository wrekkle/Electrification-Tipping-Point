"""E4 基线 B0/B1/B2 的可执行实现（R8-B）。

信息公平（PLAN §3.2 / DESIGN_MATRIX）：
- 三个基线都只读 rules.ObservableState 的可见字段（车型 is_ev、当前占用与资源、历史统计与预测），
  不使用 needs_charge（隐藏意愿）、真实离场时间或未来到达；因此标记 online_observable。
- 每个基线在输出里显式记录 information 标记；任何离线上界只出现在 offline_opt.py，
  并标注 offline_upper_bound_not_executable。

文献状态（任务要求：三种状态之一）：
- B0 FCFS / B1 固定配额：不涉及文献复现，literature_status=None。
- B2 文献改编：literature_status="规则改编"。
  * M07（笔记：literature/notes/M07-混合停车充电滚动分配与不准时.md）：借鉴"先分充电、后分停车"
    的分配次序与"临近到达前仍可调整"的滚动思想；本实现只把它落成在线准入次序 + 借用上限，
    未求解其 MIP/滚动优化模型 → 不是完整复现。
  * P26（笔记：literature/notes/P26-成本参数摘读.md）：借鉴"在线准入控制"的信息结构与决策时点。
  * P09（literature/INDEX.md 条目）：仅题名/索引层信息（准入与保留容量思想），
    具体条款 UNVERIFIED——未读全文、无精读笔记，不得声称复现其定价或准入定理。
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = Path(__file__).resolve().parent
for _p in (str(_ROOT), str(_ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.parking_lab.workbench.rules import candidates as rule_candidates
from apps.parking_lab.workbench.simulation import Simulation

BASELINE_NAMES = ("B0_FCFS", "B1_QUOTA", "B2_LITERATURE")

B2_DEFAULTS = {"window_min": 30.0, "borrow_share": 0.5, "safety_margin": 1.0}

BASELINE_META = {
    "B0_FCFS": {
        "label": "先到先服务（无排队、无车型区分）",
        "information": "online_observable",
        "literature_status": None,
        "definition": ("队列容量 0：到达时若无空闲车位立即拒绝（拒绝计入分母）；"
                       "有空位时按车位编号升序分配，不区分 EV/ICE，也不保护带枪位。"),
    },
    "B1_QUOTA": {
        "label": "固定配额/保护（p_share 保护带枪位）",
        "information": "online_observable",
        "literature_status": None,
        "definition": ("复用 rules.protected_quota 的可执行判定：EV 正常优先充电位；ICE 普通位不足时，"
                       "只有当前 ICE 占用带枪位数 < charging_bays - m 才可进入充电区，否则拒绝。"
                       "m 由训练集预注册（p_share × charging_bays，向上取整），测试集不调参。"),
    },
    "B2_LITERATURE": {
        "label": "文献改编：可再用枪位的滚动预留准入",
        "information": "online_observable",
        "literature_status": "规则改编",
        "literature_sources": {
            "M07": "先充电后停车次序 + 滚动调整思想（笔记已读要点；未复现其 MIP/滚动优化）",
            "P26": "在线准入控制的信息结构与决策时点（笔记为成本参数摘读，未复现其效用最大化模型）",
            "P09": "UNVERIFIED：仅索引层题名（准入与保留容量），未读全文/无精读笔记，不复现其定价定理",
        },
        "definition": ("EV：带枪位 → 充电预留位 → 普通位（先充电后停车的次序）。"
                       "ICE：先普通位；普通位不足时允许借用充电区，当且仅当"
                       "（a）当前 ICE 占用带枪位数 < floor(charging_bays × borrow_share)（硬借用上限），且"
                       "（b）free_charging_bays - 1 - pending - ceil(predicted_charge_arrivals(window)) >= safety_margin。"
                       "参数在训练集上一次性预注册，不在测试集调参。"),
    },
}


def b0_fcfs(state):
    """B0：FCFS。返回 (有序候选车位, 理由, 审计明细)。"""
    if not state.free_bays:
        return [], "rejected_no_free_bay", {"rule": "B0_FCFS", "queue_capacity": 0,
                                            "free_bays": 0}
    return list(state.free_bays), "fcfs_lowest_free_bay", {
        "rule": "B0_FCFS", "queue_capacity": 0, "free_bays": len(state.free_bays),
        "type_blind": True}


def b1_quota(state, *, protected_bays):
    """B1：固定配额/保护；直接复用正式规则 protected_quota 的同一实现。"""
    ordered, reason, detail = rule_candidates(state, "protected_quota",
                                              protected_bays=protected_bays)
    detail = dict(detail)
    detail.update({"rule": "B1_QUOTA", "protected_bays": protected_bays})
    return ordered, reason, detail


def b2_literature(state, *, window_min=None, borrow_share=None, safety_margin=None):
    """B2：文献改编的可再用枪位滚动预留准入（在线可执行，只读可见状态）。"""
    window = B2_DEFAULTS["window_min"] if window_min is None else float(window_min)
    share = B2_DEFAULTS["borrow_share"] if borrow_share is None else float(borrow_share)
    margin = B2_DEFAULTS["safety_margin"] if safety_margin is None else float(safety_margin)
    if not 0.0 <= share <= 1.0:
        raise ValueError("borrow_share 必须在 [0, 1] 内")
    if window < 0 or margin < 0:
        raise ValueError("window_min / safety_margin 必须非负")
    equipped, designated, ordinary = state.groups()
    if state.is_ev:
        ordered = list(equipped) + list(designated) + list(ordinary)
        return ordered, "ev_charging_first", {"rule": "B2_LITERATURE", "stage": "ev_first"}
    if ordinary:
        return (list(ordinary) + list(equipped) + list(designated),
                "ice_ordinary_first", {"rule": "B2_LITERATURE", "stage": "ice_ordinary"})
    free_charging = len(equipped) + len(designated)
    predicted = (state.arrival_rate_per_hour / 60.0 * state.p_ev * state.p_charge_given_ev
                 * window)
    pending = 0  # 同批次已放行 ICE 的占用由调用方通过 ice_charging_bays 反映
    borrow_cap = int(math.floor(state.charging_bays * share + 1e-12))
    occupied = state.ice_charging_bays
    slack = free_charging - 1 - pending - math.ceil(predicted)
    detail = {"rule": "B2_LITERATURE", "stage": "ice_borrow_gate",
              "window_min": window, "borrow_share": share, "safety_margin": margin,
              "predicted_charge_arrivals": predicted, "borrow_cap": borrow_cap,
              "ice_charging_bays": occupied, "free_charging_bays": free_charging,
              "slack_after_borrow": slack}
    if occupied is None:
        detail["fallback"] = "ice_charging_bays_unavailable_reject"
        return [], "rejected_unknown_occupancy", detail
    if occupied >= borrow_cap:
        return [], "rejected_borrow_cap", detail
    if free_charging <= 0:
        return [], "rejected_no_free_charging_bay", detail
    if slack < margin:
        return [], "rejected_ev_reserve", detail
    return list(equipped) + list(designated), "ice_borrowed_by_gate", detail


def decide(baseline, state, *, protected_bays=None, b2_params=None):
    """统一入口：按基线名返回 (有序候选车位, 理由, 审计明细)。"""
    if baseline not in BASELINE_NAMES:
        raise ValueError("未知基线：%r；可选 %s" % (baseline, ", ".join(BASELINE_NAMES)))
    if baseline == "B0_FCFS":
        return b0_fcfs(state)
    if baseline == "B1_QUOTA":
        if protected_bays is None:
            raise ValueError("B1_QUOTA 需要 protected_bays（训练集预注册的 m）")
        return b1_quota(state, protected_bays=protected_bays)
    params = dict(B2_DEFAULTS)
    params.update(b2_params or {})
    return b2_literature(state, **params)


class BaselineSimulation(Simulation):
    """把 B0/B1/B2 接到现有事件引擎上（子类只覆写 choose_bay，不改动已有模块）。

    config.policy 只作载体：B0/B2 需允许 ICE 进入充电区，故传入 π1（full_open_ice_first）；
    准入决策由基线函数给出，last_decision 记录 baseline 名称与理由，便于审计。
    """

    def __init__(self, config, baseline, arrivals=None, *, protected_bays=None,
                 b2_params=None):
        if baseline not in BASELINE_NAMES:
            raise ValueError("未知基线：%r" % (baseline,))
        super().__init__(config, arrivals=arrivals)
        self.baseline = baseline
        self.quota_bays = protected_bays if protected_bays is not None else config.protected_bays
        self.b2_params = dict(B2_DEFAULTS)
        self.b2_params.update(b2_params or {})

    def choose_bay(self, a, forecast):
        c = self.config
        free = [bay for bay in range(c.n_spaces) if bay not in self.active]
        state = self.observable_state(a, forecast, free)
        ordered, reason, detail = decide(self.baseline, state,
                                         protected_bays=self.quota_bays,
                                         b2_params=self.b2_params)
        bay = ordered[0] if ordered else None
        self.last_decision = {"rule": None, "baseline": self.baseline, "reason": reason,
                              "bay": bay, "detail": detail, "legacy": False}
        return bay
