"""第三轮独立验收：不复制实现公式，用黑盒/手算/独立枚举核对。

运行：python research/round3_20261031/verify_round3.py
输出：research/round3_20261031/results/verify_round3_report.json；全过 EXIT=0。
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "research", "round3_20261031", "results")
R3 = os.path.join(ROOT, "research", "round3_20261031")
FROZEN = {
    "research/traffic_generation_20261031/fitted_parameters.json": "1dfc14a2a29e204d",
    "research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json": "3d77f693a8d5514b",
    "research/calibration/charging_probability_20261030/model_20261031.json": "75c4f03498398cde",
    "research/round2_20261031/results/analysis_v2_all.json": "00ec8cdc46f9ec98",
}
checks = []


def check(name, fn):
    try:
        detail = fn()
        ok = detail.get("ok", True) if isinstance(detail, dict) else bool(detail)
        checks.append({"name": name, "passed": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name, flush=True)
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": name, "passed": False, "error": "%s: %s" % (type(exc).__name__, exc)})
        print("FAIL " + name + " -> " + repr(exc), flush=True)


def sha16(path):
    with open(os.path.join(ROOT, path), "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()[:16]


def load(name):
    with open(os.path.join(OUT, name), encoding="utf-8") as handle:
        return json.load(handle)


def check_independent_generator():
    from apps.parking_lab.workbench import traffic_gen
    params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031",
                                         "fitted_parameters.json"), encoding="utf-8"))
    sample, meta = [], {}
    for seed in (1, 2, 3, 4, 5):
        arrivals, meta = traffic_gen.generate_for_lot(
            params, "TPE0008", seed, scenario_model="independent",
            p_ev=0.05, q_need=0.70, strict=True)
        sample.extend(arrivals)
    shares = [a for a in sample if a.is_ev]
    need = [a for a in shares if a.needs_charge]
    ev_share = len(shares) / len(sample)
    need_share = len(need) / len(shares)
    return {"ok": (meta["scenario_model"] == "independent" and meta["product_coupled"] is False
                   and abs(meta["q_need"] - 0.70) < 1e-12 and abs(ev_share - 0.05) < 0.03
                   and abs(need_share - 0.70) < 0.12),
            "ev_share": ev_share, "need_share": need_share, "meta": {
                k: meta.get(k) for k in ("scenario_model", "p_ev", "q_need", "product_coupled")}}


def check_legacy_generator():
    from apps.parking_lab.workbench import traffic_gen
    params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031",
                                         "fitted_parameters.json"), encoding="utf-8"))
    _, meta = traffic_gen.generate_for_lot(params, "TPE0008", 1, p_ev=0.30)
    return {"ok": meta["scenario_model"] == "legacy_product" and meta["product_coupled"] is True
            and meta["clipped"] is False}


def check_strict_rejects():
    from apps.parking_lab.workbench import traffic_gen
    params = json.load(open(os.path.join(ROOT, "research", "traffic_generation_20261031",
                                         "fitted_parameters.json"), encoding="utf-8"))
    rejected = []
    for kwargs in ({"scenario_model": "legacy_product", "q_need": 1.2},
                   {"scenario_model": "legacy_product", "q_need": float("nan")},
                   {"scenario_model": "independent", "p_ev": 0.1, "q_need": 1.2},
                   {"scenario_model": "independent", "p_ev": 0.1}):
        try:
            traffic_gen.generate_for_lot(params, "TPE0008", 1, strict=True, **kwargs)
        except ValueError:
            rejected.append(True)
        else:
            rejected.append(False)
    return {"ok": all(rejected), "rejected": rejected}


def check_service_metrics_hand():
    from apps.parking_lab.workbench.service_metrics import summarise
    visits = [
        # 外生 EV 充电请求，被拒：进 EV 停车失败、容量未满足、充电请求分母
        {"vehicle_id": 10, "time_min": 10, "is_ev": True, "needs_charge": True,
         "admitted": False, "departed": False, "departure_min": 100,
         "energy_kwh": 10.0, "delivered_kwh": 0.0},
        # 外生 EV 无充电需求，正常入园
        {"vehicle_id": 11, "time_min": 20, "is_ev": True, "needs_charge": False,
         "admitted": True, "departed": True, "departure_min": 120,
         "energy_kwh": 0.0, "delivered_kwh": 0.0, "charge_start_min": None},
        # 外生 EV 充电请求，已离场但缺电 4/10
        {"vehicle_id": 12, "time_min": 30, "is_ev": True, "needs_charge": True,
         "admitted": True, "departed": True, "departure_min": 200,
         "energy_kwh": 10.0, "delivered_kwh": 6.0, "charge_start_min": 35},
        # 外生 EV 充电请求，期末仍在场：pending，不算失败
        {"vehicle_id": 13, "time_min": 40, "is_ev": True, "needs_charge": True,
         "admitted": True, "departed": False, "departure_min": 500,
         "energy_kwh": 8.0, "delivered_kwh": 3.0, "charge_start_min": 45},
        # 外生 ICE 被拒
        {"vehicle_id": 14, "time_min": 50, "is_ev": False, "needs_charge": False,
         "admitted": False, "departed": False, "departure_min": 90,
         "energy_kwh": 0.0, "delivered_kwh": 0.0},
        # 期初车辆，不计外生分母
        {"vehicle_id": 0, "time_min": 0, "is_ev": True, "needs_charge": True,
         "admitted": True, "departed": True, "departure_min": 60,
         "energy_kwh": 10.0, "delivered_kwh": 0.0, "charge_start_min": None},
    ]
    got = summarise(visits, horizon_min=240, initial_ids={0})
    n, d = got["numerators"], got["denominators"]
    expect = {
        "capacity_unmet_requests": 2, "exogenous_charge_requests": 3,
        "ev_parking_failures": 1, "exogenous_ev_visits": 4,
        "ice_parking_failures": 1, "exogenous_ice_visits": 1,
        "departed_shortfall_kwh": 4.0, "departed_requested_kwh": 10.0,
        "pending_count": 1, "pending_energy_kwh": 5.0, "censored_sessions": 1,
        "initial_occupancy_n": 1,
    }
    values = {**n, **d, **got["levels"]}
    wrong = {k: (values.get(k), v) for k, v in expect.items() if not math.isclose(
        float(values.get(k, -999)), float(v), abs_tol=1e-9)}
    return {"ok": not wrong, "wrong": wrong, "rates": got["rates"]}


def check_config_roundtrip():
    from apps.parking_lab.workbench.config import Config
    c = Config.parse({"n_spaces": 30, "charging_bays": 6, "chargers": 6,
                      "prediction_object": "ev_arrivals", "coordinate_window": False,
                      "protected_bays": 3, "policy": "protected_quota"})
    again = Config.parse(c.to_dict())
    return {"ok": again == c and c.protected_bays == 3 and c.coordinate_window is False,
            "to_dict_keys": sorted(c.to_dict())[:6]}


def _run(policy, protected):
    from apps.parking_lab.workbench.config import Config
    from apps.parking_lab.workbench.simulation import Simulation
    cfg = Config.parse({"n_spaces": 24, "charging_bays": 6, "chargers": 6, "charger_kw": 7,
                        "feeder_kw": 336, "duration_hours": 8, "start_hour": 10,
                        "arrival_rate_hour": 45, "ev_share": 0.35, "charge_probability": 0.6,
                        "scenario": "steady", "seed": 5, "policy": policy,
                        "protected_bays": protected})
    sim = Simulation(cfg)
    sim.run()
    visits = sim.export()["visits"]
    ice_on_charging = sum(1 for v in visits if (not v["is_ev"]) and v["admitted"]
                          and v["bay"] is not None and v["bay"] < 6)
    return {"ice_on_charging": ice_on_charging, "visits": len(visits),
            "rule": policy, "protected": protected}


def check_rule_c_endpoints():
    pi0 = _run("dedicated_by_type", 0)
    pi1 = _run("full_open_ice_first", 0)
    c0 = _run("protected_quota", 0)
    ck = _run("protected_quota", 6)
    return {"ok": pi0["ice_on_charging"] == 0 and pi1["ice_on_charging"] > 0
            and c0["ice_on_charging"] == pi1["ice_on_charging"]
            and ck["ice_on_charging"] == 0,
            "detail": {"pi0": pi0, "pi1": pi1, "c_m0": c0, "c_mk": ck}}


def check_hidden_info_states():
    from apps.parking_lab.workbench.rules import ObservableState, decide
    state = ObservableState(time_min=100.0, is_ev=False, free_bays=tuple(range(5, 20)),
                            n_spaces=20, charging_bays=5, chargers=5,
                            arrival_rate_per_hour=30, p_ev=0.3, p_charge_given_ev=0.5,
                            mean_ice_occupancy_min=90.0, ice_charging_bays=1)
    decisions = [decide(state, rule, window_min=10, safety_margin=0, protected_bays=2).to_dict()
                 for rule in ("dedicated_by_type", "full_open_ice_first",
                              "predictive_shared_ice_first", "protected_quota")]
    text = json.dumps(decisions, ensure_ascii=False)
    hidden = [key for key in ("needs_charge", "energy_kwh", "dwell_min", "departure_min")
              if key in text]
    return {"ok": not hidden, "hidden_fields_found": hidden,
            "decisions": [d["reason"] for d in decisions]}


def manual_joint(by_k, alpha=0.05):
    for k in sorted(by_k):
        row = by_k[k]
        requests = row.get("charge_requests") or 0
        cap = ((row.get("unmet_no_connector_events") or 0) / requests) if requests else None
        ev_n = row.get("ev_arrivals") or 0
        ev_f = row.get("ev_rejected") or 0
        ev_rate = ev_f / ev_n if ev_n else None
        ice_n = (row.get("arrivals") or 0) - ev_n
        ice_f = row.get("ice_rejected") or 0
        ice_rate = ice_f / ice_n if ice_n else None
        if all(v is None or v <= alpha + 1e-12 for v in (cap, ev_rate, ice_rate)):
            return k
    return None


def check_joint_recompute():
    analysis = load("analysis_round3.json")
    pairs = analysis["delta_k"]["B_pi1"]["by_lot_seed"]
    curve = load("main_B_pi1_ref_s10.json")
    grouped = {}
    for row in curve["rows"]:
        grouped.setdefault((row["lot_id"], int(row["seed"])), {})[int(row["k"])] = row
    wrong = []
    for pair in pairs[:10]:
        want = manual_joint(grouped[(pair["lot"], pair["seed"])])
        if want != pair["k_rule"]:
            wrong.append({"pair": pair, "manual": want})
    return {"ok": not wrong, "wrong": wrong}


def check_allocation_statuses():
    from apps.parking_lab.workbench.allocation import (integer_recommendation, min_servers_for_blocking,
                                                       service_level_k)
    no_servers = min_servers_for_blocking(0.0, 0.05, 20)
    no_demand = service_level_k({0: 0.0, 1: 0.0, 2: 0.0}, 0.05)
    unreachable = service_level_k({0: 10.0, 1: 9.8, 2: 9.5}, 0.05, search_max=2)
    achieved = service_level_k({0: 10.0, 1: 9.0, 2: 9.0, 3: 0.4}, 0.05, search_max=3)
    rec = integer_recommendation([7, 8, 10], 40)
    return {"ok": no_servers == 0 and no_demand["k"] == 0 and no_demand["status"] == "no_demand"
            and unreachable["k"] is None and unreachable["status"] == "infeasible_upper_bound"
            and unreachable["bound_kind"] == "user_bound"
            and achieved["k"] == 3 and achieved["status"] == "achieved"
            and rec["recommended_k"] == 8 and rec["status"] == "ok"
            and integer_recommendation([8, 9], 40)["status"] == "statistical_summary_not_installable",
            "detail": {"no_servers": no_servers, "unreachable": unreachable["bound_kind"],
                       "achieved": achieved["k"], "rec": rec}}


def check_cost_arithmetic():
    from apps.parking_lab.workbench.costs import facility_cost
    params = {"depreciation_annual": 365000.0, "maintenance_per_bay_day": 10.0,
              "facility_fixed_cost_per_day": 100.0}
    one = facility_cost(2, params, days=1.0)
    half = facility_cost(2, params, days=0.5)
    zero = facility_cost(0, params, days=1.0)
    return {"ok": math.isclose(one["value"], 2 * (1000 + 10) + 100)
            and math.isclose(half["value"], 2 * (1000 + 10) * 0.5 + 50)
            and math.isclose(zero["value"], 100.0)
            and zero["items"]["device_capital"] == 0.0,
            "detail": {"one": one["value"], "half": half["value"], "zero": zero["value"]}}


def check_audit_round2():
    with open(os.path.join(R3, "audit_round2.json"), encoding="utf-8") as handle:
        audit = json.load(handle)
    items = {item["id"]: item for item in audit["items"]}
    ok = (items["R2-A-9OF9"]["verdict"] == "corrected"
          and items["R2-A-9OF9"]["machine"]["achieved_any_seed"] == 8
          and items["R2-B-SEEDSPREAD"]["verdict"] == "corrected"
          and {row["lot_id"]: row["k5_range"] for row in
               items["R2-B-SEEDSPREAD"]["machine"]["table"]}["TPE0695"] == 22
          and items["R2-D-TPE1171"]["verdict"] == "partially_unsupported"
          and items["R2-E-CAPITAL"]["verdict"] == "confirmed")
    return {"ok": ok, "summary": audit.get("summary")}


def check_multiday():
    with open(os.path.join(R3, "data_audit.json"), encoding="utf-8") as handle:
        data = json.load(handle)
    days = sorted(data["date_dirs"])
    holdout = data.get("holdout") or {}
    slots = sum(day.get("parking_slots.jsonl", {}).get("unique_slots", 0)
                for day in data["date_dirs"].values())
    sufficient = holdout.get("satisfied")
    return {"ok": days == ["2026-10-30", "2026-10-31"] and slots == 307 and sufficient is False,
            "days": days, "slots": slots, "holdout": sufficient}


def check_frozen_hashes():
    changed = {path: sha16(path) for path, want in FROZEN.items() if sha16(path) != want}
    return {"ok": not changed, "changed": changed}


def check_docs_limits():
    limits = {"docs/PROGRESS.md": 3200, "docs/TODO.md": 8000,
              "docs/methods/COST-MODEL-V2.md": 3200}
    lengths = {}
    for path, cap in limits.items():
        with open(os.path.join(ROOT, path), encoding="utf-8") as handle:
            lengths[path] = len(handle.read())
    return {"ok": all(lengths[p] <= c for p, c in limits.items()), "lengths": lengths}


def check_rules_v2_corrected():
    with open(os.path.join(ROOT, "research", "round2_20261031", "rules_v2", "rules_v2.md"),
              encoding="utf-8") as handle:
        text = handle.read()
    return {"ok": "第三轮接线" in text and "ice_blocking_connector" in text}


def main():
    check("independent_generator", check_independent_generator)
    check("legacy_generator", check_legacy_generator)
    check("strict_rejects", check_strict_rejects)
    check("service_metrics_hand", check_service_metrics_hand)
    check("config_roundtrip", check_config_roundtrip)
    check("rule_c_endpoints", check_rule_c_endpoints)
    check("hidden_info_states", check_hidden_info_states)
    check("joint_recompute_independent", check_joint_recompute)
    check("allocation_statuses", check_allocation_statuses)
    check("cost_arithmetic", check_cost_arithmetic)
    check("audit_round2", check_audit_round2)
    check("multiday_audit", check_multiday)
    check("frozen_hashes", check_frozen_hashes)
    check("docs_limits", check_docs_limits)
    check("rules_v2_corrected", check_rules_v2_corrected)
    report = {"schema": "round3_verification/v1", "checks": checks,
              "passed": sum(1 for c in checks if c["passed"]), "total": len(checks)}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "verify_round3_report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"passed": report["passed"], "total": report["total"]}, ensure_ascii=False))
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
