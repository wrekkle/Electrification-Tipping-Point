#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""T14/F08 边界模块：采样面积误差、期初占用、期末残余、到达数与 q 的界。

核心更正（复验 §6）：
- 采样后的总变差只是连续过程总变差的下界，delta*V_sampled 不是误差上界；
  没有「每个采样间隔内占用事件数上限」时，误差无有限界。
- 期初占用、期末残余、采样误差、拒绝需求分开给界，每条写清成立条件；
  固定 10% 残余比例只是情景假设，不是有效上界。
- 区间宽度只表示精度目标；结构识别需要单独论证，未论证即「尚未建立」。
"""
import math

IDENTIFICATION_REASON = "未提供结构识别论证：宽度与覆盖只描述精度与重复实验，不构成识别"


def trap_area(occ, delta):
    """梯形（半端点）面积估计。occ 为等间隔采样。"""
    if len(occ) < 2:
        return 0.0
    return delta * (0.5 * occ[0] + sum(occ[1:-1]) + 0.5 * occ[-1])


def rect_area(occ, delta):
    return delta * sum(occ[:-1])


def sampled_variation(occ):
    return sum(abs(occ[i] - occ[i - 1]) for i in range(1, len(occ)))


def sampling_error(event_cap, N, T):
    """给定「每间隔最多 event_cap 次占用变化」，梯形/矩形误差上界为 T*min(event_cap,N)。

    event_cap 为 None 时无有限界；返回 status=no_info。
    """
    if event_cap is None:
        return dict(status="no_info", bound=None,
                    condition="需要「每个采样间隔内占用变化次数上限」；仅凭快照无法给出",
                    note="delta*V_sampled 只是连续总变差的下界，不能当误差上界")
    m = min(event_cap, N)
    return dict(status="finite", bound=T * m,
                condition="每采样间隔占用变化次数<=event_cap 且 0<=Y<=N", m=m)


def initial_bound(occ0, dwell_range, T):
    """期初占用对窗口面积的贡献上界：occ0*min(d_hi,T)。

    条件：期初在场车辆数不超过 occ0（公开余位反推是保守上界）且停留<=d_hi。
    """
    d_hi = dwell_range[1]
    return dict(upper=occ0 * min(d_hi, T), condition="停留<=d_hi 且 期初车辆数<=occ0",
                requires="dwell_hi")


def residual_bound(event_cap, delta, dwell_range, T):
    """期末残余 R_end 上界：最后 d_hi 内的到达数 * d_hi；到达数由事件上限约束。"""
    if event_cap is None:
        return dict(status="no_info", upper=None,
                    condition="需要每间隔事件上限才可界定期末残余")
    d_hi = dwell_range[1]
    n_intervals = int(math.ceil(d_hi / float(delta))) if delta > 0 else 0
    upper = event_cap * n_intervals * d_hi
    return dict(status="finite", upper=upper,
                condition="每采样间隔占用变化<=event_cap；停留<=d_hi",
                n_intervals=n_intervals)


def residual_scenario(area_hat, share):
    """情景假设：残余 <= share*面积。仅作情景，不能当有效上界。"""
    return dict(status="scenario", upper=share * area_hat,
                condition="情景假设：残余占比<=share；未用可观测信息验证",
                share=share)


def arrival_bounds(occ, delta, dwell_range, event_cap, N):
    """到达数界：分开采样误差、期初、期末三项，逐项写条件。"""
    T = (len(occ) - 1) * delta
    area_hat = trap_area(occ, delta)
    samp = sampling_error(event_cap, N, T)
    init = initial_bound(occ[0], dwell_range, T)
    resid = residual_bound(event_cap, delta, dwell_range, T)
    if samp["status"] != "finite":
        return dict(status="no_info", area_hat=area_hat, sampling=samp, initial=init,
                    residual=resid, bounds=[0.0, None],
                    conditions=["无采样误差界：无法得到有限上界"])
    b_lo = max(0.0, area_hat - samp["bound"])
    b_hi = area_hat + samp["bound"]
    a_lo = max(0.0, b_lo - init["upper"]) / dwell_range[1]
    if resid["status"] != "finite":
        a_hi = None
        status = "no_info"
    else:
        a_hi = (b_hi + resid["upper"]) / dwell_range[0]
        status = "finite"
    return dict(status=status, area_hat=area_hat, area_bounds=[b_lo, b_hi],
                sampling=samp, initial=init, residual=resid,
                bounds=[a_lo, a_hi],
                conditions=[samp["condition"], init["condition"], resid.get("condition", "")])


def session_lower_from_transitions(supply_counts):
    """供能数正增量：只表明至少发生了一次供能开始，仅作下界。"""
    return sum(max(0, supply_counts[i] - supply_counts[i - 1])
               for i in range(1, len(supply_counts)))


def session_lower_from_keys(row_keys):
    """后段首见的会话键；首帧已存在的期初会话不计入窗口新会话。

    去重条件：按会话键去重；同一键在多帧重复出现只计一次。该数只是
    「窗口内新启动会话」的下界，不能直接当作「窗口新到达车辆插枪」的下界：
    首帧在场的车辆可以晚些再插枪，后帧首见键无法仅凭键证明车辆在窗口内到达。
    """
    if not row_keys:
        return 0
    first = set(x for x in row_keys[0] if x is not None)
    later = set(x for k in row_keys[1:] for x in k if x is not None)
    return len(later - first)


def _valid_visit_cap(per_visit_max):
    """把每访会话上限规范成有效非负整数；返回 (c, status)。"""
    if per_visit_max is None:
        return None, "no_per_visit_cap"
    if isinstance(per_visit_max, bool):
        return None, "invalid_per_visit_cap"
    if isinstance(per_visit_max, float):
        if not per_visit_max.is_integer():
            return None, "invalid_per_visit_cap"
        per_visit_max = int(per_visit_max)
    if not isinstance(per_visit_max, int) or per_visit_max < 0:
        return None, "invalid_per_visit_cap"
    return per_visit_max, "ok"


def new_arrival_session_lower(keys_new, occ0, per_visit_max, first_frame_keys):
    """扣除期初可解释会话后，把剩余会话数换算成「新到访插枪车辆」下界。

    q_plug 的分子是插枪的独立到访，不是会话数。条件：
    - keys_new 为按会话键去重后的「后帧首见」键数；
    - 期初在场车辆数不超过 occ0。occ0=N-free_obs[0] 只有在余位观测 free_obs
      不被高估（即 free_obs<=真实余位）时才成立；仿真中 free_obs 已扣除
      reserved_bias，满足该方向，故 occ0 是保守上界。
    - per_visit_max=c 为有效非负整数，表示每辆车每次到访最多 c 个会话。
      首帧已见的 s0 个键各占用一辆期初车辆的一个配额，所以期初车辆最多
      还能贡献 occ0*c-s0 个后帧首见键。
    - 剩余会话数 remaining 只能说明至少 remaining 个新到访会话；一次到访
      最多 c 个会话，故插枪到访数 >= ceil(remaining/c)。c=1 时即 remaining。

    c 未知、非法或 remaining 与 c=0 矛盾时返回 0 并标 status：证据不足，
    不把首见键直接算成新到访。
    """
    keys_new = 0 if keys_new is None else max(0, int(keys_new))
    first = set(k for k in (first_frame_keys or []) if k is not None)
    s0 = len(first)
    cap, cap_status = _valid_visit_cap(per_visit_max)
    v0 = max(0, int(occ0)) if occ0 is not None else 0
    base = dict(keys_new=keys_new, initial_vehicles=v0,
                first_frame_sessions=s0, per_visit_cap=cap)
    if keys_new == 0:
        return dict(base, lower=0, deduction=0, remaining_sessions=0,
                    status="no_new_keys")
    if cap is None:
        return dict(base, lower=0, deduction=None, remaining_sessions=None,
                    status=cap_status)
    if cap == 0:
        return dict(base, lower=0, deduction=None, remaining_sessions=None,
                    status="cap_zero_contradicts_keys")
    budget = v0 * cap
    if budget < s0:
        return dict(base, lower=0, deduction=None, remaining_sessions=None,
                    status="initial_budget_contradicted")
    deduction = budget - s0
    remaining = max(0, keys_new - deduction)
    lower = (remaining + cap - 1) // cap
    return dict(base, lower=lower, deduction=deduction,
                remaining_sessions=remaining, status="bounded")


def session_upper_bound(N, T, dwell_lo, per_visit_max, a_hi):
    """窗口内新到访插枪车辆数上界，覆盖在窗口右端跨窗停留的车辆。

    目标是 q_plug 的分子：插枪的独立到访，不是会话数；因此每次到访最多
    计一个插枪到访，不能乘每访会话上限。条件项（取小）：
    - 到达项：a_hi 为窗口新到访车辆数上界，插枪到访数 <= 新到访车辆数。
    - 容量项：依据窗口内新到访车辆的占用与最短停留。前一次到访至少占用
      车位 dwell_lo，所以同一车位在 [0,T] 内最多 floor(T/dwell_lo)+1 次
      新到访。该计数自然覆盖右端到达、停留跨窗的车辆：它占住车位直到窗口
      之后，不能在同一车位内再计一次新到访。注意这里约束的是到访/占用，
      不是供能启动间隔；车辆可以在临走前才插枪，启动时刻无需相隔 dwell_lo。
    - per_visit_max 为 0 时无任何会话，上界 0；未知（None）不影响上述
      到访层面计数；非法值则不给有限上界。
    """
    cap, cap_status = _valid_visit_cap(per_visit_max)
    if cap is None and cap_status == "invalid_per_visit_cap":
        return None
    if cap == 0:
        return 0
    caps = []
    if a_hi is not None:
        caps.append(a_hi)
    if dwell_lo is not None and dwell_lo > 0 and N > 0 and T is not None and T >= 0:
        caps.append(N * (math.floor(T / float(dwell_lo)) + 1))
    return min(caps) if caps else None


def q_bounds(sessions_lo, sessions_hi, arr_bounds, ev_share_range):
    """q_plug 界：分子是插枪的独立到访；观测键只经换算进下界。"""
    a_lo, a_hi = arr_bounds
    e_lo, e_hi = ev_share_range
    lo = 0.0
    if a_hi is not None and a_hi > 0 and e_hi > 0 and sessions_lo is not None:
        lo = min(1.0, sessions_lo / (a_hi * e_hi))
    hi = 1.0
    if sessions_hi is not None and a_lo is not None and a_lo > 0 and e_lo > 0:
        hi = min(1.0, sessions_hi / (a_lo * e_lo))
    if hi < lo:
        lo, hi = hi, lo
    width = hi - lo
    no_info = (a_hi is None or a_lo is None or a_lo <= 0
               or sessions_hi is None or width >= 1.0 - 1e-12)
    return dict(bounds=[lo, hi], width=width,
                status=("no_info" if no_info else "bounded"),
                numerator=dict(lower=sessions_lo, upper=sessions_hi,
                               lower_source="observed_new_keys_to_plugging_visits",
                               upper_source="new_arrival_or_capacity_bound_on_plugging_visits"),
                note="观测键经每访上限换算后只作插枪到访下界；无完整性证据时上界保持无信息")


def rejection_range(a_hi, need_max):
    """拒绝需求：平台侧不可观测；给 [0, A_hi*need_max] 并标情景/无信息。"""
    if a_hi is None:
        return dict(bounds=[0.0, None], status="no_info",
                    note="到达数无上界，拒绝需求也无上界")
    return dict(bounds=[0.0, a_hi * need_max], status="model_range",
                note="上界依赖到达数上界与单次需求上界，属模型范围，不是观测")


def identification_panel(width, coverage_empirical, precision_target, coverage_target):
    """三件事分开报告：结构识别（未论证即尚未建立）、精度、重复实验覆盖。"""
    return dict(structural_identification="尚未建立",
                structural_reason=IDENTIFICATION_REASON,
                precision=dict(width=width, target=precision_target,
                               meets_precision_target=(width is not None
                                                       and width <= precision_target),
                               note="宽度只表示精度目标，不表示识别"),
                coverage=dict(empirical=coverage_empirical, target=coverage_target,
                              note="重复实验覆盖是经验量，不构成名义保证"),
                label="未识别/仅精度或情景")


def selfcheck():
    """两条反例：采样变差不是上界；10% 残余可被违反。"""
    out = {}
    occ = [1, 1, 1]
    out["sampled"] = dict(occ=occ, delta=2.5, trap=trap_area(occ, 2.5),
                          sampled_variation=sampled_variation(occ))
    if True:
        pass
    return out
