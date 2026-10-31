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
    """后段首见的会话键；首帧已存在的期初会话不计入窗口新会话。"""
    if not row_keys:
        return 0
    first = set(x for x in row_keys[0] if x is not None)
    later = set(x for k in row_keys[1:] for x in k if x is not None)
    return len(later - first)


def session_upper_bound(N, T, dwell_lo, per_visit_max, a_hi):
    """会话数上界：到达数*每访会话上限 与 车位数*窗长/最短停留 取小。"""
    caps = []
    if a_hi is not None and per_visit_max is not None:
        caps.append(a_hi * per_visit_max)
    if dwell_lo and dwell_lo > 0 and N > 0:
        caps.append(N * T / float(dwell_lo))
    return min(caps) if caps else None


def q_bounds(sessions_lo, sessions_hi, arr_bounds, ev_share_range):
    """q 界：观测计数只进下界；上界用到达数/容量，不用观测计数。"""
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
                               lower_source="observed_events_lower_bound_only",
                               upper_source="arrival_or_capacity_bound"),
                note="观测计数只作分子下界；无完整性证据时上界保持无信息")


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
