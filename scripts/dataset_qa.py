#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一事件契约 CSV 的数据质量检查（只读输入，显式 --out 才写文件）。

输入列（全部必填）:
    site_id, event_id, arrival_ts_utc, departure_ts_utc, dwell_min,
    site_capacity, day_local, arrival_local_hour, source_dataset, source_row

输出: <out>/qa_stats.json 与 <out>/qa_report.md。
口径说明:
  - 所有计数分母都是总行数 total_rows；"可解析行"指两个时间戳都能解析的行数 parseable_rows。
  - duration_min = (departure_ts_utc - arrival_ts_utc) 折算分钟；dwell_delta_min = duration_min - dwell_min。
  - 负时长/不一致/跨日等指标只在可解析行上计算，分母为 parseable_rows，报告中写明。
  - 容量冲突扫描：按 (site_id, arrival_ts_utc, event_id) 排序后逐场站扫描，
    每个样本的在场数 = 该场站中满足 arrival <= t_sample 且 departure > t_sample 的事件数（含自身），
    超过该场站 site_capacity 即计一次冲突样本。
  - 完整24h覆盖日：某场站某天本地有事件到达且覆盖 0..23 全部 24 个本地小时。
退出码: 0 = 正常完成；1 = 数据存在质量问题；2 = 用法或输入错误（缺列、空文件等）。
用法:
    python scripts/dataset_qa.py --events events.csv --out outdir
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

REQUIRED_COLUMNS = [
    "site_id", "event_id", "arrival_ts_utc", "departure_ts_utc", "dwell_min",
    "site_capacity", "day_local", "arrival_local_hour", "source_dataset", "source_row",
]


