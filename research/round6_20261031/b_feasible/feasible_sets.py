# -*- coding: utf-8 -*-
r"""Q3：由既有完整 k=0..40 曲线计算可行配置集合 K_(pi) 的形状与跨规则关系。

只读 round3/round4 既有 JSON；不重跑仿真。语义按 round5 review/none_semantics_4way
（A 的 service_semantics.py 尚未就绪，本脚本等价实现并注明）。
命令：C:/anaconda/python.exe research/round6_20261031/b_feasible/feasible_sets.py
输出：q3_feasible_sets.json
"""
from __future__ import annotations
import glob, hashlib, json, math, sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ALPHA = 0.05
EPS = 1e-12
K_MAX = 40
CONSTRAINTS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")
NA = "not_applicable_zero_demand"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classify(row, name):
    """"valid"/"not_applicable_zero_demand"/"missing"/"illegal"（等价 none_semantics_4way）。"""
    if name == "capacity_only_unmet_rate":
        value, den = row.get(name), row.get("charge_requests")
        source = "row.capacity_only_unmet_rate/row.charge_requests"
    else:
        sm = row.get("service_metrics") or {}
        rates = sm.get("rates") or {}
        dens = sm.get("denominators") or {}
        den_key = {"ev_parking_failure_rate": "exogenous_ev_visits",
                   "ice_parking_failure_rate": "exogenous_ice_visits"}[name]
        value, den = rates.get(name), dens.get(den_key)
        source = "service_metrics.rates.%s/denominators.%s" % (name, den_key)
    if value is None:
        if not isinstance(den, (int, float)) or isinstance(den, bool) or not math.isfinite(float(den)):
            return {"status": "missing", "value": None, "denominator": den, "source": source}
        if float(den) <= 0.0:
            return {"status": NA, "value": None, "denominator": den, "source": source}
        return {"status": "missing", "value": None, "denominator": den, "source": source}
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
        return {"status": "illegal", "value": value, "denominator": den, "source": source}
    if value < -EPS or value > 1.0 + EPS:
        return {"status": "illegal", "value": float(value), "denominator": den, "source": source}
    return {"status": "valid", "value": float(value), "denominator": den, "source": source}


def judge(row):
    cells = {name: classify(row, name) for name in CONSTRAINTS}
    strict = all(c["status"] == "valid" and c["value"] <= ALPHA + EPS for c in cells.values())
    inclusive = all((c["status"] == "valid" and c["value"] <= ALPHA + EPS) or c["status"] == NA
                    for c in cells.values())
    undecidable = any(c["status"] in ("missing", "illegal") for c in cells.values())
    return {"cells": cells, "strict": strict, "inclusive": inclusive, "undecidable": undecidable}


def shape(ks, judged):
    feasible = [k for k in ks if judged[k]["inclusive"]]
    strict = [k for k in ks if judged[k]["strict"]]
    gaps = []
    for a, b in zip(feasible, feasible[1:]):
        if b != a + 1:
            gaps.append([a, b])
    info = {
        "k_values": ks[:1] + ks[-1:], "n_k": len(ks), "K": feasible, "K_strict": strict,
        "n_feasible": len(feasible), "empty_set": not feasible,
        "is_interval": bool(feasible) and not gaps, "gaps": gaps,
        "min_known_feasible": feasible[0] if feasible else None,
        "max_known_feasible": feasible[-1] if feasible else None,
        "truncated_at_kmax": bool(feasible) and feasible[-1] == ks[-1],
        "n_undecidable": sum(1 for k in ks if judged[k]["undecidable"]),
        "capacity_na_all_k": all(judged[k]["cells"]["capacity_only_unmet_rate"]["status"] == NA for k in ks),
        "strict_empty_inclusive_nonempty": (not strict) and bool(feasible),
        "unknown_beyond_kmax": not feasible,
    }
    mk = info["min_known_feasible"]
    if mk is None:
        info["confirmed_minimal"] = False
    elif mk == ks[0]:
        info["confirmed_minimal"] = True
    else:
        lower = judged.get(mk - 1)
        info["confirmed_minimal"] = bool(lower) and not lower["inclusive"] and not lower["undecidable"]
    return info


