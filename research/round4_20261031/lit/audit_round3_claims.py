"""R4 第三轮主张审查：以 round3 结果 JSON 复算分母/配对/调参/区间证据。

只读 research/round3_20261031/results/ 与 evidence；不改任何第三轮文件。
输出 round3_claims_audit.json（同目录），供 round3_claims_audit.md 引用。
"""
import json
import os
import statistics
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
R3 = os.path.abspath(os.path.join(HERE, "..", "..", "round3_20261031", "results"))
ALPHA = 0.05
CONS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")
RATE_KEYS = CONS + ("departed_shortfall_energy_rate",)


def load(name):
    with open(os.path.join(R3, name), encoding="utf-8") as fh:
        return json.load(fh)


def rate(row, key):
    if key == "capacity_only_unmet_rate":
        return row.get(key)
    value = ((row.get("service_metrics") or {}).get("rates") or {}).get(key)
    return value if value is not None else row.get(key)


def group(rows):
    out = defaultdict(dict)
    for row in rows:
        out[(row["lot_id"], int(row["seed"]))][int(row["k"])] = row
    return out


def expansion_map(data):
    out = {}
    for cell in data["cells"]:
        if cell.get("status") != "achieved":
            continue
        key = (cell["tag"], cell["lot"], int(cell["seed"]))
        prev = out.get(key)
        if prev is None or cell["k"] < prev:
            out[key] = int(cell["k"])
    return out


EXPAND = expansion_map(load("expansion_results.json"))
TAG = {"A_pi0": "A_pi0", "B_pi1": "B_pi1", "C_quota": "C_quota", "D_pi2": "D_pi2"}


def joint_k(curve, tag):
    out = {}
    for key, by_k in group(curve["rows"]).items():
        chosen = None
        for k in sorted(by_k):
            row = by_k[k]
            vals = [rate(row, name) for name in CONS]
            if all(v is None or v <= ALPHA + 1e-12 for v in vals):
                chosen = int(k)
                break
        if chosen is None:
            exp = EXPAND.get((tag, key[0], key[1]))
            if exp is not None:
                chosen = exp
        out[key] = chosen
    return out


def deltas(base, other):
    pairs, missing = [], []
    for key, kb in base.items():
        ko = other.get(key)
        if kb is None or ko is None:
            missing.append({"lot": key[0], "seed": key[1],
                            "k_base": kb, "k_rule": ko,
                            "base_feasible": kb is not None, "rule_feasible": ko is not None})
            continue
        pairs.append({"lot": key[0], "seed": key[1], "dk": kb - ko, "k_base": kb, "k_rule": ko})
    return pairs, missing


def summarise_pairs(pairs):
    dks = [p["dk"] for p in pairs]
    per_lot = defaultdict(list)
    for p in pairs:
        per_lot[p["lot"]].append(p["dk"])
    return {
        "pairs": len(pairs),
        "positive": sum(1 for d in dks if d > 0),
        "zero": sum(1 for d in dks if d == 0),
        "negative": sum(1 for d in dks if d < 0),
        "mean": (sum(dks) / len(dks)) if dks else None,
        "median": statistics.median(dks) if dks else None,
        "min": min(dks) if dks else None,
        "nonzero_pairs": [p for p in pairs if p["dk"] != 0],
        "per_lot": {lot: {"n": len(v), "mean": sum(v) / len(v), "values": v} for lot, v in per_lot.items()},
    }


