"""第三轮分析：联合服务约束下的整数 k、Δk、配对区间、规则选择与条件误差。

只读 results/ 的曲线 JSON；所有结论按预登记口径（PREREGISTRATION.json）输出。
"""
from __future__ import annotations

import argparse
import glob
import re
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "research", "round3_20261031", "results")
TRAIN = ["TPE0008", "TPE0610", "TPE0401", "TPE0695", "TPE0330"]
VALID = ["TPE1376", "TPE0930", "TPE1171", "TPE1380"]
ALL9 = TRAIN + VALID
RULES = {"A_pi0": "dedicated_by_type", "B_pi1": "full_open_ice_first",
         "C_quota": "protected_quota", "D_pi2": "predictive_shared_ice_first"}
CONSTRAINTS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")
BOOT = 5000


def load(name):
    path = os.path.join(OUT, name)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_curve(tag, seeds_n):
    """主曲线 + 扩展到 k>40 的分场站结果（扩展文件存在时以其为准，覆盖该场站全部 k）。"""
    document = load("main_%s_ref_s%d.json" % (tag, seeds_n))
    rows = list(document["rows"])
    lots = []
    for path in sorted(glob.glob(os.path.join(OUT, "expand_%s_*_s%d.json" % (tag, seeds_n)))):
        extra = load(os.path.basename(path))
        covered = {row["lot_id"] for row in extra["rows"]}
        rows = [row for row in rows if row["lot_id"] not in covered] + list(extra["rows"])
        lots.extend(sorted(covered))
    document = dict(document)
    document["rows"] = rows
    document["expanded_lots"] = sorted(set(lots))
    return document


def group(rows):
    out = {}
    for row in rows:
        out.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    return out


def _rate(row, key):
    if key == "capacity_only_unmet_rate":
        return row.get(key)
    sm = row.get("service_metrics") or {}
    rates = sm.get("rates") or {}
    if key in rates:
        return rates[key]
    return row.get(key)


def joint_k(by_k, alpha=0.05):
    """联合约束下最小整数 k；None=不可行/缺数据。约束值为 None 视为不可判定并记录。"""
    ks = sorted(by_k)
    unknown = []
    last = ks[-1] if ks else None
    for k in ks:
        row = by_k[k]
        ok, vals = True, {}
        for name in CONSTRAINTS:
            value = _rate(row, name)
            vals[name] = value
            if value is None:
                unknown.append(name)
                continue
            if value > alpha + 1e-12:
                ok = False
                break
        if ok:
            return {"k": int(k), "status": "achieved", "k_max": last,
                    "rates": vals, "unknown_skipped": sorted(set(unknown)),
                    "evaluated": [int(x) for x in ks]}
    return {"k": None, "status": "infeasible_upper_bound", "k_max": last,
            "rates": {name: _rate(by_k[last], name) for name in CONSTRAINTS},
            "unknown_skipped": sorted(set(unknown)),
            "evaluated": [int(x) for x in ks]}


def lot_seed_joint(curve, tag=None):
    g = group(curve["rows"])
    out = {key: joint_k(by_k) for key, by_k in g.items()}
    path = os.path.join(OUT, "expansion_results.json")
    if tag and os.path.exists(path):
        cells = json.load(open(path, encoding="utf-8"))["cells"]
        for cell in cells:
            if cell["tag"] != tag or cell["status"] != "achieved":
                continue
            key = (cell["lot"], int(cell["seed"]))
            if key in out and out[key]["k"] is None:
                out[key] = {"k": int(cell["k"]), "status": "achieved",
                            "k_max": cell["k_max"], "rates": cell.get("rates_at_k"),
                            "unknown_skipped": [], "expanded_from": 40,
                            "evaluated": [40, cell["k"]]}
    return out


