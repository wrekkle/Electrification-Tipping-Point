"""双服务水平指标语义入口（第六轮 A）：五态分类 + 约束判定。

本模块是第六轮 CONTRACT §1 的唯一语义入口。旧 analyze_round3.joint_k 不改写；
所有新分析（可行集合、四类可行性、信息条件比较）一律调用这里。

五态（RATE_STATES）
-------------------
- valid：值有限且落在 [0,1]，可参与“≤α”判定；
- not_applicable_zero_demand：分母=0 且对应需求计数=0；按预登记记录并跳过，
  不是 achieved，也不是失败；
- censored_no_departure：仅离场能量率会出现——分母 departed_requested_kwh=0 但
  exogenous_charge_requests>0（有充电需求、窗口内无离场样本）；删失，不判成功；
- missing：rate 缺失（或分母缺失无法判定）；不得跳过判 achieved；
- illegal：非有限数值、越界 [0,1]、类型错、分母为负；不得跳过判 achieved。

分母口径（与 service_metrics.py 一致）
-------------------------------------
- capacity_only_unmet_rate：charge_requests（缺省回退 service_metrics 的
  exogenous_charge_requests）；
- ev_parking_failure_rate：exogenous_ev_visits；
- ice_parking_failure_rate：exogenous_ice_visits；
- departed_shortfall_energy_rate：departed_requested_kwh；其“需求计数”是
  exogenous_charge_requests（分母=0 时用它区分零需求 N/A 与删失）。

兼容性锚点（第五轮只读审计）
---------------------------
- review/none_semantics_4way.json：容量率 valid 31,360 / N/A 615；
  EV、ICE 各 valid 31,975；离场能量率 valid 22,895 / N/A 615 / 删失 8,465；
  真实缺失 0、非法 0（59 条曲线、31,975 行）。
- review/joint_k_none_audit.json：三约束按 N/A 跳过 achieved 780/975、
  严格 765/975；四约束按 N/A 跳过 310/975、严格 51/975。
本模块在同样输入上必须复现这些计数（见 research/round6_20261031/a_semantics/）。
"""
from __future__ import annotations

import math

EPS = 1e-12
ALPHA = 0.05

RATE_STATES = ("valid", "not_applicable_zero_demand", "censored_no_departure",
               "missing", "illegal")

RATE_NAMES = ("capacity_only_unmet_rate", "ev_parking_failure_rate",
              "ice_parking_failure_rate", "departed_shortfall_energy_rate")

# 三约束（第三轮预登记主口径）与四约束（追加离场能量率，只作删失条件下的辅助）。
CONSTRAINTS_3 = ("capacity_only_unmet_rate", "ev_parking_failure_rate",
                 "ice_parking_failure_rate")
CONSTRAINTS_4 = CONSTRAINTS_3 + ("departed_shortfall_energy_rate",)

# 每项率的 service_metrics 分母键；capacity 特殊（顶层 charge_requests）。
DENOMINATOR_KEYS = {
    "capacity_only_unmet_rate": "exogenous_charge_requests",
    "ev_parking_failure_rate": "exogenous_ev_visits",
    "ice_parking_failure_rate": "exogenous_ice_visits",
    "departed_shortfall_energy_rate": "departed_requested_kwh",
}

SOURCE = {
    "capacity_only_unmet_rate": "row.capacity_only_unmet_rate / row.charge_requests",
    "ev_parking_failure_rate":
        "row.service_metrics.rates.ev_parking_failure_rate / denominators.exogenous_ev_visits",
    "ice_parking_failure_rate":
        "row.service_metrics.rates.ice_parking_failure_rate / denominators.exogenous_ice_visits",
    "departed_shortfall_energy_rate":
        "row.service_metrics.rates.departed_shortfall_energy_rate / denominators.departed_requested_kwh",
}


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite(value):
    return _num(value) and math.isfinite(float(value))


def _metrics_block(row):
    """兼容两种输入：曲线结果行（row["service_metrics"]）或 summarise() 直接输出。"""
    if not isinstance(row, dict):
        return None
    block = row.get("service_metrics")
    if isinstance(block, dict):
        return block
    if isinstance(row.get("rates"), dict) or isinstance(row.get("denominators"), dict):
        return row
    return None


def _rate_value(row, name):
    if name == "capacity_only_unmet_rate":
        return row.get(name)
    block = _metrics_block(row)
    if block is None:
        return None
    rates = block.get("rates") if isinstance(block.get("rates"), dict) else {}
    return rates.get(name)


def _denominator(row, name):
    block = _metrics_block(row)
    if name == "capacity_only_unmet_rate":
        value = row.get("charge_requests")
        if value is None and block is not None:
            value = (block.get("denominators") or {}).get("exogenous_charge_requests")
        return value, ("row.charge_requests" if row.get("charge_requests") is not None
                       else "service_metrics.denominators.exogenous_charge_requests")
    if block is None:
        return None, "service_metrics 缺失"
    dens = block.get("denominators") if isinstance(block.get("denominators"), dict) else {}
    return dens.get(DENOMINATOR_KEYS[name]), "service_metrics.denominators." + DENOMINATOR_KEYS[name]


