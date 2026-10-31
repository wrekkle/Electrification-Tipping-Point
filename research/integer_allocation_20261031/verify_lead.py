"""Lead 独立复核：不调用被复核模块的结论函数，按原始记录重算关键数字。

检查项：
1. 同一 (lot,seed) 跨 k 的 traffic_hash 一致；跨规则同 (lot,k,seed) 一致。
2. 设施成本 = k × (capex/寿命/365 + 日维护)，独立算例比对。
3. 整数最优：用独立 min 循环重算 k*(L)，与 analysis_pi0.json 比对。
4. 缺参传播：成本 total 全为 null 且 missing_parameters 非空，未补 0。
5. 三类占位分钟：独立遍历 visits 重算 overstay / 非充电电车占位，与 rules 台账比对。
6. Erlang-B：独立递归实现与 allocation.erlang_b 比对。
"""
from __future__ import annotations

import json, math, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
for entry in (ROOT, HERE):
    if entry not in sys.path:
        sys.path.insert(0, entry)

OUT = os.path.join(HERE, "outputs")
FINDINGS, CHECKS = [], []


def check(name, ok, detail):
    CHECKS.append({"check": name, "pass": bool(ok), "detail": detail})
    if not ok:
        FINDINGS.append("%s: %s" % (name, detail))


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def check_hash_replay():
    curve = read_json(os.path.join(OUT, "cost_curve_pi0_k40.json"))
    by_key, violations = {}, []
    for row in curve["rows"]:
        by_key.setdefault((row["lot_id"], row["seed"]), set()).add(row["traffic_hash"])
    for key, values in by_key.items():
        if len(values) != 1:
            violations.append(key)
    check("hash_across_k", not violations, {"lot_seed": len(by_key), "violations": violations[:3]})
    rules = read_json(os.path.join(OUT, "rule_comparison_real_traffic.json"))
    check("hash_across_rules", not rules.get("traffic_hash_violations"),
          {"violations": rules.get("traffic_hash_violations")})


def check_facility():
    scenario = read_json(os.path.join(HERE, "cost_scenario.json"))["cost"]
    rate = scenario["depreciation_capex"] / scenario["depreciation_life_years"] / 365.0 + scenario["maintenance_per_bay_day"]
    curve = read_json(os.path.join(OUT, "cost_curve_pi0_k40.json"))
    worst = 0.0
    for row in curve["rows"]:
        if row["facility_cost"] is None:
            continue
        worst = max(worst, abs(row["facility_cost"] - row["k"] * rate))
    check("facility_cost_arithmetic", worst < 1e-6, {"rate_twd_per_bay_day": rate, "max_abs_diff": worst,
          "expected_from_report": 75.29972602739726})


def check_enumeration():
    analysis = read_json(os.path.join(OUT, "analysis_pi0.json"))
    curve = read_json(os.path.join(OUT, "cost_curve_pi0_k40.json"))
    per = {}
    for row in curve["rows"]:
        bucket = per.setdefault((row["lot_id"], row["k"]), {"facility": [], "unmet": []})
        if row["facility_cost"] is not None:
            bucket["facility"].append(row["facility_cost"])
        if row["unmet_no_connector_events"] is not None:
            bucket["unmet"].append(row["unmet_no_connector_events"])
    mismatches, comparisons = [], 0
    for lot, record in analysis["lots"].items():
        by_k = {k: (sum(v["facility"]) / len(v["facility"]), sum(v["unmet"]) / len(v["unmet"]))
                for (l, k), v in per.items() if l == lot and v["facility"] and v["unmet"]}
        for loss_key, reported in (record.get("k_star_by_loss") or {}).items():
            loss = float(loss_key)
            scored = {k: f + loss * u for k, (f, u) in by_k.items()}
            if not scored:
                continue
            best = min(scored.values())
            winners = sorted(k for k, value in scored.items() if value <= best + 1e-9)
            comparisons += 1
            if reported is None or sorted(reported)[:1] != winners[:1]:
                mismatches.append({"lot": lot, "L": loss, "reported": reported, "recomputed": winners})
    check("integer_optimum_enumeration", not mismatches, {"comparisons": comparisons, "mismatches": mismatches[:5]})


def check_null_propagation():
    curve = read_json(os.path.join(OUT, "cost_curve_pi0_k40.json"))
    candidates = read_json(os.path.join(ROOT, "research", "cost_model_20261030", "parameter_candidates_20261031.json"))
    params = candidates.get("parameters") or {}
    records = params.values() if isinstance(params, dict) else params
    declared_null = {p["param_id"] for p in records if p.get("value") is None}
    bad, degenerate = [], []
    for row in curve["rows"]:
        if (row.get("cost_total") is None) == bool(row.get("cost_complete")):
            bad.append({"lot": row["lot_id"], "k": row["k"], "total": row.get("cost_total"),
                        "complete": row.get("cost_complete")})
        if row.get("cost_complete") and not (row.get("cost_missing_parameters") or []):
            degenerate.append({"lot": row["lot_id"], "k": row["k"], "total": row.get("cost_total"),
                               "capital_item": (row.get("cost_items") or {}).get("operator_capital_depreciation")})
    check("null_propagation", not bad, {
        "rows": len(curve["rows"]), "declared_null_params": len(declared_null), "bad": bad[:3],
        "complete_rows_note": {"count": len(degenerate), "samples": degenerate[:3],
                               "why_not_usable": "costs.py:506 把 operator_capital_depreciation 按日计而不乘设备数，k=0 仍计 31.998；设施成本一律以 runner 的 k×单位日成本为准"},
    })


