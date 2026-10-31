"""第二轮契约最小反例（R2-D5/D6/D7 + 新增搜索状态）：修复前必须失败，修复后必须通过。

用法：python research/round2_20261031/search_status/repro_contract.py
退出码：0=全部契约断言通过；1=存在未满足项（修复前即 1）。

本脚本只做契约断言，不修改被测代码。开头的 [证据] 行记录修复前旧实现的实际行为：
- D5：by_k 中没有任何 k 达标时，旧 analyze_run.service_level_k 返回 max(by_k)，
  把"枚举上限截断"伪装成推荐 k；契约要求 status=infeasible_upper_bound 且 k=None。
  预算耗尽但未到硬上限时应为 budget_exhausted 且 k=None。
- D6：mean_connector_load 对需充电 EV 用充电时长，与"充满不释放枪"冲突；
  契约要求默认 occupancy_model="dwell"（占位=全部 EV 停留）。
- D7：旧报告 §10 手算 B(1,1)=1/3 错误（正确 0.5）；本脚本用独立闭式求和校验
  B(0.5,1)=1/3、B(1,1)=0.5、B(2,2)=0.4、B(5,3)=0.529661（6 位小数）。
"""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

FAILURES = []


def check(name, function):
    try:
        function()
    except Exception as exc:  # 契约断言失败/接口缺失都算失败
        FAILURES.append(name)
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        print(f"PASS {name}")


def load_old_service_level_k():
    """加载修复前旧实现（research/integer_allocation_20261031/analyze_run.py），只读。"""
    path = ROOT / "research" / "integer_allocation_20261031" / "analyze_run.py"
    spec = importlib.util.spec_from_file_location("round2_old_analyze", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.service_level_k


def case_d5_fake_recommendation():
    by_k = {
        0: {"unmet_no_connector_events": 10.0},
        1: {"unmet_no_connector_events": 8.0},
        2: {"unmet_no_connector_events": 5.0},
    }
    old_k = load_old_service_level_k()(by_k, 0.05)
    print(f"  [D5 证据] 旧 analyze_run.service_level_k -> {old_k!r}（即 max(by_k)=2，未达标也返回 2）")
    assert old_k == 2
    result = alloc.service_level_k(by_k, 0.05, k_hard_max=2)
    assert result["status"] == "infeasible_upper_bound", result
    assert result["k"] is None, result
    assert result["evaluated_max"] == 2, result
    assert result["baseline"] == 10.0, result
    print(f"  [D5] 新实现 -> status={result['status']}, k={result['k']}, note={result['note']}")


def case_d5_budget_exhausted():
    by_k = {
        0: {"unmet_no_connector_events": 10.0},
        1: {"unmet_no_connector_events": 9.0},
        2: {"unmet_no_connector_events": 5.0},
    }
    result = alloc.service_level_k(by_k, 0.05, k_hard_max=5)
    assert result["status"] == "budget_exhausted", result
    assert result["k"] is None, result
    assert result["evaluated_max"] == 2, result
    print(f"  [D5] 预算耗尽 -> status={result['status']}, k={result['k']}, note={result['note']}")


def case_d5_boundary_achieved():
    by_k = {
        0: {"unmet_no_connector_events": 10.0},
        1: {"unmet_no_connector_events": 9.0},
        2: {"unmet_no_connector_events": 8.0},
        3: {"unmet_no_connector_events": 1.0},
        4: {"unmet_no_connector_events": 0.4},
    }
    result = alloc.service_level_k(by_k, 0.05, k_hard_max=4)
    assert result["status"] == "achieved", result
    assert result["k"] == 4, result
    assert result["boundary"] is True, result
    print(f"  [D5] 边界达标 -> status={result['status']}, k={result['k']}, boundary={result['boundary']}")


def case_d5_no_demand_and_missing():
    no_demand = alloc.service_level_k({0: 0.0}, 0.05)
    assert no_demand["status"] == "no_demand", no_demand
    assert no_demand["k"] == 0, no_demand
    missing_baseline = alloc.service_level_k({1: 1.0}, 0.05)
    assert missing_baseline["status"] == "missing_data", missing_baseline
    assert missing_baseline["k"] is None and missing_baseline["baseline"] is None, missing_baseline
    gap = alloc.service_level_k({0: 10.0, 1: 8.0, 3: 5.0}, 0.05)
    assert gap["status"] == "missing_data", gap
    print(f"  [D5] no_demand/missing_data -> {no_demand['status']}/{missing_baseline['status']}/{gap['status']}")


def case_d6_dwell_default():
    # 10 EV/h；q_need=0.2（2 辆/h 需要充电），充电 30 min，停留 90 min（充完不释放枪）。
    dwell = alloc.mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0)
    print(f"  [D6 当前默认口径] mean_connector_minutes={dwell['mean_connector_minutes']} "
          f"offered_load_erlang={dwell['offered_load_erlang']}")
    assert dwell["mean_connector_minutes"] == 90.0, dwell
    assert dwell["offered_load_erlang"] == 15.0, dwell
    assert dwell["legacy"] is False, dwell
    assert dwell["occupancy_model"] == "dwell", dwell
    legacy = alloc.mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0, occupancy_model="charge")
    assert abs(legacy["mean_connector_minutes"] - 78.0) < 1e-12, legacy
    assert abs(legacy["offered_load_erlang"] - 13.0) < 1e-12, legacy
    assert legacy["legacy"] is True, legacy
    k_dwell = alloc.min_servers_for_blocking(15.0, 0.05, 60)
    k_legacy = alloc.min_servers_for_blocking(13.0, 0.05, 60)
    print(f"  [D6] dwell/legacy 负荷=15.0/13.0 Erlang -> k(5%)={k_dwell}/{k_legacy}")
    assert k_dwell > k_legacy, (k_dwell, k_legacy)