def _demand_count(row, name):
    """分母=0 时用于区分“零需求 N/A”与“有需求但无离场样本（删失）”的需求计数。"""
    if name == "capacity_only_unmet_rate":
        value = row.get("charge_requests")
        if value is not None:
            return value
        block = _metrics_block(row)
        return (block.get("denominators") or {}).get("exogenous_charge_requests") if block else None
    if name == "departed_shortfall_energy_rate":
        block = _metrics_block(row)
        if block is None:
            return None
        return (block.get("denominators") or {}).get("exogenous_charge_requests")
    return _denominator(row, name)[0]


def _cell(status, value, denominator, reason, source, numerator=None, skipped=False):
    return {"status": status, "state": status, "value": value,
            "numerator": numerator, "denominator": denominator,
            "reason": reason, "source": source, "skipped": bool(skipped)}


def classify_rate(name, row, alpha=None):
    """把一项率分类为五态之一。

    返回 {"status", "state", "value", "numerator", "denominator", "reason",
    "source", "skipped"}。alpha 只影响 reason 中的阈值描述，不改变状态分类。
    """
    if name not in RATE_NAMES:
        raise ValueError("未知率：" + str(name) + "；可选 " + ", ".join(RATE_NAMES))
    if not isinstance(row, dict):
        return _cell("missing", None, None, "输入行不是 dict", SOURCE[name])
    if _metrics_block(row) is None:
        return _cell("missing", None, None, "service_metrics 缺失", SOURCE[name])

    value = _rate_value(row, name)
    den, den_source = _denominator(row, name)
    demand = _demand_count(row, name)
    numerator = None
    block = _metrics_block(row)
    if block is not None:
        numerators = block.get("numerators") if isinstance(block.get("numerators"), dict) else {}
        if name == "capacity_only_unmet_rate":
            numerator = row.get("capacity_only_unmet_requests")
        elif name == "ev_parking_failure_rate":
            numerator = numerators.get("ev_parking_failures")
        elif name == "ice_parking_failure_rate":
            numerator = numerators.get("ice_parking_failures")
        elif name.endswith("energy_rate"):
            numerator = numerators.get("departed_shortfall_kwh")
    _ = den_source

    # 1) 值本身：非 None 时先校验类型/有限/范围（非法不得被跳过）。
    if value is not None:
        if not _num(value):
            return _cell("illegal", value, den, "值不是数值（类型=%s）" % type(value).__name__,
                         SOURCE[name], numerator)
        if not math.isfinite(float(value)):
            return _cell("illegal", value, den, "非有限数", SOURCE[name], numerator)
        if float(value) < -EPS or float(value) > 1.0 + EPS:
            return _cell("illegal", value, den, "越界 [0,1]", SOURCE[name], numerator)

    # 2) 分母不可判定。
    if den is None:
        if value is None:
            return _cell("missing", None, None, "rate=None 且分母缺失/不可判定",
                         SOURCE[name], numerator)
        return _cell("missing", value, None, "分母缺失，无法判定（不判 achieved）",
                     SOURCE[name], numerator)
    if not _num(den):
        return _cell("illegal", value, den, "分母不是数值", SOURCE[name], numerator)
    denominator = float(den)
    if not math.isfinite(denominator):
        return _cell("missing", value, den, "分母非有限，无法判定", SOURCE[name], numerator)
    if denominator < -EPS:
        return _cell("illegal", value, den, "分母为负", SOURCE[name], numerator)

    # 3) 零分母：按需求计数分 N/A 与删失。
    if denominator <= EPS:
        if demand is None:
            return _cell("missing", value, denominator, "分母=0 且需求计数缺失，无法区分 N/A/删失",
                         SOURCE[name], numerator)
        if not _num(demand):
            return _cell("illegal", value, denominator, "需求计数不是数值", SOURCE[name], numerator)
        if float(demand) <= 0.0:
            return _cell("not_applicable_zero_demand", value, denominator,
                         "零需求：分母=0 且需求计数=0；记录并跳过，不判成功",
                         SOURCE[name], numerator, skipped=True)
        return _cell("censored_no_departure", value, denominator,
                     "有需求（%s=%s）但分母=0：窗口内无离场样本，删失，不判成功"
                     % (DENOMINATOR_KEYS[name], demand), SOURCE[name], numerator,
                     skipped=False)

    # 4) 分母>0。
    if value is None:
        return _cell("missing", None, denominator, "分母>0 但 rate=None",
                     SOURCE[name], numerator)
    return _cell("valid", float(value), denominator, "", SOURCE[name], numerator)


def classify_rates(row, names=RATE_NAMES):
    return {name: classify_rate(name, row) for name in names}


