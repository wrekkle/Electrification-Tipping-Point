import sys, json
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案")
from apps.parking_lab.workbench import traffic_gen
from apps.parking_lab.workbench.simulation import Simulation
params = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json", encoding="utf-8"))
arr, meta = traffic_gen.generate_for_lot(params, "TPE0151", 1)
print("n arrivals", len(arr), "meta n_ev", meta.get("n_ev"), "p_ev", meta.get("p_ev"), "q_need", meta.get("q_need"), "mean_dwell", round(meta.get("mean_dwell_min") or 0,1))
print("meta keys:", list(meta.keys()))
cfg = {"n_spaces":151,"charging_bays":3,"chargers":3,"reserve_fixed":0,"charger_kw":7,"feeder_kw":120,
       "duration_hours":24,"start_hour":11.5,"seed":1,"policy":"dedicated_by_type","cost":{}}
sim = Simulation(cfg, arrivals=arr); sim.run()
m = sim.snapshot()["metrics"]
print("sim mean_occ_rate", round(m["mean_occupancy_rate"],3), "peak_occ", m["peak_occupancy"], "arrivals", m["arrivals"], "delivered", round(m["energy_delivered_kwh"],1))
print("observed mean occ vehicles ~100.0 of 151 = 0.662")
hist = sim.history
for idx in (0, 60, 180, 360, 540, 720, 1080, 1380):
    if idx < len(hist): print(" t=", int(hist[idx]["time_min"]), "occ=", hist[idx]["occupancy"])
