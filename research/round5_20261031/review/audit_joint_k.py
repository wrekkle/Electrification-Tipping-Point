# -*- coding: utf-8 -*-
"""审查核查 1/3：joint_k 中 None 语义审计（只读既有曲线结果，不重跑仿真）。

分类：valid[0,1] / zero_denominator(not_applicable，分母=0) / true_missing(分母>0 或 service_metrics 缺失) / illegal。
对照预登记语义（PREREGISTRATION.json:61）：零分母标 not_applicable、约束跳过并记录。
当前 analyze_round3.joint_k 对所有 None 一律跳过；严格语义为「缺失→不 achieved」。

命令：python research/round5_20261031/review/audit_joint_k.py
输出：research/round5_20261031/review/joint_k_none_audit.json
"""
from __future__ import annotations

import glob
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R3DIR = ROOT / "research/round3_20261031"
sys.path.insert(0, str(R3DIR))
import analyze_round3 as A3  # noqa: E402

OUT = HERE / "joint_k_none_audit.json"
COMMAND = "python research/round5_20261031/review/audit_joint_k.py"
RATES = ("capacity_only_unmet_rate", "ev_parking_failure_rate",
         "ice_parking_failure_rate", "departed_shortfall_energy_rate")
DEN_KEY = {"ev_parking_failure_rate": "exogenous_ev_visits",
           "ice_parking_failure_rate": "exogenous_ice_visits",
           "departed_shortfall_energy_rate": "departed_requested_kwh"}
CONSTRAINTS = tuple(A3.CONSTRAINTS)
B4 = CONSTRAINTS + ("departed_shortfall_energy_rate",)
ALPHA = 0.05
EPS = 1e-12


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _classify(value, den):
    if value is None:
        if not _num(den) or not math.isfinite(float(den)):
            return {"category": "true_missing", "reason": "rate=None 且分母缺失/不可判定"}
        if float(den) <= 0.0:
            return {"category": "zero_denominator",
                    "reason": "分母=0；service_metrics 约定比值为 None 不写 0，预登记标 not_applicable"}
        return {"category": "true_missing", "reason": "rate=None 但分母>0"}
    if not _num(value):
        return {"category": "illegal", "reason": "值不是有限数值（类型=%s）" % type(value).__name__}
    if not math.isfinite(float(value)):
        return {"category": "illegal", "reason": "非有限数"}
    if float(value) < -EPS or float(value) > 1.0 + EPS:
        return {"category": "illegal", "reason": "越界 [0,1]"}
    return {"category": "valid", "reason": ""}


def rate_cell(row, name):
    if name == "capacity_only_unmet_rate":
        value = row.get(name)
        den = row.get("charge_requests")
        cell = _classify(value, den)
        cell.update({"value": value, "denominator": den,
                     "source": "row.capacity_only_unmet_rate / row.charge_requests"})
        return cell
    sm = row.get("service_metrics")
    if not isinstance(sm, dict):
        return {"category": "true_missing", "value": None, "denominator": None,
                "source": "service_metrics 缺失", "reason": "行内无 service_metrics"}
    rates = sm.get("rates") if isinstance(sm.get("rates"), dict) else {}
    dens = sm.get("denominators") if isinstance(sm.get("denominators"), dict) else {}
    value = rates.get(name)
    den = dens.get(DEN_KEY[name])
    cell = _classify(value, den)
    cell.update({"value": value, "denominator": den,
                 "source": "row.service_metrics.rates.%s / denominators.%s" % (name, DEN_KEY[name])})
    return cell


def curve_specs():
    specs = []
    for tag in ("A_pi0", "B_pi1", "C_quota", "D_pi2"):
        document = A3.load_curve(tag, 10)
        specs.append({"id": "round3/main_%s_ref_s10" % tag, "class": "round3_ref",
                      "path": "research/round3_20261031/results/main_%s_ref_s10.json" % tag,
                      "rows": document["rows"], "meta": document.get("meta", {}),
                      "expanded_lots": document.get("expanded_lots", [])})
    pattern = str(ROOT / "research/round4_20261031/results/scenario_*_s5.json")
    for path in sorted(glob.glob(pattern)):
        name = Path(path).name
        if "manifest" in name:
            continue
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        specs.append({"id": "round4/" + name[:-5], "class": "round4_scenario",
                      "path": "research/round4_20261031/results/" + name,
                      "rows": document["rows"], "meta": document.get("meta", {}),
                      "expanded_lots": []})
    pattern = str(ROOT / "research/round4_20261031/results/fixedk/fixedk_*.json")
    for path in sorted(glob.glob(pattern)):
        name = Path(path).name
        if "manifest" in name:
            continue
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        specs.append({"id": "round4/fixedk/" + name[:-5], "class": "round4_fixedk",
                      "path": "research/round4_20261031/results/fixedk/" + name,
                      "rows": document["rows"], "meta": document.get("meta", {}),
                      "expanded_lots": []})
    return specs