def constraint_status(name, row, alpha=ALPHA):
    """单项约束状态：satisfied / violated / not_applicable / censored / missing / illegal。

    只有 valid 且 ≤α 才是 satisfied；N/A 记录但不算 satisfied。
    """
    cell = classify_rate(name, row)
    state = cell["status"]
    if state == "valid":
        status = "satisfied" if float(cell["value"]) <= float(alpha) + EPS else "violated"
    elif state == "not_applicable_zero_demand":
        status = "not_applicable"
    elif state == "censored_no_departure":
        status = "censored"
    else:
        status = state
    return {"name": name, "status": status, "cell": cell}


def judge(row, constraints=CONSTRAINTS_3, alpha=ALPHA, na_policy="skip"):
    """判定一个 k 是否满足约束集合。

    na_policy="skip"：零需求 N/A 记录并跳过（预登记口径）；censored/missing/illegal
    一律不判成功。
    na_policy="strict"：只有全部 satisfied 才算 achieved（N/A 也不通过）。

    返回 {"achieved", "status", "constraints", "violated", "not_applicable",
    "censored", "missing", "illegal", "undecidable", "alpha", "na_policy"}。
    其中 status ∈ achieved / violated / undecidable_missing / undecidable_illegal /
    undecidable_censored / not_achieved_strict。
    """
    if na_policy not in ("skip", "strict"):
        raise ValueError("na_policy 只能是 skip 或 strict")
    if not constraints:
        raise ValueError("constraints 不能为空")
    items = {name: constraint_status(name, row, alpha) for name in constraints}
    violated = [n for n, i in items.items() if i["status"] == "violated"]
    na = [n for n, i in items.items() if i["status"] == "not_applicable"]
    censored = [n for n, i in items.items() if i["status"] == "censored"]
    missing = [n for n, i in items.items() if i["status"] == "missing"]
    illegal = [n for n, i in items.items() if i["status"] == "illegal"]
    satisfied = [n for n, i in items.items() if i["status"] == "satisfied"]
    undecidable = missing + illegal + censored

    if illegal:
        status = "undecidable_illegal"
    elif missing:
        status = "undecidable_missing"
    elif censored:
        status = "undecidable_censored"
    elif violated:
        status = "violated"
    elif na_policy == "strict" and na:
        status = "not_achieved_strict"
    else:
        status = "achieved"
    vacuous = status == "achieved" and not satisfied
    return {"achieved": status == "achieved", "achieved_na_skip": status == "achieved",
            "vacuous": bool(vacuous), "status": status, "constraints": items,
            "violated": violated, "not_applicable": na, "censored": censored,
            "missing": missing, "illegal": illegal, "undecidable": undecidable,
            "satisfied": satisfied, "alpha": float(alpha), "na_policy": na_policy}


def feasible(row, constraints=CONSTRAINTS_3, alpha=ALPHA, na_policy="skip"):
    """三态可行性：True / False / None（None=删失/缺失/非法，不可判定）。"""
    verdict = judge(row, constraints=constraints, alpha=alpha, na_policy=na_policy)
    status = verdict["status"]
    if status == "achieved":
        return True
    if status.startswith("undecidable"):
        return None
    return False


def minimal_feasible(by_k, constraints=CONSTRAINTS_3, alpha=ALPHA, k_max=None,
                     na_policy="skip"):
    """给定 {k: row}，返回最小已知可行 k 与集合形状字段。

    - min_known_feasible：最小 assessed=feasible 的 k；None 表示网格内无可行（或全不可判定）；
    - confirmed_minimal：k=0 可行，或 k_min−1 已评估且不可行（非不可判定）；
    - truncated_at_kmax：k_max 处仍可行且网格上界由调用方截断（需显式传入 k_max）；
    - is_interval：可行 k 集合在网格上连续（忽略不可判定格）；
    - empty_set：无任何 assessed 可行格。
    """
    ks = sorted(int(k) for k in by_k)
    verdicts = {k: feasible(by_k[k], constraints, alpha, na_policy) for k in ks}
    feasible_ks = [k for k in ks if verdicts[k] is True]
    k_min = feasible_ks[0] if feasible_ks else None
    confirmed = False
    if k_min is not None:
        if k_min == ks[0] or k_min == 0:
            confirmed = True
        else:
            previous = k_min - 1
            confirmed = previous in verdicts and verdicts[previous] is False
    last = ks[-1] if ks else None
    return {"min_known_feasible": k_min, "confirmed_minimal": bool(confirmed),
            "empty_set": not feasible_ks, "feasible": feasible_ks,
            "truncated_at_kmax": bool(k_max is not None and last == k_max
                                      and k_min is not None and last in feasible_ks),
            "is_interval": (len(feasible_ks) == (feasible_ks[-1] - feasible_ks[0] + 1)
                            if feasible_ks else False),
            "k_grid": [ks[0], last] if ks else [None, None],
            "undecidable_ks": [k for k in ks if verdicts[k] is None],
            "infeasible_ks": [k for k in ks if verdicts[k] is False]}
