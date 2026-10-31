# -*- coding: utf-8 -*-
"""审查核查 3/3：四类可行性（复用第四轮 fixed-k 独立种子评价与机制小算例）。

不重跑 split-half、不扩枚举：只读 research/round4_20261031/results/fixedk/*.json 与
research/round4_20261031/mechanism/shared_capacity_mechanism.json。
在同一 k（A 的训练中位 k）下比较专用规则 A 与共享规则 B/D 在 seeds 5-10 的可行性。

命令：python research/round5_20261031/review/four_categories.py
输出：research/round5_20261031/review/four_categories.json
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R4 = ROOT / "research/round4_20261031"
FIXEDK = R4 / "results" / "fixedk"
MECH = R4 / "mechanism" / "shared_capacity_mechanism.json"
OUT = HERE / "four_categories.json"
COMMAND = "python research/round5_20261031/review/four_categories.py"
ALPHA = 0.05
EPS = 1e-12
CONSTRAINTS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")
DEN_KEY = {"ev_parking_failure_rate": "exogenous_ev_visits",
           "ice_parking_failure_rate": "exogenous_ice_visits",
           "departed_shortfall_energy_rate": "departed_requested_kwh"}


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def rate_cell(row, name):
    if name == "capacity_only_unmet_rate":
        value, den = row.get(name), row.get("charge_requests")
        source = "row"
    else:
        sm = row.get("service_metrics") or {}
        rates = sm.get("rates") if isinstance(sm.get("rates"), dict) else {}
        dens = sm.get("denominators") if isinstance(sm.get("denominators"), dict) else {}
        value = rates.get(name)
        den = dens.get(DEN_KEY[name]) if name in DEN_KEY else None
        source = "service_metrics"
    if value is None:
        if _num(den) and math.isfinite(float(den)) and float(den) <= 0.0:
            return {"category": "zero_denominator", "value": None, "den": den, "source": source}
        return {"category": "missing", "value": None, "den": den, "source": source}
    if not _num(value) or not math.isfinite(float(value)) or float(value) < -EPS or float(value) > 1 + EPS:
        return {"category": "illegal", "value": value, "den": den, "source": source}
    return {"category": "valid", "value": float(value), "den": den, "source": source}


def feasible(row):
    detail = {}
    ok = True
    for name in CONSTRAINTS:
        cell = rate_cell(row, name)
        detail[name] = cell
        if cell["category"] == "valid":
            if cell["value"] > ALPHA + EPS:
                ok = False
        elif cell["category"] == "zero_denominator":
            continue
        else:
            ok = False
    return ok, detail


def load_rows(name):
    path = FIXEDK / name
    document = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for row in document["rows"]:
        out[int(row["seed"])] = row
    return out, document.get("meta", {})


def mean(values):
    vals = [float(v) for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def main():
    manifest = json.loads((FIXEDK / "fixedk_manifest.json").read_text(encoding="utf-8"))
    selection = manifest["selection"]["A"]
    cells = []
    file_records = []
    for lot in sorted(selection):
        k = selection[lot]["k"]
        if k is None:
            cells.append({"lot": lot, "seed": None, "rule": None, "k": None,
                          "note": "A 在训练 seeds 全部未达成，无 fixed-k 评价"})
            continue
        own_a, meta_a = load_rows("fixedk_own_A_%s.json" % lot)
        shared = {}
        for rule in ("B", "D"):
            rows, meta = load_rows("fixedk_common_%s_%s.json" % (rule, lot))
            shared[rule] = rows
            file_records.append({"lot": lot, "rule": rule, "mode": "common", "k": k,
                                 "file": "research/round4_20261031/results/fixedk/fixedk_common_%s_%s.json" % (rule, lot),
                                 "charge_scenario_id": meta.get("charge_scenario", {}).get("scenario_id")
                                 if isinstance(meta.get("charge_scenario"), dict) else None})
        for seed in sorted(own_a):
            if seed not in shared["B"] or seed not in shared["D"]:
                continue
            a_ok, a_detail = feasible(own_a[seed])
            for rule in ("B", "D"):
                row = shared[rule][seed]
                s_ok, s_detail = feasible(row)
                if a_ok and s_ok:
                    category = "both_feasible"
                elif a_ok:
                    category = "only_dedicated"
                elif s_ok:
                    category = "only_shared"
                else:
                    category = "neither_feasible"
                record = {"lot": lot, "seed": seed, "rule": rule, "k": k,
                          "category": category,
                          "dedicated": {"feasible": a_ok,
                                        "rates": {n: a_detail[n]["value"] for n in a_detail},
                                        "categories": {n: a_detail[n]["category"] for n in a_detail}},
                          "shared": {"feasible": s_ok,
                                     "rates": {n: s_detail[n]["value"] for n in s_detail},
                                     "categories": {n: s_detail[n]["category"] for n in s_detail}},
                          "energy_rate_dedicated": rate_cell(own_a[seed], "departed_shortfall_energy_rate"),
                          "energy_rate_shared": rate_cell(row, "departed_shortfall_energy_rate")}
                cells.append(record)
    data_cells = [c for c in cells if c.get("seed") is not None]

    def summarize(subset):
        rates = {name: mean([c["dedicated"]["rates"][name] for c in subset])
                 for name in CONSTRAINTS}
        shared_rates = {name: mean([c["shared"]["rates"][name] for c in subset])
                        for name in CONSTRAINTS}
        return {"n_cells": len(subset),
                "k_values": sorted({c["k"] for c in subset}),
                "dedicated": rates,
                "shared": shared_rates,
                "dedicated_departed_shortfall_energy_rate": mean(
                    [c["energy_rate_dedicated"]["value"] for c in subset]),
                "shared_departed_shortfall_energy_rate": mean(
                    [c["energy_rate_shared"]["value"] for c in subset]),
                "n_valid_rate_cells": {name: sum(1 for c in subset
                                                 if c["dedicated"]["categories"][name] == "valid")
                                       for name in CONSTRAINTS},
                "n_energy_rate_valid_cells": sum(
                    1 for c in subset if c["energy_rate_shared"]["category"] == "valid")}

    by_rule = {}
    for rule in ("B", "D"):
        subset_rule = [c for c in data_cells if c["rule"] == rule]
        by_rule[rule] = {}
        for category in ("both_feasible", "only_dedicated", "only_shared", "neither_feasible"):
            part = [c for c in subset_rule if c["category"] == category]
            by_rule[rule][category] = summarize(part)
        by_rule[rule]["counts"] = {category: sum(1 for c in subset_rule if c["category"] == category)
                                   for category in ("both_feasible", "only_dedicated",
                                                    "only_shared", "neither_feasible")}
        by_rule[rule]["total_cells"] = len(subset_rule)

    pooled = {}
    for category in ("both_feasible", "only_dedicated", "only_shared", "neither_feasible"):
        part = [c for c in data_cells if c["category"] == category]
        pooled[category] = summarize(part)
        pooled[category]["by_rule"] = {rule: sum(1 for c in part if c["rule"] == rule)
                                       for rule in ("B", "D")}

    mechanism = {}
    if MECH.exists():
        doc = json.loads(MECH.read_text(encoding="utf-8"))
        for variant, summary in doc.get("summary", {}).items():
            mechanism[variant] = {k: summary.get(k) for k in
                                  ("instances", "both_feasible", "positive_delta_k",
                                   "zero_delta_k", "negative_delta_k",
                                   "restorations_pi0_infeasible_pi1_feasible",
                                   "pi0_only_feasible", "both_infeasible")}
    md_path = R4 / "mechanism" / "shared_capacity_mechanism.md"
    md_lines = []
    if md_path.exists():
        lines = md_path.read_text(encoding="utf-8").splitlines()
        md_lines = [{"line": idx + 1, "text": text.strip()}
                    for idx, text in enumerate(lines)
                    if ("定理" in text or "不能" in text or "反例" in text)]
    document = {
        "schema": "review/four_categories/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": COMMAND,
        "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
        "scope": "fixed-k 独立种子(5-10)评价：A 与 B/D 在同一 k 下的可行性四分类；机制小算例只引用，不重跑",
        "method": {
            "k_definition": "k = A 在训练 seeds 1-4 的达成 k 中位数（fixedk_manifest.selection.A）",
            "same_k": "共享规则 B/D 用 A 的同一个 k（fixedk_common_*），不是在各自最小 k 上比较",
            "alpha": ALPHA,
            "constraints": list(CONSTRAINTS),
            "na_policy": "零分母标 not_applicable 跳过；真实缺失记 not achieved",
            "evaluation_seeds": [5, 6, 7, 8, 9, 10],
            "split_discipline": "selection 只用 seeds 1-4；evaluation 只用 seeds 5-10；本轮不重跑 split-half",
            "interval": "区间/计数只描述既定情景与既定 k，不作总体显著性推断",
        },
        "selection": selection,
        "files": file_records,
        "cells": data_cells,
        "summary": {
            "total_cells": len(data_cells),
            "by_rule": by_rule,
            "pooled": pooled,
            "note_tpe0330": "TPE0330 的 A 在训练 seeds 未达成（k=None），按第四轮设计不进入 fixed-k 评价",
        },
        "mechanism_rule_semantics": {
            "path": "research/round4_20261031/mechanism/shared_capacity_mechanism.json",
            "summary": mechanism,
            "md_limits": md_lines,
            "interpretation": "有限枚举实例上的机制分解；positive_delta_k 计数表示存在共享省枪的实例，不能写成定理",
        },
    }
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "cells": len(data_cells),
                      "counts": {r: by_rule[r]["counts"] for r in by_rule}}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