def joint_variant(by_k, alpha, constraints, missing_policy):
    ks = sorted(int(k) for k in by_k)
    first_block, blocks, saw_missing = None, [], False
    for k in ks:
        row = by_k[k]
        ok = True
        vals = {}
        for name in constraints:
            cell = rate_cell(row, name)
            vals[name] = cell["value"]
            cat = cell["category"]
            if cat == "valid":
                if float(cell["value"]) > alpha + EPS:
                    ok = False
                    blocks.append({"k": int(k), "rate": name, "category": "exceeds_alpha",
                                   "value": cell["value"]})
                    break
            elif cat == "zero_denominator" and missing_policy == "skip_na":
                continue
            else:
                ok = False
                saw_missing = True
                blocks.append({"k": int(k), "rate": name, "category": cat, "value": cell["value"]})
                break
        if ok:
            return {"k": int(k), "status": "achieved", "rates": vals,
                    "k_max": ks[-1] if ks else None}
        if first_block is None:
            first_block = blocks[-1]
    status = "infeasible_upper_bound"
    if saw_missing:
        status = "indeterminate_missing"
    return {"k": None, "status": status, "k_max": ks[-1] if ks else None,
            "first_block": first_block,
            "n_blocks": len(blocks)}


def main():
    specs = curve_specs()
    counts = {name: {"valid": 0, "zero_denominator": 0, "true_missing": 0, "illegal": 0}
              for name in RATES}
    per_curve = []
    units = {}
    total_cells = 0
    rows_with_sm_missing_fields = 0
    illegal_examples = []
    zero_den_examples = []
    for spec in specs:
        local = {name: {"valid": 0, "zero_denominator": 0, "true_missing": 0, "illegal": 0}
                 for name in RATES}
        for row in spec["rows"]:
            lot, seed, rule = row["lot_id"], int(row["seed"]), row["rule"]
            k = int(row["k"])
            sm = row.get("service_metrics")
            if isinstance(sm, dict) and sm.get("missing"):
                rows_with_sm_missing_fields += 1
            by_k = units.setdefault((spec["id"], lot, seed, rule), {})
            by_k[k] = row
            for name in RATES:
                cell = rate_cell(row, name)
                cat = cell["category"]
                counts[name][cat] += 1
                local[name][cat] += 1
                total_cells += 1
                if cat == "illegal" and len(illegal_examples) < 20:
                    illegal_examples.append({"curve": spec["id"], "lot": lot, "seed": seed,
                                             "k": k, "rate": name, "value": cell["value"]})
                if cat == "zero_denominator" and len(zero_den_examples) < 20:
                    zero_den_examples.append({"curve": spec["id"], "lot": lot, "seed": seed,
                                              "k": k, "rate": name})
        per_curve.append({"id": spec["id"], "class": spec["class"], "path": spec["path"],
                          "rows": len(spec["rows"]),
                          "lots": sorted({r["lot_id"] for r in spec["rows"]}),
                          "seeds": sorted({int(r["seed"]) for r in spec["rows"]}),
                          "rules": sorted({r["rule"] for r in spec["rows"]}),
                          "k_min": min(int(r["k"]) for r in spec["rows"]),
                          "k_max": max(int(r["k"]) for r in spec["rows"]),
                          "expanded_lots": spec["expanded_lots"],
                          "counts": local})

    affected = []
    for (cid, lot, seed, rule), by_k in units.items():
        first = {}
        for name in RATES:
            hits = [(k, rate_cell(by_k[k], name)["category"]) for k in sorted(by_k)]
            hits = [(k, cat) for k, cat in hits if cat != "valid"]
            if hits:
                first[name] = {"k": int(hits[0][0]), "category": hits[0][1],
                               "n_cells": len(hits),
                               "categories": sorted({cat for _, cat in hits})}
        if first:
            affected.append({"curve": cid, "lot": lot, "seed": seed, "rule": rule,
                             "first_none": first,
                             "min_k": min(v["k"] for v in first.values())})

    comparisons = []
    changed = {"A3": [], "B4": []}
    flags = {"A3": [], "B4": []}
    for (cid, lot, seed, rule), by_k in units.items():
        current = A3.joint_k(by_k, ALPHA)
        a3_skip = joint_variant(by_k, ALPHA, CONSTRAINTS, "skip_na")
        a3_strict = joint_variant(by_k, ALPHA, CONSTRAINTS, "strict")
        b4_skip = joint_variant(by_k, ALPHA, B4, "skip_na")
        b4_strict = joint_variant(by_k, ALPHA, B4, "strict")
        first_any = {}
        for name in RATES:
            for k in sorted(by_k):
                cat = rate_cell(by_k[k], name)["category"]
                if cat != "valid":
                    first_any[name] = {"k": int(k), "category": cat}
                    break
        rec = {"curve": cid, "lot": lot, "seed": seed, "rule": rule,
               "k_values": [min(int(k) for k in by_k), max(int(k) for k in by_k)],
               "first_none": first_any,
               "current_A3": {"k": current["k"], "status": current["status"]},
               "A3_prereg_skip_na": {"k": a3_skip["k"], "status": a3_skip["status"]},
               "A3_strict": {"k": a3_strict["k"], "status": a3_strict["status"],
                             "first_block": a3_strict.get("first_block")},
               "B4_prereg_skip_na": {"k": b4_skip["k"], "status": b4_skip["status"]},
               "B4_strict": {"k": b4_strict["k"], "status": b4_strict["status"],
                             "first_block": b4_strict.get("first_block")}}
        if (current["k"], current["status"]) != (a3_skip["k"], a3_skip["status"]):
            rec["A3_current_vs_prereg_differs"] = True
        if (a3_skip["k"], a3_skip["status"]) != (a3_strict["k"], a3_strict["status"]):
            changed["A3"].append({k: rec[k] for k in ("curve", "lot", "seed", "rule",
                                                      "current_A3", "A3_strict", "first_none")})
        if (b4_skip["k"], b4_skip["status"]) != (b4_strict["k"], b4_strict["status"]):
            changed["B4"].append({k: rec[k] for k in ("curve", "lot", "seed", "rule",
                                                      "B4_prereg_skip_na", "B4_strict", "first_none")})
        a3_constraint_missing = [n for n in first_any if n in CONSTRAINTS]
        if a3_constraint_missing and a3_skip["k"] is not None:
            low = min(first_any[n]["k"] for n in a3_constraint_missing)
            if low <= a3_skip["k"]:
                flags["A3"].append({k: rec[k] for k in ("curve", "lot", "seed", "rule",
                                                        "first_none", "A3_prereg_skip_na")})
        if b4_skip["k"] is not None and first_any:
            low = min(v["k"] for v in first_any.values())
            if low <= b4_skip["k"]:
                flags["B4"].append({k: rec[k] for k in ("curve", "lot", "seed", "rule",
                                                        "first_none", "B4_prereg_skip_na")})
        comparisons.append(rec)

    a3_vacuous = 0
    b4_vacuous = 0
    b4_na_below = 0
    for (cid, lot, seed, rule), by_k in units.items():
        cur = A3.joint_k(by_k, ALPHA)
        if cur["k"] is not None:
            row = by_k[int(cur["k"])]
            if any(rate_cell(row, n)["category"] != "valid" for n in CONSTRAINTS):
                a3_vacuous += 1
        b4 = joint_variant(by_k, ALPHA, B4, "skip_na")
        if b4["k"] is not None:
            if rate_cell(by_k[int(b4["k"])], "departed_shortfall_energy_rate")["category"] != "valid":
                b4_vacuous += 1
        firsts = []
        for name in RATES:
            for k in sorted(by_k):
                if rate_cell(by_k[k], name)["category"] != "valid":
                    firsts.append(k)
                    break
        if b4["k"] is not None and firsts and min(firsts) < b4["k"]:
            b4_na_below += 1

    summary = {
        "curves": len(specs),
        "units": len(units),
        "four_rate_cells": total_cells,
        "rows_with_service_metrics_missing_fields": rows_with_sm_missing_fields,
        "cells_per_category": counts,
        "cells_all_rates": {cat: sum(counts[n][cat] for n in RATES)
                            for cat in ("valid", "zero_denominator", "true_missing", "illegal")},
        "affected_units": len(affected),
        "affected_units_by_rate": {n: sum(1 for a in affected if n in a["first_none"])
                                   for n in RATES},
        "min_k_by_rate": {n: min((a["first_none"][n]["k"] for a in affected if n in a["first_none"]),
                                 default=None) for n in RATES},
        "joint_k_alpha": ALPHA,
        "A3": {"units": len(comparisons),
               "current_achieved": sum(1 for c in comparisons if c["current_A3"]["k"] is not None),
               "prereg_achieved": sum(1 for c in comparisons if c["A3_prereg_skip_na"]["k"] is not None),
               "strict_achieved": sum(1 for c in comparisons if c["A3_strict"]["k"] is not None),
               "current_vs_prereg_changed": sum(1 for c in comparisons
                                                if c["current_A3"]["k"] != c["A3_prereg_skip_na"]["k"]),
               "prereg_vs_strict_changed": len(changed["A3"])},
        "B4": {"units": len(comparisons),
               "prereg_achieved": sum(1 for c in comparisons if c["B4_prereg_skip_na"]["k"] is not None),
               "strict_achieved": sum(1 for c in comparisons if c["B4_strict"]["k"] is not None),
               "prereg_vs_strict_changed": len(changed["B4"])},
        "vacuous_at_achieved_k": {"A3_any_constraint_na": a3_vacuous,
                                   "B4_fourth_na": b4_vacuous,
                                   "B4_na_at_lower_k_below_achieved": b4_na_below},
        "low_k_flags": {"A3_constraints": len(flags["A3"]), "B4_any_rate": len(flags["B4"]),
                        "definition": "首个 None（零分母或缺失）出现在 <= 推荐 k 的单元：推荐值依赖跳过，不得确认为全域最小"},
    }
    document = {
        "schema": "review/joint_k_none_audit/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": COMMAND,
        "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
        "scope": "现有曲线结果的四项率 None 分类 + 当前/严格语义下 alpha=0.05 推荐 k 对照（只读，不重跑）",
        "semantics_reference": [
            {"path": "research/round3_20261031/PREREGISTRATION.json", "line": 61,
             "quote": "\"zero_denominator\": \"该项标 not_applicable，约束跳过并记录\""},
            {"path": "research/round3_20261031/analyze_round3.py", "lines": "65-89",
             "quote": "joint_k：约束值为 None 时 unknown.append(name) 并 continue；k 命中即 achieved"},
            {"path": "apps/parking_lab/workbench/service_metrics.py", "lines": "20, 64-72",
             "quote": "零分母（或分母缺失）时比值一律 None，不写 0"},
            {"path": "research/integer_allocation_20261031/run_cost_curve.py", "lines": "225-226",
             "quote": "capacity_only_unmet_rate = capacity_only/charge_requests；charge_requests=0 时为 None"},
        ],
        "curves": per_curve,
        "classification_counts": counts,
        "zero_denominator_examples": zero_den_examples,
        "illegal_examples": illegal_examples,
        "affected_units": affected,
        "joint_comparison": {"alpha": ALPHA,
                             "constraint_sets": {"A3": list(CONSTRAINTS), "B4": list(B4)},
                             "units": comparisons},
        "changed_units": changed,
        "low_k_flag_units": flags,
        "summary": summary,
        "notes": [
            "当前 analyze_round3.joint_k 把 None（含零分母 not_applicable）当作跳过，若某 k 的三条约束全部可跳过则直接 achieved。",
            "严格语义：任何非 valid（含零分母、真实缺失、非法）在该 k 记 not achieved；零分母是否豁免只影响 B 集（第四条）。",
            "k=None 在现有实现中记 infeasible_upper_bound，含义是搜索上界内未达成，不是物理不可行。",
        ],
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "summary": summary}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
