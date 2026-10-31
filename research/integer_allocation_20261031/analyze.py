"""整数配桩成本曲线分析（Lead）：枚举最优、边际、取整回代、盈亏平衡、经验公式与样本外验证。

输入：run_cost_curve.py 产出的 cost_curve_*.json；本脚本只做分析，不产生仿真数据。
口径见 research/integer_allocation_20261031/DESIGN.md 与 CONTRACT.md §8。
缺参一律 None：任一成本项为 None 时该 k 的完整成本为 None，不得补 0。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.parking_lab.workbench import allocation as alloc  # noqa: E402  (需先把项目根加入 sys.path)

COST_KEYS = ("total_cost_mean", "facility_cost_mean", "user_cost_mean", "operating_cost_mean")


def _clean(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    return None


def cost_curve(rows, key="total_cost_mean"):
    curve = {}
    for row in rows:
        k = int(row["k"])
        curve[k] = _clean(row.get(key))
    return dict(sorted(curve.items()))


def service_curve(rows, key="unmet_charging_requests_mean"):
    curve = {}
    for row in rows:
        k = int(row["k"])
        curve[k] = _clean(row.get(key))
    return dict(sorted(curve.items()))


def summarize(rows, cost_key="total_cost_mean"):
    curve = cost_curve(rows, cost_key)
    evaluation = alloc.evaluate_integer_costs(curve)
    best_k = evaluation["best_k"]
    best_cost = evaluation["best_cost"]
    deltas = evaluation["deltas"]
    # 边际成本符号变化次数：用于判断目标是否非凸（不只看一次变号）。
    sign_changes = 0
    previous_sign = None
    for k in sorted(deltas):
        value = deltas[k]
        if value is None:
            continue
        sign = 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)
        if previous_sign is not None and sign != previous_sign and sign != 0:
            sign_changes += 1
        previous_sign = sign
    return {
        "cost_key": cost_key,
        "cost_curve": curve,
        "feasible_k": evaluation["feasible_k"],
        "best_k": best_k,
        "best_cost": best_cost,
        "deltas": deltas,
        "marginal_non_decreasing": evaluation["marginal_non_decreasing"],
        "delta_sign_changes": sign_changes,
        "requires_full_enumeration": evaluation["marginal_non_decreasing"] is not True,
    }


def rounding_check(rows, k_cont, cost_key="total_cost_mean"):
    curve = cost_curve(rows, cost_key)
    return alloc.compare_rounding(curve, k_cont)


def break_even(rows, facility_key="facility_cost_mean", service_key="unmet_charging_requests_mean"):
    """相邻 k 的盈亏平衡：多 1 个带枪位每天多花 ΔF，少发生 ΔS 次未满足服务。

    L*_k = ΔF/ΔS 是"每次未满足服务的社会损失"的临界值；L > L* 时增加该桩才划算。
    ΔS<=0 或 ΔF 任一为 None 时不给阈值（None），不编造。
    """
    facility = cost_curve(rows, facility_key)
    service = service_curve(rows, service_key)
    thresholds = {}
    for k in sorted(facility):
        if k + 1 not in facility:
            continue
        current_f = facility.get(k)
        next_f = facility.get(k + 1)
        current_s = service.get(k)
        next_s = service.get(k + 1)
        if None in (current_f, next_f, current_s, next_s):
            thresholds[k] = None
            continue
        delta_f = next_f - current_f
        delta_s = current_s - next_s
        if delta_s <= 0:
            thresholds[k] = None
            continue
        thresholds[k] = delta_f / delta_s
    return {"loss_per_unserved_threshold": thresholds,
            "note": "L*_k=Δ设施成本/Δ未满足服务次数；与外部可得损失估计比较，不预设 L"}


def service_level_k(rows, target_fraction, service_key="unmet_charging_requests_mean"):
    """服务水平规则：取最小的 k，使未满足服务 ≤ target_fraction × k=0 时未满足服务。"""
    service = service_curve(rows, service_key)
    baseline = service.get(0)
    if baseline is None:
        return {"target_fraction": target_fraction, "k": None,
                "reason": "k=0 未满足服务不可得，无法定义服务水平"}
    if baseline <= 0:
        return {"target_fraction": target_fraction, "k": 0, "baseline": baseline,
                "reason": "无充电需求，任意 k 都不产生未满足服务"}
    chosen = None
    for k, value in service.items():
        if value is None:
            continue
        if value <= target_fraction * baseline:
            chosen = k
            break
    return {"target_fraction": target_fraction, "k": chosen, "baseline": baseline,
            "threshold_events": target_fraction * baseline}


def _solve3(matrix, rhs):
    a = [list(matrix[i]) + [rhs[i]] for i in range(3)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("拟合矩阵奇异")
        a[col], a[pivot] = a[pivot], a[col]
        for row in range(3):
            if row == col:
                continue
            factor = a[row][col] / a[col][col]
            for j in range(col, 4):
                a[row][j] -= factor * a[col][j]
    return tuple(a[i][3] / a[i][i] for i in range(3))


def fit_affine_sqrt(points):
    """拟合 k = a + b*A + c*sqrt(A)（A 为 offered load，Erlang）。points: [(A, k)]。"""
    if len(points) < 3:
        raise ValueError("至少需要 3 个点拟合 3 参数模型")
    normal = [[0.0] * 3 for _ in range(3)]
    target = [0.0] * 3
    for load, k in points:
        features = (1.0, load, math.sqrt(max(load, 0.0)))
        for i in range(3):
            target[i] += features[i] * k
            for j in range(3):
                normal[i][j] += features[i] * features[j]
    a, b, c = _solve3(normal, target)
    return {"a": a, "b": b, "c": c, "form": "k = a + b*A + c*sqrt(A)",
            "n_points": len(points), "train_points": points}


def predict_k(formula, load):
    return formula["a"] + formula["b"] * load + formula["c"] * math.sqrt(max(load, 0.0))


def validate_formula(formula, validation_points):
    """validation_points: [(A, k_star, cost_curve)]；后悔值 = (C(k̂)-C(k*))/C(k*)。"""
    errors, regrets, details = [], [], []
    for load, k_star, curve in validation_points:
        continuous = predict_k(formula, load)
        candidates = alloc.rounding_candidates(continuous)
        feasible = [k for k in candidates if curve.get(k) is not None]
        if not feasible:
            details.append({"load": load, "k_star": k_star, "predicted_continuous": continuous,
                            "reason": "候选整数在成本曲线中不可得"})
            continue
        k_hat = min(feasible, key=lambda k: (curve[k], k))
        best = alloc.evaluate_integer_costs(curve)["best_cost"]
        regret = None
        if best not in (None, 0):
            regret = (curve[k_hat] - best) / abs(best)
        errors.append(abs(k_hat - k_star))
        if regret is not None:
            regrets.append(regret)
        details.append({"load": load, "k_star": k_star, "predicted_continuous": continuous,
                        "k_hat": k_hat, "abs_error": abs(k_hat - k_star), "regret": regret})
    return {"n_validation": len(details),
            "mae_k": (sum(errors) / len(errors)) if errors else None,
            "max_abs_error_k": max(errors) if errors else None,
            "mean_regret": (sum(regrets) / len(regrets)) if regrets else None,
            "max_regret": max(regrets) if regrets else None,
            "details": details}


def k_star_distribution(curves):
    """curves: {scenario: {k: cost}}；返回 k* 分布（含并列）。"""
    counts = {}
    per_scenario = {}
    for name, curve in curves.items():
        best = alloc.evaluate_integer_costs(curve)["best_k"]
        per_scenario[name] = best
        for k in best:
            counts[k] = counts.get(k, 0) + 1
    total = sum(counts.values())
    return {"counts": dict(sorted(counts.items())), "per_scenario": per_scenario,
            "share": {k: (v / total) for k, v in sorted(counts.items())} if total else {},
            "n_scenarios": len(curves)}


def _self_test():
    rows = [
        {"k": 0, "total_cost_mean": 1000.0, "facility_cost_mean": 0.0, "unmet_charging_requests_mean": 100.0},
        {"k": 1, "total_cost_mean": 600.0, "facility_cost_mean": 100.0, "unmet_charging_requests_mean": 50.0},
        {"k": 2, "total_cost_mean": 500.0, "facility_cost_mean": 200.0, "unmet_charging_requests_mean": 30.0},
        {"k": 3, "total_cost_mean": 550.0, "facility_cost_mean": 300.0, "unmet_charging_requests_mean": 25.0},
    ]
    summary = summarize(rows)
    assert summary["best_k"] == [2], summary["best_k"]
    assert summary["deltas"] == {0: -400.0, 1: -100.0, 2: 50.0}, summary["deltas"]
    assert summary["delta_sign_changes"] == 1
    assert summary["requires_full_enumeration"] is False
    thresholds = break_even(rows)["loss_per_unserved_threshold"]
    assert thresholds[0] == 2.0, thresholds
    assert thresholds[1] == 5.0, thresholds
    assert thresholds[2] == 20.0, thresholds
    assert 3 not in thresholds
    level = service_level_k(rows, 0.30)
    assert level["k"] == 2, level
    # 非凸：三邻点不一定含全局最优
    nonconvex = {0: 100.0, 1: 200.0, 2: 150.0, 3: 300.0, 4: 120.0}
    evaluated = alloc.evaluate_integer_costs(nonconvex)
    assert evaluated["best_k"] == [0]
    # 缺参：任何 None 不补 0
    missing = [{"k": 0, "total_cost_mean": None, "unmet_charging_requests_mean": 5.0},
               {"k": 1, "total_cost_mean": None, "unmet_charging_requests_mean": 1.0}]
    assert summarize(missing)["best_k"] == []
    formula = fit_affine_sqrt([(1.0, 2), (4.0, 4), (9.0, 6)])
    assert abs(predict_k(formula, 16.0) - 8.0) < 1e-9
    return {"self_test": "ok"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="整数配桩成本曲线分析")
    parser.add_argument("--curve", action="append", default=[], help="cost_curve_*.json 路径，可多次")
    parser.add_argument("--out", default=None)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--targets", default="0.01,0.05,0.10")
    args = parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(_self_test(), ensure_ascii=False))
        return 0
    result = {"inputs": args.curve, "curves": {}}
    for path in args.curve:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        rows = data["rows"]
        entry = {"meta": data.get("meta", {}), "summary": summarize(rows),
                 "break_even": break_even(rows),
                 "service_levels": {t: service_level_k(rows, float(t)) for t in args.targets.split(",")}}
        result["curves"][os.path.basename(path)] = entry
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)
        print("wrote " + args.out)
    else:
        print(text[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
