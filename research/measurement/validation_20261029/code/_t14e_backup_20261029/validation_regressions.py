# -*- coding: utf-8 -*-
"""T14 边界/会话回归与 F08 判据（从 run_validation_t14.py 机械拆分）。"""
from validation_common import BND, PREREG, LEVELS, estimate

def _reg(rid, name, observed, expected, ok):
    d = dict(id=rid, name=name, observed=observed, expected=expected,
             outcome="PASS" if ok else "FAIL")
    d["pass"] = bool(ok)
    return d


def _get(d, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _row(t, sup=1, free=0, chg=None):
    return dict(t=t, free_obs=free, n_supply=sup, n_idle=0, n_fault=0,
                stale_flag=False, chg=(chg or []))


def _mk_view(level, rows, N, delta, H, days=1, **over):
    A = dict(PREREG["assumptions"])
    A.update(over)
    return dict(level=level, delta=delta, H=H, N=N, days=days,
                rows=rows, assumptions=A)


def f08_regressions():
    """F08 采样/识别/残余/无信息反例。"""
    out = []
    occ = [1, 1, 1]
    delta = 2.5
    true_area = 2.0
    trap = BND.trap_area(occ, delta)
    legacy = delta * BND.sampled_variation(occ)
    no_cap = BND.sampling_error(None, 80, 5.0)
    with_cap = BND.sampling_error(2, 80, 5.0)
    out.append(_reg(
        "R1-sampling-area", "采样变差不是连续总变差上界",
        dict(trap=trap, true_area=true_area, legacy_bound=legacy,
             legacy_holds=(abs(trap - true_area) <= legacy),
             no_cap_status=no_cap["status"], cap2_bound=with_cap["bound"]),
        dict(trap=5.0, legacy_holds=False, no_cap_status="no_info"),
        abs(trap - 5.0) < 1e-9 and legacy == 0.0
        and not (abs(trap - true_area) <= legacy)
        and no_cap["status"] == "no_info"
        and abs(trap - true_area) <= with_cap["bound"]))
    panel = BND.identification_panel(0.1, 0.0,
                                     PREREG["assumptions"]["precision_target"],
                                     PREREG["assumptions"]["coverage_target"])
    out.append(_reg(
        "R2-point-identification", "宽度只表示精度，不表示识别",
        dict(width=0.1, coverage=0.0,
             structural=panel["structural_identification"],
             precision_met=panel["precision"]["meets_precision_target"]),
        dict(structural="尚未建立", precision_met=True),
        panel["structural_identification"] == "尚未建立"
        and panel["precision"]["meets_precision_target"]))
    scen = BND.residual_scenario(1.0, PREREG["assumptions"]["residual_share"])
    out.append(_reg(
        "R3-residual-scenario", "10% 残余是情景假设而非上界",
        dict(area=1.0, residual=30.0, scenario_upper=scen["upper"],
             violates=(30.0 > scen["upper"])),
        dict(status="scenario", violates=True),
        scen["status"] == "scenario" and 30.0 > scen["upper"]))
    arr = BND.arrival_bounds([1, 1, 1], 2.5, [30.0, 180.0], None, 80)
    qb = BND.q_bounds(10, None, arr["bounds"], [0.30, 0.42])
    out.append(_reg(
        "R4-no-info", "缺事件上限时给无信息界而不是零误差",
        dict(A_bounds=arr["bounds"], A_status=arr["status"],
             q_bounds=qb["bounds"], q_status=qb["status"]),
        dict(A_upper=None, q_upper=1.0, q_status="no_info"),
        arr["status"] == "no_info" and arr["bounds"][1] is None
        and qb["status"] == "no_info" and qb["bounds"][1] == 1.0))
    init = BND.initial_bound(1, [30.0, 180.0], 840.0)
    contrib = min(400.0, 840.0)
    out.append(_reg(
        "R5-initial-condition", "期初上界的条件（停留<=d_hi）",
        dict(bound=init["upper"], true_contrib=contrib,
             holds=(contrib <= init["upper"])),
        dict(holds=False), contrib > init["upper"]))
    rb = BND.residual_bound(3, 5.0, [30.0, 180.0], 840.0)
    out.append(_reg(
        "R6-residual-bound", "给事件上限后期末残余有有限界",
        dict(status=rb["status"], upper=rb["upper"]),
        dict(status="finite"),
        rb["status"] == "finite" and rb["upper"] is not None))
    return out


def session_regressions():
    """会话分子界：周转、漏会话、期初、去重、无信息。"""
    out = []
    # R13 供能数不变但周转（根复验 §8 反例形状）
    rows = [_row(5 * i, sup=1, free=0) for i in range(101)]
    v = _mk_view("L1", rows, 10, 5, 500, e_range=[0.2, 0.2], e_mid=0.2,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    arr = e["area"]["bounds"]
    out.append(_reg(
        "R13-turnover", "供能数不变但发生周转：观测只作下界",
        dict(sessions_lo=e["sessions_lo"], sessions_hi=e["sessions_hi"],
             q_bounds=e["q_bounds"], q_status=e["q_status"],
             arrival_bounds=arr, truth_q=0.5,
             contains=(e["q_bounds"][0] <= 0.5 <= e["q_bounds"][1]),
             legacy_observed_only=[0.0, 0.0]),
        dict(sessions_lo=0, contains=True, q_hi_gt_0=True,
             arrival_contains_100=True),
        e["sessions_lo"] == 0 and e["q_bounds"][1] > 0
        and e["q_bounds"][0] <= 0.5 <= e["q_bounds"][1]
        and arr[0] <= 100 <= arr[1]))
    # R14 漏会话：会话在两次采样之间开始并结束
    rows = [_row(0, sup=1, free=0, chg=[("S4", "k0")]),
            _row(10, sup=1, free=2, chg=[]),
            _row(20, sup=1, free=2, chg=[("S4", "k2")]),
            _row(30, sup=1, free=2, chg=[("S4", "k2")]),
            _row(40, sup=1, free=2, chg=[("S4", "k2")])]
    v = _mk_view("L2", rows, 10, 10, 40, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    obs = e["sessions_observed"]
    out.append(_reg(
        "R14-missed-session", "漏会话时观测计数只是下界；首见键不证明新到达",
        dict(sessions_lo=e["sessions_lo"], observed_new_keys=obs["keys"],
             initial_deduction=obs["initial_deduction"], truth_sessions=3,
             q_bounds=e["q_bounds"], q_status=e["q_status"]),
        dict(sessions_lo=0, observed_new_keys=1, initial_deduction=9,
             sessions_lo_lt_truth=True, q_hi=1.0),
        e["sessions_lo"] == 0 and obs["keys"] == 1
        and obs["initial_deduction"] == 9
        and e["sessions_lo"] < 3 and e["q_bounds"][1] == 1.0))
    # R15 期初会话不计入窗口新会话
    rows = [_row(0, sup=1, free=2, chg=[("S4", "k0"), ("S4", "k1")]),
            _row(10, sup=1, free=2, chg=[("S4", "k0"), ("S4", "k1")])]
    v = _mk_view("L2", rows, 10, 10, 10, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    out.append(_reg(
        "R15-initial-session", "期初已存在的会话不抬高下界",
        dict(sessions_lo=e["sessions_lo"], q_lo=e["q_bounds"][0]),
        dict(sessions_lo=0, q_lo=0.0),
        e["sessions_lo"] == 0 and e["q_bounds"][0] == 0.0))
    # R16 去重：同一会话键重复出现在多帧只计一次
    rows = [_row(0, sup=1, free=0, chg=[("S4", "k_init")]),
            _row(10, sup=1, free=2, chg=[("S4", "k2")]),
            _row(20, sup=1, free=2, chg=[("S4", "k2")]),
            _row(30, sup=1, free=2, chg=[("S4", "k2")])]
    v = _mk_view("L2", rows, 10, 10, 30, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2)
    e = estimate(v)
    obs = e["sessions_observed"]
    out.append(_reg(
        "R16-dedup", "重复会话键去重后只计一次（且不当作新到达）",
        dict(sessions_lo=e["sessions_lo"], observed_new_keys=obs["keys"]),
        dict(sessions_lo=0, observed_new_keys=1),
        e["sessions_lo"] == 0 and obs["keys"] == 1))
    # R17 证据不足：无事件上限时即使有观测计数也保留无信息 q 范围
    rows = [_row(5 * i, sup=1, free=0) for i in range(101)]
    v = _mk_view("L1", rows, 10, 5, 500, e_range=[0.2, 0.2], e_mid=0.2,
                 dwell_range=[40.0, 60.0], event_cap=None)
    e = estimate(v)
    out.append(_reg(
        "R17-no-info-range", "证据不足时保留无信息范围",
        dict(q_bounds=e["q_bounds"], q_status=e["q_status"],
             A_upper=e["A_bounds"][1]),
        dict(q_upper=1.0, q_status="no_info"),
        e["q_bounds"][1] == 1.0 and e["q_status"] == "no_info"))
    # R18 完整事件史：期初 EV 在 t=1 才插枪，窗口内新到达 EV 全部不插枪。
    # N=10, T=500, delta=5, 每区间事件<=4, 停留 50, 新到达 100（EV 20%），真 q=0。
    N18, T18, d18 = 10, 500.0, 5.0
    events = []
    for bay in range(N18):
        if bay == 0:
            arrs = [-1.0] + [49.0 + 50.0 * k for k in range(10)]
            plugs = [True] + [False] * 10
            evs = [True] * 11
        else:
            phase = 2.5 + 5.0 * bay
            arrs = [phase - 50.0] + [phase + 50.0 * k for k in range(10)]
            plugs = [False] * 11
            evs = [bay in (0, 1)] * 11
        events += [dict(bay=bay, arr=a, leave=a + 50.0, ev=ev, plug=pg)
                   for a, ev, pg in zip(arrs, evs, plugs)]
    times = [d18 * i for i in range(101)]
    rows = []
    for t in times:
        active = [v for v in events if v["arr"] <= t < v["leave"]]
        supply = [v for v in active if v["plug"] and 1 <= t]
        rows.append(_row(t, sup=len(supply), free=N18 - len(active),
                         chg=[("S1", "initial_ev_late_plug")] if supply else []))
    cap_counts = [sum(a < v["arr"] <= b for v in events)
                  + sum(a < v["leave"] <= b for v in events)
                  for a, b in zip(times, times[1:])]
    new = [v for v in events if 0 <= v["arr"] < T18]
    conditions = dict(
        event_cap_holds=max(cap_counts) <= 4,
        dwell_holds=all(40.0 <= v["leave"] - v["arr"] <= 60.0 for v in events),
        ev_share=(sum(v["ev"] for v in new) / len(new) == 0.2),
        new_arrivals=len(new) == 100,
        new_arrival_plugs=sum(v["plug"] for v in new) == 0)
    v = _mk_view("L2", rows, N18, d18, T18, e_range=[0.2, 0.2], e_mid=0.2,
                 dwell_range=[40.0, 60.0], event_cap=4)
    e = estimate(v)
    obs = e["sessions_observed"]
    out.append(_reg(
        "R18-initial-late-plug", "期初车辆晚插枪不证明窗口新到达",
        dict(conditions=conditions, sessions_lo=e["sessions_lo"],
             observed_new_keys=obs["keys"],
             initial_deduction=obs["initial_deduction"],
             q_bounds=e["q_bounds"], q_status=e["q_status"]),
        dict(all_conditions=True, sessions_lo=0, q_lo=0.0),
        all(conditions.values()) and e["sessions_lo"] == 0
        and e["q_bounds"][0] == 0.0))
    # R19 右端跨窗：车辆 t=4 到达、插枪并停到 54；容量项不能给 0.125。
    cap = BND.session_upper_bound(1, 5, 40.0, 1, 1)
    rows = [_row(0, sup=0, free=1), _row(5, sup=1, free=0)]
    v = _mk_view("L1", rows, 1, 5, 5, e_range=[1.0, 1.0], e_mid=1.0,
                 dwell_range=[40.0, 60.0], event_cap=1)
    e = estimate(v)
    out.append(_reg(
        "R19-right-censored-cap", "右端跨窗车辆的有效插枪到访上界",
        dict(returned_cap=cap, sessions_hi=e["sessions_hi"],
             actual_new_sessions=1, window=[0, 5], stay=[4, 54]),
        dict(cap_at_least=1, hi_at_least=1),
        cap is not None and cap >= 1
        and (e["sessions_hi"] is None or e["sessions_hi"] >= 1)))
    # R20 每访多会话：两个后帧首见键可由同一新到访产生，只能换算出 1 个插枪到访。
    rows = [_row(0, sup=0, free=2, chg=[]),
            _row(10, sup=1, free=1, chg=[("S4", "s1")]),
            _row(20, sup=1, free=1, chg=[("S4", "s1")]),
            _row(30, sup=1, free=1, chg=[("S4", "s2")])]
    v = _mk_view("L2", rows, 2, 10, 30, e_range=[0.4, 0.6], e_mid=0.5,
                 dwell_range=[40.0, 60.0], event_cap=2, session_per_visit_max=2)
    e = estimate(v)
    direct = BND.new_arrival_session_lower(2, 0, 2, [])
    obs = e["sessions_observed"]
    out.append(_reg(
        "R20-multi-session-per-visit", "同一新到访的两个会话只换算出 1 个插枪到访",
        dict(direct_lower=direct["lower"], direct_status=direct["status"],
             sessions_lo=e["sessions_lo"], observed_new_keys=obs["keys"],
             remaining_sessions=obs["remaining_sessions"],
             per_visit_cap=obs["per_visit_cap"]),
        dict(direct_lower=1, sessions_lo=1, observed_new_keys=2),
        direct["lower"] == 1 and e["sessions_lo"] == 1
        and obs["keys"] == 2 and obs["remaining_sessions"] == 2
        and obs["per_visit_cap"] == 2))
    # R21 未知/非法每访上限：不把会话直接当插枪到访，也不给无依据的有限界。
    no_cap = BND.new_arrival_session_lower(2, 0, None, [])
    bad_cap = BND.new_arrival_session_lower(2, 0, -1, [])
    frac_cap = BND.new_arrival_session_lower(2, 0, 1.5, [])
    zero_cap = BND.new_arrival_session_lower(2, 0, 0, [])
    upper_none = BND.session_upper_bound(1, 5, 40, None, 1)
    upper_bad = BND.session_upper_bound(1, 5, 40, -1, 1)
    upper_zero = BND.session_upper_bound(1, 5, 40, 0, 1)
    out.append(_reg(
        "R21-visit-cap-edge", "未知/非法每访上限时诚实返回无信息",
        dict(no_cap=no_cap, bad_cap=bad_cap, frac_cap=frac_cap,
             zero_cap=zero_cap, upper_none=upper_none,
             upper_bad=upper_bad, upper_zero=upper_zero),
        dict(no_cap_lower=0, no_cap_status="no_per_visit_cap",
             bad_cap_lower=0, bad_cap_status="invalid_per_visit_cap",
             frac_cap_status="invalid_per_visit_cap",
             zero_cap_status="cap_zero_contradicts_keys",
             upper_none=1, upper_bad=None, upper_zero=0),
        no_cap["lower"] == 0 and no_cap["status"] == "no_per_visit_cap"
        and bad_cap["lower"] == 0 and bad_cap["status"] == "invalid_per_visit_cap"
        and frac_cap["lower"] == 0 and frac_cap["status"] == "invalid_per_visit_cap"
        and zero_cap["lower"] == 0 and zero_cap["status"] == "cap_zero_contradicts_keys"
        and upper_none == 1 and upper_bad is None and upper_zero == 0))
    return out


def regressions(reg_f08, res):
    out = list(reg_f08) + session_regressions()
    out.append(_reg("R7-log-hash", "同一需求日志跨配置哈希一致",
                    dict(all_equal=res["F04"]["all_equal"]),
                    dict(all_equal=True), bool(res["F04"]["all_equal"])))
    params = _get(res["F05"], "estimate_params", "read_keys", "signature")
    out.append(_reg("R8-truth-isolation", "估计器只读 view，不读真值",
                    dict(read=params,
                         legacy_drift=_get(res["F05"], "legacy_probe")),
                    dict(read=["view"]),
                    params == ["view"] or params == "view"))
    f6 = res["F06"]
    viol = _get(f6["tight_scenario"], "non_ev_in_protected_during_window",
                "violations")
    out.append(_reg("R9-protection", "R4 与 R3 决策不同且保护期内无违规",
                    dict(r4_must_differ=f6["r4_must_differ"], violations=viol),
                    dict(r4_must_differ=True, violations=0),
                    bool(f6["r4_must_differ"]) and viol == 0))
    f7 = res["F07"]
    out.append(_reg("R10-conservation", "逐步交付不超剩余需求且总量守恒",
                    dict(passes=f7["passes"],
                         residual=_get(f7, "max_conservation_residual", "residual")),
                    dict(residual_lt=1e-9), bool(f7["passes"])))
    qp = {lv: res["E5"]["levels"][lv]["q_point_status"] for lv in LEVELS}
    out.append(_reg("R11-no-q-point", "分母/去重不足时不给 q 点估计",
                    qp, dict(all_not_established=True),
                    all(v == "not_established" for v in qp.values())))
    bnd = {}
    for cap in PREREG["cost"]["c_cap_range"]:
        bnd["%g" % cap] = {lv: res["E5"]["c_cap=%g" % cap][lv]["boundary"]
                           for lv in LEVELS}
    boundary_ok = all(
        res["E5"]["c_cap=%g" % cap][lv]["boundary"] ==
        (res["E5"]["c_cap=%g" % cap][lv]["chosen"] in
         (min(PREREG["n_c_grid"]), max(PREREG["n_c_grid"])))
        for cap in PREREG["cost"]["c_cap_range"] for lv in LEVELS)
    true_boundary_ok = all(
        res["E5"]["c_cap=%g" % cap][lv]["true_optimum_boundary"] ==
        any(k in (min(PREREG["n_c_grid"]), max(PREREG["n_c_grid"]))
            for k in res["E5"]["c_cap=%g" % cap][lv]["true_optimal_set"])
        for cap in PREREG["cost"]["c_cap_range"] for lv in LEVELS)
    out.append(_reg("R12-no-flip", "不追翻转；上下边界与真值最优如实记录",
                    dict(any_flip=res["E5"]["any_flip"], boundary=bnd,
                         note="q=.5为情景；上下边界均需标记；有限q网格不保证全范围"),
                    dict(any_flip=False, boundary_consistent=True),
                    not res["E5"]["any_flip"] and boundary_ok and true_boundary_ok))
    return out


def f08_criteria(e5, e7, reg):
    rows = {}
    for level, d in e5["levels"].items():
        panel = BND.identification_panel(
            d["q_bounds_width_mean"], d["bound_coverage"],
            PREREG["assumptions"]["precision_target"],
            PREREG["assumptions"]["coverage_target"])
        panel["assumption_midpoint"] = d["q_assumption_mid_mean"]
        panel["bias_vs_truth"] = d["q_bias"]
        panel["A_provenance"] = d["A_provenance"]
        panel["q_status"] = d["q_status"]
        panel["sessions_lo_mean"] = d["sessions_lo_mean"]
        panel["sessions_hi_mean"] = d["sessions_hi_mean"]
        rows[level] = panel
    return dict(per_level=rows,
                tv_distance=e7["observation_equivalence"]["total_variation_distance"],
                tv_threshold=1e-6,
                sampling_rule="无每间隔事件上限即无有限采样界；delta*V_sampled 不是上界",
                residual_rule="10% 残余仅为情景假设，可被违反（见 R3）",
                numerator_rule="快照/键计数只作会话分子下界；上界用到达数或容量，不用观测计数；证据不足保留无信息范围",
                regressions_pass=all(r["pass"] for r in reg),
                removed=PREREG["removed_criteria"])
