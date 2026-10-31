"""Validate model_20261031_v2.json identification boundary against v1 and T28 evidence (read-only checks)."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ID = HERE.parents[1] / "official_data_20261031" / "identification_20261031"

def main() -> int:
    problems = []
    v1_raw = (HERE / "model_20261031.json").read_bytes()
    v2 = json.loads((HERE / "model_20261031_v2.json").read_text(encoding="utf-8"))
    v1 = json.loads(v1_raw)
    v1_sha = hashlib.sha256(v1_raw).hexdigest()
    if not v1_sha.startswith("75c4f03498398cde"):
        problems.append(f"v1 changed: sha256 {v1_sha[:16]} != baseline 75c4f03498398cde")
    if len(v1.get("q_use_records", [])) != 7 or len(v1.get("q_need_scenarios", [])) != 6:
        problems.append("v1 q_use/q_need counts changed")
    z = v2["renamed_identified_quantity"]["value"]
    if abs(z - 0.03636583089107938) > 1e-15:
        problems.append("z value mismatch")
    rq = v2["renamed_identified_quantity"]
    if rq.get("status") != "usage_proxy" or not rq.get("deprecated"):
        problems.append("renamed quantity must be status=usage_proxy and deprecated=true")
    if not rq.get("previous_names"):
        problems.append("deprecated mapping previous_names missing")
    grid = v2["feasible_region"]["grid"]
    if len(grid) != 13:
        problems.append(f"grid size {len(grid)} != 13")
    for row in grid:
        p = row["p_EV"]; q = row["q_need"]; st = row["status"]
        if p < z:
            if st != "incompatible" or q <= 1.0:
                problems.append(f"p={p}: expected incompatible with q>1, got {st} q={q}")
        elif abs(p - z) < 1e-6:
            if st != "boundary_q_equals_1" or abs(q - 1.0) > 1e-6:
                problems.append(f"boundary row wrong: {row}")
        else:
            if st != "feasible" or q > 1.0 or abs(q - z / p) > 1e-6:
                problems.append(f"p={p}: feasible row inconsistent {row}")
    for ex in v2["feasible_region"]["incompatible_examples"]:
        if ex["status"] != "incompatible" or ex["q_need"] <= 1.0:
            problems.append(f"incompatible example wrong: {ex}")
    pe = v2["p_ev_evidence"]
    for key in ("actual_new_car_sales_share", "public_charging_usage_share", "lot_level_ev_arrival_share"):
        if pe[key].get("value") is not None or pe[key].get("status") != "UNVERIFIED":
            problems.append(f"p_EV evidence {key} must stay null/UNVERIFIED")
    if not (HERE.parents[1] / "official_data_20261031" / "identification_20261031" / "mechanism_audit.md").exists():
        problems.append("mechanism_audit.md missing")
    reg = json.loads((ID / "t28_p_ev_evidence.json").read_text(encoding="utf-8"))
    if len(reg.get("sources", [])) != 12:
        problems.append(f"t28 sources {len(reg.get('sources', []))} != 12")
    if len(reg.get("gaps", [])) != 4:
        problems.append("t28 gaps != 4")
    for src in reg["sources"]:
        if src["status"] == "available" and src.get("value") is not None and not src.get("sha256"):
            problems.append(f"available source {src['evidence_id']} lacks sha256")
    print(json.dumps({"v1_sha256_prefix": v1_sha[:16], "z": z, "grid_rows": len(grid),
                      "feasible": sum(1 for r in grid if r["status"] == "feasible"),
                      "incompatible": sum(1 for r in grid if r["status"] == "incompatible"),
                      "t28_sources": len(reg["sources"]), "t28_gaps": len(reg["gaps"]),
                      "problems": problems}, ensure_ascii=False, indent=1))
    return 0 if not problems else 1

if __name__ == "__main__":
    raise SystemExit(main())
