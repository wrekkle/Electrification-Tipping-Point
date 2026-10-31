import sys, json
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案")
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031")
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.simulation import Simulation
from apps.parking_lab.workbench.rules import type_occupancy_ledger
import run_cost_curve as runner

base = runner.build_base(60, 12.0, 7.0, 7.0, 120.0)
base.update({"arrival_rate_hour": 30.0, "ev_share": 0.25, "charge_probability": 0.3})
for k in (0, 4, 12):
    cfg = dict(base); cfg["charging_bays"] = k; cfg["chargers"] = k; cfg["reserve_fixed"] = 0; cfg["policy"] = "dedicated_by_type"; cfg["cost"] = {}
    sim = Simulation(cfg)
    sim.run()
    metrics = sim.snapshot()["metrics"]
    extra = runner._visit_metrics(sim)
    ledger = type_occupancy_ledger(sim.visits, sim.config, sim.horizon)
    print("k=", k, "hash=", sim.traffic_hash[:12], "reject=", extra["rejected_total"],
          "unserved=", extra["unserved_charge_events"], "unserved_kwh=", round(extra["unserved_charge_energy_kwh"],1),
          "delivered=", round(extra["delivered_energy_kwh"],1), "typeocc=",
          {key: round(ledger.get(key) or 0, 1) for key in ("no_charging_demand_bay_min", "overstay_after_complete_min", "ice_blocking_connector_min")},
          "cost_complete=", metrics.get("cost_complete"), "total=", metrics.get("total_cost"))
print("facility", runner.facility_cost_per_period(12, {}))
print("facility2", runner.facility_cost_per_period(12, {"depreciation_capex": 60000.0, "depreciation_life_years": 8, "maintenance_per_bay_day": 5.0}))
