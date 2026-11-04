"""Build a full-history NYC panel summary (v3) from the complete kj7g-u4gp snapshot.

The v2 panel kept 365 days per site and matched a single naming regime.  The
source dataset actually runs from 2021-07 to 2026-09 and changes naming twice,
so this script maps every documented location_name to a site_id, rebuilds the
occupancy timeline with the same duration-authoritative rules as v2, and reports:

  * coverage and capacity growth (first/last session per charge box),
  * daily peak occupancy (full history and last 365 days),
  * connector status counts (PAID / ROAMING / DISCONNECTED / INVALID / ABORTED),
  * observed power class per box (L2 vs DC fast, from energy / charge minutes),
  * day-of-week session counts against the posted opening hours.

It writes summaries only; per-session CSVs stay out of the repository because the
raw snapshot is 90+ MB.  Re-running needs the raw file (hash in sources.md).

Usage:
    python data/tools/build_nyc_v3_panel.py --raw tmp/raw/kj7g-u4gp_all.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "data", "tools"))
import rebuild_nyc_v2 as R2  # noqa: E402  (shared time/merge/peak rules)

V3 = os.path.join(ROOT, "data", "charger_sites", "nyc_v3")
DEFAULT_RAW = os.path.join(ROOT, "tmp", "raw", "kj7g-u4gp_all.jsonl")
DEFAULT_OUT = os.path.join(V3, "panel_summary.json")
DEFAULT_MD = os.path.join(V3, "CAPACITY_TIMELINE.md")
DEFAULT_MD2 = os.path.join(V3, "HOURS_AND_STATUS.md")

# Every location_name string in the snapshot -> site_id.
# Naming changed twice (2021-07..2024-03 unprefixed, 2024-03.. prefixed, plus a
# third variant for JON from 2025-09).  "Queensboro Hall" is a *different*
# facility listed separately by NYC DOT at the same street address as qbo, so it
# is held out instead of being merged into the qbo series.
LOCATION_TO_SITE = {
    "QBO - Queens Borough Hall Municipal Parking Garage": "nyc-qbo",
    "Queens Borough Hall Municipal Parking Garage": "nyc-qbo",
    "CSQ - Court Square Municipal Parking Garage": "nyc-csq",
    "Court Square Municipal Parking Garage": "nyc-csq",
    "DES - Delancey and Essex Municipal Parking Garage": "nyc-des",
    "Delancey and Essex Municipal Parking Garage": "nyc-des",
    "JGU - Jerome Gun Hill Road Municipal Parking Garage": "nyc-jgu",
    "Jerome-Gun Hill Road Municipal Parking Garage": "nyc-jgu",
    "BRI - Bay Ridge Municipal Parking Garage": "nyc-bri",
    "Bay Ridge Municipal Parking Garage": "nyc-bri",
    "JON - Jerome 190th Street Municipal Parking": "nyc-jon",
    "JON - Jerome 190th Street Municipal Parking Garage": "nyc-jon",
    "Jerome 190th Street Municipal Parking": "nyc-jon",
    "SGE - St. George Courthouse Garage": "nyc-sge",
    "SGE - St. George Courthouse Municipal Parking Garage": "nyc-sge",
    "St. George Courthouse": "nyc-sge",
    "QFA - Queens Family Court Municipal Garage": "nyc-qfa",
    "QFA - Queens Family Court Municipal Parking Garage": "nyc-qfa",
    "Queens Family Court Municipal Garage": "nyc-qfa",
    "STW - Steinway #2 Municipal Parking Field": "nyc-stw",
    "CPO - College Point Municipal Parking Field": "nyc-cpo",
    "WPL - White Plains Road Municipal Parking Field": "nyc-wpl",
    "The additional L2 EVSEs are not available yet. - WPL - White Plains Road Municipal Parking Field": "nyc-wpl",
    "HPO - Hunts Point Municipal Parking Field": "nyc-hpo",
}
HELD_OUT = {"Queensboro Hall": "separate DOT facility at the qbo street address",
            "N/A": "no location name in the source row"}


def parse_rows(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            loc = r.get("location_name")
            sid = LOCATION_TO_SITE.get(loc)
            r["_site"] = sid
            out.append(r)
    return out


def power_class(kw):
    if kw is None:
        return "unclassified"
    if kw < 20:
        return "L2"
    return "DCFC"


def build_site(sid, recs):
    stats = Counter()
    rows = []
    for r in recs:
        stats["rows"] += 1
        try:
            dur = float(r.get("connected_duration_min"))
        except Exception:
            stats["bad_duration"] += 1
            continue
        ct, dt = r.get("connected_time"), r.get("disconnected_time")
        if not ct or not dt:
            stats["bad_time"] += 1
            continue
        d = R2.parse_date(r["date"])
        score, fold, start, end = R2.choose_fold(d, ct, dt, dur)
        wall = R2.wall_minutes(ct, dt)
        cls, diff, dst = R2.classify(dur, wall, start, end)
        stats[cls] += 1
        if cls in ("other", "nonpositive"):
            continue
        rows.append({
            "start": start, "end": end, "dur": dur, "box": r.get("charge_box_id"),
            "conn": int(r.get("connector_id") or 0), "energy": r.get("energy_provided_kwh"),
            "status": r.get("session_status"), "reason": r.get("invalidity_reason"),
            "charge_min": r.get("charge_duration_min"), "driver": r.get("driver_id"),
        })

    seen, kept = set(), []
    for x in rows:
        key = (x["box"], x["conn"], x["start"], x["end"])
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(x)

    byk = defaultdict(list)
    for x in kept:
        byk[(x["box"], x["conn"])].append((x["start"], x["end"]))
    merged = {k: R2.merge(v) for k, v in byk.items()}
    all_start = min((a for v in merged.values() for a, b in v), default=None)
    all_end = max((b for v in merged.values() for a, b in v), default=None)
    if all_start is None:
        return None
    span = [all_start.date() + timedelta(days=i) for i in range((all_end.date() - all_start.date()).days + 1)]
    # bucket intervals by calendar day first: a straight per-day scan over every
    # interval is O(days * sessions) and takes minutes on the 5-year panel
    by_day = defaultdict(list)
    for v in merged.values():
        for a, b in v:
            d = a.date()
            while d <= b.date():
                ds, de = R2.day_bounds(d)
                st, en = max(a, ds), min(b, de)
                if en > st:
                    by_day[d].append((st, en))
                d += timedelta(days=1)
    peaks = {str(d): R2.peak(by_day.get(d, [])) for d in span}

    # capacity timeline: first / last session per box
    first_seen, last_seen = {}, {}
    for x in kept:
        b = x["box"]
        d = x["start"].date()
        if b not in first_seen or d < first_seen[b]:
            first_seen[b] = d
        if b not in last_seen or d > last_seen[b]:
            last_seen[b] = d
    boxes_by_year = Counter(str(d.year) for d in first_seen.values())
    by_month = Counter()
    for x in kept:
        by_month["%04d-%02d" % (x["start"].year, x["start"].month)] += 1

    # observed power class per box
    box_kw = defaultdict(list)
    for x in kept:
        try:
            e = float(x["energy"])
            cm = float(x["charge_min"])
        except Exception:
            continue
        if e > 1 and cm >= 10:
            box_kw[x["box"]].append(e / (cm / 60.0))
    box_class = {}
    for b, vals in box_kw.items():
        vals.sort()
        box_class[b] = power_class(vals[len(vals) // 2])
    class_counts = Counter(box_class.values())

    status = Counter(x["status"] for x in kept)
    reasons = Counter(x["reason"] for x in kept if x["reason"])
    zero_energy = 0
    for x in kept:
        try:
            if float(x["energy"] or 0) == 0:
                zero_energy += 1
        except (TypeError, ValueError):
            continue
    dow = Counter(x["start"].strftime("%a") for x in kept)

    last_day = span[-1]
    cutoff = last_day - timedelta(days=364)
    recent = {k: v for k, v in peaks.items() if date.fromisoformat(k) >= cutoff}
    drivers = [x["driver"] for x in kept if x["driver"]]
    driver_counts = Counter(drivers)

    return {
        "site_id": sid,
        "rows_in_source": stats["rows"],
        "rows_kept": len(kept),
        "rows_merged_out": stats["duplicate"],
        "class_counts": {k: stats[k] for k in ("consistent", "multi_day", "dst", "other", "nonpositive")},
        "first_session_day": str(span[0]),
        "last_session_day": str(span[-1]),
        "days_in_span": len(span),
        "days_with_events": sum(1 for v in peaks.values() if v > 0),
        "peak_all_history": max(peaks.values()) if peaks else 0,
        "peak_last_365d": max(recent.values()) if recent else None,
        "mean_peak_last_365d": (round(sum(recent.values()) / len(recent), 3) if recent else None),
        "peak_histogram_all": {str(k): v for k, v in sorted(Counter(peaks.values()).items())},
        "peak_histogram_last_365d": {str(k): v for k, v in sorted(Counter(recent.values()).items())},
        "peaks_last_365d": {k: v for k, v in sorted(recent.items())},
        "charge_boxes": len(first_seen),
        "boxes_first_seen_by_year": dict(sorted(boxes_by_year.items())),
        "box_first_seen": {b: str(d) for b, d in sorted(first_seen.items(), key=lambda kv: kv[1])},
        "box_last_seen": {b: str(d) for b, d in sorted(last_seen.items(), key=lambda kv: kv[1])},
        "sessions_by_month": dict(sorted(by_month.items())),
        "power_class_boxes": dict(class_counts),
        "box_median_kw": {b: round(sorted(v)[len(v) // 2], 2) for b, v in box_kw.items()},
        "status_counts": dict(status),
        "invalidity_reasons": dict(reasons),
        "zero_energy_sessions": zero_energy,
        "zero_energy_share_pct": round(100.0 * zero_energy / len(kept), 3) if kept else None,
        "sessions_by_weekday": dict(dow),
        "drivers_distinct": len(driver_counts),
        "sessions_per_driver_mean": round(len(drivers) / len(driver_counts), 2) if driver_counts else None,
        "top_driver_share_pct": round(100.0 * driver_counts.most_common(1)[0][1] / len(drivers), 2) if drivers else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=DEFAULT_RAW)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--md", default=DEFAULT_MD)
    ap.add_argument("--md2", default=DEFAULT_MD2)
    args = ap.parse_args()
    if not os.path.exists(args.raw):
        print("missing raw snapshot: %s" % args.raw)
        return 2

    allrows = parse_rows(args.raw)
    by_site = defaultdict(list)
    held = Counter()
    for r in allrows:
        if r["_site"]:
            by_site[r["_site"]].append(r)
        else:
            held[r.get("location_name")] += 1

    out = {"source": {"snapshot": os.path.relpath(args.raw, ROOT),
                      "manifest": os.path.relpath(args.raw + ".manifest.json", ROOT),
                      "rows_total": len(allrows)},
           "held_out": {k: {"rows": v, "reason": HELD_OUT.get(k, "unmapped")} for k, v in held.items()},
           "sites": {}}
    for sid in sorted(by_site):
        b = build_site(sid, by_site[sid])
        if b:
            out["sites"][sid] = b
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    lines = ["# NYC 全历史容量时间线（v3）", "", "类型: 数据说明", "状态: 生效", "负责人: tho25",
             "日期: 2026-11-03", "生成命令: python data/tools/build_nyc_v3_panel.py", "",
             "| site | 首末会话 | 天数 | 有事件日 | 充电箱数 | 首见年份分布 | 全历史峰值 | 近 365 天峰值 |",
             "|---|---|---|---:|---:|---|---:|---:|"]
    for sid, b in out["sites"].items():
        lines.append("| %s | %s..%s | %d | %d | %d | %s | %s | %s |" % (
            sid.replace("nyc-", ""), b["first_session_day"], b["last_session_day"], b["days_in_span"],
            b["days_with_events"], b["charge_boxes"],
            ", ".join("%s:%d" % (k, v) for k, v in b["boxes_first_seen_by_year"].items()),
            b["peak_all_history"], b["peak_last_365d"]))
    lines += ["", "## 说明", "",
              "- 名称映射覆盖快照里全部 location_name；`Queensboro Hall` 与 `N/A` 不进任何站点序列。",
              "- 峰值口径与 v2 相同：同一 (charge_box_id, connector_id) 的区间先合并，再按日历日扫最大重叠。",
              "- “首见年份”是设备投运的观测代理，不是投运日；未使用的设备不会出现。",
              "- 全历史把 2021-07 起的旧命名与 2024-03 起的新命名接在同一站点上，若设备在期间扩容，",
              "  全历史峰值与近 365 天峰值不可直接比较。", ""]
    with open(args.md, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))

    lines2 = ["# NYC 会话状态、功率类别与星期分布（v3）", "", "类型: 数据说明", "状态: 生效",
              "负责人: tho25", "日期: 2026-11-03",
              "生成命令: python data/tools/build_nyc_v3_panel.py", "",
              "| site | 保留会话 | 零电量 | 零电量% | INVALID | ABORTED | DISCONNECTED | L2箱 | DCFC箱 | 周日会话占比 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for sid, b in out["sites"].items():
        n = b["rows_kept"] or 1
        st = b["status_counts"]
        sunday = b["sessions_by_weekday"].get("Sun", 0)
        lines2.append("| %s | %d | %d | %.2f | %d | %d | %d | %d | %d | %.1f%% |" % (
            sid.replace("nyc-", ""), b["rows_kept"], b["zero_energy_sessions"], b["zero_energy_share_pct"] or 0,
            st.get("INVALID", 0), st.get("ABORTED", 0), st.get("DISCONNECTED", 0),
            b["power_class_boxes"].get("L2", 0), b["power_class_boxes"].get("DCFC", 0),
            100.0 * sunday / n))
    lines2 += ["", "## 说明", "",
               "- 零电量＝energy_provided_kwh 为 0 的会话；其中 NO_ENERGY_DISPENSED 与 ZERO_CHARGING_TIME",
               "  是“插枪但没充上”的观测记录，属于连接器侧失败，不等于“排队被拒”。",
               "- L2/DCFC 分类用该箱会话的中位观测功率（energy / charge_duration），阈值 20 kW；",
               "  观测平均功率不是额定功率，只用于区分慢充与快充两类设备。",
               "- 星期分布只描述观测；若要判断是否违反挂牌营业时间，需与 hours_raw 一起读。", ""]
    with open(args.md2, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines2))

    print("rows:", len(allrows), " sites:", len(out["sites"]), " held out:", dict(held))
    for sid, b in out["sites"].items():
        print("  %-8s %s..%s boxes=%d peak_all=%d peak_365=%s" % (
            sid.replace("nyc-", ""), b["first_session_day"], b["last_session_day"],
            b["charge_boxes"], b["peak_all_history"], b["peak_last_365d"]))
    print("wrote:", os.path.relpath(args.out, ROOT), os.path.relpath(args.md, ROOT), os.path.relpath(args.md2, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
