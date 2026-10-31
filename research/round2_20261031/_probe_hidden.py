import sys, traceback
sys.path.insert(0, r"C:\Projects\停车场充电桩优化方案")
from apps.parking_lab.workbench.demand import Arrival
from apps.parking_lab.workbench.simulation import Simulation
def decisions(needs_flags):
    arrivals = [Arrival(i, 5.0*i, True, n, 60.0, 20.0) for i, n in enumerate(needs_flags)]
    sim = Simulation({"n_spaces": 4, "charging_bays": 2, "chargers": 2, "charger_kw": 7.0, "feeder_kw": 120.0,
                      "duration_hours": 4.0, "start_hour": 11.5, "interval_level": 0.9, "arrival_rate_hour": 0.0,
                      "ev_share": 0.0, "charge_probability": 0.0, "policy": "dedicated_by_type",
                      "reserve_fixed": 0, "seed": 1}, arrivals=tuple(arrivals))
    sim.run()
    return [(v["time_min"], v["is_ev"], v["admitted"], v["bay"]) for v in sim.visits]
try:
    print(decisions([True, False, True]))
    print(decisions([False, True, True]))
except Exception:
    traceback.print_exc()
