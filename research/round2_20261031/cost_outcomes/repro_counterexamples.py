"""R2-A（cost-eng）修复前最小反例：可执行，修复前应失败并打印实际值。

用法: python research/round2_20261031/cost_outcomes/repro_counterexamples.py
退出码 0 = 全部通过（修复后）；1 = 存在失败（修复前）。
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.parking_lab.workbench import costs
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.demand import Arrival
from apps.parking_lab.workbench.simulation import Simulation

SYNTHETIC = {
    "vot_per_hour": 600.0, "search_min": 6.0, "detour_min": 4.0, "walking_min": 3.0,
    "detour_km_per_failure": 2.0, "ev_kwh_per_km": 0.18, "ev_energy_price_per_kwh": 5.0,
    "alternative_charging_delta_per_kwh": 4.0, "residual_trip_loss_per_kwh": 8.0,
    "emission_cost_per_km": 1.5, "fuel_l_per_km": 0.08, "fuel_price_per_l": 30.0,
    "activity_loss_per_failure": 50.0, "electricity_price_per_kwh": 3.0,
    "maintenance_per_kwh": 0.5, "maintenance_per_bay_day": 20.0,
    "depreciation_annual": 365000.0, "parking_fee_per_hour": 40.0, "charging_fee_per_kwh": 8.0,
}
# 真实情景参数（research/integer_allocation_20261031/cost_scenario.json）；仅设备/电费，无站级固定成本。
SCENARIO = {
    "depreciation_capex": 116792.62, "depreciation_life_years": 10.0,
    "maintenance_per_bay_day": 43.29969863013699, "electricity_price_per_kwh": 4.08,
}
CAPEX_DAILY = SCENARIO["depreciation_capex"] / SCENARIO["depreciation_life_years"] / 365.0
DEVICE_DAILY = CAPEX_DAILY + SCENARIO["maintenance_per_bay_day"]

records = []


def record(name, ok, detail):
    records.append({"check": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + " :: " + repr(detail))


def close(actual, expected, tol=1e-9):
    return actual is not None and abs(actual - expected) <= tol


def config(**changes):
    cost = {"provenance": "illustrative_not_calibrated", **SYNTHETIC}
    raw = {"n_spaces": 2, "charging_bays": 2, "chargers": 2, "reserve_fixed": 0,
           "policy": "open", "scenario": "steady", "duration_hours": 1,
           "arrival_rate_hour": 0, "seed": 42, "cost": cost}
    raw.update(changes)
    return Config.parse(raw)


# C1 k=0 仍计资本（真实情景 31.997978 TWD/日）
ledger = costs.CostLedger(SCENARIO)
report = ledger.summary(elapsed_min=1440.0, chargers=0)
record("C1 k=0 设备资本必须为 0.0（修复前 31.998）",
       close(report["items"]["operator_capital_depreciation"], 0.0),
       {"expected": 0.0, "actual": report["items"]["operator_capital_depreciation"],
        "bug_value": CAPEX_DAILY})

# C2 π1 下油车占带枪位：应进 ice_blocking_connector，不得进 no_charging_demand
pi1 = config(policy="full_open_ice_first", n_spaces=2, charging_bays=1, chargers=1)
sim = Simulation(pi1, [Arrival(0, 0.0, False, False, 10.0, 0.0),
                       Arrival(1, 1.0, False, False, 10.0, 0.0)])
sim.run()
occ = costs.occupancy_minutes(sim)
rules_ice = sim.type_occupancy()["metrics"]["ice_blocking_connector_min"]
record("C2a 油车占带枪位分钟与 rules 台账一致（10.0）",
       close(occ.get("ice_blocking_connector"), rules_ice) and close(rules_ice, 10.0),
       {"costs.ice_blocking_connector": occ.get("ice_blocking_connector"),
        "rules.ice_blocking_connector_min": rules_ice})
record("C2b no_charging_demand 不再混入油车（应为 EV-only 0.0）",
       close(occ.get("no_charging_demand"), 0.0),
       {"expected": 0.0, "actual": occ.get("no_charging_demand"),
        "bug_value": "油车 10 分钟被并入该键"})

# C3 k=2、12h 窗口：资本应为整日（k=2）的一半 = 单设备整日成本
report = ledger.summary(elapsed_min=720.0, chargers=2)
record("C3 k=2 12h 设备资本 = 整日（k=2）的一半",
       close(report["items"]["operator_capital_depreciation"], CAPEX_DAILY),
       {"expected": CAPEX_DAILY,
        "actual": report["items"]["operator_capital_depreciation"]})
# C3b k=1、12h：整日单设备成本的一半（旧实现也成立，用于核对窗口换算本身正确）
report = ledger.summary(elapsed_min=720.0, chargers=1)
record("C3b k=1 12h 设备资本 = 0.5 × 31.998",
       close(report["items"]["operator_capital_depreciation"], 0.5 * CAPEX_DAILY),
       {"expected": 0.5 * CAPEX_DAILY,
        "actual": report["items"]["operator_capital_depreciation"]})

# C4 k=2、24h：资本应乘设备数
report = ledger.summary(elapsed_min=1440.0, chargers=2)
record("C4 k=2 24h 设备资本 = 2 × 31.998",
       close(report["items"]["operator_capital_depreciation"], 2 * CAPEX_DAILY),
       {"expected": 2 * CAPEX_DAILY,
        "actual": report["items"]["operator_capital_depreciation"]})

# C5 唯一权威入口 facility_cost 是否已存在，且 k=0 为 0.0 + not_applicable
facility = getattr(costs, "facility_cost", None)
if facility is None:
    record("C5 facility_cost 唯一入口存在", False, {"error": "costs.facility_cost 不存在"})
    record("C6 facility_cost k=0 为 0.0 且归 not_applicable", False, {"error": "函数不存在"})
    record("C7 facility_cost 折算日口径 = 75.2977 TWD/设备位·日", False, {"error": "函数不存在"})
    record("C8 facility_cost 站级固定成本单列并按天折算", False, {"error": "函数不存在"})
else:
    res = facility(0, SCENARIO, days=1.0)
    record("C5 facility_cost 唯一入口存在", True, {"ok": True})
    record("C6 facility_cost k=0 为 0.0 且归 not_applicable",
           close(res["value"], 0.0) and set(res["not_applicable"]) >= {"device_capital", "device_maintenance"},
           {"value": res["value"], "not_applicable": res["not_applicable"], "missing": res["missing"]})
    res = facility(1, SCENARIO, days=1.0)
    record("C7 facility_cost 折算日口径 = 75.2977 TWD/设备位·日",
           close(res["value"], DEVICE_DAILY), {"expected": DEVICE_DAILY, "actual": res["value"]})
    res = facility(2, dict(SCENARIO, facility_fixed_cost_per_day=100.0), days=0.25)
    record("C8 facility_cost 站级固定成本单列并按天折算",
           close(res["items"]["facility_fixed"], 25.0)
           and close(res["value"], 2 * DEVICE_DAILY * 0.25 + 25.0),
           {"items": res["items"], "value": res["value"]})

failed = [row for row in records if not row["ok"]]
print("\nSUMMARY: %d/%d PASS, %d FAIL" % (len(records) - len(failed), len(records), len(failed)))
sys.exit(1 if failed else 0)

