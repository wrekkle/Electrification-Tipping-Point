# -*- coding: utf-8 -*-
"""Lead 独立复核：由既有 round3 main_A/B/C/D 曲线计算可行集合 K 与形状（独立实现，不导入 A 的语义模块）。
只读；输出 research/round6_20261031/lead/q3_indep.json"""
from __future__ import annotations
import json, math, sys
from pathlib import Path

ROOT = Path(r"C:\Projects\停车场充电桩优化方案")
RES = ROOT / "research/round3_20261031/results"
OUT = ROOT / "research/round6_20261031/lead/q3_indep.json"
RULES = ["main_A_pi0_ref_s10", "main_B_pi1_ref_s10", "main_C_quota_ref_s10", "main_D_pi2_ref_s10"]
ALPHA = 0.05
EPS = 1e-12


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def rate_state(value, den, valid_range=True):
    if den is None or not num(den):
        return "missing"
    den = float(den)
    if den <= 0.0:
        return "not_applicable_zero_demand"
    if value is None:
        return "missing"
    if not num(value):
        return "illegal"
    value = float(value)
    if value < -EPS or value > 1.0 + EPS:
        return "illegal"
    return "valid"


def cell(row, name):
    if name == "capacity_only_unmet_rate":
        return rate_state(row.get(name), row.get("charge_requests")), row.get(name)
    sm = row.get("service_metrics") or {}
    rates = sm.get("rates") or {}
    dens = sm.get("denominators") or {}
    key = {"ev_parking_failure_rate": "exogenous_ev_visits",
           "ice_parking_failure_rate": "exogenous_ice_visits"}[name]
    return rate_state(rates.get(name), dens.get(key)), rates.get(name)


CONSTRAINTS = ("capacity_only_unmet_rate", "ev_parking_failure_rate", "ice_parking_failure_rate")


def feasible_at(row):
    flags = []
    ok = True
    for name in CONSTRAINTS:
        st, val = cell(row, name)
        flags.append(st)
        if st == "valid":
            if float(val) > ALPHA + EPS:
                ok = False
        elif st == "not_applicable_zero_demand":
            pass  # 预登记：N/A 跳过，不判失败
        else:
            ok = False  # missing/illegal 不得判 achieved
    return ok, flags


def main():
    out = {"schema": "round6/lead_q3_indep/v1", "alpha": ALPHA, "rules": {}, "summary": {}}
    sets = {}
    for tag in RULES:
        doc = json.loads((RES / (tag + ".json")).read_text(encoding="utf-8"))
        groups = {}
        for row in doc["rows"]:
            key = (row["lot_id"], row["seed"])
            groups.setdefault(key, {})[int(row["k"])] = row
        for key, by_k in groups.items():
            K, na_cells, bad = [], 0, 0
            for k in sorted(by_k):
                ok, flags = feasible_at(by_k[k])
                na_cells += sum(1 for f in flags if f == "not_applicable_zero_demand")
                bad += sum(1 for f in flags if f in ("missing", "illegal"))
                if ok:
                    K.append(k)
            r = tag.split("_")[1]
            sets[(r, key[0], key[1])] = K
            out["rules"].setdefault(r, {"units": 0, "empty": 0, "nonempty": 0, "intervals": 0,
                                        "gaps": 0, "max_k40": 0, "na_cells": 0, "bad_cells": 0}) 
            st = out["rules"][r]
            st["units"] += 1
            if not K:
                st["empty"] += 1
            else:
                st["nonempty"] += 1
                st["intervals"] += int(K == list(range(K[0], K[-1] + 1)))
                st["gaps"] += int(K != list(range(K[0], K[-1] + 1)))
                st["max_k40"] += int(K[-1] >= 40)
            st["na_cells"] += na_cells
            st["bad_cells"] += bad
    # 跨规则关系（同一 lot,seed）
    rel = {"equal": 0, "A_subset": 0, "B_subset": 0, "disjoint": 0,
           "overlap_not_nested": 0, "one_empty": 0}
    for (lot, seed) in sorted({(k[1], k[2]) for k in sets}):
        ka = set(sets.get(("A", lot, seed), []))
        for other in ("B", "C", "D"):
            kb = set(sets.get((other, lot, seed), []))
            if not ka and not kb:
                continue
            if ka == kb:
                rel["equal"] += 1
            elif not ka or not kb:
                rel["one_empty"] += 1
            elif ka < kb:
                rel["A_subset"] += 1
            elif kb < ka:
                rel["B_subset"] += 1
            elif not (ka & kb):
                rel["disjoint"] += 1
            else:
                rel["overlap_not_nested"] += 1
    out["cross_rule"] = rel
    # Δk 形状关系：|min_B - min_A| >= 5 的单元及其 K 形状
    jumps = []
    for (lot, seed) in sorted({(k[1], k[2]) for k in sets}):
        ka = sets.get(("A", lot, seed), [])
        kb = sets.get(("B", lot, seed), [])
        if ka and kb:
            d = min(kb) - min(ka)
            if abs(d) >= 5:
                jumps.append({"lot": lot, "seed": seed, "min_A": min(ka), "min_B": min(kb),
                              "delta": d, "K_A_interval": ka == list(range(ka[0], ka[-1] + 1)),
                              "K_B_interval": kb == list(range(kb[0], kb[-1] + 1))})
    out["large_delta"] = {"count": len(jumps), "examples": jumps[:20]}
    out["summary"] = {"units_per_rule": len({(k[1], k[2]) for k in sets}),
                      "rules": {r: out["rules"][r] for r in out["rules"]},
                      "cross_rule": rel, "large_delta_count": len(jumps)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
