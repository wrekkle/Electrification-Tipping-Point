# -*- coding: utf-8 -*-
"""收口核对：零需求 N/A / 尚无离场样本 / 真实缺失 / 非法值 四类语义（只读既有曲线）。

背景：audit_joint_k.py 把 departed_shortfall_energy_rate 的 0 分母统一记为
zero_denominator(not_applicable)。但该分母是 departed_requested_kwh：
=0 有两种含义——(a) 该情景从未产生充电需求（零需求 N/A）；
(b) 有充电需求但窗口内没有离场样本（删失/随访不足，不能当 N/A，也不能当 achieved）。
本脚本按 rate 分母与需求计数细分，输出计数与受影响单元；不重跑仿真。

命令：python research/round5_20261031/review/none_semantics_4way.py
输出：research/round5_20261031/review/none_semantics_4way.json
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import audit_joint_k as AJ  # noqa: E402

OUT = HERE / "none_semantics_4way.json"
RATES = AJ.RATES
EPS = 1e-12


def classify(row, name):
    """返回 (category, detail)；category ∈ valid / zero_demand_na / no_departure_sample / true_missing / illegal。"""
    cell = AJ.rate_cell(row, name)
    cat = cell["category"]
    if cat != "zero_denominator":
        return cat, cell
    if name == "capacity_only_unmet_rate":
        cr = row.get("charge_requests")
        return ("zero_demand_na" if (isinstance(cr, (int, float)) and not isinstance(cr, bool)
                                     and float(cr) <= 0.0) else "true_missing"), cell
    sm = row.get("service_metrics") or {}
    dens = sm.get("denominators") or {}
    ev_visits = dens.get("exogenous_ev_visits")
    ice_visits = dens.get("exogenous_ice_visits")
    reqs = dens.get("exogenous_charge_requests")
    if name == "departed_shortfall_energy_rate":
        if isinstance(reqs, (int, float)) and float(reqs) <= 0.0:
            return "zero_demand_na", cell
        return "no_departure_sample", cell
    if name == "ev_parking_failure_rate":
        return ("zero_demand_na" if isinstance(ev_visits, (int, float)) and float(ev_visits) <= 0.0
                else "true_missing"), cell
    if name == "ice_parking_failure_rate":
        return ("zero_demand_na" if isinstance(ice_visits, (int, float)) and float(ice_visits) <= 0.0
                else "true_missing"), cell
    return cat, cell


def main():
    specs = AJ.curve_specs()
    counts = {r: {"valid": 0, "zero_demand_na": 0, "no_departure_sample": 0,
                  "true_missing": 0, "illegal": 0} for r in RATES}
    units = {"curves": 0, "rows": 0, "units": set(),
             "shortfall_no_departure_units": set(), "shortfall_zero_demand_units": set()}
    for spec in specs:
        units["curves"] += 1
        for row in spec["rows"]:
            units["rows"] += 1
            lot, seed = row.get("lot_id"), row.get("seed")
            for name in RATES:
                cat, _ = classify(row, name)
                counts[name][cat] += 1
                if name == "departed_shortfall_energy_rate" and cat == "no_departure_sample":
                    units["shortfall_no_departure_units"].add((spec["id"], lot, seed))
                if name == "departed_shortfall_energy_rate" and cat == "zero_demand_na":
                    units["shortfall_zero_demand_units"].add((spec["id"], lot, seed))
    out = {
        "schema": "review/none_semantics_4way/v1",
        "generated_utc": None,
        "command": "python research/round5_20261031/review/none_semantics_4way.py",
        "interpreter": sys.version.split()[0],
        "scope": "59 条既有曲线（round3 main 4 + round4 scenario/fixedk），只读，不重跑仿真",
        "method": {
            "capacity_only_unmet_rate": "分母=row.charge_requests=0 → zero_demand_na",
            "departed_shortfall_energy_rate": "分母=departed_requested_kwh=0：exogenous_charge_requests=0 → zero_demand_na；否则 no_departure_sample（有需求但窗口内无离场样本，删失）",
            "ev/ice_parking_failure_rate": "分母=exogenous_ev_visits/exogenous_ice_visits=0 → zero_demand_na",
            "true_missing": "rate=None 且分母>0，或 service_metrics/分母缺失",
            "illegal": "非有限数值、越界 [0,1]",
            "prereg": "零需求 N/A 按 PREREGISTRATION.json:61 跳过并记录；尚无离场样本不是 achieved，也不等于 N/A，应与真实缺失分开报告",
        },
        "counts": counts,
        "units": {k: (len(v) if isinstance(v, set) else v) for k, v in units.items()},
    }
    # 逐单元是否存在“尚无离场样本”格（用于 B4 解释）
    out["units"] = {
        "curves": units["curves"], "rows": units["rows"],
        "n_units_with_shortfall_no_departure": len(units["shortfall_no_departure_units"]),
        "n_units_with_shortfall_zero_demand": len(units["shortfall_zero_demand_units"]),
    }
    out["b4_interpretation"] = {
        "note": "review 中 4 约束“310→51”是把零分母一律当失败的严格口径，属于口径变化，不是修复结果；按预登记 N/A 口径仍为 310。",
        "energy_constraint_status": "若进入主结论，必须先固定到达群体（独立情景、既定 lot/seed）、拒绝需求口径（capacity unmet 未服务，不等于离场缺电）和离场随访（离场后补能行为无观测，costs.py:718 保持 null）；否则只能作删失条件下的辅助结果。",
    }
    out["generated_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(out["counts"], ensure_ascii=False, indent=1))
    print("units:", out["units"], "b4:", out["b4_interpretation"]["note"][:60])


if __name__ == "__main__":
    main()
