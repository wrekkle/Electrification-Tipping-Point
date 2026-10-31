# -*- coding: utf-8 -*-
"""Fixed-k EV/ICE trade-off re-selection for C and D (round 4).

For every train cell (seeds 1..3) at the dedicated rule's minimal k, re-run each C/D
configuration at exactly that k. This removes the k-step mismatch of the round-3 tuning
files and asks: conditional on the same device count, which configuration serves EV
capacity and ICE parking best? Selection is a Pareto/EV-first rule, not a weighted sum.
"""
from __future__ import annotations

import glob
import json
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research", "round3_20261031"))
import analyze_round3 as R3  # noqa: E402
from research.integer_allocation_20261031 import run_cost_curve as RC  # noqa: E402

PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
OUT = os.path.join(ROOT, "research", "round4_20261031", "results")
TRAIN = ["TPE0008", "TPE0401", "TPE0610", "TPE0695"]
SEEDS = (1, 2, 3)


def load(name):
    with open(os.path.join(R3.OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def a_k_map():
    doc = load("main_A_pi0_ref_s10.json")
    grouped = R3.group(doc["rows"])
    out = {}
    for lot in TRAIN:
        for seed in SEEDS:
            res = R3.joint_k(grouped.get((lot, seed), {}))
            if res["k"] is not None:
                out[(lot, seed)] = int(res["k"])
    return out


def cost_params():
    with open(COST, encoding="utf-8") as fh:
        doc = json.load(fh)
    block = doc.get("cost", doc)
    return {k: v for k, v in block.items() if v is not None or k in RC.FACILITY_KEYS}


def run_cell(lot, seed, k, rule, extra):
    with open(PARAMS, encoding="utf-8") as fh:
        params = json.load(fh)
    n_spaces = int(RC.lot_meta(params, lot)["n_spaces"])
    base = RC.build_base(n_spaces, 24.0, 11.5, 7.0, 336.0)
    base.update({"p_ev_override": 0.10, "q_need_override": 0.36, "demand_scale_override": None,
                 "scenario_model": "independent", "charge_provenance": None, "dwell_scale": 1.0,
                 "protected_bays": 0, "prediction_object": "charge_arrivals",
                 "coordinate_window": True, "ice_share_forecast_window_min": 30.0,
                 "ice_share_free_bay_margin": 1.0})
    base.update(extra)
    task = (lot, PARAMS, seed, [k], base, rule, cost_params(), "per_day")
    result = RC.run_lot_seed(task)
    if not result.get("ok"):
        raise RuntimeError(result.get("error"))
    return result["rows"][0]


def rates(row):
    return {"capacity_only_unmet_rate": row.get("capacity_only_unmet_rate"),
            "ev_parking_failure_rate": (row.get("service_metrics") or {}).get("rates", {}).get("ev_parking_failure_rate"),
            "ice_parking_failure_rate": (row.get("service_metrics") or {}).get("rates", {}).get("ice_parking_failure_rate")}


def mean_rates(rows):
    fields = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")
    out = {}
    for f in fields:
        vals = [r[f] for r in rows if r.get(f) is not None]
        out[f] = statistics.mean(vals) if vals else None
    return out


def configs():
    out = []
    for m in (0, 1, 2, 3, 4, 6, 8):
        out.append({"id": "C_m%d" % m, "rule": "protected_quota",
                    "extra": {"protected_bays": m}, "family": "C", "m": m})
    for path in sorted(glob.glob(os.path.join(R3.OUT, "tune_D_*_train_s123.json"))):
        name = os.path.basename(path)
        match = re.match(r"tune_D_(charge_arrivals|ev_arrivals|connector_load)_w(\d+)_m(\d+)_", name)
        obj, window, margin = match.group(1), int(match.group(2)), int(match.group(3))
        out.append({"id": "D_%s_w%d_m%d" % (obj, window, margin),
                    "rule": "predictive_shared_ice_first",
                    "extra": {"prediction_object": obj, "ice_share_forecast_window_min": float(window),
                              "ice_share_free_bay_margin": float(margin)},
                    "family": "D", "object": obj, "window": window, "margin": margin})
    return out


def main():
    ak = a_k_map()
    cells = sorted(ak)
    a_rows = {key: rates(run_cell(key[0], key[1], ak[key], "dedicated_by_type", {})) for key in cells}
    out = {"cells": [{"lot": k[0], "seed": k[1], "k": ak[k]} for k in cells],
           "A": mean_rates(list(a_rows.values())), "configs": {}, "pareto": []}
    for cfg in configs():
        rows = []
        for key in cells:
            row = run_cell(key[0], key[1], ak[key], cfg["rule"], cfg["extra"])
            rows.append(rates(row))
        out["configs"][cfg["id"]] = dict(cfg, rates=mean_rates(rows))
    ids = list(out["configs"])
    # Pareto on (capacity unmet, ICE failure), both minimized.
    for i in ids:
        ri = out["configs"][i]["rates"]
        dominated = False
        for j in ids:
            if i == j:
                continue
            rj = out["configs"][j]["rates"]
            if all(rj[f] is not None and ri[f] is not None for f in ("capacity_only_unmet_rate", "ice_parking_failure_rate")):
                if (rj["capacity_only_unmet_rate"] <= ri["capacity_only_unmet_rate"] + 1e-12
                        and rj["ice_parking_failure_rate"] <= ri["ice_parking_failure_rate"] + 1e-12
                        and (rj["capacity_only_unmet_rate"] < ri["capacity_only_unmet_rate"] - 1e-12
                             or rj["ice_parking_failure_rate"] < ri["ice_parking_failure_rate"] - 1e-12)):
                    dominated = True
                    break
        if not dominated:
            out["pareto"].append(i)
    a = out["A"]
    eligible = [i for i in ids if out["configs"][i]["rates"]["ice_parking_failure_rate"] is not None
                and a["ice_parking_failure_rate"] is not None
                and out["configs"][i]["rates"]["ice_parking_failure_rate"] <= a["ice_parking_failure_rate"] + 1e-12]
    out["ev_first_selection"] = min(
        eligible, key=lambda i: (out["configs"][i]["rates"]["capacity_only_unmet_rate"],
                                 out["configs"][i]["rates"]["ice_parking_failure_rate"])
    ) if eligible else None
    out["original_selection"] = {"C_m0": out["configs"].get("C_m0"),
                                 "D_charge_arrivals_w10_m0": out["configs"].get("D_charge_arrivals_w10_m0")}
    out["dominates_A"] = [i for i in ids if all(out["configs"][i]["rates"][f] is not None for f in
                                               ("capacity_only_unmet_rate", "ice_parking_failure_rate"))
                          and out["configs"][i]["rates"]["capacity_only_unmet_rate"] <= a["capacity_only_unmet_rate"] + 1e-12
                          and out["configs"][i]["rates"]["ice_parking_failure_rate"] <= a["ice_parking_failure_rate"] + 1e-12
                          and (out["configs"][i]["rates"]["capacity_only_unmet_rate"] < a["capacity_only_unmet_rate"] - 1e-12
                               or out["configs"][i]["rates"]["ice_parking_failure_rate"] < a["ice_parking_failure_rate"] - 1e-12)]
    with open(os.path.join(OUT, "tradeoff_fixedk.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"cells": len(cells), "configs": len(ids), "A": a,
                      "pareto": out["pareto"], "ev_first": out["ev_first_selection"],
                      "dominates_A": out["dominates_A"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
