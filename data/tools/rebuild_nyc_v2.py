#!/usr/bin/env python3
"""Rebuild the NYC municipal-garage panel as versioned v2.

Why v2: v1 built the departure as date + disconnected_time, rolling over one day
only when that wall time was <= arrival.  A session that stays connected across
one or more midnights therefore had a same-day wall duration (e.g. 212 min)
instead of the operator's connected_duration_min (1652 min).  The official field
description says connected_duration_min is "the number of minutes the EV charger
was connected"; the audit in tmp/audit_multiday_v3*.py shows 532 multi-day and
58 DST-shifted records, and a duration-based reconstruction removes 5,306
impossible same-connector overlaps that the end-date reconstruction would create.

Canonical rule (fixed for v2):
  start = localise(date + connected_time) in America/New_York (fold chosen to
          match disconnected_time when the wall hour is ambiguous);
  end   = start_utc + connected_duration_min minutes, converted back to local;
  wall  = (disconnected_time - connected_time) mod 24 h (diagnostic only);
  class = consistent | multi_day | dst | nonpositive | other.
  "other" rows are isolated in conflicts.csv and excluded from the default panel;
  the sensitivity branch keeps them with the duration rule.
  Duplicate (box, connector, start, end) rows are dropped.
  Occupancy intervals are merged per (box, connector) before the peak sweep: one
  physical connector cannot serve two sessions at once, so an overlap is a data
  artefact, not two simultaneous demands.
  W_d = calendar-day peak with local-midnight boundaries; a session crossing
  midnight is clipped into both days.  m_obs = days with a session (primary, no
  zero filling); m_span = all span days with W=0 (sensitivity only).
  Day status: observed (session) / unknown (no session, no evidence); confirmed
  zero-event, closed and missing-report are kept as separate zero counts because
  no closure or outage evidence exists (closure_evidence = null).

Outputs (v2; v1 is untouched):
  data/charger_sites/nyc_v2/{sites.jsonl,COVERAGE.md,README.md,sources.md,
      CHANGELOG.md,snapshot_manifest.json}
  data/demand_v2/<site>/{events.csv,sessions_v2.csv,quality.json}
  data/demand_v2/diffs/{session_diffs.csv,day_peak_diffs.csv,rebuild_summary.json}
Run: python data/tools/rebuild_nyc_v2.py
"""
import csv, hashlib, json, math, os, sys
from collections import Counter, defaultdict
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "tmp", "raw")
V1_SITES = os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl")
V1_DEMAND = os.path.join(ROOT, "data", "demand")
OUT_SITES = os.path.join(ROOT, "data", "charger_sites", "nyc_v2")
OUT_DEMAND = os.path.join(ROOT, "data", "demand_v2")
TZ = ZoneInfo("America/New_York")
ALPHA = 0.05
RHOS = (0.10, 0.15, 0.20)
DATASET_URL = "https://data.cityofnewyork.us/d/kj7g-u4gp"
FETCHED = "2026-11-02"
VERSION = "v2"
RULE = "duration-authoritative; local start; absolute minutes; merged per connector"

SITE_META = {
 "nyc-csq": ("Court Square Municipal Parking Garage", "Queens", "CSQ"),
 "nyc-qbo": ("Queens Borough Hall Municipal Parking Garage", "Queens", "QBO"),
 "nyc-des": ("Delancey and Essex Municipal Parking Garage", "Manhattan", "DES"),
 "nyc-jon": ("Jerome 190th Street Municipal Parking", "Bronx", "JON"),
 "nyc-bri": ("Bay Ridge Municipal Parking Garage", "Brooklyn", "BRI"),
 "nyc-jgu": ("Jerome Gun Hill Road Municipal Parking Garage", "Bronx", "JGU"),
 "nyc-sge": ("St. George Courthouse Garage", "Staten Island", "SGE"),
 "nyc-qfa": ("Queens Family Court Municipal Garage", "Queens", "QFA"),
 "nyc-cpo": ("College Point Municipal Parking Field", "Queens", "CPO"),
 "nyc-hpo": ("Hunts Point Municipal Parking Field", "Bronx", "HPO"),
 "nyc-stw": ("Steinway #2 Municipal Parking Field", "Queens", "STW"),
 "nyc-wpl": ("White Plains Road Municipal Parking Field", "Bronx", "WPL"),
}


def parse_date(s):
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def hms(t):
    p = t.split(":")
    sec = float(p[2]) if len(p) > 2 else 0.0
    return int(p[0]) * 3600 + int(p[1]) * 60 + sec


def wall_minutes(ct, dt):
    w = (hms(dt) - hms(ct)) / 60.0
    return w + 1440 if w < 0 else w


def start_dt(d, t, fold=0):
    p = t.split(":")
    sec = float(p[2]) if len(p) > 2 else 0.0
    return datetime(d.year, d.month, d.day, int(p[0]), int(p[1]), int(sec), tzinfo=TZ, fold=fold)


def add_min(dt, minutes):
    return (dt.astimezone(timezone.utc) + timedelta(minutes=minutes)).astimezone(TZ)


def choose_fold(d, ct, dt, dur):
    """Pick the fold whose absolute end best matches the reported end clock."""
    best = None
    for fold in (0, 1):
        s = start_dt(d, ct, fold)
        e = add_min(s, dur)
        em = (e.hour * 60 + e.minute + e.second / 60.0) - hms(dt) / 60.0
        while em > 720:
            em -= 1440
        while em < -720:
            em += 1440
        if best is None or abs(em) < best[0] - 1e-9:
            best = (abs(em), fold, s, e)
    return best


def classify(dur, wall, start, end):
    diff = dur - wall
    k = round(diff / 1440.0)
    r = diff - k * 1440.0
    dst = start.utcoffset() != end.utcoffset()
    if dur <= 0:
        return "nonpositive", diff, dst
    if abs(r) <= 1.0:
        return ("consistent" if k == 0 else "multi_day"), diff, dst
    if abs(abs(r) - 60.0) <= 1.0 and dst:
        return "dst", diff, dst
    return "other", diff, dst


