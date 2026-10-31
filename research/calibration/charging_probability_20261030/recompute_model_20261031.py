"""Recompute and validate model_20261031.json against evidence.json; read-only for inputs.

Checks:
1. q_use values recomputed from (numerator, denominator) match stored values.
2. M10 combined = train + validation counts, recomputed probability.
3. No selected default; q_need scenarios carry is_scenario/basis/conditions.
4. Identification states q_need is unidentified; p_EV_arrival not stock share.
Exit code 0 only if all checks pass.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    model = json.loads((HERE / "model_20261031.json").read_text(encoding="utf-8"))
    evidence = json.loads((HERE / "evidence.json").read_text(encoding="utf-8"))
    ev_sha = hashlib.sha256((HERE / "evidence.json").read_bytes()).hexdigest()
    problems: list[str] = []
    rows = []
    for rec in model["q_use_records"]:
        num, den, val = rec["numerator"], rec["denominator"], rec["value"]
        calc = num / den
        if abs(calc - val) > 1e-12:
            problems.append(f"{rec['q_id']}: stored {val} != recomputed {calc}")
        rows.append({"q_id": rec["q_id"], "numerator": num, "denominator": den, "recomputed": calc})
    # cross-check against evidence.json counts
    ev = {}
    for src in evidence["sources"]:
        for item in src.get("event_counts", []):
            ev[(src["id"], item["context"])] = (item["charging_events"], item["parking_events"])
    unmatched = []
    for rec in model["q_use_records"]:
        key = (rec["source_id"], rec["evidence_context"])
        if key in ev and ev[key] != (rec["numerator"], rec["denominator"]):
            problems.append(f"{rec['q_id']}: differs from evidence.json {ev[key]}")
        elif key not in ev:
            unmatched.append(key)
    if model.get("selected_default") is not None:
        problems.append("selected_default must be null")
    if not rows:
        problems.append("no q_use records")
    # M10 combination
    m10 = {r["q_id"]: r for r in model["q_use_records"] if r["source_id"] == "M10"}
    tr = m10["M10-T3-TRAIN"]; va = m10["M10-T3-VALID"]; co = m10["M10-T3-COMBINED"]
    if (tr["numerator"] + va["numerator"], tr["denominator"] + va["denominator"]) != (co["numerator"], co["denominator"]):
        problems.append("M10 train+valid counts do not sum to combined")
    if abs((tr["numerator"] + va["numerator"]) / (tr["denominator"] + va["denominator"]) - co["value"]) > 1e-12:
        problems.append("M10 combined value mismatch")
    # scenarios
    scen_ids = set()
    for sc in model["q_need_scenarios"]:
        scen_ids.add(sc["scenario_id"])
        for k in ("is_scenario", "basis", "applicable_conditions", "limitations"):
            if k not in sc:
                problems.append(f"scenario {sc['scenario_id']} missing {k}")
    ident = model["identification"]
    if ident.get("status") != "unidentified":
        problems.append("identification.status must be unidentified")
    if model["covariate_model"].get("status") not in ("未拟合", "unfitted"):
        problems.append("covariate_model.status must state 未拟合/unfitted")
    pev = model["p_EV_arrival"]
    if pev.get("status") != "unidentified":
        problems.append("p_EV_arrival.status must be unidentified")
    if "stock" not in "".join(pev.get("why_stock_share_not_arrival_share", [])).lower():
        problems.append("p_EV_arrival must explain stock vs arrival share")
    prob_objects = {"q_use", "q_need", "q_location_share", "device_time_utilization", "potential_demand"}
    for entry in model.get("denominator_ledger", []):
        p = entry.get("value")
        if entry.get("probability_object") in prob_objects and p is not None and not 0 <= p <= 1:
            problems.append(f"denominator_ledger {entry.get('record_id')} value out of [0,1]: {p}")
    print(json.dumps({"checks": len(rows), "rows": rows, "unmatched_evidence": unmatched,
                      "evidence_sha256": ev_sha, "problems": problems}, ensure_ascii=False, indent=1))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