def parse_ts(value):
    """解析 ISO-8601 UTC 时间戳；失败返回 None。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_float(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_events(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in header]
        if missing:
            raise SystemExit("缺少必需列: " + ", ".join(missing))
        rows = list(reader)
    if not rows:
        raise SystemExit("输入为空文件（只有表头或完全为空）")
    return rows


def analyze(rows):
    n = len(rows)
    stats = {
        "total_rows": n,
        "missing_required_fields": {},
        "duplicate_event_ids": 0,
        "duplicate_site_arrival": 0,
        "negative_duration": 0,
        "dwell_mismatch": 0,
        "cross_day_events": 0,
        "capacity_conflict_samples": 0,
        "empty_or_nonpositive_capacity": 0,
        "unparseable_timestamps": 0,
        "per_site_event_counts": {},
        "full_24h_coverage_days": {},
        "dwell_minutes_quantiles": {},
        "arrival_local_hour_distribution": {},
        "denominators": {},
    }

    # ---- 缺失必填字段（每列各计一次，同一行多列缺失分别计入各列）----
    for col in REQUIRED_COLUMNS:
        cnt = sum(1 for r in rows if r.get(col) is None or str(r[col]).strip() == "")
        stats["missing_required_fields"][col] = cnt

    # ---- 重复计数（基于原始字符串，去空白后比较）----
    seen_eid = {}
    dup_eid = 0
    for r in rows:
        k = str(r.get("event_id") or "").strip()
        if not k:
            continue
        if k in seen_eid:
            dup_eid += 1
        else:
            seen_eid[k] = True
    stats["duplicate_event_ids"] = dup_eid

    seen_sa = {}
    dup_sa = 0
    for r in rows:
        k = (str(r.get("site_id") or "").strip(), str(r.get("arrival_ts_utc") or "").strip())
        if k[0] == "" and k[1] == "":
            continue
        if k in seen_sa:
            dup_sa += 1
        else:
            seen_sa[k] = True
    stats["duplicate_site_arrival"] = dup_sa

    # ---- 时间戳解析 / 时长 / 不一致 / 跨日 / 容量 / 分布 ----
    parseable = 0
    unparseable = 0
    negative = 0
    mismatch = 0
    cross_day = 0
    bad_cap = 0
    per_site = {}
    site_day_hours = {}
    dwell_vals = []
    hour_hist = {h: 0 for h in range(24)}
    scan_items = []

    for r in rows:
        a_raw = str(r.get("arrival_ts_utc") or "").strip()
        d_raw = str(r.get("departure_ts_utc") or "").strip()
        a = parse_ts(a_raw)
        d = parse_ts(d_raw)
        if a is None or d is None:
            unparseable += 1
            continue
        parseable += 1

        dur_min = (d - a).total_seconds() / 60.0
        if dur_min < 0:
            negative += 1

        dw = parse_float(r.get("dwell_min"))
        if dw is not None:
            dwell_vals.append(dw)
            if abs(dur_min - dw) > 1e-9:
                mismatch += 1

        dl = str(r.get("day_local") or "").strip()
        if dl and dl != a.date().isoformat():
            cross_day += 1

        cap = parse_float(r.get("site_capacity"))
        if cap is None or cap <= 0:
            bad_cap += 1

        site = str(r.get("site_id") or "").strip()
        per_site[site] = per_site.get(site, 0) + 1

        h = parse_float(r.get("arrival_local_hour"))
        if h is not None and 0 <= int(h) <= 23 and float(h).is_integer():
            hour_hist[int(h)] += 1

        if site and dl:
            key = (site, dl)
            site_day_hours.setdefault(key, set()).add(int(h) if h is not None and float(h).is_integer() else -1)

        scan_items.append((site, a, d, cap))

    stats["unparseable_timestamps"] = unparseable
    stats["negative_duration"] = negative
    stats["dwell_mismatch"] = mismatch
    stats["cross_day_events"] = cross_day
    stats["empty_or_nonpositive_capacity"] = bad_cap
    stats["per_site_event_counts"] = dict(sorted(per_site.items()))

    full_days = {}
    for (site, dl), hours in sorted(site_day_hours.items()):
        ok = all(h in hours for h in range(24))
        full_days[dl + "@" + site] = bool(ok)
    stats["full_24h_coverage_days"] = full_days

    # ---- 容量冲突扫描（按到达排序，同场站内部扫描）----
    conflict = 0
    by_site = {}
    for site, a, d, cap in scan_items:
        by_site.setdefault(site, []).append((a, d, cap))
    for site, items in by_site.items():
        items.sort(key=lambda x: (x[0], x[1]))
        for i, (ai, di, ci) in enumerate(items):
            if ci is None or ci <= 0:
                continue
            present = 0
            for j, (aj, dj, _) in enumerate(items):
                if aj <= ai and dj > ai:
                    present += 1
            if present > ci:
                conflict += 1
    stats["capacity_conflict_samples"] = conflict

    # ---- 停留时长分位数（分母 = 可解析 dwell_min 的行数）----
    q = {"p50": None, "p90": None, "p99": None, "max": None}
    if dwell_vals:
        import numpy as np
        arr = np.asarray(dwell_vals, dtype=float)
        q["p50"] = float(np.percentile(arr, 50))
        q["p90"] = float(np.percentile(arr, 90))
        q["p99"] = float(np.percentile(arr, 99))
        q["max"] = float(arr.max())
    stats["dwell_minutes_quantiles"] = q
    stats["arrival_local_hour_distribution"] = {str(h): hour_hist[h] for h in range(24)}

    stats["denominators"] = {
        "total_rows": n,
        "parseable_rows": parseable,
        "rows_with_dwell_min": len(dwell_vals),
        "note": ("缺失/重复计数分母为 total_rows；负时长、dwell 不一致、跨日、时间戳不可解析、"
                 "容量冲突分母为 parseable_rows（两时间戳均可解析的行）；"
                 "分位数分母为 rows_with_dwell_min；hour 分布分母为 total_rows。"),
    }
    return stats


def write_outputs(stats, out_dir, events_path):
    os.makedirs(out_dir, exist_ok=True)
    js_path = os.path.join(out_dir, "qa_stats.json")
    md_path = os.path.join(out_dir, "qa_report.md")

    with open(js_path, "w", encoding="utf-8", newline="") as fh:
        json.dump({"input": os.path.abspath(events_path), "generated_at": datetime.now().isoformat(timespec="seconds"), **stats}, fh, ensure_ascii=False, indent=2)

    L = []
    ap = L.append
    ap("# 数据集 QA 报告")
    ap("")
    ap("- 输入: " + os.path.abspath(events_path))
    ap("- 生成时间: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    ap("- 总行数: " + str(stats["total_rows"]))
    ap("- 可解析行（两时间戳均可解析）: " + str(stats["denominators"]["parseable_rows"]))
    ap("")
    ap("## 逐项计数（分母见末节）")
    ap("")
    ap("| 指标 | 值 | 分母 |")
    ap("|---|---|---|")
    ap("| 总行数 | " + str(stats["total_rows"]) + " | — |")
    ap("| 缺失必填字段合计 | " + str(sum(stats["missing_required_fields"].values())) + " | total_rows × 10 列 |")
    ap("| 重复 event_id | " + str(stats["duplicate_event_ids"]) + " | total_rows |")
    ap("| 重复 (site_id, arrival_ts_utc) | " + str(stats["duplicate_site_arrival"]) + " | total_rows |")
    ap("| 负 duration | " + str(stats["negative_duration"]) + " | parseable_rows |")
    ap("| dwell_min 与时间戳不一致 | " + str(stats["dwell_mismatch"]) + " | rows_with_dwell_min |")
    ap("| 跨日事件（day_local ≠ 到达日） | " + str(stats["cross_day_events"]) + " | parseable_rows |")
    ap("| 容量冲突样本 | " + str(stats["capacity_conflict_samples"]) + " | parseable_rows |")
    ap("| 空或 <=0 的 site_capacity | " + str(stats["empty_or_nonpositive_capacity"]) + " | total_rows |")
    ap("| 时间戳无法解析 | " + str(stats["unparseable_timestamps"]) + " | total_rows |")
    ap("")
    ap("### 缺失必填字段（按列）")
    ap("")
    ap("| 列 | 缺失数 |")
    ap("|---|---|")
    for col in REQUIRED_COLUMNS:
        ap("| " + col + " | " + str(stats["missing_required_fields"][col]) + " |")
    ap("")
    ap("### 每场站事件数")
    ap("")
    ap("| site_id | 事件数 |")
    ap("|---|---|")
    for site, cnt in stats["per_site_event_counts"].items():
        ap("| " + (site or "(空)") + " | " + str(cnt) + " |")
    ap("")
    ap("### 每日本地完整 24h 覆盖日（site@day → 是否覆盖 0..23 全部小时）")
    ap("")
    ap("| site@day_local | 完整覆盖 |")
    ap("|---|---|")
    for key, ok in stats["full_24h_coverage_days"].items():
        ap("| " + key + " | " + ("是" if ok else "否") + " |")
    ap("")
    ap("### 停留时长分位数（分钟，分母 = rows_with_dwell_min = " + str(stats["denominators"]["rows_with_dwell_min"]) + "）")
    ap("")
    q = stats["dwell_minutes_quantiles"]
    ap("| p50 | p90 | p99 | max |")
    ap("|---|---|---|---|")
    ap("| " + str(q["p50"]) + " | " + str(q["p90"]) + " | " + str(q["p99"]) + " | " + str(q["max"]) + " |")
    ap("")
    ap("### arrival_local_hour 分布（24 桶，分母 = total_rows）")
    ap("")
    ap("| hour | count |")
    ap("|---|---|")
    for h in range(24):
        ap("| " + str(h) + " | " + str(stats["arrival_local_hour_distribution"][str(h)]) + " |")
    ap("")
    ap("## 分母说明")
    ap("")
    ap(stats["denominators"]["note"])
    ap("")
    with open(md_path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(L) + "\n")
    return js_path, md_path


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="统一事件契约 CSV 数据质量检查")
    ap.add_argument("--events", required=True, help="输入 CSV 路径")
    ap.add_argument("--out", required=True, help="输出目录（写 qa_stats.json 与 qa_report.md）")
    args = ap.parse_args()

    if not os.path.isfile(args.events):
        print("找不到输入文件: " + args.events, file=sys.stderr)
        return 2
    rows = load_events(args.events)
    stats = analyze(rows)
    js_path, md_path = write_outputs(stats, args.out, args.events)

    problem_keys = ["duplicate_event_ids", "duplicate_site_arrival", "negative_duration",
                    "dwell_mismatch", "cross_day_events", "capacity_conflict_samples",
                    "empty_or_nonpositive_capacity", "unparseable_timestamps"]
    problems = sum(stats[k] for k in problem_keys) + sum(stats["missing_required_fields"].values())
    print("总行数: " + str(stats["total_rows"]))
    print("问题计数合计: " + str(problems))
    print("qa_stats.json: " + js_path)
    print("qa_report.md: " + md_path)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
