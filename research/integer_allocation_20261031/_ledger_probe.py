import sys, json
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案")
from apps.parking_lab.workbench.config import Config
from apps.parking_lab.workbench.simulation import Simulation
from apps.parking_lab.workbench.rules import type_occupancy_ledger
cfg = {"n_spaces":60,"charging_bays":8,"chargers":8,"reserve_fixed":0,"charger_kw":7,"feeder_kw":120,
       "duration_hours":12,"start_hour":7,"seed":42,"arrival_rate_hour":30,"ev_share":0.3,
       "charge_probability":0.3,"policy":"dedicated_by_type","cost":{}}
sim = Simulation(cfg); sim.run()
led = type_occupancy_ledger(sim.visits, sim.config, sim.horizon)
print("ledger type:", type(led).__name__)
print(json.dumps(led, ensure_ascii=False, default=str)[:1500])
visits = sim.visits
print("n visits", len(visits), "ev no-need", sum(1 for v in visits if v["is_ev"] and not v["needs_charge"]))
print("sample visit keys", list(visits[0].keys()))