def fixed_k_effect(ref, curve, ks):
    g_ref, g = group(ref["rows"]), group(curve["rows"])
    num = {"capacity_unmet_requests": 0.0, "ev_parking_failures": 0.0, "ice_parking_failures": 0.0}
    den = {"exogenous_charge_requests": 0.0, "exogenous_ev_visits": 0.0, "exogenous_ice_visits": 0.0}
    rate_diffs = {name: [] for name in RATE_KEYS}
    pairs = 0
    for (lot, seed), k_ref in ks.items():
        if k_ref is None:
            continue
        base_row = (g_ref.get((lot, seed)) or {}).get(k_ref)
        row = (g.get((lot, seed)) or {}).get(k_ref)
        if base_row is None or row is None:
            continue
        pairs += 1
        for name in RATE_KEYS:
            a, b = rate(base_row, name), rate(row, name)
            if a is not None and b is not None:
                rate_diffs[name].append(b - a)
        sm_base = base_row.get("service_metrics") or {}
        sm = row.get("service_metrics") or {}
        nb, n = sm_base.get("numerators") or {}, sm.get("numerators") or {}
        db, d = sm_base.get("denominators") or {}, sm.get("denominators") or {}
        for label, key in (("capacity_unmet_requests", "capacity_unmet_requests"),
                           ("ev_parking_failures", "ev_parking_failures"),
                           ("ice_parking_failures", "ice_parking_failures")):
            if key in n and key in nb:
                num[label] += n[key] - nb[key]
        for label, key in (("exogenous_charge_requests", "exogenous_charge_requests"),
                           ("exogenous_ev_visits", "exogenous_ev_visits"),
                           ("exogenous_ice_visits", "exogenous_ice_visits")):
            if key in d and key in db:
                den[label] += d[key]
    return {
        "pairs": pairs,
        "mean_rate_diff_pp": {name: (sum(v) / len(v) * 100 if v else None) for name, v in rate_diffs.items()},
        "pairs_rate_defined": {name: len(v) for name, v in rate_diffs.items()},
        "delta_counts_total": num,
        "denominators_total": den,
        "pooled_pp": {
            "capacity_unmet_rate": (num["capacity_unmet_requests"] / den["exogenous_charge_requests"] * 100
                                    if den["exogenous_charge_requests"] else None),
            "ev_parking_failure_rate": (num["ev_parking_failures"] / den["exogenous_ev_visits"] * 100
                                        if den["exogenous_ev_visits"] else None),
            "ice_parking_failure_rate": (num["ice_parking_failures"] / den["exogenous_ice_visits"] * 100
                                         if den["exogenous_ice_visits"] else None),
        },
    }


def tune_scores(pattern, extra_key):
    scores = []
    for name in sorted(os.listdir(R3)):
        if not (name.startswith(pattern) and name.endswith(".json")):
            continue
        data = load(name)
        ks = joint_k(data, None)  # 调参曲线无扩展，tag=None 查不到扩展即可
        total = 0
        infeasible = 0
        cells = 0
        for (_lot, _seed), k in ks.items():
            cells += 1
            if k is None:
                infeasible += 1
                total += 100
            else:
                total += k
        scores.append({"file": name, **extra_key(name), "sum_k": total,
                       "cells": cells, "infeasible": infeasible})
    return scores


