"""R2-A 修复后独立验证：逐条复算 facility_cost / 账本 / 三类占位，输出 JSON 证据。

用法: python research/round2_20261031/cost_outcomes/verify_fix.py [输出JSON路径]
退出码 0 = 全部通过；1 = 有失败。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from apps.parking_lab.workbench import costs  # noqa: E402
from apps.parking_lab.workbench.config import Config  # noqa: E402
from apps.parking_lab.workbench.demand import Arrival  # noqa: E402
from apps.parking_lab.workbench.simulation import Simulation  # noqa: E402

SYNTHETIC = {
    "vot_per_hour": 600.0, "search_min": 6.0, "detour_min": 4.0, "walking_min": 3.0,
    "detour_km_per_failure": 2.0, "ev_kwh_per_km": 0.18, "ev_energy_price_per_kwh": 5.0,
    "alternative_charging_delta_per_kwh": 4.0, "residual_trip_loss_per_kwh": 8.0,
    "emission_cost_per_km": 1.5, "fuel_l_per_km": 0.08, "fuel_price_per_l": 30.0,
    "activity_loss_per_failure": 50.0, "electricity_price_per_kwh": 3.0,
    "maintenance_per_kwh": 0.5, "maintenance_per_bay_day": 20.0,
    "depreciation_annual": 365000.0, "parking_fee_per_hour": 40.0, "charging_fee_per_kwh": 8.0,
}
SCENARIO = {
    "depreciation_capex": 116792.62, "depreciation_life_years": 10.0,
    "maintenance_per_bay_day": 43.29969863013699, "electricity_price_per_kwh": 4.08,
}
CAPEX_DAILY = SCENARIO["depreciation_capex"] / SCENARIO["depreciation_life_years"] / 365.0
DEVICE_DAILY = CAPEX_DAILY + SCENARIO["maintenance_per_bay_day"]
cases, failures = [], []


def close(actual, expected, tol=1e-9):
    return actual is not None and abs(actual - expected) <= tol


def check(name, ok, **detail):
    row = {"check": name, "ok": bool(ok), **detail}
    cases.append(row)
    if not ok:
        failures.append(row)
    print(("PASS " if ok else "FAIL ") + name)


def sha256_file(rel):
    path = os.path.join(_ROOT, rel)
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def config(**changes):
    cost = {"provenance": "illustrative_not_calibrated", **SYNTHETIC}
    raw = {"n_spaces": 2, "charging_bays": 2, "chargers": 2, "reserve_fixed": 0,
           "policy": "open", "scenario": "steady", "duration_hours": 1,
           "arrival_rate_hour": 0, "seed": 42, "cost": cost}
    raw.update(changes)
    return Config.parse(raw)


# 1) facility_cost：k=0/1/2 × 12h/24h/36h
grid = {}
for k in (0, 1, 2):
    for label, days in (("12h", 0.5), ("24h", 1.0), ("36h", 1.5)):
        result = costs.facility_cost(k, SCENARIO, days=days)
        expected = k * DEVICE_DAILY * days
        grid["k=%d,%s" % (k, label)] = {
            "items": result["items"], "value": result["value"],
            "missing": result["missing"], "not_applicable": result["not_applicable"],
            "expected_value": expected,
        }
        check("facility_cost k=%d days=%s = k×设备日成本×天数" % (k, days),
              close(result["value"], expected), **grid["k=%d,%s" % (k, label)])
        if k == 0:
            check("facility_cost k=0 资本/维护 0.0 且 not_applicable",
                  result["items"]["device_capital"] == 0.0
                  and result["items"]["device_maintenance"] == 0.0
                  and set(result["not_applicable"]) >= {"device_capital", "device_maintenance"}
                  and result["missing"] == [], items=result["items"],
                  not_applicable=result["not_applicable"])
# 2) 缺参 vs 零设备
no_capital = costs.facility_cost(1, {"maintenance_per_bay_day": 20.0}, days=1.0)
check("缺资本参数 -> value None，depreciation_annual 进 missing",
      no_capital["value"] is None and "depreciation_annual" in no_capital["missing"], result=no_capital)
no_maintenance = costs.facility_cost(
    1, {"depreciation_capex": 3650000.0, "depreciation_life_years": 10.0}, days=1.0)
check("缺维护参数 -> value None，maintenance_per_bay_day 进 missing",
      no_maintenance["value"] is None and "maintenance_per_bay_day" in no_maintenance["missing"],
      result=no_maintenance)
bare_zero = costs.facility_cost(0, {}, days=1.0)
check("k=0 即使全缺参也是 0.0 且 missing 为空（零设备不是未知）",
      bare_zero["value"] == 0.0 and bare_zero["missing"] == [], result=bare_zero)
# 3) 站级固定成本单列
fixed = costs.facility_cost(2, dict(SCENARIO, facility_fixed_cost_per_day=288.0), days=0.25)
check("站级固定成本单列并按天折算（288×0.25=72）",
      close(fixed["items"]["facility_fixed"], 72.0)
      and close(fixed["value"], 2 * DEVICE_DAILY * 0.25 + 72.0), result=fixed)
fixed_unknown = costs.facility_cost(1, dict(SCENARIO, facility_fixed_cost_per_day=None), days=1.0)
check("站级固定成本显式 None -> 该项 None 且进 missing",
      fixed_unknown["items"]["facility_fixed"] is None and fixed_unknown["value"] is None
      and "facility_fixed_cost_per_day" in fixed_unknown["missing"], result=fixed_unknown)
absent = costs.facility_cost(1, SCENARIO, days=1.0)
check("未提供站级固定成本 = 不纳入核算（0.0 且不进 missing）",
      absent["items"]["facility_fixed"] == 0.0
      and "facility_fixed_cost_per_day" not in absent["missing"], result=absent)

# 4) 账本：窗口口径 + 折算日口径，不重复相乘
ledger = costs.CostLedger(SCENARIO)
ledger_grid = {}
for k, minutes in ((0, 720.0), (1, 720.0), (1, 1440.0), (2, 720.0), (2, 1440.0), (2, 2160.0)):
    report = ledger.summary(elapsed_min=minutes, chargers=k)
    days = minutes / 1440.0
    expected_capital = k * CAPEX_DAILY * days
    per_day = report["daily_equivalent"]["operator_capital_depreciation_per_day"]
    row = {
        "k": k, "elapsed_min": minutes, "days": days,
        "operator_capital_depreciation": report["items"]["operator_capital_depreciation"],
        "daily_equivalent": report["daily_equivalent"],
        "operator_maintenance": report["items"]["operator_maintenance"],
        "operator_facility_fixed": report["items"]["operator_facility_fixed"],
        "total": report["total"],
        "expected_capital": expected_capital,
    }
    ledger_grid["k=%d,min=%s" % (k, minutes)] = row
    check("summary k=%d 窗口=%smin 资本=k×日成本×elapsed/1440 且=折算日×days" % (k, minutes),
          close(report["items"]["operator_capital_depreciation"], expected_capital)
          and close(per_day, k * CAPEX_DAILY)
          and close(report["items"]["operator_capital_depreciation"], per_day * days), **row)
    if k > 0:
        check("summary k=%d 窗口=%smin 按位维护只乘一次设备数" % (k, minutes),
              close(report["items"]["operator_maintenance"],
                    k * SCENARIO["maintenance_per_bay_day"] * days), **row)
fixed_ledger = costs.CostLedger(dict(SCENARIO, facility_fixed_cost_per_day=120.0)).summary(
    elapsed_min=720.0, chargers=2)
check("summary 站级固定成本单列（120×0.5=60）且完整",
      close(fixed_ledger["items"]["operator_facility_fixed"], 60.0)
      and fixed_ledger["facility_cost"]["facility_fixed_included"] is True, report=fixed_ledger["facility_cost"])
plain_ledger = costs.CostLedger(SCENARIO).summary(elapsed_min=720.0, chargers=2)
check("summary 未提供站级固定成本 -> 0.0 且标记 not included",
      plain_ledger["items"]["operator_facility_fixed"] == 0.0
      and plain_ledger["facility_cost"]["facility_fixed_included"] is False,
      block=plain_ledger["facility_cost"])
check("summary facility_cost 块 source=costs.facility_cost",
      plain_ledger["facility_cost"]["source"] == "costs.facility_cost"
      and plain_ledger["facility_cost"]["k"] == 2)
check("summary 含 12h/36h 窗口两种折算",
      ledger_grid["k=2,min=1440.0"]["days"] == 1.0
      and ledger_grid["k=2,min=2160.0"]["days"] == 1.5)

# 5) 三类占位
pi1 = config(policy="full_open_ice_first", n_spaces=2, charging_bays=1, chargers=1)
pi1_sim = Simulation(pi1, [Arrival(0, 0.0, False, False, 10.0, 0.0),
                           Arrival(1, 1.0, False, False, 10.0, 0.0)])
pi1_sim.run()
pi1_occ = costs.occupancy_minutes(pi1_sim)
rules_ice = pi1_sim.type_occupancy()["metrics"]["ice_blocking_connector_min"]
check("π1 油车占枪单列 ice_blocking_connector=10 且与 rules 台账一致",
      close(pi1_occ["ice_blocking_connector"], 10.0) and close(pi1_occ["ice_blocking_connector"], rules_ice),
      occupancy=pi1_occ, rules=rules_ice)
check("π1 no_charging_demand 仅 EV（油车不再混入，=0）",
      close(pi1_occ["no_charging_demand"], 0.0), occupancy=pi1_occ)
pi0_sim = Simulation(config(policy="dedicated_by_type", n_spaces=2, charging_bays=1, chargers=1),
                     [Arrival(0, 0.0, False, False, 10.0, 0.0),
                      Arrival(1, 1.0, False, False, 10.0, 0.0)])
pi0_sim.run()
pi0_occ = costs.occupancy_minutes(pi0_sim)
check("π0 油车被拒，ice_blocking_connector=0", pi0_occ["ice_blocking_connector"] == 0.0, occupancy=pi0_occ)
ev_no_need = Simulation(config(charger_kw=7), [Arrival(0, 0.0, True, False, 30.0, 0.0)])
ev_no_need.run()
ev_occ = costs.occupancy_minutes(ev_no_need)
check("无充电需求 EV 占枪 30min 归 no_charging_demand",
      close(ev_occ["no_charging_demand"], 30.0) and ev_occ["ice_blocking_connector"] == 0.0,
      occupancy=ev_occ)
overstay = Simulation(config(charger_kw=7), [Arrival(0, 0.0, True, True, 60.0, 1.0)])
overstay.run()
overstay_occ = costs.occupancy_minutes(overstay)
check("充后滞留单列 overstay=60-60/7",
      close(overstay_occ["overstay_after_complete"], 60.0 - 60.0 / 7.0, 1e-6),
      occupancy=overstay_occ)
relocation = Simulation(
    config(n_spaces=2, charging_bays=1, chargers=1, charger_kw=7, feeder_kw=7, policy="strict",
           cost={"relocation_cost_per_move": 10.0}),
    [Arrival(0, 0.0, True, True, 50.0, 1.0)], intervention={"release_after_complete": True})
relocation.run()
relocation_occ = costs.occupancy_minutes(relocation)
relocation_res = costs.resource_minutes(relocation)
check("挪车释放后带枪位占用在 released_min 结束（connector=60/7，overstay=0）",
      close(relocation_res["connector_min"], 60.0 / 7.0, 1e-6)
      and relocation_occ["overstay_after_complete"] == 0.0,
      occupancy=relocation_occ, resources=relocation_res)
check("occupancy 输出键与 OCCUPANCY_REASONS 完全一致",
      set(ev_occ) == set(costs.OCCUPANCY_REASONS), keys=sorted(ev_occ))
check("旧键 deprecated 迁移映射：旧 no_charging_demand ≈ 新 EV + 油车",
      close(costs.legacy_no_charging_demand(
          {"no_charging_demand": 4.0, "ice_blocking_connector": 6.0}), 10.0)
      and costs.DEPRECATED_OCCUPANCY_KEY_MAP["no_charging_demand"]["replacement"]
      == ("no_charging_demand", "ice_blocking_connector")
      and "迁移" in costs.occupancy_minutes.__doc__)

# 6) cost_report 调用处：唯一入口与导出字段
report_sim = Simulation(config(), [])
report_sim.run()
report = costs.cost_report(report_sim)
check("cost_report 通过 facility_cost 计算且导出 façade 块",
      report["facility_cost"]["source"] == "costs.facility_cost"
      and close(report["items"]["operator_capital_depreciation"], 2 * 1000.0 / 24.0)
      and report["facility_cost"]["k"] == 2,
      facility_cost=report["facility_cost"], capital=report["items"]["operator_capital_depreciation"])
check("cost_report assumptions 写明唯一入口与三类占位口径",
      "facility_cost" in report["assumptions"]["facility_cost_entry"]
      and "ice_blocking_connector" in report["assumptions"]["occupancy_attribution"],
      assumptions=report["assumptions"])

result = {
    "schema": "r2a_cost_occupancy_validation/v1",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "version_tag": "round2-20261031-cost-occupancy",
    "command": "python research/round2_20261031/cost_outcomes/verify_fix.py "
               "research/round2_20261031/cost_outcomes/after_validation.json",
    "interpreter": sys.version,
    "source_sha256": {
        "apps/parking_lab/workbench/costs.py": sha256_file("apps/parking_lab/workbench/costs.py"),
        "apps/parking_lab/workbench/tests/test_costs.py": sha256_file(
            "apps/parking_lab/workbench/tests/test_costs.py"),
    },
    "scenario": {"device_params": SCENARIO, "capex_daily": CAPEX_DAILY, "device_daily": DEVICE_DAILY},
    "facility_grid": grid,
    "ledger_grid": ledger_grid,
    "cases": cases,
    "summary": {"passed": len(cases) - len(failures), "failed": len(failures), "total": len(cases)},
}
if len(sys.argv) > 1:
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
print("\nSUMMARY: %d/%d PASS, %d FAIL" % (
    result["summary"]["passed"], result["summary"]["total"], result["summary"]["failed"]))
sys.exit(1 if failures else 0)