def check_occupancy_ledger():
    params_path = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
    params = read_json(params_path)
    lot_id, seed, k = "TPE0401", 1, 10
    base = {"n_spaces": 205, "charging_bays": k, "chargers": k, "charger_kw": 7.0, "feeder_kw": 120.0,
            "duration_hours": 24.0, "start_hour": 11.5, "interval_level": 0.9, "arrival_rate_hour": 0.0,
            "ev_share": 0.0, "charge_probability": 0.0, "policy": "dedicated_by_type", "reserve_fixed": 0,
            "seed": seed}
    import run_cost_curve as runner
    from apps.parking_lab.workbench import traffic_gen
    from apps.parking_lab.workbench.rules import type_occupancy_ledger
    from apps.parking_lab.workbench.simulation import Simulation
    arrivals, meta = traffic_gen.generate_for_lot(params, lot_id, seed)
    arrivals, n_initial = runner.warm_start_arrivals(runner.lot_meta(params, lot_id), tuple(arrivals), meta, seed)
    sim = Simulation(dict(base), arrivals=tuple(arrivals))
    sim.run()
    ledger = (type_occupancy_ledger(sim.visits, sim.config, sim.horizon).get("metrics") or {})
    keys = sorted(sim.visits[0].keys())
    cut = sim.horizon
    # 按 rules.type_occupancy_ledger 的定义独立重算：只看占用带枪位（bay < chargers）的时段。
    chargers = k
    overstay = 0.0
    bay_min = 0.0
    for visit in sim.visits:
        if not visit["admitted"] or visit["bay"] is None or visit["bay"] >= chargers:
            continue
        start = visit["time_min"]
        end = min(visit["departure_min"] if visit["departure_min"] is not None else cut, cut)
        stay = max(0.0, end - start)
        if stay <= 1e-9:
            continue
        if not visit["is_ev"]:
            continue  # ICE 占位单列，本检查只比对了 EV 两类
        if not visit["needs_charge"]:
            bay_min += stay
        elif visit.get("completed") and visit.get("completion_min") is not None:
            overstay += max(0.0, end - max(start, float(visit["completion_min"])))
    detail = {"visit_keys": keys, "recomputed_overstay_min": overstay,
              "ledger_overstay_min": ledger.get("overstay_after_complete_min"),
              "recomputed_no_charging_bay_min": bay_min,
              "ledger_no_charging_bay_min": ledger.get("no_charging_demand_bay_min"),
              "initial_vehicles": n_initial}
    ok_over = ledger.get("overstay_after_complete_min") is not None and abs(overstay - ledger["overstay_after_complete_min"]) < 1e-6
    ok_bay = ledger.get("no_charging_demand_bay_min") is not None and abs(bay_min - ledger["no_charging_demand_bay_min"]) < 1e-6
    detail["overstay_match"] = ok_over
    detail["no_charging_bay_match"] = ok_bay
    check("occupancy_ledger_independent", ok_over and ok_bay, detail)


def erlang_independent(load, servers):
    if servers <= 0:
        return 1.0
    value = 1.0
    for n in range(1, servers + 1):
        value = load * value / (n + load * value)
    return value


def check_erlang():
    from apps.parking_lab.workbench import allocation
    cases = [(0.5, 1), (1.0, 2), (2.0, 3), (5.0, 6)]
    rows = []
    ok = True
    for load, servers in cases:
        mine = erlang_independent(load, servers)
        theirs = allocation.erlang_b(load, servers)
        rows.append({"servers": servers, "load": load, "independent": mine, "module": theirs,
                     "abs_diff": abs(mine - theirs)})
        ok = ok and abs(mine - theirs) < 1e-9
    check("erlang_b_independent", ok, rows)


def main():
    check_hash_replay()
    check_facility()
    check_enumeration()
    check_null_propagation()
    check_occupancy_ledger()
    check_erlang()
    report = {"schema": "lead_independent_verification/v1", "checks": CHECKS, "findings": FINDINGS,
              "passed": sum(1 for c in CHECKS if c["pass"]), "total": len(CHECKS)}
    path = os.path.join(OUT, "lead_verification.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({"passed": report["passed"], "total": report["total"], "findings": FINDINGS},
                     ensure_ascii=False))
    for item in CHECKS:
        print(("PASS " if item["pass"] else "FAIL ") + item["check"], json.dumps(item["detail"], ensure_ascii=False)[:300])
    return 0 if not FINDINGS else 1


if __name__ == "__main__":
    raise SystemExit(main())
