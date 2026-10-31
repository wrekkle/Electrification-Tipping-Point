"""k 最小性五分类（E3，R8-B）。

严格区分（PLAN §3.4 / DESIGN_MATRIX.families[E3].classes）：
- confirmed_minimal：0..k-1 每个整数都实测不可行，k 可行；
- minimality_unconfirmed：k 可行，但更小的整数有未测/未收敛/不可判定项；
- physically_infeasible：k=N 仍不可行，且原因可归为容量/服务冲突（搜索到物理边界）；
- budget_not_covered：枚举上限截断，无法判定（含超出小实例完整枚举范围）；
- missing_data：缺参数/缺字段导致无法判定。

注意：confirmed_minimal 是"在声明模型内、对 0..k-1 每个整数都实测不可行"的结论；
它不是物理意义上的已证明下界（见 offline_opt 的 model/direction 标记），
也不允许从"单调性假设"或"峰值×均值×安全系数"推出来。
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_ENGINE = Path(__file__).resolve().parent
for _p in (str(_ROOT), str(_ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CLASSES = ("confirmed_minimal", "minimality_unconfirmed", "physically_infeasible",
           "budget_not_covered", "missing_data")

CLASS_DEFINITIONS = {
    "confirmed_minimal": "0..k-1 每个整数都实测不可行，且 k 可行（声明模型内）",
    "minimality_unconfirmed": "k 可行，但更小的整数存在未测/未收敛/不可判定项",
    "physically_infeasible": "k 搜到物理边界（枪位/车位上限）仍不可行，原因是容量/服务冲突",
    "budget_not_covered": "枚举上限截断或超出小实例完整枚举范围，无法判定",
    "missing_data": "缺参数/缺字段，无法判定",
}

CAPACITY_REASONS = {"parking_capacity_exceeded", "insufficient_connector_minutes",
                    "window_too_short", "no_connector_with_charge_demand",
                    "chargers_exceed_charging_bays", "no_deliverable_power"}


def _result(cls, *, reason, k_star=None, search=None, tested=None, uncovered=None,
            evidence=None):
    return {"class": cls, "reason": reason, "k_star": k_star,
            "k_max_searched": None if search is None else search.get("k_max_searched"),
            "physical_bound": None if search is None else search.get("physical_bound"),
            "stop_reason": None if search is None else search.get("stop_reason"),
            "model": None if search is None else search.get("model"),
            "information": None if search is None else search.get("information"),
            "tested_k": tested, "uncovered_k": uncovered,
            "evidence": evidence or {},
            "definition": CLASS_DEFINITIONS[cls],
            "note": ("confirmed_minimal 只在本文件记录的离线声明模型内成立；"
                     "不得写成物理下界或在线可执行结论")}


def classify(search, *, missing_fields=None, instance_note=None):
    """把 offline_opt.min_connectors() 的搜索结果分类；不猜、不补测。"""
    if not isinstance(search, dict) or "per_k" not in search:
        return _result("missing_data", reason="搜索结果为缺失或格式错误",
                       evidence={"instance_note": instance_note})
    per_k = dict(search["per_k"])
    if missing_fields:
        return _result("missing_data",
                       reason="缺字段/参数：" + ", ".join(sorted(missing_fields)),
                       tested=sorted(per_k), evidence={"missing_fields": sorted(missing_fields)})
    if not per_k:
        return _result("missing_data", reason="没有任何 k 的实测记录", search=search)
    statuses = {int(k): rec.get("status") for k, rec in per_k.items()}
    if "missing_data" in statuses.values():
        bad = sorted(k for k, s in statuses.items() if s == "missing_data")
        return _result("missing_data", reason="k 记录本身缺数据", tested=sorted(per_k),
                       search=search, evidence={"missing_data_k": bad})
    k_min = search.get("k_min")
    if k_min is not None:
        smaller = sorted(k for k in statuses if k < k_min)
        uncovered = [k for k in range(0, k_min) if k not in statuses]
        unknown = sorted(k for k in smaller if statuses[k] not in ("infeasible", "feasible"))
        feasible_smaller = sorted(k for k in smaller if statuses[k] == "feasible")
        if uncovered or unknown or feasible_smaller:
            return _result("minimality_unconfirmed",
                           reason=("k=%d 可行，但更小的整数有未测/不可判定项"
                                   % k_min),
                           k_star=k_min, search=search, tested=sorted(per_k),
                           uncovered=uncovered or unknown or feasible_smaller,
                           evidence={"per_k_status": statuses})
        return _result("confirmed_minimal",
                       reason="k=%d 可行；0..%d 每个整数都实测不可行" % (k_min, k_min - 1),
                       k_star=k_min, search=search, tested=sorted(per_k),
                       uncovered=[], evidence={"per_k_status": statuses})
    # 网格内无可行 k
    cap = search.get("k_max_searched")
    physical = search.get("physical_bound")
    last_k = max(statuses)
    last_reason = (per_k[last_k] or {}).get("reason")
    if cap is not None and physical is not None and cap >= physical \
            and last_reason in CAPACITY_REASONS:
        return _result("physically_infeasible",
                       reason=("搜到物理边界 k=%d 仍不可行：%s" % (cap, last_reason)),
                       k_star=None, search=search, tested=sorted(per_k),
                       evidence={"per_k_status": statuses, "last_reason": last_reason})
    return _result("budget_not_covered",
                   reason=("枚举上限 k=%s 截断（物理边界 %s），无法判定；最后一条原因：%s"
                           % (cap, physical, last_reason)),
                   k_star=None, search=search, tested=sorted(per_k),
                   evidence={"per_k_status": statuses, "last_reason": last_reason})


def count_classes(results):
    """E3 分类计数（含零类别，避免表格缺行被误读）。"""
    counts = {name: 0 for name in CLASSES}
    for result in results:
        cls = result.get("class")
        if cls not in counts:
            raise ValueError("未知分类：%r" % (cls,))
        counts[cls] += 1
    return counts


def rows(classified, *, instance_id=None, n_vehicles=None, search=None):
    """分类结果 + 搜索明细 -> E3 CSV 行（per_k 逐行 + 汇总行）。"""
    out = []
    info = classified or {}
    search = search or {}
    per_k = search.get("per_k") or {}
    for k in sorted(per_k):
        record = per_k[k]
        evidence = record.get("evidence") or {}
        out.append({
            "row_kind": "per_k", "instance_id": instance_id or search.get("instance_id"),
            "n_vehicles": n_vehicles, "k": k, "status": record.get("status"),
            "reason": record.get("reason"),
            "demanded_minutes": evidence.get("demanded_minutes"),
            "schedulable_minutes": evidence.get("schedulable_minutes"),
            "peak_occupancy": evidence.get("peak_occupancy"),
            "k_class": info.get("class"), "k_star": info.get("k_star"),
            "model": (classified or {}).get("model") or search.get("model"),
            "information": (classified or {}).get("information") or search.get("information"),
            "evidence_model": search.get("model"),
        })
    out.append({
        "row_kind": "summary", "instance_id": instance_id or search.get("instance_id"),
        "n_vehicles": n_vehicles, "k": info.get("k_star"),
        "status": info.get("class"), "reason": info.get("reason"),
        "k_class": info.get("class"), "k_star": info.get("k_star"),
        "k_max_searched": info.get("k_max_searched"),
        "physical_bound": info.get("physical_bound"),
        "tested_k": info.get("tested_k"), "uncovered_k": info.get("uncovered_k"),
        "model": info.get("model"), "information": info.get("information"),
        "evidence_model": search.get("model"),
    })
    return out