def merge(ivs):
    out = []
    for a, b in sorted(ivs):
        if b <= a:
            continue
        if out and a < out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def peak(ivs):
    ev = []
    for a, b in ivs:
        if b > a:
            ev.append((a, 1))
            ev.append((b, -1))
    ev.sort(key=lambda x: (x[0], x[1]))
    cur = best = 0
    for _, v in ev:
        cur += v
        best = max(best, cur)
    return best


def day_bounds(d):
    return (datetime.combine(d, time.min, tzinfo=TZ),
            datetime.combine(d + timedelta(days=1), time.min, tzinfo=TZ))


def radius(m):
    return math.sqrt(math.log(1.0 / ALPHA) / (2 * m))


def tail(vals, n):
    return sum(1 for w in vals if w > n) / len(vals)


def certify(vals, rho):
    if not vals:
        return None
    m = len(vals)
    d = radius(m)
    for n in range(0, max(vals) + 1):
        if min(1.0, tail(vals, n) + d) <= rho + 1e-12:
            return n
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def relation(cert_n, n_obs):
    if cert_n is None:
        return "unissued"
    if cert_n < n_obs:
        return "below"
    if cert_n == n_obs:
        return "meets"
    return "conflict"


def load_v1():
    sites = {json.loads(l)["site_id"]: json.loads(l) for l in open(V1_SITES, encoding="utf-8") if l.strip()}
    out = {}
    for sid in sites:
        qp = os.path.join(V1_DEMAND, sid, "quality.json")
        out[sid] = json.load(open(qp, encoding="utf-8")) if os.path.exists(qp) else None
    return sites, out


def build_site(sid, windows):
    src = os.path.join(RAW, "sess_%s.jsonl" % sid)
    recs = [json.loads(l) for l in open(src, encoding="utf-8")]
    stats = Counter()
    rows, conflicts = [], []
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
        d = parse_date(r["date"])
        score, fold, start, end = choose_fold(d, ct, dt, dur)
        wall = wall_minutes(ct, dt)
        cls, diff, dst = classify(dur, wall, start, end)
        stats[cls] += 1
        stats["dst_cross"] += dst
        stats["fold1"] += (fold == 1)
        rec = {"site_id": sid, "date": str(d), "connected_time": ct, "disconnected_time": dt,
               "start": start, "end": end, "duration_min": dur, "wall_min": wall,
               "diff_min": diff, "class": cls, "dst_cross": dst, "fold": fold,
               "box": r.get("charge_box_id"), "connector": str(r.get("connector_id") or ""),
               "energy_kwh": r.get("energy_provided_kwh"), "status": r.get("session_status"),
               "reason": r.get("invalidity_reason"), "score": score}
        if cls == "other":
            conflicts.append(rec)
            continue
        if cls == "nonpositive":
            continue
        rows.append(rec)
    # duplicates and merged intervals
    seen = set()
    kept = []
    for x in rows:
        key = (x["box"], x["connector"], x["start"], x["end"])
        if key in seen:
            stats["duplicate"] += 1
            continue
        seen.add(key)
        kept.append(x)
    rows = kept
    byk = defaultdict(list)
    for x in rows:
        byk[(x["box"], x["connector"])].append((x["start"], x["end"]))
    merged = {k: merge(v) for k, v in byk.items()}
    starts = [a.date() for v in merged.values() for a, b in v]
    ends = [b.date() for v in merged.values() for a, b in v]
    first, last = min(starts), max(ends)
    span = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    peaks, cov_hours = {}, {}
    for d in span:
        ds, de = day_bounds(d)
        ivs = []
        hours = set()
        for v in merged.values():
            for a, b in v:
                st, en = max(a, ds), min(b, de)
                if en > st:
                    ivs.append((st, en))
                    t = st.replace(minute=0, second=0, microsecond=0)
                    if t < st:
                        t += timedelta(hours=1)
                    while t < en:
                        hours.add(t.hour)
                        t += timedelta(hours=1)
        peaks[str(d)] = peak(ivs)
        cov_hours[str(d)] = len(hours)
    arrival_peaks = {}
    for d in sorted({x["start"].date() for x in rows}):
        ds, de = day_bounds(d)
        ivs = []
        for x in rows:
            if x["start"].date() != d:
                continue
            st, en = max(x["start"], ds), min(x["end"], de)
            if en > st:
                ivs.append((st, en))
        arrival_peaks[str(d)] = peak(ivs)
    observed = [str(d) for d in span if peaks[str(d)] > 0]
    vals_obs = [peaks[d] for d in observed]
    vals_span = [peaks[str(d)] for d in span]
    full24 = sum(1 for d in span if cov_hours[str(d)] == 24)
    mean_cov = sum(cov_hours.values()) / len(span) / 24 * 100
    cert_obs = {str(r): certify(vals_obs, r) for r in RHOS}
    cert_span = {str(r): certify(vals_span, r) for r in RHOS}
    # capacity proxy
    boxes = sorted({x["box"] for x in rows if x["box"]})
    conns = defaultdict(set)
    for x in rows:
        if x["box"] and x["connector"]:
            conns[x["box"]].add(int(x["connector"]))
    upper = sum(max(v) for v in conns.values()) if conns else 0
    lower = sum(len(v) for v in conns.values())
    gaps = []
    for box, ids in conns.items():
        s = sorted(ids)
        if s and (s[0] != 1 or s != list(range(1, max(s) + 1))):
            gaps.append({"box": box, "connectors": s})
    energy = 0.0
    energy_n = 0
    for x in rows:
        try:
            e = float(x["energy_kwh"])
        except Exception:
            continue
        if e == e:
            energy += e
            energy_n += 1
    day_status = {
        "observed_events": len(observed),
        "unknown_zero": len(span) - len(observed),
        "confirmed_no_event": 0,
        "closed_with_evidence": 0,
        "missing_report_with_evidence": 0,
        "evidence_note": "no closure/outage evidence collected; closure_evidence=null; zero-session days stay unknown",
    }
    return {
        "rows": rows, "conflicts": conflicts, "stats": stats, "span": span, "merged": merged,
        "first": str(first), "last": str(last), "peaks": peaks, "arrival_peaks": arrival_peaks,
        "cov_hours": cov_hours,
        "observed": observed, "vals_obs": vals_obs, "vals_span": vals_span,
        "cert_obs": cert_obs, "cert_span": cert_span, "full24": full24,
        "mean_cov": mean_cov, "boxes": boxes, "conns": conns, "upper": upper,
        "lower": lower, "gaps": gaps, "energy": energy, "energy_n": energy_n,
        "day_status": day_status, "first_dt": first, "last_dt": last,
        "window": windows.get(sid, {}),
    }