def load_curves():
    specs = []
    for tag in ("A_pi0", "B_pi1", "C_quota", "D_pi2"):
        path = ROOT / "research" / "round3_20261031" / "results" / ("main_%s_ref_s10.json" % tag)
        doc = json.loads(path.read_text(encoding="utf-8"))
        specs.append({"id": "round3/main_%s_ref_s10" % tag, "class": "round3_ref", "rule": tag.split("_")[0],
                      "scenario": "REF", "rows": doc["rows"], "path": str(path.relative_to(ROOT)),
                      "meta": doc.get("meta", {}), "sha256": sha(path)})
    for path in sorted(glob.glob(str(ROOT / "research" / "round4_20261031" / "results" / "scenario_*_s5.json"))):
        p = Path(path)
        if "manifest" in p.name:
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        parts = p.stem.split("_")
        scen, rule = "_".join(parts[1:-2]), parts[-2]
        specs.append({"id": "round4/" + p.stem, "class": "round4_scenario", "rule": rule,
                      "scenario": scen, "rows": doc["rows"], "path": str(p.relative_to(ROOT)),
                      "meta": doc.get("meta", {}), "sha256": sha(p)})
    return specs


def main():
    specs = load_curves()
    groups = {}
    for spec in specs:
        for row in spec["rows"]:
            key = (spec["scenario"], spec["rule"], row["lot_id"], int(row["seed"]))
            groups.setdefault(key, {})[int(row["k"])] = row
    sets, examples = {}, {}
    for key, by_k in sorted(groups.items()):
        ks = sorted(by_k)
        if ks != list(range(0, K_MAX + 1)):
            continue
        judged = {k: judge(by_k[k]) for k in ks}
        sets[key] = shape(ks, judged)
        examples[key] = {k: {"cells": judged[k]["cells"], "undecidable": judged[k]["undecidable"]}
                         for k in ks if judged[k]["undecidable"]}
    # TPE0330 k>40 扩展（只作预算截断记录，不并入 [0,40] 的 K）
    expansion = {"path": "research/round3_20261031/results/expand_A_pi0_TPE0330_s10.json"}
    exp_path = ROOT / expansion["path"]
    if exp_path.exists():
        exp_rows = json.loads(exp_path.read_text(encoding="utf-8"))["rows"]
        by_seed = {}
        for row in exp_rows:
            if int(row["k"]) > K_MAX:
                by_seed.setdefault(int(row["seed"]), {})[int(row["k"])] = row
        cells = []
        for seed, by_k in sorted(by_seed.items()):
            ks = sorted(by_k)
            judged = {k: judge(by_k[k]) for k in ks}
            first = next((k for k in ks if judged[k]["inclusive"]), None)
            cells.append({"seed": seed, "k_min_beyond_40": first, "k_max_tested": ks[-1],
                          "empty_beyond_40": first is None,
                          "budget_truncated_above": ks[-1]})
        expansion.update({"sha256": sha(exp_path), "cells": cells})
    # 跨规则成对：包含/互不包含/四类可行配对/恢复/省设备/同 k 改善
    by_cell = {}
    for (scen, rule, lot, seed), info in sets.items():
        by_cell.setdefault((scen, lot, seed), {})[rule] = info
    pairs = {}
    for (scen, lot, seed), rules in sorted(by_cell.items()):
        for a, b in combinations(sorted(rules), 2):
            A, B = rules[a], rules[b]
            ka, kb = set(A["K"]), set(B["K"])
            if not ka and not kb:
                category = "neither"
            elif ka and kb:
                category = "both"
            elif ka:
                category = "only_first"
            else:
                category = "only_second"
            overlap = bool(ka & kb)
            incl = ("A_subset_B" if ka and ka <= kb else
                    "B_subset_A" if kb and kb <= ka else
                    "equal" if ka == kb else
                    "disjoint" if not overlap else "partial_overlap")
            key = (scen, a, b)
            rec = pairs.setdefault(key, {"pairs": 0, "both": 0, "only_first": 0, "only_second": 0,
                                         "neither": 0, "inclusion": {}, "restoration": 0,
                                         "device_saving": 0, "same_k_improvement": 0,
                                         "both_disjoint": 0, "both_partial_overlap": 0,
                                         "same_k_worse": 0, "examples": []})
            rec["pairs"] += 1
            rec[category] += 1
            rec["inclusion"][incl] = rec["inclusion"].get(incl, 0) + 1
            if ka and kb:
                if not overlap:
                    rec["both_disjoint"] += 1
                elif not (ka <= kb or kb <= ka):
                    rec["both_partial_overlap"] += 1
            if not ka and kb:
                rec["restoration"] += 1
            if ka and kb:
                if B["min_known_feasible"] < A["min_known_feasible"]:
                    rec["device_saving"] += 1
                # 同 k 服务改善在下面按 worst_by_k 单独统计
            if len(rec["examples"]) < 3 and category != "both":
                rec["examples"].append({"scenario": scen, "lot": lot, "seed": seed, "a": a, "b": b,
                                        "K_a": A["K"], "K_b": B["K"], "inclusion": incl,
                                        "category": category})
    # 同 k 服务改善：在每个 (scen,lot,seed) 的 min_k(A) 处比较 A/B 三率最大值
    worst = {}
    for key, by_k in groups.items():
        ks = sorted(by_k)
        if ks != list(range(0, K_MAX + 1)):
            continue
        worst[key] = {k: max((c["value"] if c["status"] == "valid" else -1.0)
                            for c in judge(by_k[k])["cells"].values()) for k in ks}
    for (scen, lot, seed), rules in sorted(by_cell.items()):
        for a, b in combinations(sorted(rules), 2):
            A, B = rules[a], rules[b]
            if not A["K"] or not B["K"]:
                continue
            k_star = A["min_known_feasible"]
            if k_star not in set(B["K"]):
                continue
            wa, wb = worst[(scen, a, lot, seed)][k_star], worst[(scen, b, lot, seed)][k_star]
            rec = pairs[(scen, a, b)]
            if wb < wa - EPS:
                rec["same_k_improvement"] += 1
            elif wb > wa + EPS:
                rec["same_k_worse"] += 1
    summary = {}
    for (scen, rule, lot, seed), info in sets.items():
        s = summary.setdefault(scen, {}).setdefault(rule, {
            "groups": 0, "empty": 0, "interval": 0, "broken": 0, "truncated": 0,
            "min_k": [], "confirmed_minimal": 0, "undecidable_groups": 0})
        s["groups"] += 1
        s["empty"] += 1 if info["empty_set"] else 0
        s["interval"] += 1 if info["is_interval"] else 0
        s["broken"] += 1 if (info["K"] and not info["is_interval"]) else 0
        s["truncated"] += 1 if info["truncated_at_kmax"] else 0
        s["confirmed_minimal"] += 1 if info["confirmed_minimal"] else 0
        if info["min_known_feasible"] is not None:
            s["min_k"].append(info["min_known_feasible"])
        if info["n_undecidable"]:
            s["undecidable_groups"] += 1
    for s in summary.values():
        for r in s.values():
            if r["min_k"]:
                r["min_k_median"] = sorted(r["min_k"])[len(r["min_k"]) // 2]
                r["min_k_range"] = [min(r["min_k"]), max(r["min_k"])]
            else:
                r["min_k_median"] = None; r["min_k_range"] = [None, None]
            del r["min_k"]
    out = {"schema": "round6/b_feasible/q3_feasible_sets/v1",
           "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "command": "C:/anaconda/python.exe research/round6_20261031/b_feasible/feasible_sets.py",
           "interpreter": sys.version.split()[0], "alpha": ALPHA, "k_max": K_MAX,
           "semantics": {
               "entry": "A 的 apps/parking_lab/workbench/service_semantics.py 尚未就绪；本脚本按 round5 review/none_semantics_4way 等价实现（capacity=row 字段；EV/ICE=service_metrics 外生分母）",
               "not_applicable": "分母=0 且对应需求=0 → not_applicable_zero_demand；K_strict 只收 valid≤α，K 另列 N/A 视为不违反的 inclusive 版本（两者逐组对比）",
               "missing_illegal": "不得跳过；逐组 n_undecidable 记录"},
           "inputs": [{"path": s["path"], "sha256": s["sha256"]} for s in specs],
           "inputs_note": "round3 main 4 条 + round4 scenario %d 条；均为既有完整 k=0..40 曲线" % (len(specs) - 4),
           "n_groups": len(sets),
           "sets": {"|".join(map(str, k)): v for k, v in sets.items()},
           "summary": summary, "pairs": {"|".join(map(str, k)): v for k, v in pairs.items()},
           "tpe0330_expansion": expansion,
           "limits": {"strict_vs_inclusive_differ": sum(1 for v in sets.values() if v["K"] != v["K_strict"]),
                      "empty_in_range": sum(1 for v in sets.values() if v["empty_set"]),
                      "empty_strict": sum(1 for v in sets.values() if not v["K_strict"]),
                      "zero_demand_na_groups": sum(1 for v in sets.values() if v["capacity_na_all_k"]),
                      "broken_in_range": sum(1 for v in sets.values() if v["K"] and not v["is_interval"]),
                      "truncated_at_kmax": sum(1 for v in sets.values() if v["truncated_at_kmax"]),
                      "unknown_beyond_kmax": sum(1 for v in sets.values() if v["unknown_beyond_kmax"])}
           }
    (HERE / "q3_feasible_sets.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"n_groups": len(sets), "limits": out["limits"],
                      "summary": summary, "pairs": {"|".join(map(str, k)): {x: v[x] for x in
                                                          ("pairs", "both", "only_first", "only_second", "neither",
                                                           "inclusion", "restoration", "device_saving",
                                                           "same_k_improvement")} for k, v in pairs.items()},
                      "tpe0330": expansion.get("cells")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
