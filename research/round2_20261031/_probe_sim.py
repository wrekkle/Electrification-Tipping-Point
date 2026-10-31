import sys
sys.path.insert(0, r"C:\Projects\停车场充电桩优化方案")
from apps.parking_lab.workbench.demand import Arrival
from apps.parking_lab.workbench.simulation import Simulation
base = {"n_spaces": 4, "charging_bays": 2, "chargers": 2, "charger_kw": 7.0, "feeder_kw": 120.0,
        "duration_hours": 4.0, "start_hour": 11.5, "interval_level": 0.9,
        "arrival_rate_hour": 0.0, "ev_share": 0.0, "charge_probability": 0.0,
        "policy": "dedicated_by_type", "reserve_fixed": 0, "seed": 1}
for label, arrivals in {
    "t0": [Arrival(i, 5.0 * i, True, True, 60.0, 20.0) for i in range(5)],
    "t10": [Arrival(i, 10.0 + 5.0 * i, True, True, 60.0, 20.0) for i in range(5)],
    "dwell2": [Arrival(i, 10.0 + 5.0 * i, True, True, 2.0, 20.0) for i in range(5)],
}.items():
    try:
        sim = Simulation(dict(base), arrivals=tuple(arrivals)); sim.run()
        print(label, "OK", len(sim.visits))
    except Exception as error:
        print(label, type(error).__name__, str(error)[:300])
