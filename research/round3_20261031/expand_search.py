"""对主曲线中未达成联合约束的 (规则,非场站,seed) 单元做定向扩展搜索。

不重跑整条曲线：从 k=41 起逐个 k 模拟，直到三个约束同时满足或到达 min(n_spaces,200)。
输出 research/round3_20261031/results/expansion_results.json：
  {"cells": [{"tag","rule","lot","seed","status","k","k_max","rates_at_k","checked"}...]}
状态：achieved（找到最小整数 k）/ cap_not_achieved（到上限仍未满足）/ missing。
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "research", "round3_20261031", "results")
PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
SEEDS = 10
RULES = {"A_pi0": ("dedicated_by_type", {}), "B_pi1": ("full_open_ice_first", {}),
         "C_quota": ("protected_quota", {"protected_bays": 0}),
         "D_pi2": ("predictive_shared_ice_first", {"prediction_object": "charge_arrivals",
                                                   "window": 10.0, "margin": 0.0})}
ALPHA = 0.05


def _rates(visits, n_initial):
    needs = [v for v in visits if v["vehicle_id"] >= n_initial and v["needs_charge"]]
    admitted_needs = [v for v in needs if v["admitted"]]
    rejected = [v for v in needs if not v["admitted"]]
    no_connector = [v for v in admitted_needs if v.get("charge_start_min") is None]
    ev = [v for v in visits if v["vehicle_id"] >= n_initial and v["is_ev"]]
    ice = [v for v in visits if v["vehicle_id"] >= n_initial and not v["is_ev"]]
    cap = ((len(rejected) + len(no_connector)) / len(needs)) if needs else None
    evf = (sum(1 for v in ev if not v["admitted"]) / len(ev)) if ev else None
    icef = (sum(1 for v in ice if not v["admitted"]) / len(ice)) if ice else None
    return {"capacity_only_unmet_rate": cap, "ev_parking_failure_rate": evf,
            "ice_parking_failure_rate": icef}


def _task(cell):
    from apps.parking_lab.workbench.config import Config
    from apps.parking_lab.workbench.simulation import Simulation
    from apps.parking_lab.workbench import traffic_gen
    tag, rule, lot, seed, n_spaces = cell
    params = json.load(open(PARAMS, encoding="utf-8"))
    arrivals, meta = traffic_gen.generate_for_lot(
        params, lot, seed, horizon_min=1440.0, p_ev=0.10, q_need=0.36,
        scenario_model="independent", strict=True)
    n_initial = int(meta.get("initial_occupancy_n") or 0)
    cap_max = min(int(n_spaces), 200)
    base = {"n_spaces": int(n_spaces), "charger_kw": 7.0, "feeder_kw": 336.0,
            "duration_hours": 24.0, "start_hour": 11.5, "interval_level": 0.9,
            "arrival_rate_hour": 0.0, "ev_share": 0.0, "charge_probability": 0.0,
            "policy": rule, "seed": int(seed), "prediction_object": "charge_arrivals",
            "coordinate_window": True, "protected_bays": 0,
            "ice_share_forecast_window_min": 10.0, "ice_share_free_bay_margin": 0.0}
    if rule == "protected_quota":
        base["protected_bays"] = 0
    if rule == "predictive_shared_ice_first":
        base["ice_share_forecast_window_min"] = 10.0
        base["ice_share_free_bay_margin"] = 0.0
    checked = []
    for k in range(41, cap_max + 1):
        config = dict(base)
        config["charging_bays"] = k
        config["chargers"] = k
        config["protected_bays"] = min(int(config.get("protected_bays", 0)), k)
        sim = Simulation(Config.parse(config), arrivals=arrivals)
        sim.run()
        rates = _rates(sim.visits, n_initial)
        checked.append({"k": k, **rates})
        if all(v is None or v <= ALPHA + 1e-12 for v in rates.values()):
            return {"tag": tag, "rule": rule, "lot": lot, "seed": seed, "status": "achieved",
                    "k": k, "k_max": cap_max, "rates_at_k": rates, "checked": checked[-5:]}
    last = checked[-1] if checked else None
    return {"tag": tag, "rule": rule, "lot": lot, "seed": seed,
            "status": "cap_not_achieved", "k": None, "k_max": cap_max,
            "rates_at_k": last, "checked": checked[-5:]}


def main():
    cells = []
    for tag in RULES:
        curve = json.load(open(os.path.join(OUT, "main_%s_ref_s10.json" % tag), encoding="utf-8"))
        grouped = {}
        for row in curve["rows"]:
            grouped.setdefault((row["lot_id"], int(row["seed"])), []).append(row)
        for (lot, seed), rows in sorted(grouped.items()):
            n_spaces = rows[0]["n_spaces"]
            requests = rows[0].get("charge_requests") or 0
            # 只对主曲线未达成的单元扩展：主曲线已由 analyze 判定；这里用同一显式条件重判
            ok_found = False
            for row in sorted(rows, key=lambda r: r["k"]):
                k = row["k"]
                sm = row.get("service_metrics") or {}
                ice_n = (row.get("arrivals") or 0) - (row.get("ev_arrivals") or 0)
                rates = [row.get("capacity_only_unmet_rate"),
                         (sm.get("rates") or {}).get("ev_parking_failure_rate"),
                         (sm.get("rates") or {}).get("ice_parking_failure_rate")]
                if all(v is None or v <= ALPHA + 1e-12 for v in rates):
                    ok_found = True
                    break
            if not ok_found and 40 < n_spaces:
                cells.append((tag, RULES[tag][0], lot, seed, n_spaces))
    print("expansion cells", len(cells), flush=True)
    with ProcessPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_task, cells))
    with open(os.path.join(OUT, "expansion_results.json"), "w", encoding="utf-8") as handle:
        json.dump({"alpha": ALPHA, "cells": results}, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"achieved": sum(1 for r in results if r["status"] == "achieved"),
                      "cap_not_achieved": sum(1 for r in results if r["status"] != "achieved"),
                      "k_values": sorted({r["k"] for r in results if r["k"]})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
