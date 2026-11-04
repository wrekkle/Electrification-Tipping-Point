#!/usr/bin/env python3
"""Build the NYC municipal-garage charger panel from the raw Socrata pull.

Inputs (not shipped): tmp/raw/sess_<site_id>.jsonl, tmp/raw/windows.json
Outputs: data/charger_sites/nyc_v1/sites.jsonl, data/demand/<site>/events.csv,
         data/demand/<site>/quality.json, data/demand/<site>/sessions_b2.csv

No value is imputed: an unknown stays null and is explained in notes.
Capacity convention: charger_units = distinct charge_box_id; service_points =
sum over boxes of the highest connector_id seen (a two-gun box is one pile).

W_d convention (P0, default = D): calendar-day peak.  A session is clipped
into every calendar day it overlaps, so a session crossing midnight contributes
to both days; m = the full span, and zero-event days enter with W_d = 0.  The
arrival-day / event-days-only variant (A) is kept only as a sensitivity field
(peak_overlap_values_arrival_day) and is not the default.
The identification fields are added by recompute_certs.py; run it after this.
"""
import csv, json, math, os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW = os.path.join(ROOT, "tmp", "raw")
TZ = ZoneInfo("America/New_York")
ALPHA = 0.05

SITE_META = {
 "nyc-csq": ("Court Square Municipal Parking Garage", "Queens", "路外场库", "CSQ"),
 "nyc-qbo": ("Queens Borough Hall Municipal Parking Garage", "Queens", "路外场库", "QBO"),
 "nyc-des": ("Delancey and Essex Municipal Parking Garage", "Manhattan", "路外场库", "DES"),
 "nyc-jon": ("Jerome 190th Street Municipal Parking", "Bronx", "路外场库", "JON"),
 "nyc-bri": ("Bay Ridge Municipal Parking Garage", "Brooklyn", "路外场库", "BRI"),
 "nyc-jgu": ("Jerome Gun Hill Road Municipal Parking Garage", "Bronx", "路外场库", "JGU"),
 "nyc-sge": ("St. George Courthouse Garage", "Staten Island", "路外场库", "SGE"),
 "nyc-qfa": ("Queens Family Court Municipal Garage", "Queens", "路外场库", "QFA"),
 "nyc-cpo": ("College Point Municipal Parking Field", "Queens", "路外场库", "CPO"),
 "nyc-hpo": ("Hunts Point Municipal Parking Field", "Bronx", "路外场库", "HPO"),
 "nyc-stw": ("Steinway #2 Municipal Parking Field", "Queens", "路外场库", "STW"),
 "nyc-wpl": ("White Plains Road Municipal Parking Field", "Bronx", "路外场库", "WPL"),
}
DATASET_URL = "https://data.cityofnewyork.us/d/kj7g-u4gp"
FETCHED = "2026-11-02"


def parse_dt(date_s, time_s):
    d = datetime.strptime(date_s[:10], "%Y-%m-%d")
    t = (time_s or "").strip()
    if "T" in t or "-" in t[2:]:
        return datetime.fromisoformat(t.split(".")[0]).replace(tzinfo=TZ)
    hh, mm, ss = t.split(":")[:3]
    return d.replace(hour=int(hh), minute=int(mm), second=int(float(ss)), tzinfo=TZ)


def sweep_peak(intervals):
    ev = []
    for a, b in intervals:
        ev.append((a, 1)); ev.append((b, -1))
    ev.sort()
    cur = best = 0
    for _, v in ev:
        cur += v; best = max(best, cur)
    return best


