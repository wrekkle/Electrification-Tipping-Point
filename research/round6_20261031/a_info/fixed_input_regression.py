# -*- coding: utf-8 -*-
r"""固定输入回归探针：输出默认规则（I0）指标与逐车哈希，供 test_round6_info 固化。

命令：C:/anaconda/python.exe research/round6_20261031/a_info/fixed_input_regression.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

from apps.parking_lab.workbench.config import Config  # noqa: E402
from apps.parking_lab.workbench.demand import generate  # noqa: E402
from apps.parking_lab.workbench.simulation import Simulation  # noqa: E402

CONFIG = {
    "n_spaces": 10, "charging_bays": 3, "chargers": 2, "charger_kw": 7.0,
    "feeder_kw": 60.0, "duration_hours": 2.0, "start_hour": 8.0, "seed": 7,
    "arrival_rate_hour": 20.0, "ev_share": 0.5, "charge_probability": 0.6,
    "reserve_fixed": 0, "policy": "dedicated_by_type",
}
KEYS = ("total_cost", "peak_power_kw", "peak_occupancy", "charge_completion_rate_all",
        "unserved_charge_events", "unserved_charge_energy_kwh", "mean_occupancy_rate")


def main():
    config = Config.parse(CONFIG)
    arrivals = generate(config)
    sim = Simulation(config, arrivals=arrivals)
    sim.run()
    metrics = {key: sim.snapshot()["metrics"].get(key) for key in KEYS}
    visits = [[v["vehicle_id"], v["time_min"], v["is_ev"], v["needs_charge"],
               v["admitted"], v["bay"], round(v["delivered_kwh"], 9)] for v in sim.visits]
    digest = hashlib.sha256(json.dumps(visits, sort_keys=True).encode()).hexdigest()
    service = __import__("apps.parking_lab.workbench.service_metrics",
                         fromlist=["summarise"]).summarise(sim.visits, horizon_min=sim.horizon)
    out = {"config": CONFIG, "n_arrivals": len(arrivals),
           "demand_hash": sim.demand_hash, "traffic_hash": sim.traffic_hash,
           "metrics": metrics, "visits_sha256": digest,
           "rates": service["rates"],
           "denominators": service["denominators"]}
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