def main():
    out = {"source": R3, "alpha": ALPHA, "expansion_cells_used": len(EXPAND)}

    main_curves = {tag: load(f"main_{tag}_ref_s10.json") for tag in TAG}
    joint = {tag: joint_k(curve, tag) for tag, curve in main_curves.items()}
    out["curves"] = {tag: {"cells": len(ks),
                           "feasible": sum(1 for v in ks.values() if v is not None),
                           "infeasible_cells": sorted([list(k) + [v] for k, v in ks.items() if v is None])}
                     for tag, ks in joint.items()}

    base = joint["A_pi0"]
    out["deltas"] = {}
    for tag in ("B_pi1", "C_quota", "D_pi2"):
        pairs, missing = deltas(base, joint[tag])
        out["deltas"][tag] = {"summary": summarise_pairs(pairs), "unpaired": missing}
    # 关键：A 不可行但共享规则可行的单元（若存在即为未观测的正 Δk 方向证据）
    out["hidden_positive_cells"] = []
    for tag in ("B_pi1", "D_pi2"):
        for key, ka in base.items():
            if ka is not None:
                continue
            k_rule = joint[tag].get(key)
            if k_rule is not None:
                out["hidden_positive_cells"].append({"rule": tag, "lot": key[0], "seed": key[1],
                                                     "k_base": None, "k_rule": k_rule})

    out["fixed_k"] = {tag: fixed_k_effect(main_curves["A_pi0"], main_curves[tag], base)
                      for tag in ("B_pi1", "D_pi2")}
    out["fixed_k_anchor"] = ("k 取同一 (场站, seed) 的 π0 联合最小 k；同一条外生流配对，"
                             "不是用待评价规则的自身结果反选 k，也不是可提前部署的固定 k。")

    # 机制证据：π0 的 ICE 停车失败率是否与 k 无关（规则 π0 只让 ICE 用普通位）
    ice_by_cell = []
    for (lot, seed), by_k in group(main_curves["A_pi0"]["rows"]).items():
        vals = [rate(row, "ice_parking_failure_rate") for row in by_k.values()]
        vals = [v for v in vals if v is not None]
        if vals:
            ice_by_cell.append({"lot": lot, "seed": seed,
                                "min": min(vals), "max": max(vals), "spread": max(vals) - min(vals)})
    out["pi0_ice_rate_k_independence"] = {
        "cells": len(ice_by_cell),
        "cells_with_spread": sum(1 for c in ice_by_cell if c["spread"] > 1e-12),
        "max_spread": max((c["spread"] for c in ice_by_cell), default=None),
    }

    # 低/高需求情景（rulespq_*_s123）的 Δk，验证“无正 Δk”的网格范围
    out["scenarios"] = {}
    for scen in ("low", "high"):
        joint_scen = {}
        for tag, prefix in (("A_pi0", "A_pi0"), ("B_pi1", "B_pi1"), ("D_pi2", "D_pi2")):
            try:
                curve = load(f"rulespq_{scen}_{prefix}_s123.json")
            except FileNotFoundError:
                continue
            joint_scen[tag] = joint_k(curve, tag)
        if "A_pi0" not in joint_scen:
            continue
        entry = {"curves": {t: {"cells": len(v), "feasible": sum(1 for x in v.values() if x is not None)}
                            for t, v in joint_scen.items()}}
        for tag in ("B_pi1", "D_pi2"):
            if tag not in joint_scen:
                continue
            pairs, missing = deltas(joint_scen["A_pi0"], joint_scen[tag])
            entry[tag] = {"summary": {k: v for k, v in summarise_pairs(pairs).items()
                                      if k not in ("nonzero_pairs", "per_lot")},
                          "unpaired": missing}
        out["scenarios"][scen] = entry

    # C 调参：7 个 m 的得分；D 调参：27 个配置的得分与角点
    out["tune_C"] = tune_scores("tune_C_", lambda n: {"m": int(n.split("_m")[1].split("_")[0])})
    out["tune_D"] = tune_scores("tune_D_", lambda n: {
        "object": n.split("_")[2], "window": float(n.split("_w")[1].split("_")[0]),
        "margin": float(n.split("_m")[1].split("_")[0])})
    best_d = min(s["sum_k"] for s in out["tune_D"])
    out["tune_D_best"] = {"min_sum_k": best_d,
                          "ties": [s for s in out["tune_D"] if s["sum_k"] == best_d],
                          "at_grid_boundary": {"window": sorted({s["window"] for s in out["tune_D"]}),
                                               "margin": sorted({s["margin"] for s in out["tune_D"]})}}
    best_c = min(s["sum_k"] for s in out["tune_C"])
    out["tune_C_best"] = {"min_sum_k": best_c, "ties": [s for s in out["tune_C"] if s["sum_k"] == best_c]}

    # C m=0 是否与 B π1 行为完全一致（同一 k 下 service_metrics/numerators 相同）
    diff_cells = 0
    compared = 0
    gb = group(main_curves["B_pi1"]["rows"])
    gc = group(main_curves["C_quota"]["rows"])
    for key, by_k in gc.items():
        for k, row in by_k.items():
            other = (gb.get(key) or {}).get(k)
            if other is None:
                continue
            compared += 1
            if row.get("service_metrics") != other.get("service_metrics"):
                diff_cells += 1
    out["C_m0_equals_pi1"] = {"compared_cells": compared, "different_cells": diff_cells}

    # 验证集
    valid = {}
    for tag in ("A_pi0", "B_pi1", "D_pi2"):
        valid[tag] = joint_k(load(f"valid_{tag}_ref_s10.json"), tag)
    out["validation"] = {"curves": {t: {"cells": len(v),
                                        "feasible": sum(1 for x in v.values() if x is not None)}
                                    for t, v in valid.items()}}
    for tag in ("B_pi1", "D_pi2"):
        pairs, missing = deltas(valid["A_pi0"], valid[tag])
        summary = summarise_pairs(pairs)
        out["validation"][tag] = {"summary": summary, "unpaired": missing}
        # 去掉最大负值后的均值，检验区间是否由离群点驱动
        dks = sorted((p["dk"] for p in pairs))
        out["validation"][tag]["leave_one_out_mean"] = {
            "drop_min": (sum(dks[1:]) / len(dks[1:])) if len(dks) > 1 else None,
            "drop_max": (sum(dks[:-1]) / len(dks[:-1])) if len(dks) > 1 else None}

    os.makedirs(HERE, exist_ok=True)
    with open(os.path.join(HERE, "round3_claims_audit.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps({
        "curves": out["curves"],
        "deltas": {k: {kk: vv for kk, vv in v["summary"].items() if kk not in ("nonzero_pairs", "per_lot")}
                   for k, v in out["deltas"].items()},
        "hidden_positive_cells": out["hidden_positive_cells"],
        "fixed_k": out["fixed_k"],
        "tune_C_best": out["tune_C_best"],
        "tune_D_best": out["tune_D_best"],
        "C_m0_equals_pi1": out["C_m0_equals_pi1"],
        "validation": {t: ({kk: vv for kk, vv in v["summary"].items() if kk not in ("nonzero_pairs", "per_lot")}
                           if isinstance(v, dict) and "summary" in v else v) for t, v in out["validation"].items()},
    }, ensure_ascii=False, indent=1)[:12000])


if __name__ == "__main__":
    main()
