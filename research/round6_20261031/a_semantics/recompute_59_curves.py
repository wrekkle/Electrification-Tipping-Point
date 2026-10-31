# -*- coding: utf-8 -*-
"""第六轮 A 兼容性复算：用 service_semantics 在既有 59 条曲线上复现第五轮计数。

只读既有曲线（round3 main 4 + round4 scenario/fixedk），不重跑仿真、不改旧文件。

命令（默认解释器）：
  C:/anaconda/python.exe research/round6_20261031/a_semantics/recompute_59_curves.py
输出：
  research/round6_20261031/a_semantics/recompute_59_curves.json
退出码：0=全部锚点一致；2=任一锚点不一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "research", "round5_20261031", "review"))
sys.path.insert(0, os.path.join(ROOT, "research", "round3_20261031"))

import audit_joint_k as AJ  # noqa: E402
from apps.parking_lab.workbench import service_semantics as S  # noqa: E402

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(OUT_DIR, "recompute_59_curves.json")
COMMAND = "C:/anaconda/python.exe research/round6_20261031/a_semantics/recompute_59_curves.py"

# 第五轮锚点：review/none_semantics_4way.json 与 review/joint_k_none_audit.json
EXPECTED_COUNTS = {
    "capacity_only_unmet_rate": {"valid": 31360, "not_applicable_zero_demand": 615,
                                 "censored_no_departure": 0, "missing": 0, "illegal": 0},
    "ev_parking_failure_rate": {"valid": 31975, "not_applicable_zero_demand": 0,
                                "censored_no_departure": 0, "missing": 0, "illegal": 0},
    "ice_parking_failure_rate": {"valid": 31975, "not_applicable_zero_demand": 0,
                                 "censored_no_departure": 0, "missing": 0, "illegal": 0},
    "departed_shortfall_energy_rate": {"valid": 22895, "not_applicable_zero_demand": 615,
                                       "censored_no_departure": 8465, "missing": 0,
                                       "illegal": 0},
}
# four_na_skip=66：五态语义下 censored 不是 N/A、不判成功（none_semantics_4way 口径）。
# four_legacy_zero_denominator_skip=310：旧审计把全部零分母当 N/A 跳过，
# 正是 review 报的 310，用于证明“310→51 是口径差”而非修复效果。
EXPECTED_JOINT = {"three_na_skip": 780, "three_strict": 765,
                  "four_na_skip": 66, "four_legacy_zero_denominator_skip": 310,
                  "four_strict": 51}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def joint_units(specs):
    units = {}
    for spec in specs:
        for row in spec["rows"]:
            key = (spec["id"], row["lot_id"], int(row["seed"]), row["rule"])
            units.setdefault(key, {})[int(row["k"])] = row
    counts = {"three_na_skip": 0, "three_strict": 0, "four_na_skip": 0,
              "four_legacy_zero_denominator_skip": 0, "four_strict": 0}
    per_unit = []
    for (curve, lot, seed, rule), by_k in sorted(units.items()):
        record = {"curve": curve, "lot": lot, "seed": seed, "rule": rule}
        for label, constraints, policy in (
                ("three_na_skip", S.CONSTRAINTS_3, "skip"),
                ("three_strict", S.CONSTRAINTS_3, "strict"),
                ("four_na_skip", S.CONSTRAINTS_4, "skip"),
                ("four_strict", S.CONSTRAINTS_4, "strict")):
            k_hit = None
            for k in sorted(by_k):
                if S.judge(by_k[k], constraints=constraints, na_policy=policy)["achieved"]:
                    k_hit = k
                    break
            record[label] = k_hit
            if k_hit is not None:
                counts[label] += 1
        # 旧口径复现：四位零分母（含 censored）一律跳过，其余同 N/A 跳过。
        legacy_hit = None
        for k in sorted(by_k):
            row = by_k[k]
            ok = True
            for name in S.CONSTRAINTS_4:
                item = S.constraint_status(name, row)
                if item["status"] in ("satisfied", "not_applicable", "censored"):
                    continue
                ok = False
                break
            if ok:
                legacy_hit = k
                break
        record["four_legacy_zero_denominator_skip"] = legacy_hit
        if legacy_hit is not None:
            counts["four_legacy_zero_denominator_skip"] += 1
        per_unit.append(record)
    return units, counts, per_unit


def main():
    specs = AJ.curve_specs()
    counts = {name: {state: 0 for state in S.RATE_STATES} for name in S.RATE_NAMES}
    rows_total = 0
    for spec in specs:
        for row in spec["rows"]:
            rows_total += 1
            for name in S.RATE_NAMES:
                counts[name][S.classify_rate(name, row)["status"]] += 1
    units, joint, per_unit = joint_units(specs)
    mismatches = []
    for name in S.RATE_NAMES:
        for state in S.RATE_STATES:
            expected = EXPECTED_COUNTS[name][state]
            if counts[name][state] != expected:
                mismatches.append({"kind": "count", "rate": name, "state": state,
                                   "expected": expected, "got": counts[name][state]})
    for key, expected in EXPECTED_JOINT.items():
        if joint[key] != expected:
            mismatches.append({"kind": "joint", "variant": key,
                               "expected": expected, "got": joint[key]})
    if rows_total != 31975 or len(specs) != 59 or len(units) != 975:
        mismatches.append({"kind": "scope", "expected": [59, 31975, 975],
                           "got": [len(specs), rows_total, len(units)]})
    document = {
        "schema": "round6/a_semantics/recompute_59_curves/v1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": COMMAND,
        "interpreter": "%s | Python %s" % (sys.executable, sys.version.split()[0]),
        "exit_code": 0 if not mismatches else 2,
        "scope": "59 条既有曲线（round3 main 4 + round4 scenario/fixedk），只读，不重跑仿真",
        "anchors": {"none_semantics_4way.json": EXPECTED_COUNTS,
                    "joint_k_none_audit.json": EXPECTED_JOINT},
        "counts": counts,
        "joint_units": joint,
        "units": {"curves": len(specs), "rows": rows_total, "lot_seed_rule_units": len(units)},
        "mismatches": mismatches,
        "match": not mismatches,
        "input_sha256": {spec["path"]: sha256_file(os.path.join(ROOT, spec["path"]))
                         for spec in specs},
        "source_sha256": {
            "apps/parking_lab/workbench/service_semantics.py":
                sha256_file(os.path.join(ROOT, "apps", "parking_lab", "workbench",
                                         "service_semantics.py")),
            "research/round5_20261031/review/audit_joint_k.py":
                sha256_file(os.path.join(ROOT, "research", "round5_20261031", "review",
                                         "audit_joint_k.py")),
            "research/round6_20261031/a_semantics/recompute_59_curves.py":
                sha256_file(os.path.abspath(__file__)),
        },
        "per_unit_achieved_k": per_unit,
        "notes": [
            "N/A 按预登记跳过并记录；censored 不判成功；missing/illegal 不判 achieved。",
            "三约束 N/A 跳过 achieved 780/975、严格 765/975；四约束（五态语义）66/975、严格 51/975。",
            "旧审计把 censored 也当 N/A 跳过时四约束为 310/975；五态语义下 censored 不判成功，故为 66。",
            "310→51 是口径差（零分母一律当失败 vs 零分母跳过），不是修复效果。",
        ],
    }
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=1)
    print(json.dumps({"match": document["match"], "counts": counts, "joint": joint,
                      "mismatches": mismatches}, ensure_ascii=False))
    return document["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