def case_d7_erlang_closed_form():
    cases = ((0.5, 1, 1.0 / 3.0), (1.0, 1, 0.5), (2.0, 2, 0.4), (5.0, 3, 0.5296610169491525))
    for load, servers, expected in cases:
        recursion = alloc.erlang_b(load, servers)
        closed = alloc.erlang_b_closed_form(load, servers)
        assert round(recursion, 6) == round(expected, 6), (load, servers, recursion, expected)
        assert round(closed, 6) == round(expected, 6), (load, servers, closed, expected)
        independent = sum(load ** n / math.factorial(n) for n in range(servers + 1))
        expected_sum = (load ** servers / math.factorial(servers)) / independent
        assert abs(closed - expected_sum) < 1e-12, (load, servers, closed, expected_sum)
        print(f"  [D7] B({load:g},{servers}) = {recursion:.6f}（闭式 {closed:.6f}，独立求和 {expected_sum:.6f}）")
    assert math.isclose(alloc.erlang_b(1.0, 1), 0.5), "旧报告 §10 手算 B(1,1)=1/3 是错的"


def case_d5_budgeted_search():
    calls = []

    def evaluate(k):
        calls.append(k)
        return max(0.0, 10.0 - 0.5 * k)

    result = alloc.budgeted_service_search(evaluate, 0.05, 4, 20)
    assert result["status"] == "achieved", result
    assert result["k"] == 19, result
    assert result["boundary"] is False, result
    assert calls == list(range(21)), calls
    print(f"  [D5] 分批扩展 -> status={result['status']}, k={result['k']}, 评估次数={len(calls)}")


def main():
    print("== 第二轮搜索状态/解析负荷契约最小反例 ==")
    check("D5 全部 k 未达标不得返回 max(by_k)", case_d5_fake_recommendation)
    check("D5 预算耗尽未到硬上限 -> budget_exhausted/k=None", case_d5_budget_exhausted)
    check("D5 恰在边界达标 -> achieved/boundary=True", case_d5_boundary_achieved)
    check("D5 no_demand 与 missing_data", case_d5_no_demand_and_missing)
    check("D6 默认占位=dwell（全部 EV 停留）", case_d6_dwell_default)
    check("D7 Erlang-B 独立闭式求和与 6 位手算值", case_d7_erlang_closed_form)
    check("D5 budgeted_service_search 分批扩展", case_d5_budgeted_search)
    print(f"== 结果: {len(FAILURES)} 项失败 ==")
    for name in FAILURES:
        print(f"  - {name}")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
