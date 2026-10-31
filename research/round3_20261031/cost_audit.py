"""R3-F 成本口径独立复核：depreciation_daily / facility_cost 手算对照（不调用被测模块的算术）。

期望值一律用 fractions.Fraction 由定义式直接构造：
  annual 路径: annual / 365
  capex 路径 : capex / life_year / 365
  facility  : k x (日资本 + 日维护) x days + 站级固定成本 x days
再与 costs 的浮点输出比较，rel_tol=1e-12。本脚本只读源码，不改任何文件。

用法: python research/round3_20261031/cost_audit.py
退出码: 0 = 数值核对全部通过（文档缺口另行列出）；1 = 存在数值差异。
"""
from __future__ import annotations

import json
import math
import os
import sys
from fractions import Fraction

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.parking_lab.workbench import costs  # noqa: E402

REL_TOL = 1e-12
rows = []
failures = []


def isclose(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return math.isclose(actual, float(expected), rel_tol=REL_TOL, abs_tol=1e-12)


def fmt(value):
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    if isinstance(value, Fraction):
        return "%.12f" % float(value)
    return "%.12f" % value


def record(section, name, expected, actual, ok=None, note=""):
    if ok is None:
        ok = isclose(actual, expected)
    row = {"section": section, "name": name, "expected": expected, "actual": actual, "ok": bool(ok),
           "note": note}
    rows.append(row)
    if not ok:
        failures.append(row)
    print("%s  [%s] %s | 手算=%s 实际=%s%s" % (
        "PASS" if ok else "FAIL", section, name, fmt(expected), fmt(actual),
        (" | " + note) if note else ""))


def expect_raises(section, name, exc_type, fn):
    try:
        fn()
    except Exception as error:  # noqa: BLE001 - 记录真实异常类型
        record(section, name, exc_type.__name__, type(error).__name__,
               ok=isinstance(error, exc_type), note=str(error)[:80])
    else:
        record(section, name, exc_type.__name__, "no raise", ok=False)


print("== 1 depreciation_daily：两条路径手算 ==")
DEP_CASES = [
    ("annual=365000 -> 1000/日", {"depreciation_annual": 365000.0}, Fraction(365000, 365), ()),
    ("annual=146000.5 -> 400.00136986/日", {"depreciation_annual": 146000.5},
     Fraction(1460005, 10) / 365, ()),
    ("capex=3650000/life=10 -> 1000/日",
     {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0},
     Fraction(3650000, 10 * 365), ()),
    ("capex=116792.62/life=10 -> 31.99797808/日",
     {"depreciation_capex": 116792.62, "depreciation_life_years": 10.0},
     Fraction(11679262, 100 * 10 * 365), ()),
    ("只给 capex 缺 life -> None + missing",
     {"depreciation_capex": 100.0}, None, ("depreciation_life_years",)),
    ("两者都不给 -> None + missing", {}, None, ("depreciation_annual",)),
]
for name, params, expected, expected_missing in DEP_CASES:
    actual, missing = costs.depreciation_daily(params)
    record("dep", name, expected, actual, note="missing=%s" % (list(missing),))
    record("dep", name + "（missing 清单）", str(list(expected_missing)), str(list(missing)),
           ok=tuple(missing) == tuple(expected_missing))
expect_raises("dep", "annual 与 capex 同时给 -> ValueError", ValueError,
              lambda: costs.depreciation_daily({"depreciation_annual": 1.0,
                                                "depreciation_capex": 1.0}))
# 边界记录：life=0 只在绕过 Config.parse 时可达（配置层已拒绝 <=0），不算缺陷。
try:
    costs.depreciation_daily({"depreciation_capex": 365.0, "depreciation_life_years": 0.0})
    print("NOTE  [dep] life=0 未抛零除（与预期边界不同，请人工确认）")
except ZeroDivisionError as error:
    print("NOTE  [dep] 边界：life=0 直调 -> ZeroDivisionError（%s）；Config.parse 已拒绝 life<=0，"
          "正常链路不可达" % error)

print()
print("== 2 facility_cost：拆分 / k=0 / 缺参传播 ==")
FACILITY_CASES = [
    {
        "name": "capex 路径、整数天、k=2、无站级固定",
        "k": 2, "days": Fraction(1, 1),
        "params": {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0,
                   "maintenance_per_bay_day": 20.0},
        "items": {"device_capital": Fraction(3650000, 10 * 365) * 2,
                  "device_maintenance": Fraction(20 * 2),
                  "facility_fixed": Fraction(0)},
        "missing": [], "not_applicable": [],
    },
    {
        "name": "annual 路径、小数天 0.375、k=1、无站级固定",
        "k": 1, "days": Fraction(3, 8),
        "params": {"depreciation_annual": 730000.0, "maintenance_per_bay_day": 12.5},
        "items": {"device_capital": Fraction(730000, 365) * Fraction(3, 8),
                  "device_maintenance": Fraction(25, 2) * Fraction(3, 8),
                  "facility_fixed": Fraction(0)},
        "missing": [], "not_applicable": [],
    },
    {
        "name": "capex 路径、跨日 2.75 天、k=4、站级固定 100/日",
        "k": 4, "days": Fraction(11, 4),
        "params": {"depreciation_capex": 116792.62, "depreciation_life_years": 10.0,
                   "maintenance_per_bay_day": 43.29969863013699,
                   "facility_fixed_cost_per_day": 100.0},
        "items": {"device_capital": Fraction(11679262, 100) * Fraction(11, 3650),
                  "device_maintenance": Fraction(4329969863013699, 100000000000000) * 11,
                  "facility_fixed": Fraction(100) * Fraction(11, 4)},
        "missing": [], "not_applicable": [],
    },
    {
        "name": "annual 路径、1.5 天、k=3、站级固定显式 None",
        "k": 3, "days": Fraction(3, 2),
        "params": {"depreciation_annual": 146000.0, "maintenance_per_bay_day": 5.0,
                   "facility_fixed_cost_per_day": None},
        "items": {"device_capital": Fraction(146000, 365) * Fraction(9, 2),
                  "device_maintenance": Fraction(5) * Fraction(9, 2),
                  "facility_fixed": None},
        "missing": ["facility_fixed_cost_per_day"], "not_applicable": [],
    },
    {
        "name": "k=0 且参数齐全：资本/维护 0.0 + not_applicable",
        "k": 0, "days": Fraction(1, 1),
        "params": {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0,
                   "maintenance_per_bay_day": 20.0},
        "items": {"device_capital": Fraction(0), "device_maintenance": Fraction(0),
                  "facility_fixed": Fraction(0)},
        "missing": [], "not_applicable": ["device_capital", "device_maintenance"],
    },
    {
        "name": "k=0 且参数全缺：仍是 0.0（零设备不是未知）",
        "k": 0, "days": Fraction(1, 1),
        "params": {},
        "items": {"device_capital": Fraction(0), "device_maintenance": Fraction(0),
                  "facility_fixed": Fraction(0)},
        "missing": [], "not_applicable": ["device_capital", "device_maintenance"],
    },
    {
        "name": "k=0 且给了站级固定成本：设备 0、站级仍按天计",
        "k": 0, "days": Fraction(1, 4),
        "params": {"facility_fixed_cost_per_day": 100.0},
        "items": {"device_capital": Fraction(0), "device_maintenance": Fraction(0),
                  "facility_fixed": Fraction(25)},
        "missing": [], "not_applicable": ["device_capital", "device_maintenance"],
    },
    {
        "name": "k>0 缺维护参数 -> None 传播",
        "k": 2, "days": Fraction(1, 1),
        "params": {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0},
        "items": {"device_capital": Fraction(2000), "device_maintenance": None,
                  "facility_fixed": Fraction(0)},
        "missing": ["maintenance_per_bay_day"], "not_applicable": [],
    },
    {
        "name": "k>0 缺资本参数 -> None 传播",
        "k": 2, "days": Fraction(1, 1),
        "params": {"maintenance_per_bay_day": 20.0},
        "items": {"device_capital": None, "device_maintenance": Fraction(40),
                  "facility_fixed": Fraction(0)},
        "missing": ["depreciation_annual"], "not_applicable": [],
    },
]
for case in FACILITY_CASES:
    days = float(case["days"])
    result = costs.facility_cost(case["k"], case["params"], days=days)
    for item, expected in case["items"].items():
        record("facility", "%s / %s" % (case["name"], item), expected,
               result["items"].get(item))
    expected_value = (None if any(value is None for value in case["items"].values())
                      else sum(case["items"].values(), Fraction(0)))
    record("facility", "%s / value" % case["name"], expected_value, result["value"])
    record("facility", "%s / missing" % case["name"], str(case["missing"]),
           str(result["missing"]), ok=list(result["missing"]) == case["missing"])
    record("facility", "%s / not_applicable" % case["name"],
           str(case["not_applicable"]), str(result["not_applicable"]),
           ok=list(result["not_applicable"]) == case["not_applicable"])
    record("facility", "%s / items 键集合" % case["name"], "device_capital,device_maintenance,"
           "facility_fixed", ",".join(sorted(result["items"])),
           ok=set(result["items"]) == set(costs.FACILITY_COST_ITEMS))

print()
print("== 3 facility_cost 输入边界 ==")
for name, kwargs in (
    ("k=-1 -> ValueError", {"k": -1, "days": 1.0}),
    ("k=1.0 -> ValueError", {"k": 1.0, "days": 1.0}),
    ("k=True -> ValueError", {"k": True, "days": 1.0}),
    ("days=-0.1 -> ValueError", {"k": 1, "days": -0.1}),
    ("days=nan -> ValueError", {"k": 1, "days": float("nan")}),
    ("days=inf -> ValueError", {"k": 1, "days": float("inf")}),
    ("days='1' -> ValueError", {"k": 1, "days": "1"}),
):
    expect_raises("edge", name, ValueError,
                  lambda kwargs=kwargs: costs.facility_cost(
                      kwargs["k"], {"depreciation_annual": 365000.0,
                                    "maintenance_per_bay_day": 20.0}, days=kwargs["days"]))

print()
print("== 4 账本单一入口交叉核对（facility_cost 与 summary 同口径） ==")
LEDGER_PARAMS = {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0,
                 "maintenance_per_bay_day": 20.0}
ledger = costs.CostLedger(LEDGER_PARAMS)
for elapsed_min, days in ((1440.0, Fraction(1)), (720.0, Fraction(1, 2)),
                          (900.0, Fraction(5, 8)), (2160.0, Fraction(3, 2))):
    report = ledger.summary(elapsed_min=elapsed_min, chargers=2)
    facility = costs.facility_cost(2, LEDGER_PARAMS, days=elapsed_min / 1440.0)
    record("ledger", "elapsed=%smin / 资本=2000xdays" % elapsed_min,
           Fraction(2 * 1000) * days, report["items"]["operator_capital_depreciation"])
    record("ledger", "elapsed=%smin / 与 facility_cost 同值" % elapsed_min,
           facility["items"]["device_capital"], report["items"]["operator_capital_depreciation"])
    record("ledger", "elapsed=%smin / 按位维护=40xdays" % elapsed_min,
           Fraction(2 * 20) * days, report["items"]["operator_maintenance"])

print()
print("== 5 docs/methods/COST-MODEL-V2.md 口径写法检查 ==")
doc_path = os.path.join(_ROOT, "docs", "methods", "COST-MODEL-V2.md")
with open(doc_path, encoding="utf-8") as handle:
    doc = handle.read()
doc_checks = [
    ("是否写明 365 日/年（年折旧/365）", "365" in doc),
    ("是否写明 capex/寿命年/365 公式",
     all(token in doc for token in ("depreciation_capex", "depreciation_life_years"))),
    ("是否写明 annual/365 路径", "depreciation_annual" in doc),
    ("是否写明 days=elapsed_min/1440 换算", "1440" in doc),
    ("是否写明 facility_cost 返回键", "facility_cost" in doc and "not_applicable" in doc),
    ("§5 占桩原因数与代码一致（6 类含 ice_blocking_connector）",
     "ice_blocking_connector" in doc and "原因 5 类" not in doc),
]
doc_gaps = [name for name, ok in doc_checks if not ok]
for name, ok in doc_checks:
    print("%s  [doc] %s" % ("OK  " if ok else "GAP ", name))
print("DOC_GAPS:", len(doc_gaps), json.dumps(doc_gaps, ensure_ascii=False))

print()
print("== 汇总 ==")
passed = len(rows) - len(failures)
print("数值核对: %d/%d PASS, %d FAIL" % (passed, len(rows), len(failures)))
print("DOC_GAPS: %d（建议见 cost_audit.md §4）" % len(doc_gaps))

# 供 cost_audit.md 引用的精简对照表
print()
print("== MARKDOWN TABLE ==")
print("| # | 类别 | 检查项 | 手算期望 | costs 实际 | 差异 | 结论 |")
print("| --- | --- | --- | --- | --- | --- | --- |")
for index, row in enumerate(rows, 1):
    expected = row["expected"]
    actual = row["actual"]
    if isinstance(expected, (int, float, Fraction)) and isinstance(actual, float):
        diff = actual - float(expected)
    else:
        diff = None
    print("| %d | %s | %s | %s | %s | %s | %s |" % (
        index, row["section"], row["name"], fmt(row["expected"]), fmt(row["actual"]),
        ("%.3e" % diff) if diff is not None else "—", "PASS" if row["ok"] else "FAIL"))

sys.exit(1 if failures else 0)
