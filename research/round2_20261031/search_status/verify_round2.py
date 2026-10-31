"""R2-D5/D6/D7 独立验收（不调用 tests/ 模块，闭式求和自带一份独立实现）。

用法：python research/round2_20261031/search_status/verify_round2.py
输出：research/round2_20261031/search_status/verification.json
      含 meta（源码哈希、运行命令、退出码、解释器版本、版本标签）。
退出码：0=全部检查通过；1=任一检查失败（失败详情写入 JSON）。
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from apps.parking_lab.workbench import allocation as alloc  # noqa: E402

OUT = Path(__file__).resolve().parent / "verification.json"
COMMAND = "python research/round2_20261031/search_status/verify_round2.py"
VERSION_LABEL = "round2-search-status-20261031"
FILES = (
    "apps/parking_lab/workbench/allocation.py",
    "apps/parking_lab/workbench/tests/test_allocation.py",
    "research/round2_20261031/search_status/repro_contract.py",
)

RECORDS = []


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(name, function):
    try:
        detail = function()
    except Exception as exc:  # 验收失败要记录，不吞掉
        RECORDS.append({"name": name, "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    else:
        RECORDS.append({"name": name, "ok": True, "detail": detail})
        print(f"PASS {name}")


def independent_erlang_b(load, servers):
    """独立闭式：B=(a^c/c!)/sum_{n=0..c}a^n/n!，用整数阶乘直接求和（不复用模块函数）。"""
    if load == 0.0:
        return 0.0
    terms = [load ** n / math.factorial(n) for n in range(servers + 1)]
    return terms[-1] / math.fsum(terms)


def case_hand_values():
    rows = []
    cases = ((0.5, 1, 0.333333), (1.0, 1, 0.500000), (2.0, 2, 0.400000), (5.0, 3, 0.529661))
    for load, servers, expected in cases:
        recursion = alloc.erlang_b(load, servers)
        reference = independent_erlang_b(load, servers)
        closed = alloc.erlang_b_closed_form(load, servers)
        assert round(recursion, 6) == expected
        assert round(reference, 6) == expected
        assert round(closed, 6) == expected
        assert abs(recursion - reference) < 1e-12 and abs(closed - reference) < 1e-12
        rows.append({"offered_load": load, "servers": servers, "erlang_b": recursion,
                     "independent_sum": reference, "closed_form": closed,
                     "rounded_6": round(recursion, 6), "expected_6": expected})
    assert round(alloc.erlang_b(5.0, 3), 4) == 0.5297
    return {"hand_values": rows, "b_5_3_4dp": 0.5297}


def case_grid_agreement():
    worst = 0.0
    for load in (0.1, 0.5, 1.0, 2.7, 5.0, 12.0, 30.0):
        for servers in range(1, 22):
            reference = independent_erlang_b(load, servers)
            worst = max(worst, abs(alloc.erlang_b(load, servers) - reference),
                        abs(alloc.erlang_b_closed_form(load, servers) - reference))
    assert worst < 1e-12, worst
    return {"grid_points": 7 * 21, "max_abs_diff": worst}


def case_status_matrix():
    by_k = {
        0: {"unmet_no_connector_events": 10.0},
        1: {"unmet_no_connector_events": 9.0},
        2: {"unmet_no_connector_events": 8.0},
        3: {"unmet_no_connector_events": 1.0},
        4: {"unmet_no_connector_events": 0.4},
    }
    expected = [
        ("achieved_mid", alloc.service_level_k(by_k, 0.05, k_hard_max=6), "achieved", 4, False),
        ("achieved_boundary", alloc.service_level_k(by_k, 0.05, k_hard_max=4), "achieved", 4, True),
        ("infeasible", alloc.service_level_k(by_k, 0.05, k_hard_max=2), "infeasible_upper_bound", None, False),
        ("budget_exhausted", alloc.service_level_k({0: 10.0, 1: 9.0, 2: 8.0}, 0.05,
                                                   k_hard_max=5), "budget_exhausted", None, False),
        ("no_demand", alloc.service_level_k({0: 0.0}, 0.05), "no_demand", 0, False),
        ("missing_baseline", alloc.service_level_k({1: 1.0}, 0.05), "missing_data", None, False),
        ("missing_row", alloc.service_level_k({0: 10.0, 1: 8.0, 3: 5.0}, 0.05), "missing_data", None, False),
    ]
    keys = {"status", "k", "alpha", "evaluated_max", "baseline", "note", "boundary"}
    rows = []
    for name, result, status, k, boundary in expected:
        assert set(result) == keys, (name, sorted(result))
        assert result["status"] == status, (name, result)
        assert result["k"] == k, (name, result)
        assert result["boundary"] is boundary, (name, result)
        assert isinstance(result["note"], str) and result["note"], (name, result)
        rows.append({"case": name, "status": result["status"], "k": result["k"],
                     "evaluated_max": result["evaluated_max"], "baseline": result["baseline"],
                     "boundary": result["boundary"]})
    # 修复前反例：旧实现会返回 max(by_k)=4 或 2，这里必须是 None
    assert alloc.service_level_k(by_k, 0.02, k_hard_max=4)["k"] is None
    return rows


def case_budgeted_search():
    calls = []

    def evaluate(k):
        calls.append(k)
        return max(0.0, 10.0 - 0.5 * k)

    result = alloc.budgeted_service_search(evaluate, 0.05, 4, 20)
    assert result["status"] == "achieved" and result["k"] == 19 and result["boundary"] is False
    assert calls == list(range(21))
    constant_calls = []

    def constant(k):
        constant_calls.append(k)
        return 10.0

    infeasible = alloc.budgeted_service_search(constant, 0.05, 2, 8)
    assert infeasible["status"] == "infeasible_upper_bound" and infeasible["k"] is None
    assert constant_calls == list(range(9))
    return {"achieved": {"k": result["k"], "calls": len(calls)},
            "infeasible": {"status": infeasible["status"], "calls": len(constant_calls)}}


def case_dwell_model():
    dwell = alloc.mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0)
    charge = alloc.mean_connector_load(10.0, 1.0, 0.2, 30.0, 90.0, occupancy_model="charge")
    assert dwell["mean_connector_minutes"] == 90.0 and dwell["offered_load_erlang"] == 15.0
    assert dwell["legacy"] is False and dwell["occupancy_model"] == "dwell"
    assert abs(charge["mean_connector_minutes"] - 78.0) < 1e-12
    assert abs(charge["offered_load_erlang"] - 13.0) < 1e-12 and charge["legacy"] is True
    k_dwell = alloc.min_servers_for_blocking(15.0, 0.05, 60)
    k_charge = alloc.min_servers_for_blocking(13.0, 0.05, 60)
    assert k_dwell == 20 and k_charge == 18, (k_dwell, k_charge)
    return {"dwell_minutes": 90.0, "legacy_minutes": 78.0, "dwell_erlang": 15.0,
            "legacy_erlang": 13.0, "k_alpha_dwell": k_dwell, "k_alpha_legacy": k_charge}


def case_same_alpha_agreement():
    rows = []
    for load in (0.4, 2.0, 8.7, 24.0):
        for alpha in (0.02, 0.05, 0.10, 0.20):
            by_k = {0: {"unmet_no_connector_events": 1.0}}
            by_k.update({k: {"unmet_no_connector_events": alloc.erlang_b(load, k)}
                         for k in range(1, 61)})
            analytic = alloc.min_servers_for_blocking(load, alpha, 60)
            searched = alloc.service_level_k(by_k, alpha, k_hard_max=60)
            assert searched["k"] == analytic, (load, alpha, searched, analytic)
            rows.append({"offered_load": load, "alpha": alpha, "k": analytic,
                         "status": searched["status"]})
    return {"pairs": len(rows), "rows": rows}


def main():
    for name, function in (
        ("erlang_b_hand_values", case_hand_values),
        ("erlang_b_grid_agreement", case_grid_agreement),
        ("service_level_status_matrix", case_status_matrix),
        ("budgeted_service_search", case_budgeted_search),
        ("mean_connector_load_dwell_default", case_dwell_model),
        ("erlang_vs_integer_same_alpha", case_same_alpha_agreement),
    ):
        check(name, function)
    exit_code = 0 if all(record["ok"] for record in RECORDS) else 1
    document = {
        "meta": {
            "version_label": VERSION_LABEL,
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "command": COMMAND,
            "exit_code": exit_code,
            "python": sys.version.split()[0],
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "seed": None,
            "note": "确定性检查，无随机种子；哈希为本文件运行时读取的源码 SHA-256",
            "source_sha256": {path: sha256(ROOT / path) for path in FILES},
        },
        "checks": RECORDS,
        "summary": {"passed": sum(1 for r in RECORDS if r["ok"]),
                    "failed": sum(1 for r in RECORDS if not r["ok"]),
                    "statuses": sorted(alloc.SERVICE_LEVEL_STATUSES)},
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"== {document['summary']['passed']} 项检查通过，{document['summary']['failed']} 项失败，"
          f"退出码 {exit_code}，结果写入 {OUT.relative_to(ROOT)} ==")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