def main():
    windows = json.load(open(os.path.join(RAW, "windows.json"), encoding="utf-8"))
    geo = {}
    gp = os.path.join(RAW, "geo.json")
    if os.path.exists(gp):
        geo = json.load(open(gp, encoding="utf-8"))
    out_sites = os.path.join(ROOT, "data", "charger_sites", "nyc_v1")
    os.makedirs(out_sites, exist_ok=True)
    site_rows, summary = [], {}

    for sid, (name, borough, stype, code) in SITE_META.items():
        src = os.path.join(RAW, f"sess_{sid}.jsonl")
        if not os.path.exists(src):
            print("MISSING RAW", sid); continue
        rows, seen, dropped = [], set(), Counter()
        for line in open(src, encoding="utf-8"):
            r = json.loads(line)
            try:
                arr = parse_dt(r["date"], r["connected_time"])
                dep = parse_dt(r["date"], r["disconnected_time"])
            except Exception:
                dropped["unparseable_time"] += 1; continue
            if dep <= arr:
                dep += timedelta(days=1)
                dropped["overnight_rollover_fixed"] += 1
            if dep <= arr:
                dropped["nonpositive_duration"] += 1; continue
            key = (r.get("charge_box_id"), r.get("connector_id"), arr.isoformat(), dep.isoformat())
            if key in seen:
                dropped["duplicate"] += 1; continue
            seen.add(key)
            rows.append({"arr": arr, "dep": dep, "box": r.get("charge_box_id"),
                         "con": str(r.get("connector_id") or ""), "kwh": r.get("energy_provided_kwh"),
                         "status": r.get("session_status"), "dur_min": r.get("connected_duration_min")})
        rows.sort(key=lambda x: x["arr"])
        if not rows:
            print("NO EVENTS", sid); continue

        per_day = defaultdict(list)
        for x in rows:
            per_day[x["arr"].date()].append((x["arr"], x["dep"]))
        days = sorted(per_day)
        first, last = days[0], days[-1]
        expected = (last - first).days + 1
        span = [first + timedelta(days=i) for i in range(expected)]
        missing = [str(d) for d in span if d not in per_day]
        # default convention D: calendar-day peak (clip each session into every day it overlaps)
        cal_day = defaultdict(list)
        for x in rows:
            d = x["arr"].date()
            while d <= x["dep"].date():
                ds = datetime.combine(d, datetime.min.time()).replace(tzinfo=TZ)
                de = ds + timedelta(days=1)
                st, en = max(x["arr"], ds), min(x["dep"], de)
                if en > st:
                    cal_day[d].append((st, en))
                d += timedelta(days=1)
        peaks = {str(d): sweep_peak(cal_day[d]) for d in span}
        peaks_arrival = {str(d): sweep_peak(per_day[d]) for d in days}

        # hourly coverage: hour bins of a local date overlapped by >=1 session
        cov = defaultdict(set)
        for x in rows:
            t = x["arr"].replace(minute=0, second=0, microsecond=0)
            while t < x["dep"]:
                cov[t.date()].add(t.hour)
                t = (t + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        hours_by_day = {d: len(cov[d]) for d in days}
        full24 = sum(1 for d in days if hours_by_day[d] == 24)
        ge95 = sum(1 for d in days if hours_by_day[d] >= 23)
        mean_cov = sum(hours_by_day.values()) / len(days) / 24 * 100

        pv = list(peaks.values())
        pv_a = list(peaks_arrival.values())
        m = expected  # D: sample = span days, zero-event days included as W_d = 0
        m_event = len(days)
        # v7 Prop.10 uses the one-sided Massart radius (1.1097x tighter at alpha=.05)
        dm = math.sqrt(math.log(1 / ALPHA) / (2 * m))
        rho_min = dm
        cert = {}
        for rho in (0.10, 0.15, 0.20):
            n_ok = None
            for n in range(0, max(pv) + 1):
                phat = sum(1 for w in pv if w > n) / m
                if min(1.0, phat + dm) <= rho:
                    n_ok = n; break
            cert[str(rho)] = n_ok
        boxes = sorted({x["box"] for x in rows if x["box"]})
        conns = defaultdict(set)
        for x in rows:
            if x["box"] and x["con"]:
                conns[x["box"]].add(int(x["con"]))
        service_points = sum(max(v) for v in conns.values())
        cross_day = sum(1 for x in rows if x["arr"].date() != x["dep"].date())

        dem = os.path.join(ROOT, "data", "demand", sid)
        os.makedirs(dem, exist_ok=True)
        with open(os.path.join(dem, "events.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["site_id", "arrival_ts", "departure_ts", "space_type", "cross_day"])
            for x in rows:
                w.writerow([sid, x["arr"].isoformat(sep=" "), x["dep"].isoformat(sep=" "),
                            "off_street_garage", int(x["arr"].date() != x["dep"].date())])
        with open(os.path.join(dem, "sessions_b2.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["site_id", "start", "end", "energy_kWh", "connected_minutes", "session_status"])
            for x in rows:
                w.writerow([sid, x["arr"].isoformat(sep=" "), x["dep"].isoformat(sep=" "),
                            x["kwh"], x["dur_min"], x["status"]])
        quality = {
            "site_id": sid,
            "source": {"dataset_url": DATASET_URL, "fetched_date": FETCHED,
                       "window_start": windows[sid]["start"], "window_end": windows[sid]["end"],
                       "timezone": "America/New_York",
                       "dst_handling": "zoneinfo localizes wall-clock times; DST days are 23/25 h long and are kept as calendar dates"},
            "event_count": len(rows),
            "date_first": str(first), "date_last": str(last),
            "days_with_events": m_event, "days_in_span": expected,
            "certificate_m": m,
            "missing_days_count": len(missing), "missing_days": missing[:400],
            "day_coverage_pct": round(100.0 * m_event / expected, 2),
            "hourly_coverage_mean_pct": round(mean_cov, 2),
            "hourly_coverage_definition": "share of the 24 clock hours of each observed date that are overlapped by at least one session interval; averaged over days",
            "days_full_24h": full24, "days_full_24h_pct": round(100.0 * full24 / m_event, 2),
            "days_ge_23h": ge95, "days_ge_23h_pct": round(100.0 * ge95 / m_event, 2),
            "hours_by_day_min": min(hours_by_day.values()), "hours_by_day_max": max(hours_by_day.values()),
            "peak_overlap_histogram": {str(k): v for k, v in sorted(Counter(pv).items())},
            "peak_overlap_max": max(pv), "peak_overlap_mean": round(sum(pv) / m, 3),
            "peak_overlap_values": peaks,
            "peak_overlap_max_arrival_day": max(pv_a),
            "peak_overlap_mean_arrival_day": round(sum(pv_a) / m_event, 3),
            "peak_overlap_values_arrival_day": peaks_arrival,
            "daily_event_counts": {str(d): len(per_day[d]) for d in days},
            "certified_capacity_by_rho": cert,
            "dkw_radius_dm": round(dm, 6),
            "days_needed": {"rho_0.10": math.ceil(math.log(1 / ALPHA) / (2 * 0.10 ** 2)),
                            "rho_0.15": math.ceil(math.log(1 / ALPHA) / (2 * 0.15 ** 2))},
            "min_certifiable_rho": round(rho_min, 6),
            "cross_day_events": cross_day,
            "charger_units_observed": len(boxes),
            "service_points_observed": service_points,
            "dropped_rows": dict(dropped),
            "notes": "events are charging-session intervals from the operator log; buffer b=0; concurrent sessions proxy simultaneous demand",
            "peak_definition": "W_d = calendar-day peak overlap: each session is clipped into every calendar day it overlaps, so a session crossing midnight counts on both days",
            "peak_definition_default": "D (calendar-day peak; m = span, zero-event days included as W_d = 0)",
            "peak_definition_sensitivity": "A = arrival-day peak over event days only (peak_overlap_values_arrival_day); retained as the sensitivity convention, not the default",
            "certificate_sample": "m = days in span, zero-event days included (calendar-day convention)",
        }
        json.dump(quality, open(os.path.join(dem, "quality.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

        g = geo.get(sid, {})
        elig = m >= math.ceil(math.log(1 / ALPHA) / (2 * 0.15 ** 2))
        site_rows.append({
            "site_id": sid, "site_name": name, "city": "New York", "district": borough,
            "lat": g.get("lat"), "lon": g.get("lon"), "site_type": stype,
            "charger_units": len(boxes), "service_points": service_points,
            "power_mix": None,
            "operator": "New York City Department of Transportation (NYCDOT)",
            "status": "已投运", "as_of_date": str(last), "date_semantics": "现状快照",
            "source_url": DATASET_URL, "source_type": "开放数据", "fetched_date": FETCHED,
            "raw_text": f"location_name contains '{code}'; distinct charge_box_id={len(boxes)}; sum of max connector_id per box={service_points}",
            "notes": "charger_units = distinct charge_box_id seen in window; service_points = sum of max connector_id per box (two-gun boxes counted as one pile, two service points). No independent inventory cross-check obtained.",
            "total_spaces": None, "space_type": "off_street_garage",
            "spaces_as_of_date": None, "spaces_source_url": None, "spaces_source_type": None,
            "spaces_raw_text": None,
            "spaces_notes": "not obtained: NYC Municipal Parking Facilities datasets returned HTTP 403; report section 2",
            "analysis_eligible": elig,
            "eligibility_reason": (f"{m} span days: rho=0.15 feasible" if 67 <= m < 150
                                   else f"{m} span days: rho=0.15 and rho=0.10 feasible" if m >= 150
                                   else f"{m} span days: below the 67-day minimum for rho=0.15"),
            "lat_lon_status": "null: Nominatim returned no match on 2026-11-02; see report section 2",
        })
        summary[sid] = {"events": len(rows), "days": m_event, "span": expected, "missing": len(missing),
                        "cov": round(mean_cov, 1), "full24": full24, "peak_max": max(pv),
                        "boxes": len(boxes), "points": service_points, "rho_min": round(rho_min, 4),
                        "cert": cert}

    with open(os.path.join(out_sites, "sites.jsonl"), "w", encoding="utf-8") as f:
        for r in sorted(site_rows, key=lambda z: z["site_id"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    json.dump(summary, open(os.path.join(RAW, "build_summary.json"), "w"), indent=1)
    for k, v in summary.items():
        print(k, v)


if __name__ == "__main__":
    main()
