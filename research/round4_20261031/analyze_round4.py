# -*- coding: utf-8 -*-
"""Round-4 analysis: source scenarios, fixed-k holdout, dwell sensitivity, EV/ICE trade-off.

Reads only saved result JSON. Every rate is computed from the same joint-constraint helper
used in round 3; EV and ICE denominators are kept separate (no pooled confidence interval).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
R4 = os.path.join(ROOT, "research", "round4_20261031")
RES = os.path.join(R4, "results")
sys.path.insert(0, os.path.join(ROOT, "research", "round3_20261031"))
import analyze_round3 as R3  # noqa: E402

TRAIN = ["TPE0008", "TPE0401", "TPE0610", "TPE0695", "TPE0330"]
CONSTRAINTS = R3.CONSTRAINTS


def load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def curve_stats(path):
    if not os.path.exists(path):
        return None
    doc = load(path)
    grouped = R3.group(doc["rows"])
    results = {key: R3.joint_k(by_k) for key, by_k in grouped.items()}
    return {"document": doc, "grouped": grouped, "results": results,
            "summary": R3.summary(results)}


def delta(rule_curve, base_curve, lots):
    pairs, infeasible = R3.delta_pairs(base_curve["results"], rule_curve["results"])
    ci = R3.cluster_bootstrap(pairs, lots) if pairs else None
    return {"pairs": len(pairs), "infeasible_pairs": infeasible,
            "mean": statistics.mean(p["dk"] for p in pairs) if pairs else None,
            "median": statistics.median(p["dk"] for p in pairs) if pairs else None,
            "positive": sum(1 for p in pairs if p["dk"] > 0),
            "zero": sum(1 for p in pairs if p["dk"] == 0),
            "negative": sum(1 for p in pairs if p["dk"] < 0),
            "min": min((p["dk"] for p in pairs), default=None),
            "max": max((p["dk"] for p in pairs), default=None),
            "ci": ci, "pairs_detail": pairs}


def scenario_analysis():
    scenarios = ["REF", "M08-NEAR-BEV", "M08-NEAR-COMBINED",
                 "M10-OUT-OF-HOME", "M08-ALL-AWAY-REF"]
    out = {"scenarios": {}, "k_shift_vs_ref": {}, "note": "Δk = k_A − k_rule within each scenario; infeasible pairs excluded and counted"}
    base_ref = {}
    for scenario in scenarios:
        curves = {}
        for tag in ("A", "B", "D"):
            curves[tag] = curve_stats(os.path.join(RES, "scenario_%s_%s_s5.json" % (scenario, tag)))
        if any(v is None for v in curves.values()):
            out["scenarios"][scenario] = {"missing": [t for t, v in curves.items() if v is None]}
            continue
        item = {"summaries": {tag: curves[tag]["summary"] for tag in curves},
                "delta": {tag: delta(curves[tag], curves["A"], TRAIN) for tag in ("B", "D")}}
        out["scenarios"][scenario] = item
        if scenario == "REF":
            base_ref = curves
        elif base_ref:
            shifts = {}
            for tag in ("A", "B", "D"):
                vals, infeasible = [], 0
                for key, ref_res in base_ref[tag]["results"].items():
                    other = curves[tag]["results"].get(key)
                    if other is None:
                        continue
                    if ref_res["k"] is None or other["k"] is None:
                        infeasible += 1
                        continue
                    vals.append(other["k"] - ref_res["k"])
                shifts[tag] = {"n": len(vals), "infeasible": infeasible,
                               "median": statistics.median(vals) if vals else None,
                               "mean": statistics.mean(vals) if vals else None,
                               "min": min(vals) if vals else None, "max": max(vals) if vals else None}
            out["k_shift_vs_ref"][scenario] = shifts
    return out


def _row_rates(row):
    return {name: R3._rate(row, name) for name in CONSTRAINTS}


def _feasible(row):
    vals = _row_rates(row)
    known = [v for v in vals.values() if v is not None]
    return bool(known) and all(v <= 0.05 + 1e-12 for v in known)


def _agg(rows):
    rates = {name: [] for name in CONSTRAINTS}
    rates["departed_shortfall_energy_rate"] = []
    for row in rows:
        for name in rates:
            value = R3._rate(row, name)
            if value is not None:
                rates[name].append(value)
    return {name: (statistics.mean(v) if v else None) for name, v in rates.items()}


def fixedk_analysis():
    manifest_path = os.path.join(RES, "fixedk", "fixedk_manifest.json")
    if not os.path.exists(manifest_path):
        return {"missing": manifest_path}
    manifest = load(manifest_path)
    out = {"selection": manifest["selection"], "selection_seeds": manifest["selection_seeds"],
           "evaluation_seeds": manifest["evaluation_seeds"], "own": {}, "common": {}}
    runs = manifest["runs"]
    own_cells = {}
    common_cells = {}
    for run in runs:
        doc = load(run["out"])
        for row in doc["rows"]:
            key = (run["rule"], run["lot"], int(row["seed"]))
            target = own_cells if run["mode"] == "own" else common_cells
            target.setdefault(key, []).append(row)
    by_rule = {}
    for (rule, lot, seed), rows in own_cells.items():
        by_rule.setdefault(rule, []).extend(rows)
    for rule, rows in sorted(by_rule.items()):
        out["own"][rule] = {"cells": len(rows),
                            "feasible": sum(1 for r in rows if _feasible(r)),
                            "rates": _agg(rows)}
    # common-k: B/D evaluated at A's k; compare to A's own-k row per lot/seed
    a_by_key = {(lot, seed): rows[0] for (rule, lot, seed), rows in own_cells.items() if rule == "A"}
    for rule in ("B", "D"):
        pairs = []
        for (rr, lot, seed), rows in common_cells.items():
            if rr != rule:
                continue
            a_row = a_by_key.get((lot, seed))
            if not a_row:
                continue
            row = rows[0]
            same_k = int(row["k"]) == int(a_row["k"])
            diff = {}
            for name in CONSTRAINTS:
                av, bv = R3._rate(a_row, name), R3._rate(row, name)
                diff[name] = (bv - av) if (av is not None and bv is not None) else None
            pairs.append({"lot": lot, "seed": seed, "same_k": same_k,
                          "A_feasible": _feasible(a_row), "rule_feasible": _feasible(row),
                          "rates_rule": _row_rates(row), "rates_A": _row_rates(a_row), "diff": diff})
        out["common"][rule] = {
            "cells": len(pairs),
            "same_k_cells": sum(1 for p in pairs if p["same_k"]),
            "A_feasible": sum(1 for p in pairs if p["A_feasible"]),
            "rule_feasible": sum(1 for p in pairs if p["rule_feasible"]),
            "mean_diff": {name: (statistics.mean([p["diff"][name] for p in pairs
                                                  if p["diff"][name] is not None])
                                 if any(p["diff"][name] is not None for p in pairs) else None)
                          for name in CONSTRAINTS},
            "rule_worse_capacity": sum(1 for p in pairs if (p["diff"].get("capacity_only_unmet_rate") or 0) > 0),
            "rule_better_ice": sum(1 for p in pairs if (p["diff"].get("ice_parking_failure_rate") or 0) < 0),
            "detail": pairs}
    return out


def dwell_analysis():
    scales = (0.8, 1.0, 1.2)
    out = {}
    ref = {}
    for scale in scales:
        curves = {}
        for tag in ("A", "B", "D"):
            path = os.path.join(RES, "dwell", "dwell_%s_%s_s3.json" % (scale, tag))
            curves[tag] = curve_stats(path)
        if any(v is None for v in curves.values()):
            out[str(scale)] = {"missing": [t for t, v in curves.items() if v is None]}
            continue
        item = {"summaries": {tag: curves[tag]["summary"] for tag in curves},
                "delta": {tag: delta(curves[tag], curves["A"], ["TPE0008", "TPE0401", "TPE0610"])
                          for tag in ("B", "D")}}
        out[str(scale)] = item
        if scale == 1.0:
            ref = curves
    if ref:
        for scale in (0.8, 1.2):
            curves = {}
            for tag in ("A", "B", "D"):
                path = os.path.join(RES, "dwell", "dwell_%s_%s_s3.json" % (scale, tag))
                curves[tag] = curve_stats(path)
            if any(v is None for v in curves.values()):
                continue
            shift = {}
            for tag in ("A", "B", "D"):
                vals = [curves[tag]["results"][key]["k"] - ref[tag]["results"][key]["k"]
                        for key in ref[tag]["results"] if key in curves[tag]["results"]
                        and ref[tag]["results"][key]["k"] is not None
                        and curves[tag]["results"][key]["k"] is not None]
                shift[tag] = {"n": len(vals), "median": statistics.median(vals) if vals else None,
                              "min": min(vals) if vals else None, "max": max(vals) if vals else None}
            out[str(scale)]["k_shift_vs_scale1"] = shift
    return out


def _tune_rows(pattern):
    rows = []
    for path in sorted(glob.glob(os.path.join(R3.OUT, pattern))):
        doc = load(path)
        name = os.path.basename(path)
        for row in doc["rows"]:
            rows.append({"config": name, "row": row})
    return rows


def tradeoff_analysis():
    fixed = os.path.join(RES, "tradeoff_fixedk.json")
    if os.path.exists(fixed):
        return {"source": fixed, "note": "exact fixed-k re-runs; C/D configurations at A's joint k",
                **load(fixed)}
    base_curve = load(os.path.join(R3.OUT, "main_A_pi0_ref_s10.json"))
    base_group = R3.group(base_curve["rows"])
    a_k = {}
    for (lot, seed), by_k in base_group.items():
        res = R3.joint_k(by_k)
        if res["k"] is not None:
            a_k[(lot, seed)] = res["k"]
    families = {"C": _tune_rows("tune_C_m*_train_s123.json"),
                "D": _tune_rows("tune_D_*_train_s123.json")}
    out = {"objective": "Pareto/EV-first at fixed k=A joint k, seeds 1..3, train lots only",
           "families": {}, "A": {}}
    a_rates = []
    for item in families["C"]:
        row = item["row"]
        key = (row["lot_id"], int(row["seed"]))
        if key not in a_k or int(row["k"]) != a_k[key]:
            continue
        a_rates.append(_row_rates(row))
    # A fixed-k rates from main curve (same k, all seeds 1..3)
    a_rows = [base_group[key][a_k[key]] for key in a_k if key in base_group and base_group[key].get(a_k[key])]
    a_rows = [r for r in a_rows if int(r["seed"]) <= 3]
    out["A"] = {"cells": len(a_rows), "rates": _agg(a_rows)}
    for family, items in families.items():
        by_config = {}
        for item in items:
            row = item["row"]
            key = (row["lot_id"], int(row["seed"]))
            if key not in a_k or int(row["k"]) != a_k[key] or int(row["seed"]) > 3:
                continue
            by_config.setdefault(item["config"], []).append(row)
        table = {}
        for config, rows in by_config.items():
            rates = _agg(rows)
            # Dominates A only if EV capacity <= A and ICE <= A (both known, one strict).
            dominates = (rates["capacity_only_unmet_rate"] is not None
                         and out["A"]["rates"]["capacity_only_unmet_rate"] is not None
                         and rates["ice_parking_failure_rate"] is not None
                         and out["A"]["rates"]["ice_parking_failure_rate"] is not None
                         and rates["capacity_only_unmet_rate"] <= out["A"]["rates"]["capacity_only_unmet_rate"] + 1e-12
                         and rates["ice_parking_failure_rate"] <= out["A"]["rates"]["ice_parking_failure_rate"] + 1e-12
                         and (rates["capacity_only_unmet_rate"] < out["A"]["rates"]["capacity_only_unmet_rate"] - 1e-12
                              or rates["ice_parking_failure_rate"] < out["A"]["rates"]["ice_parking_failure_rate"] - 1e-12))
            table[config] = {"cells": len(rows), "rates": rates, "dominates_A": dominates}
        out["families"][family] = table
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description="round4 分析")
    parser.add_argument("--out", default=os.path.join(RES, "analysis_round4.json"))
    args = parser.parse_args(argv)
    payload = {"scenario": scenario_analysis(), "fixedk": fixedk_analysis(),
               "dwell": dwell_analysis(), "tradeoff": tradeoff_analysis()}
    os.makedirs(RES, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(json.dumps({"out": args.out,
                      "scenario_count": len(payload["scenario"]),
                      "fixedk_own": list(payload["fixedk"].get("own", {})),
                      "dwell_scales": list(payload["dwell"]),
                      "tradeoff_families": list(payload["tradeoff"].get("families", {}))},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
