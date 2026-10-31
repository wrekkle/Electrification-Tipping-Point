"""main22 透明度报告：每个约束在留出流上"从哪个 k 开始成立"，以及仍物理不可行的流数。

输入：experiments_main22/E2/curve_E2.csv（同参数：10 站点、同 split、同 seed、k=0..charging_bays）。
- 停车服务：EV 停车失败率 <=5% 且 ICE 停车失败率 <=5%
- 充电接入：capacity_only_unmet_rate <=5%
- 能量服务：departed_shortfall_energy_rate <=10%（补充阈值，不作为三约束标准）
输出：experiments_main22/constraint_thresholds.csv + .json
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "research" / "round8_20261031" / "experiments_main22"
THRESHOLDS = {
    "parking_service": 0.05,
    "charging_access": 0.05,
    "energy_service": 0.10,
}


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _min_k(rows, predicate):
    for row in sorted(rows, key=lambda item: int(item["k"])):
        if predicate(row):
            return int(row["k"])
    return None


def main():
    with open(BASE / "E2" / "curve_E2.csv", encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("split") == "test"]
    groups = {}
    for row in rows:
        key = (row["policy"], row["stream_id"], row["site_id"])
        groups.setdefault(key, []).append(row)
    per_stream = []
    for (policy, stream_id, site_id), subset in sorted(groups.items()):
        entry = {"policy": policy, "stream_id": stream_id, "site_id": site_id,
                 "k_grid_max": max(int(row["k"]) for row in subset)}
        entry["parking_service_k"] = _min_k(subset, lambda r: (
            (_num(r["service_ev_parking_failure_rate"]) or 0) <= THRESHOLDS["parking_service"]
            and (_num(r["service_ice_parking_failure_rate"]) or 0) <= THRESHOLDS["parking_service"]))
        entry["charging_access_k"] = _min_k(subset, lambda r: (
            (_num(r["capacity_only_unmet_rate"]) or 0) <= THRESHOLDS["charging_access"]))
        entry["energy_service_k"] = _min_k(subset, lambda r: (
            (_num(r["service_departed_shortfall_energy_rate"]) or 0) <= THRESHOLDS["energy_service"]))
        entry["three_constraints_k"] = _min_k(subset, lambda r: str(r.get("feasible_3constraints")) == "True")
        entry["infeasible_reason"] = None
        if entry["charging_access_k"] is None:
            entry["infeasible_reason"] = "no k in 0..charging_bays meets capacity_only_unmet<=5%"
        elif entry["three_constraints_k"] is None:
            entry["infeasible_reason"] = "capacity ok but ev/ice parking failure not both <=5%"
        per_stream.append(entry)
    summary = {"thresholds": THRESHOLDS, "unit": "independent stream (site-day)",
               "k_grid": "0..charging_bays",
               "per_policy": {}, "files": ["constraint_thresholds.csv", "constraint_thresholds.json"]}
    for policy in sorted({entry["policy"] for entry in per_stream}):
        subset = [entry for entry in per_stream if entry["policy"] == policy]
        item = {}
        for field in ("parking_service_k", "charging_access_k", "energy_service_k", "three_constraints_k"):
            values = [entry[field] for entry in subset if entry[field] is not None]
            item[field] = {"n_streams": len(subset), "n_hold": len(values),
                           "n_no_k": len(subset) - len(values),
                           "median_k": statistics.median(values) if values else None,
                           "min_k": min(values) if values else None,
                           "max_k": max(values) if values else None}
        item["infeasible_streams"] = [entry["stream_id"] for entry in subset
                                      if entry["three_constraints_k"] is None]
        summary["per_policy"][policy] = item
    with open(BASE / "constraint_thresholds.csv", "w", encoding="utf-8", newline="") as handle:
        fieldnames = []
        for entry in per_stream:
            for key in entry:
                if key not in fieldnames:
                    fieldnames.append(key)
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(per_stream)
    (BASE / "constraint_thresholds.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"per_policy": {k: {f: v[f] for f in ("parking_service_k", "charging_access_k",
                                                            "energy_service_k", "three_constraints_k")}
                                      for k, v in summary["per_policy"].items()}},
                     ensure_ascii=True))
    return summary


if __name__ == "__main__":
    main()