def summary(results):
    pairs = [r["k"] for r in results.values() if r["k"] is not None]
    if not pairs:
        return {"n": len(results), "achieved": 0, "infeasible": len(results)}
    ordered = sorted(pairs)
    return {"n": len(results), "achieved": len(pairs), "infeasible": len(results) - len(pairs),
            "min": ordered[0], "median": ordered[len(ordered) // 2],
            "max": ordered[-1], "mean": sum(ordered) / len(ordered)}


def delta_pairs(base, other):
    """同一 (场站, seed) 配对的 Δk = k_A − k_rule；不可行对单列。"""
    out, infeasible = [], 0
    for key, base_res in base.items():
        other_res = other.get(key)
        if other_res is None:
            continue
        if base_res["k"] is None or other_res["k"] is None:
            infeasible += 1
            continue
        out.append({"lot": key[0], "seed": key[1], "dk": base_res["k"] - other_res["k"],
                    "k_base": base_res["k"], "k_rule": other_res["k"]})
    return out, infeasible


def cluster_bootstrap(pairs, lots, draws=BOOT, seed=20261031):
    """按场站整块重采样（保留同一次重复的整条曲线），返回均值 Δk 的 95% 百分位区间。"""
    rng = random.Random(seed)
    by_lot = {}
    for p in pairs:
        by_lot.setdefault(p["lot"], []).append(p["dk"])
    available = [lot for lot in lots if lot in by_lot]
    if len(available) < 2:
        return None
    means = []
    for _ in range(draws):
        chosen = [rng.choice(available) for _ in available]
        values = [v for lot in chosen for v in by_lot[lot]]
        means.append(sum(values) / len(values))
    means.sort()
    lo = means[int(0.025 * (len(means) - 1))]
    hi = means[int(0.975 * (len(means) - 1))]
    return {"mean": sum(means) / len(means), "lo": lo, "hi": hi,
            "lots_resampled": len(available), "draws": draws,
            "note": "场站聚类配对 bootstrap；只重采样场站块，种子固定"}


def fixed_k_compare(ref, curve, k_ref_by_key):
    """在 A 的联合最小 k 上比较各规则的指标（固定 k 运营效应）。"""
    g = group(curve["rows"])
    diffs = {name: [] for name in CONSTRAINTS}
    diffs["departed_shortfall_energy_rate"] = []
    for key, k_ref in k_ref_by_key.items():
        row = (g.get(key) or {}).get(k_ref)
        base_row = (ref.get(key) or {}).get(k_ref)
        if row is None or base_row is None:
            continue
        for name in diffs:
            a, b = _rate(base_row, name), _rate(row, name)
            if a is not None and b is not None:
                diffs[name].append(b - a)
    return {name: (sum(v) / len(v) if v else None) for name, v in diffs.items()}, {
        name: len(v) for name, v in diffs.items()}


def _score(curve, lots):
    res = lot_seed_joint(curve)
    total, n_done, infeasible = 0, 0, 0
    for (lot, seed), r in res.items():
        if lot not in lots:
            continue
        if r["k"] is None:
            total += 100
            infeasible += 1
        else:
            total += r["k"]
        n_done += 1
    return {"sum_k": total, "cells": n_done, "infeasible": infeasible}


def select():
    out = {}
    best = None
    for path in sorted(glob.glob(os.path.join(OUT, "tune_C_m*_train_s123.json"))):
        m = int(os.path.basename(path).split("_m")[1].split("_")[0])
        score = _score(load(os.path.basename(path)), TRAIN)
        key = (score["sum_k"], m)
        if best is None or key < best[0]:
            best = (key, {"protected_bays": m, **score})
    out["C"] = best[1]
    best = None
    for path in sorted(glob.glob(os.path.join(OUT, "tune_D_*_train_s123.json"))):
        name = os.path.basename(path)
        match = re.match(r"tune_D_(.+)_w(\d+)_m(\d+)_train_s123\.json$", name)
        if not match:
            raise ValueError("无法解析调参文件名：" + name)
        obj, window, margin = match.group(1), float(match.group(2)), float(match.group(3))
        score = _score(load(name), TRAIN)
        key = (score["sum_k"], margin, window, obj)
        if best is None or key < best[0]:
            best = (key, {"prediction_object": obj, "window_min": window,
                          "margin": margin, **score})
    out["D"] = best[1]
    out["objective"] = "训练场站×种子的联合约束 k 之和最小（不可行记 100）；平局取更小 m/margin/window"
    out["train_lots"] = TRAIN
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds-n", type=int, default=10)
    parser.add_argument("--select", action="store_true")
    parser.add_argument("--plan-expansion", action="store_true")
    parser.add_argument("--validation", action="store_true")
    parser.add_argument("--scenarios", action="store_true")
    args = parser.parse_args(argv)
    document = {"source": "research/round3_20261031/run_experiments.py", "alpha": 0.05,
                "constraints": CONSTRAINTS}
    if args.select:
        selection = select()
        document["selection"] = selection
        with open(os.path.join(OUT, "selection.json"), "w", encoding="utf-8") as handle:
            json.dump(selection, handle, ensure_ascii=False, indent=1)
        print(json.dumps(selection, ensure_ascii=False))
        return 0
    if args.validation:
        document = {"mode": "validation", "lots": VALID, "alpha": 0.05,
                    "constraints": CONSTRAINTS, "curves": {}, "delta_k": {}}
        curves = {tag: lot_seed_joint(load("valid_%s_ref_s%d.json" % (tag, args.seeds_n)), tag)
                  for tag in RULES}
        document["curves"] = {tag: summary(res) for tag, res in curves.items()}
        base = curves["A_pi0"]
        for tag in ("B_pi1", "C_quota", "D_pi2"):
            pairs, infeasible = delta_pairs(base, curves[tag])
            dk = [p["dk"] for p in pairs]
            document["delta_k"][tag] = {
                "pairs": len(pairs), "infeasible_pairs": infeasible,
                "mean": (sum(dk) / len(dk)) if dk else None,
                "median": (sorted(dk)[len(dk) // 2] if dk else None),
                "positive": sum(1 for v in dk if v > 0),
                "zero": sum(1 for v in dk if v == 0),
                "negative": sum(1 for v in dk if v < 0),
                "cluster_bootstrap": cluster_bootstrap(pairs, VALID),
            }
        with open(os.path.join(OUT, "analysis_round3_validation.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=1)
        print(json.dumps({k: document[k] for k in ("curves", "delta_k")},
                         ensure_ascii=False, indent=1)[:3500])
        return 0
    if args.scenarios:
        document = {"mode": "scenario_rules", "alpha": 0.05,
                    "constraints": CONSTRAINTS, "results": {}}
        for label in ("low", "high"):
            curves = {tag: lot_seed_joint(
                load("rulespq_%s_%s_s123.json" % (label, tag))) for tag in RULES}
            block = {"curves": {tag: summary(res) for tag, res in curves.items()},
                     "delta_k": {}}
            for tag in ("B_pi1", "C_quota", "D_pi2"):
                pairs, infeasible = delta_pairs(curves["A_pi0"], curves[tag])
                dk = [p["dk"] for p in pairs]
                block["delta_k"][tag] = {
                    "pairs": len(pairs), "infeasible_pairs": infeasible,
                    "mean": (sum(dk) / len(dk)) if dk else None,
                    "positive": sum(1 for v in dk if v > 0),
                    "zero": sum(1 for v in dk if v == 0),
                    "negative": sum(1 for v in dk if v < 0),
                }
            document["results"][label] = block
        with open(os.path.join(OUT, "analysis_round3_scenarios.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=1)
        print(json.dumps(document["results"], ensure_ascii=False, indent=1)[:3000])
        return 0
    if args.plan_expansion:
        selection = load("selection.json")
        plan = []
        for tag in RULES:
            curve = load_curve(tag, args.seeds_n)
            res = lot_seed_joint(curve)
            n_spaces = {row["lot_id"]: int(row["n_spaces"]) for row in curve["rows"]}
            for (lot, seed), r in sorted(res.items()):
                if r["k"] is None and r["k_max"] < min(n_spaces.get(lot, 40), 200):
                    name = "expand_%s_%s_s%d" % (tag, lot, args.seeds_n)
                    if any(p["name"] == name for p in plan):
                        continue
                    plan.append({"name": name, "tag": tag, "rule": RULES[tag], "lot": lot,
                                 "seeds_n": args.seeds_n, "k_max": min(n_spaces.get(lot, 40), 200),
                                 "selection": selection})
        with open(os.path.join(OUT, "expansion_plan.json"), "w", encoding="utf-8") as handle:
            json.dump(plan, handle, ensure_ascii=False, indent=1)
        print(json.dumps(plan, ensure_ascii=False)[:2000])
        return 0
    curves = {}
    for tag in RULES:
        curves[tag] = lot_seed_joint(load_curve(tag, args.seeds_n), tag)
    document["curves"] = {tag: summary(res) for tag, res in curves.items()}
    base = curves["A_pi0"]
    k_ref = {key: res["k"] for key, res in base.items() if res["k"] is not None}
    document["delta_k"] = {}
    for tag in ("B_pi1", "C_quota", "D_pi2"):
        pairs, infeasible = delta_pairs(base, curves[tag])
        dk = [p["dk"] for p in pairs]
        document["delta_k"][tag] = {
            "pairs": len(pairs), "infeasible_pairs": infeasible,
            "mean": (sum(dk) / len(dk)) if dk else None,
            "median": (sorted(dk)[len(dk) // 2] if dk else None),
            "positive": sum(1 for v in dk if v > 0), "zero": sum(1 for v in dk if v == 0),
            "negative": sum(1 for v in dk if v < 0),
            "by_lot_seed": pairs,
            "cluster_bootstrap": cluster_bootstrap(pairs, ALL9),
        }
    document["fixed_k"] = {}
    ref_rows = group(load_curve("A_pi0", args.seeds_n)["rows"])
    for tag in ("B_pi1", "C_quota", "D_pi2"):
        diffs, counts = fixed_k_compare(ref_rows, load_curve(tag, args.seeds_n), k_ref)
        document["fixed_k"][tag] = {"mean_diff_rule_minus_pi0": diffs, "pairs": counts}
    # 选择偏差：预定场站×种子全计入
    document["selection_bias"] = {}
    for tag, res in curves.items():
        values = list(res.values())
        document["selection_bias"][tag] = {
            "planned_cells": len(values),
            "achieved_cells": sum(1 for r in res.values() if r["k"] is not None),
            "infeasible_cells": sum(1 for r in res.values() if r["k"] is None),
            "achieved_lots": len({key[0] for key, r in res.items() if r["k"] is not None}),
            "planned_lots": len({key[0] for key in res}),
        }
    with open(os.path.join(OUT, "analysis_round3.json"), "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    print(json.dumps({k: document[k] for k in ("curves", "delta_k", "selection_bias")},
                     ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