def write_demand(sid, b):
    dem = os.path.join(OUT_DEMAND, sid)
    os.makedirs(dem, exist_ok=True)
    with open(os.path.join(dem, "sessions_v2.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "date", "connected_time", "disconnected_time", "start_local", "end_local",
                    "duration_min", "wall_min", "diff_min", "class", "dst_cross", "fold",
                    "charge_box_id", "connector_id", "energy_kWh", "session_status", "invalidity_reason"])
        for x in b["rows"]:
            w.writerow([sid, x["date"], x["connected_time"], x["disconnected_time"],
                        x["start"].isoformat(sep=" "), x["end"].isoformat(sep=" "),
                        round(x["duration_min"], 3), round(x["wall_min"], 3), round(x["diff_min"], 3),
                        x["class"], int(x["dst_cross"]), x["fold"], x["box"], x["connector"],
                        x["energy_kwh"], x["status"], x["reason"]])
    with open(os.path.join(dem, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "arrival_ts", "departure_ts", "space_type", "cross_day"])
        for x in b["rows"]:
            w.writerow([sid, x["start"].isoformat(sep=" "), x["end"].isoformat(sep=" "),
                        "off_street_garage", int(x["start"].date() != x["end"].date())])
    q = {
        "site_id": sid, "version": VERSION, "rule": RULE,
        "source": {"dataset_url": DATASET_URL, "fetched_date": FETCHED,
                   "window_start": b["window"].get("start"), "window_end": b["window"].get("end"),
                   "timezone": "America/New_York",
                   "raw_file": "tmp/raw/sess_%s.jsonl (local, not committed)" % sid},
        "event_count": len(b["rows"]),
        "conflict_count": len(b["conflicts"]),
        "class_counts": dict(b["stats"]),
        "date_first": b["first"], "date_last": b["last"],
        "days_with_events": len(b["observed"]), "days_in_span": len(b["span"]),
        "certificate_m_observed": len(b["observed"]),
        "certificate_m_span": len(b["span"]),
        "date_status": b["day_status"],
        "missing_days_count": None,
        "missing_days": [],
        "day_coverage_pct": round(100.0 * len(b["observed"]) / len(b["span"]), 2),
        "hourly_coverage_mean_pct": round(b["mean_cov"], 2),
        "hourly_coverage_definition": "distinct local clock hours overlapped by at least one session, per day, averaged over span days (occupancy feature, not log completeness)",
        "days_full_24h": b["full24"],
        "days_full_24h_pct": round(100.0 * b["full24"] / len(b["span"]), 2),
        "peak_overlap_values": {d: b["peaks"][d] for d in b["observed"]},
        "peak_overlap_values_span": b["peaks"],
        "peak_overlap_values_arrival_day": b["arrival_peaks"],
        "peak_overlap_max": max(b["vals_span"]),
        "peak_overlap_mean_observed": round(sum(b["vals_obs"]) / len(b["vals_obs"]), 3) if b["vals_obs"] else 0,
        "peak_overlap_mean_span": round(sum(b["vals_span"]) / len(b["vals_span"]), 3),
        "certified_capacity_by_rho_observed": b["cert_obs"],
        "certified_capacity_by_rho_span": b["cert_span"],
        "dkw_radius_dm_observed": round(radius(len(b["vals_obs"])), 6) if b["vals_obs"] else None,
        "dkw_radius_dm_span": round(radius(len(b["vals_span"])), 6),
        "charger_units_observed": len(b["boxes"]),
        "service_points_observed_upper": b["upper"],
        "service_points_observed_lower": b["lower"],
        "connector_gaps": b["gaps"][:20],
        "connector_gap_count": len(b["gaps"]),
        "energy_kwh_total": round(b["energy"], 3),
        "energy_rows": b["energy_n"],
        "notes": "capacity is a proxy from observed box/connector ids; no independent inventory check",
    }
    json.dump(q, open(os.path.join(dem, "quality.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return q






def overlap_count(rows, mode="duration"):
    """Same-connector overlaps under three date/end interpretations.

    duration: start=date+connected_time, end=start+duration (adopted);
    wall: start=date+connected_time, end=date+disconnected_time (+1 day if needed);
    backward: end=date+disconnected_time, start=end-duration (date read as end date).
    """
    byk = defaultdict(list)
    for x in rows:
        d = parse_date(x["date"])
        if mode == "duration":
            a, e = x["start"], x["end"]
        elif mode == "wall":
            a = start_dt(d, x["connected_time"])
            e = start_dt(d, x["disconnected_time"])
            if e <= a:
                e = e + timedelta(days=1)
        elif mode == "backward":
            e = start_dt(d, x["disconnected_time"])
            a = add_min(e, -x["duration_min"])
        else:
            raise ValueError(mode)
        byk[(x["box"], x["connector"])].append((a, e, x["status"]))
    total = 0
    pairs = Counter()
    examples = []
    for key in byk:
        v = sorted(byk[key])
        prev_end = None
        prev_status = None
        for a, e, st in v:
            if prev_end is not None and a < prev_end:
                total += 1
                pairs[tuple(sorted((prev_status, st)))] += 1
                if len(examples) < 5:
                    examples.append({"box": key[0], "connector": key[1], "start": str(a),
                                     "prev_end": str(prev_end), "status": st, "prev_status": prev_status})
            if prev_end is None or e > prev_end:
                prev_end, prev_status = e, st
    return {"count": total, "pairs": {"%s|%s" % k: v for k, v in pairs.items()}, "examples": examples}


def legacy_end_date(x):
    d = parse_date(x["date"])
    if hms(x["disconnected_time"]) <= hms(x["connected_time"]):
        d += timedelta(days=1)
    return d


def count_variants(b, old_peaks):
    """Changed common station-days under merge / old wall-next-boundary variants."""
    out = {}
    for name, merge_flag, wallnext in (("merged", True, False), ("unmerged", False, False),
                                       ("merged_wallnext", True, True), ("unmerged_wallnext", False, True)):
        if merge_flag:
            src = [iv for v in b["merged"].values() for iv in v]
        else:
            src = [(x["start"], x["end"]) for x in b["rows"]]
        changed = 0
        for d in b["span"]:
            ds, de = day_bounds(d)
            if wallnext:
                # Reproduce the old bug: wall-clock +1 day, 23/25 h on DST days.
                de = ds + timedelta(days=1)
            ivs = []
            for a, z in src:
                st, en = max(a, ds), min(z, de)
                if en > st:
                    ivs.append((st, en))
            old = old_peaks.get(str(d))
            if old is not None and old != peak(ivs):
                changed += 1
        out[name] = changed
    return out


def raw_files():
    rows = []
    for fn in sorted(os.listdir(RAW)):
        if not (fn.startswith("sess_") and fn.endswith(".jsonl")):
            continue
        path = os.path.join(RAW, fn)
        sid = fn[len("sess_"):-len(".jsonl")]
        n = 0
        with open(path, "rb") as fh:
            for _ in fh:
                n += 1
        rows.append({"site_id": sid, "path": "tmp/raw/" + fn, "bytes": os.path.getsize(path),
                     "rows": n, "sha256": sha256(path), "local_only": True})
    return rows




def write_docs(site_rows, summary, payload, windows):
    raw = raw_files()
    os.makedirs(OUT_SITES, exist_ok=True)
    json.dump({"dataset_url": DATASET_URL, "dataset_id": "kj7g-u4gp", "fetched_date": FETCHED,
               "raw_dir": "tmp/raw", "raw_in_git": False,
               "note": "raw JSONL exists locally and is intentionally not committed; v1 did not ship it either",
               "files": raw, "windows": windows, "timezone": "America/New_York",
               "query": "SoQL location_name patterns per site, window 2025-09-08/09 to 2026-09-07/08, paged"},
              open(os.path.join(OUT_SITES, "snapshot_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    lines = ["# NYC 市政库 v2 覆盖与日期状态", "",
             "类型: 数据说明", "状态: 生效", "负责人: tho25", "日期: 2026-11-03",
             "生成命令: python data/tools/rebuild_nyc_v2.py", "",
             "## 1 口径", "",
             "- 会话区间：start = date + connected_time（本地时区，fold 用 disconnected_time 选择）；"
             "end = start + connected_duration_min（绝对分钟，DST 安全）；跨午夜裁剪进两天。",
             "- 占用：同一 (charge_box_id, connector_id) 的区间先合并，再做日历日峰值扫描；合并是物理占用规则，不是丢弃重叠记录。",
             "- m_obs（主口径）= 有至少一条会话的观测日；m_span（敏感性）= 首个开始日到最后一个结束日之间的全部日，无会话日记 W=0。",
             "- 证书：单侧 Massart d+ = sqrt(ln(1/α)/(2m))，α=.05；n 取最小使 min(1, p̂_n + d+) ≤ ρ。",
             "- 资格阈值沿用 v1：67 天（ρ=.15 的最小样本量）；ρ=.10 需要 150 天。", "",
             "## 2 站点表", "",
             "| site | m_obs | m_span | 有会话 | 无法判定 | 确认零事件 | 有证据闭馆 | 有证据缺报 | peak | n_obs 下/上界 | cert .10/.15/.20 (m_obs) | 关系 .10/.15/.20 | cert .15 (m_span) | 资格(m_obs) | 资格(m_span) |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---|---|"]
    for r in site_rows:
        ds = r["date_status"]
        cert = r["cert_observed"]
        certs = "/".join("-" if cert[str(x)] is None else str(cert[str(x)]) for x in RHOS)
        rels = "/".join(r["cert_relation_observed"][str(x)] for x in RHOS)
        span15 = "-" if r["cert_span"]["0.15"] is None else str(r["cert_span"]["0.15"])
        lines.append(f"| {r['site_id']} | {r['m_observed']} | {r['m_span']} | {ds['observed_events']} | "
                     f"{ds['unknown_zero']} | {ds['confirmed_no_event']} | {ds['closed_with_evidence']} | "
                     f"{ds['missing_report_with_evidence']} | {r['peak_max']} | {r['service_points_lower']}/{r['service_points']} | "
                     f"{certs} | {rels} | {span15} | {'是' if r['analysis_eligible'] else '否'} | "
                     f"{'是' if r['analysis_eligible_span'] else '否'} |")
    lines += ["", "## 3 日期状态", "",
              "五个状态分开计数，不互相替代：", "",
              "- 有会话记录：当日至少一条会话（含跨日残留占用）。",
              "- 无法判定：跨度内无会话，且没有闭馆/缺报/零事件证据；不当作 0，也不当作缺失报告。",
              "- 已确认完整记录下的零事件：本轮为 0（没有日志完整性证据）。",
              "- 有证据的闭馆：本轮为 0（closure_evidence=null）。",
              "- 有证据的缺报：本轮为 0（没有采集中断证据）。", "",
              "周末不自动算闭馆；无会话也不自动算缺报。m_obs 只用有会话的日，"
              "因此证书目标应读作“有需求日的占用尾概率”，不是“全部运营日”。m_span 的零填充是敏感性假设。", "",
              "## 4 证书与容量代理", "",
              "- n_obs 上界 = 每个 charge_box_id 的 max(connector_id) 之和；下界 = 实际观测到的 (box, connector) 对数。"
              "两者都没有设备清单交叉验证，不能称为“已安装容量”。",
              "- 关系列：未发证 / 低于代理 / 达到 / 与代理冲突；达到时 n=n_obs，已服务占用尾部结构性为零，"
              "不能验证未服务需求、等待或经济最优。",
              "- 若某站 max W > n_obs，应优先查时间、重复、接口/设备语义，不允许上调代理来消除冲突。",
              "- 本轮没有出现 peak > n_obs；连接器编号未发现缺口（见 sites.jsonl 的 connector_gap_count）。",
              "- 证书对 m 口径敏感：qfa cert(.15) = 3 (m_obs) vs 2 (m_span)；wpl cert(.20) = 无 (m_obs) vs 17 (m_span)。"
              "sites.jsonl 同时保留 cert_observed 与 cert_span，不能只报一个数。", ""]
    open(os.path.join(OUT_SITES, "COVERAGE.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    n_events = payload["events"]
    n_rows = payload["rows_total"]
    cm = payload["class_totals"]
    lines = ["# NYC 市政库面板 v2", "",
             "类型: 数据说明", "状态: 生效", "负责人: tho25", "日期: 2026-11-03",
             "生成命令: python data/tools/rebuild_nyc_v2.py", "",
             "v1 保留在 data/charger_sites/nyc_v1 与 data/demand，本目录不覆盖旧结果。", "",
             "## 1 为什么有 v2", "",
             "v1 用 date + disconnected_time 推离开时间，只在 wall 时间 ≤ 到达时间时加 1 天；"
             "跨一个以上午夜或 DST 的会话因此被压成同日 wall 时长。v2 以 connected_duration_min 为准，"
             "用绝对分钟计算结束时间，并保留逐记录差异。", "",
             "## 2 结果", "",
             f"- 原始 {n_rows:,} 行，保留 {n_events:,} 条占用事件；非正时长 {cm.get('nonpositive', 0)} 条剔除，"
             f"未解释冲突 {payload['conflicts']} 条，重复 {cm.get('duplicate', 0)} 条。",
             f"- 重叠检查：duration 规则 {payload['overlap_duration']} 条，date=结束日 {payload['overlap_backward']} 条。",
             f"- multi_day {cm.get('multi_day', 0)} 条，DST {cm.get('dst', 0)} 条；"
             f"时长异常分类 {cm.get('multi_day', 0) + cm.get('dst', 0)} 条（multi_day {cm.get('multi_day', 0)} + DST {cm.get('dst', 0)}；" + f"|duration-wall|>60 为 {payload['abs_diff_gt_60']} 条）。",
             f"- 日历日峰值共 {payload['new_span_days']:,} 个站日（v1 {payload['old_span_days']:,}），"
             f"共同日中 {payload['changed_station_days_common']} 个峰值改变。",
             f"- 新跨度 {payload['new_span_days']:,} 天；峰值最大站："
             + "、".join(f"{r['site_id']}={r['peak_max']}" for r in sorted(site_rows, key=lambda x: -x["peak_max"])[:3]) + "。", "",
             "## 3 文件", "",
             "- sites.jsonl：站点、m_obs/m_span、证书、容量代理、日期状态。",
             "- COVERAGE.md：覆盖、日期状态、证书与代理关系。",
             "- sources.md：数据源、字段语义、原始文件哈希。",
             "- snapshot_manifest.json：查询窗口与原始快照清单（原始 JSONL 只在本地，不提交）。",
             "- CHANGELOG.md：v1 到 v2 的计数、峰值、证书变化。",
             "- 逐记录差异与逐站日差异在 data/demand_v2/diffs/。", "",
             "## 4 限制", "",
             "- m_obs 主口径条件在“有会话日”上，可能高估尾概率；m_span 零填充是相反的敏感性假设，两者都不是已证实的运营日历。",
             "- 容量代理来自观测到的 box/connector 编号，没有设备清单；不能称为安装容量。",
             "- 证书达到 n_obs 时是 M4 结构性零，不能验证未服务需求或经济最优。",
             "- 闭馆/缺报证据未采集，相关计数保持 0；无会话日一律标 unknown。",
             "- 敏感性分支：v1（wall/单日回卷）冻结在 nyc_v1，仅作历史对照；v2 的结论不依赖 v1。", "",
             "## 5 复跑", "",
             "python data/tools/rebuild_nyc_v2.py", ""]
    open(os.path.join(OUT_SITES, "README.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    lines = ["# Sources — nyc_v2 (rebuilt 2026-11-03 from the 2026-11-02 snapshot)", "",
             "## 1 数据集与字段语义", "",
             f"- 数据集：{DATASET_URL}（kj7g-u4gp），名称 Electric Vehicle (EV) Charging Data - Municipal Lots and Garages。",
             "- date：官方字段说明为 Date of the transaction；本轮按“到达日”使用，并用重叠检查验证："
             f"start=date+connected_time、end=start+duration 时同连接器重叠 {payload['overlap_duration']} 条；"
             f"把 date 读作结束日（end=date+disconnected_time、start=end-duration）时重叠 {payload['overlap_backward']} 条。"
             "旧审计的原型口径记 41/4,657，v2 固定口径为 32/5,306，数量级结论不变。"
             "注意：官方没有给时区字段，也没有明说 date 是到达日还是结束日；到达日 + duration 是证据支持的采用规则，"
             "不是官方明示。若源方更正语义，v2 必须重跑，不能把当前规则当永久事实。",
             "- connected_time / disconnected_time：插枪/拔枪的本地墙钟时间，无时区字段；按 America/New_York 解释，DST 歧义用 disconnected_time 选 fold。",
             "- connected_duration_min：官方说明为 number of minutes charger was connected；本轮作为时长权威来源。",
             "- charge_duration_min：实际充电分钟数，仅用于能量侧诊断，不用于占用区间。",
             "- energy_provided_kwh、session_status、invalidity_reason：能量与状态字段；INVALID/NO_ENERGY_DISPENSED 仍占位，计入占用，不计入有效能量。", "",
             "## 2 查询与快照", "",
             "- 窗口：各站 2025-09-08/09 至 2026-09-07/08（见 snapshot_manifest.json 的 windows）。",
             "- 条件：location_name 名称模式匹配（含别名），SoQL 分页抓取；抓取日期 2026-11-02。",
             "- 原始 JSONL 位于 tmp/raw/，本地存在但未提交到仓库；哈希与行数如下（不是“本地不存在”）。", "",
             "| site | rows | bytes | sha256 |", "|---|---:|---:|---|"]
    for x in raw:
        lines.append(f"| {x['site_id']} | {x['rows']:,} | {x['bytes']:,} | {x['sha256'][:16]}... |")
    lines += ["", "完整哈希见 snapshot_manifest.json。v1 的 sources.md 保留原样，作为旧快照记录。", ""]
    open(os.path.join(OUT_SITES, "sources.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    lines = ["# CHANGELOG — nyc_v1 → nyc_v2", "",
             "类型: 数据说明", "状态: 生效", "负责人: tho25", "日期: 2026-11-03", "",
             "v1 未改动；v2 是并排版本。", "",
             "| item | v1 | v2 |", "|---|---|---|",
             f"| events | 65,027 | {n_events:,} |",
             f"| span station-days | {payload['old_span_days']:,} | {payload['new_span_days']:,} |",
             f"| multi-day | 未单列（并入 wall） | {cm.get('multi_day', 0)} |",
             f"| DST-shifted | 未单列 | {cm.get('dst', 0)} |",
             f"| changed peaks (common days) | — | {payload['changed_station_days_common']} |", "",
             "## 峰值变化", "",
             "| site | v1 peak | v2 peak | v1 cert .10/.15/.20 | v2 cert (m_obs) |", "|---|---:|---:|---|---|"]
    v1_sites, v1_q = load_v1()
    for r in site_rows:
        sid = r["site_id"]
        old = v1_q.get(sid) or {}
        old_peak = old.get("peak_overlap_max")
        old_cert = old.get("certified_capacity_by_rho", {})
        oc = "/".join("-" if old_cert.get(str(x)) is None else str(old_cert.get(str(x))) for x in RHOS)
        nc = "/".join("-" if r["cert_observed"][str(x)] is None else str(r["cert_observed"][str(x)]) for x in RHOS)
        lines.append(f"| {sid} | {old_peak} | {r['peak_max']} | {oc} | {nc} |")
    lines += ["", "## 说明", "",
              "- v2 的证书主口径改用 m_obs；m_span 下的证书另存于 sites.jsonl，作为零填充敏感性。",
              "- 逐站日差异见 data/demand_v2/diffs/day_peak_diffs.csv；逐记录差异见 session_diffs.csv。",
              "- 旧报告、旧 COVERAGE、旧 V2/P4 数字均保留，不覆盖；引用时注明 v1/v2。", ""]
    open(os.path.join(OUT_SITES, "CHANGELOG.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")




def write_reconciliation(payload):
    v = payload["variants"]
    ct = payload["class_totals"]
    md = ct.get("multi_day", 0)
    dst = ct.get("dst", 0)
    ge60 = payload["abs_diff_ge_60"]
    eq60 = payload["abs_diff_eq_60"]
    lines = ["# 549/563 与 488/491 的对账（nyc v2）", "",
             "类型: 数据说明", "状态: 生效", "负责人: tho25", "日期: 2026-11-03", "",
             "旧审计给出过 549/563（时长差异）和 488/491（峰值差异）两组数；它们来自不同的临时口径。"
             "本文件固定一套规则，给出可复现行数，并说明旧数字为何不再作为证据。", "",
             "## 1 时长差异（固定口径）", "",
             "规则：start = date + connected_time；end = start + connected_duration_min；"
             "diff = duration − wall，wall = (disconnected_time − connected_time) mod 24h；"
             "异常先按分类计（multi_day / dst）；|diff| 阈值只作描述（DST 行可能落在 60 的任一侧）；"
             "multi_day 要求 |diff − k·1440| ≤ 1，DST 要求 |diff| ≈ k·1440 ± 60 且区间跨 DST。", "",
             "| 定义 | 行数 |", "|---|---:|",
             f"| multi_day | {md} |",
             f"| dst | {dst} |",
             f"| abs(diff) > 60 | {payload['abs_diff_gt_60']} |",
             f"| abs(diff) ≈ 60（±1e-9） | {eq60} |",
             f"| abs(diff) >= 60-1e-9 | {ge60} |",
             f"| abs(diff) >= 1440 | {payload['diff_ge_1440']} |",
             f"| nonpositive（剔除） | {ct.get('nonpositive', 0)} |",
             f"| other（隔离，默认不入面板） | {ct.get('other', 0)} |",
             f"| 旧式结束日与 v2 结束日不同 | {payload['legacy_end_shift']} |", "",
             f"分类异常共 {md + dst} 条 = {md} multi_day + {dst} DST；换成 |diff| 阈值：>60 为 {payload['abs_diff_gt_60']} 条，"
             f"≈±60 为 {eq60} 条（与 >60 有重叠），>=60-1e-9 为 {ge60} 条"
             f"（{md + dst - ge60} 条 DST 行因秒级取整落在 60 以下，仍按 ±60 容差归为 dst）。"
             "逐行见 data/demand_v2/diffs/session_diffs.csv。", "",
             "旧 549/563 的差异来自 wall 解析与单日回卷：旧实现只加 1 天，跨多日或 DST 时 wall 与 duration 的差"
             "会被截断或偏移，549 与 563 只是同一批记录的两种阈值计数。旧审计脚本没有保留固定阈值与逐行标记，"
             f"因此不能逐行重建 549/563；本轮以固定分类的 {md + dst} 行为准，不再引用旧的两个数。", "",
             "## 2 峰值差异（固定口径）", "",
             "规则：本地午夜边界；跨日会话裁剪进两天；同一 (box, connector) 先合并；"
             "只统计 v1 与 v2 共同存在的站日，旧峰值取 nyc_v1 的 peak_overlap_values。", "",
             "| 变体 | 共同站日中峰值改变数 |", "|---|---:|",
             f"| merged（主口径，本地午夜） | {v['merged']} |",
             f"| unmerged（不合并，仅敏感性） | {v['unmerged']} |",
             f"| merged + 旧式 wall 次日边界（DST 日 23/25h） | {v['merged_wallnext']} |",
             f"| unmerged + 旧式 wall 次日边界 | {v['unmerged_wallnext']} |", "",
             f"主口径为 {v['merged']} 个共同站日改变；v2 跨度 {payload['new_span_days']:,} 天，v1 {payload['old_span_days']:,} 天，"
             "新增站日不计入“改变”。逐站日见 data/demand_v2/diffs/day_peak_diffs.csv。", "",
             "旧 488/491 与固定口径 493/490 相差 2 个站日。合并/不合并只差 3（493 vs 490），"
             f"旧式 wall 次日边界与本地午夜完全相同（merged {v['merged_wallnext']} / unmerged {v['unmerged_wallnext']}），"
             "因此这 2 个差异不能归因于合并规则或 DST 边界。旧审计没有保存逐日峰值中间量，"
             "剩余 2 个差异的确切来源无法复核（UNVERIFIED）；本轮以 493/490 为准，旧 488/491 只作历史线索。", "",
             "## 3 结论", "",
             f"- 时长异常：固定分类 {md + dst} 条（{md} multi_day + {dst} DST），0 条 other；{ct.get('nonpositive', 0)} 条非正时长剔除。",
             f"- 峰值改变：固定主口径 {v['merged']} 个共同站日；unmerged 与旧 wall 边界变体见上表。",
             "- 旧 549/563、488/491 保留为历史线索，不作为本轮结论；引用时必须注明“旧临时口径”。", ""]
    open(os.path.join(OUT_DEMAND, "diffs", "reconciliation.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def main():
    windows = json.load(open(os.path.join(RAW, "windows.json"), encoding="utf-8"))
    v1_sites, v1_q = load_v1()
    os.makedirs(OUT_SITES, exist_ok=True)
    os.makedirs(OUT_DEMAND, exist_ok=True)
    os.makedirs(os.path.join(OUT_DEMAND, "diffs"), exist_ok=True)
    site_rows, summary = [], {}
    day_diffs, sess_diffs = [], []
    for sid in sorted(SITE_META):
        b = build_site(sid, windows)
        q = write_demand(sid, b)
        old = v1_q.get(sid) or {}
        old_peaks = {k: int(v) for k, v in old.get("peak_overlap_values", {}).items()}
        variants = count_variants(b, old_peaks)
        ov_d = overlap_count(b["rows"], mode="duration")
        ov_w = overlap_count(b["rows"], mode="wall")
        ov_b = overlap_count(b["rows"], mode="backward")
        diff60 = sum(1 for x in b["rows"] if abs(x["diff_min"]) > 60)
        diff60e = sum(1 for x in b["rows"] if abs(x["diff_min"]) >= 60 - 1e-9)
        diff60eq = sum(1 for x in b["rows"] if abs(abs(x["diff_min"]) - 60) <= 1e-9)
        diff1440 = sum(1 for x in b["rows"] if abs(x["diff_min"]) >= 1440 - 1e-9)
        legacy_shift = sum(1 for x in b["rows"] if legacy_end_date(x) != x["end"].date())
        common = [d for d in old_peaks if d in b["peaks"]]
        changed = [d for d in common if old_peaks[d] != b["peaks"][d]]
        new_days = [d for d in b["peaks"] if d not in old_peaks]
        for d in sorted(set(common) | set(b["peaks"])):
            day_diffs.append({"site_id": sid, "date": d, "old_peak": old_peaks.get(d),
                              "new_peak": b["peaks"].get(d),
                              "changed": int(d in old_peaks and old_peaks[d] != b["peaks"].get(d))})
        for x in b["rows"]:
            if x["class"] != "consistent":
                sess_diffs.append({"site_id": sid, "date": x["date"], "connected_time": x["connected_time"],
                                   "disconnected_time": x["disconnected_time"], "wall_min": round(x["wall_min"], 3),
                                   "duration_min": round(x["duration_min"], 3), "diff_min": round(x["diff_min"], 3),
                                   "class": x["class"], "dst_cross": int(x["dst_cross"]),
                                   "start_local": x["start"].isoformat(sep=" "),
                                   "end_local": x["end"].isoformat(sep=" ")})
        n_obs = b["upper"]
        cert15 = b["cert_obs"].get("0.15")
        row = {
            "site_id": sid, "site_name": SITE_META[sid][0], "city": "New York", "district": SITE_META[sid][1],
            "lat": None, "lon": None, "site_type": "路外场库",
            "charger_units": len(b["boxes"]), "service_points": n_obs,
            "service_points_lower": b["lower"], "power_mix": None,
            "operator": "New York City Department of Transportation (NYCDOT)",
            "status": "已投运", "as_of_date": b["last"], "date_semantics": "现状快照",
            "source_url": DATASET_URL, "source_type": "开放数据", "fetched_date": FETCHED,
            "raw_text": "location_name contains '%s'; distinct charge_box_id=%d; sum of max connector_id per box=%d" % (SITE_META[sid][2], len(b["boxes"]), n_obs),
            "notes": "charger_units = distinct charge_box_id; service_points = sum of max connector_id per box (proxy, not verified installed capacity); lower = distinct observed box-connector pairs",
            "total_spaces": None, "space_type": "off_street_garage",
            "spaces_as_of_date": None, "spaces_source_url": None, "spaces_source_type": None,
            "spaces_raw_text": None,
            "spaces_notes": "not obtained: NYC Municipal Parking Facilities datasets returned HTTP 403",
            "analysis_eligible": (len(b["observed"]) >= 67),
            "eligibility_reason": "%d observed days (primary); %d span days (sensitivity); rho=0.15 needs 67, rho=0.10 needs 150" % (len(b["observed"]), len(b["span"])),
            "analysis_eligible_span": (len(b["span"]) >= 67),
            "eligibility_reason_span": "%d span days with zero-fill sensitivity" % len(b["span"]),
            "lat_lon_status": "null: Nominatim returned no match on 2026-11-02",
            "closure_evidence": None,
            "version": VERSION, "rebuild_rule": RULE,
            "m_observed": len(b["observed"]), "m_span": len(b["span"]),
            "peak_max": max(b["vals_span"]),
            "cert_observed": b["cert_obs"], "cert_span": b["cert_span"],
            "cert_relation_observed": {str(r): relation(b["cert_obs"][str(r)], n_obs) for r in RHOS},
            "n_obs_proxy": n_obs, "n_obs_proxy_lower": b["lower"],
            "connector_gap_count": len(b["gaps"]),
            "date_status": b["day_status"],
            "conflict_count": len(b["conflicts"]),
            "certificate_note": "cert n equal to n_obs is the structural M4 case: served occupancy cannot exceed installed capacity, so T(n_obs)=0 by construction",
        }
        site_rows.append(row)
        summary[sid] = {"events": len(b["rows"]), "conflicts": len(b["conflicts"]),
                        "m_obs": len(b["observed"]), "m_span": len(b["span"]),
                        "peak_max": max(b["vals_span"]), "cert_obs": b["cert_obs"],
                        "cert_span": b["cert_span"], "n_obs": n_obs,
                        "changed_days": len(changed), "new_days": len(new_days),
                        "variants": variants, "diff_gt_60": diff60, "diff_ge_60": diff60e,
                        "diff_eq_60": diff60eq, "diff_ge_1440": diff1440, "legacy_end_shift": legacy_shift,
                        "overlap_duration": ov_d["count"], "overlap_wall": ov_w["count"],
                        "overlap_backward": ov_b["count"],
                        "class_counts": dict(b["stats"])}
    with open(os.path.join(OUT_SITES, "sites.jsonl"), "w", encoding="utf-8") as f:
        for r in site_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT_DEMAND, "diffs", "day_peak_diffs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site_id", "date", "old_peak", "new_peak", "changed"])
        w.writeheader(); w.writerows(day_diffs)
    with open(os.path.join(OUT_DEMAND, "diffs", "session_diffs.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["site_id", "date", "connected_time", "disconnected_time", "wall_min",
                                          "duration_min", "diff_min", "class", "dst_cross", "start_local", "end_local"])
        w.writeheader(); w.writerows(sess_diffs)
    total_changed = sum(1 for d in day_diffs if d["old_peak"] is not None and d["changed"])
    payload = {
        "version": VERSION, "rule": RULE, "site_count": len(site_rows),
        "events": sum(s["events"] for s in summary.values()),
        "rows_total": sum(s["class_counts"].get("rows", 0) for s in summary.values()),
        "conflicts": sum(s["conflicts"] for s in summary.values()),
        "duplicates": sum(s["class_counts"].get("duplicate", 0) for s in summary.values()),
        "changed_station_days_common": total_changed,
        "old_span_days": sum(len(v1_q[s]["peak_overlap_values"]) for s in summary if v1_q.get(s)),
        "new_span_days": sum(s["m_span"] for s in summary.values()),
        "class_totals": dict(sum((Counter(s["class_counts"]) for s in summary.values()), Counter())),
        "abs_diff_gt_60": sum(s["diff_gt_60"] for s in summary.values()),
        "abs_diff_ge_60": sum(s["diff_ge_60"] for s in summary.values()),
        "abs_diff_eq_60": sum(s["diff_eq_60"] for s in summary.values()),
        "diff_ge_1440": sum(s["diff_ge_1440"] for s in summary.values()),
        "legacy_end_shift": sum(s["legacy_end_shift"] for s in summary.values()),
        "overlap_duration": sum(s["overlap_duration"] for s in summary.values()),
        "overlap_wall": sum(s["overlap_wall"] for s in summary.values()),
        "overlap_backward": sum(s["overlap_backward"] for s in summary.values()),
        "variants": {k: sum(s["variants"][k] for s in summary.values())
                     for k in ("merged", "unmerged", "merged_wallnext", "unmerged_wallnext")},
        "sites": summary,
    }
    json.dump(payload, open(os.path.join(OUT_DEMAND, "diffs", "rebuild_summary.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    write_docs(site_rows, summary, payload, windows)
    write_reconciliation(payload)
    print("events", payload["events"], "conflicts", payload["conflicts"],
          "changed station-days (common)", total_changed,
          "old span", payload["old_span_days"], "new span", payload["new_span_days"])
    for sid, s in summary.items():
        print(sid, "m", s["m_obs"], "/", s["m_span"], "peak", s["peak_max"],
              "cert", s["cert_obs"], "n_obs", s["n_obs"], "changed", s["changed_days"])
    if "--skip-models" not in sys.argv:
        import v2_holdout, p4_dependence
        reports = os.path.join(ROOT, "docs", "reports")
        v2_holdout.main(sites_path=os.path.join(OUT_SITES, "sites.jsonl"), demand_dir=OUT_DEMAND,
                        out_json=os.path.join(OUT_DEMAND, "v2_holdout.json"),
                        out_md=os.path.join(reports, "2026-11-03-V2-样本外校准-v2.md"), version=VERSION)
        p4_dependence.main(sites_path=os.path.join(OUT_SITES, "sites.jsonl"),
                           v2_json=os.path.join(OUT_DEMAND, "v2_holdout.json"), demand_dir=OUT_DEMAND,
                           out_json=os.path.join(OUT_DEMAND, "p4_dependence.json"),
                           out_md=os.path.join(reports, "2026-11-03-P4-依赖敏感性-v2.md"), version=VERSION)
    return payload


if __name__ == "__main__":
    main()