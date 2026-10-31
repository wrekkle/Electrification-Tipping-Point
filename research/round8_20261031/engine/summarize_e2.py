"""E2 曲线汇总：按 k 对独立场站-日重采样给均值与 bootstrap 区间（不是把快照当样本）。

输入：experiments/E2/curve_E2.csv（每行 = 一个策略 × 一个独立流 × 一个 k）。
输出：experiments/E2/curve_E2_summary.csv + .json（含方法说明）。
统计单位 = 独立流（场站-日）；bootstrap 次数不是样本量。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ENGINE = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ENGINE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.parking_lab.workbench.stat_tools import bootstrap_ci

BASE = ROOT / "research" / "round8_20261031" / "experiments" / "E2"
N_BOOT = 1000
SEED = 20261031
METRICS = ("service_capacity_unmet_rate", "service_ev_parking_failure_rate",
           "service_ice_parking_failure_rate", "charging_access_rate", "energy_service_rate")


def main():
    source = BASE / "curve_E2.csv"
    with open(source, encoding="utf-8") as handle:
        rows = [row for row in csv.DictReader(handle) if row.get("status") != "error"]
    groups = {}
    for row in rows:
        key = (row["policy"], int(row["k"]))
        groups.setdefault(key, []).append(row)
    out = []
    for (policy, k), subset in sorted(groups.items()):
        entry = {"policy": policy, "k": k, "n_streams": len(subset),
                 "n_events": sum(int(float(row["n_events"])) for row in subset),
                 "unit": "independent stream (site-day)",
                 "bootstrap": {"n_boot": N_BOOT, "seed": SEED, "method": "percentile"}}
        for metric in METRICS:
            values = [float(row[metric]) for row in subset if row.get(metric) not in ("", None)]
            if len(values) < 2:
                entry[metric + "_mean"] = None
                entry[metric + "_low"] = None
                entry[metric + "_high"] = None
                continue
            ci = bootstrap_ci(values, n_boot=N_BOOT, alpha=0.05, seed=SEED)
            entry[metric + "_mean"] = ci["point"]
            entry[metric + "_low"] = ci["low"]
            entry[metric + "_high"] = ci["high"]
        out.append(entry)
    target = BASE / "curve_E2_summary.csv"
    fieldnames = []
    for entry in out:
        for key in entry:
            if key not in fieldnames:
                fieldnames.append(key)
    with open(target, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for entry in out:
            writer.writerow({key: (json.dumps(value, ensure_ascii=False)
                                  if isinstance(value, (dict, list)) else value)
                             for key, value in entry.items()})
    meta = {"source": source.name, "rows": len(out), "n_boot": N_BOOT, "seed": SEED,
            "unit": "independent stream (site-day)",
            "note": ("bootstrap 重采样单位=独立场站-日；bootstrap 次数不是样本量；"
                     "未做多重比较校正（E2 为曲线描述，不作确认性比较）；"
                     "service_* 为失败率，越低越好；charging_access_rate 为交付过电量比例"),
            "metrics": list(METRICS)}
    (BASE / "curve_E2_summary.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(out), "output": str(target),
                      "k_values": sorted({entry["k"] for entry in out})},
                     ensure_ascii=True))
    return out


if __name__ == "__main__":
    main()
