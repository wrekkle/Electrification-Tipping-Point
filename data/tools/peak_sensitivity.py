#!/usr/bin/env python3
"""Peak-definition sensitivity for W_d.

Compares four variants (P0: D is the default since 2026-11-02):
  A (sensitivity): arrival-day peak, event days only
  B: arrival-day peak, all span days (zero-event days added as W=0)
  C: calendar-day peak (cross-day sessions clipped into both days), event days only
  D (default): calendar-day peak, all span days

A is read from the retained field peak_overlap_values_arrival_day; D is recomputed
here from events.csv and checked against the stored default (peak_overlap_values),
so a mismatch is a real contradiction, not a formatting difference.
Writes data/demand/peak_definition_sensitivity.json and prints a compact table.
Read-only: does not modify quality.json.
"""
import csv, json, math, os
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ALPHA = 0.05
# Day boundaries must use the local zone, not the fixed UTC offset embedded in each
# timestamp: on DST days a fixed offset puts midnight one hour off and moves a
# cross-day session to the wrong calendar date (nyc-des 2025-11-02, found 2026-11-02).
TZ = ZoneInfo("America/New_York")
RHOS = (0.10, 0.15, 0.20)


def peak(intervals):
    ev = []
    for a, b in intervals:
        ev.append((a, 1)); ev.append((b, -1))
    ev.sort()
    cur = best = 0
    for _, v in ev:
        cur += v
        best = max(best, cur)
    return best


def tail(vals, n):
    return sum(1 for w in vals if w > n) / len(vals)


def form(vals, n_obs):
    t_lo = tail(vals, n_obs - 1)
    t_hi = tail(vals, n_obs)
    if t_lo == 0:
        return "empty"
    return "one_sided" if t_hi == 0 else "two_sided"


def cert(vals, rho):
    m = len(vals)
    d = math.sqrt(math.log(1.0 / ALPHA) / (2 * m))
    for n in range(0, max(vals) + 1):
        if min(1.0, tail(vals, n) + d) <= rho + 1e-12:
            return n
    return None


def main():
    sp = os.path.join(ROOT, "data", "charger_sites", "nyc_v1", "sites.jsonl")
    sites = [json.loads(l) for l in open(sp, encoding="utf-8") if l.strip()]
    rows = []
    for s in sites:
        sid = s["site_id"]
        qp = os.path.join(ROOT, "data", "demand", sid, "quality.json")
        ep = os.path.join(ROOT, "data", "demand", sid, "events.csv")
        if not (os.path.exists(qp) and os.path.exists(ep)):
            continue
        q = json.load(open(qp, encoding="utf-8"))
        pv = {k: int(v) for k, v in q.get("peak_overlap_values_arrival_day", {}).items()}
        stored_D = {k: int(v) for k, v in q["peak_overlap_values"].items()}
        first = date.fromisoformat(q["date_first"])
        last = date.fromisoformat(q["date_last"])
        span = [first + timedelta(days=i) for i in range((last - first).days + 1)]
        by_day = defaultdict(list)
        for r in csv.DictReader(open(ep, encoding="utf-8")):
            a = datetime.fromisoformat(r["arrival_ts"].replace(" ", "T")).astimezone(TZ)
            b = datetime.fromisoformat(r["departure_ts"].replace(" ", "T")).astimezone(TZ)
            if b <= a:
                continue
            for d in span:
                ds = datetime.combine(d, datetime.min.time()).replace(tzinfo=TZ)
                de = ds + timedelta(days=1)
                st, en = max(a, ds), min(b, de)
                if en > st:
                    by_day[d].append((st, en))
        cal = {str(d): peak(by_day[d]) for d in span}
        arr_days = sorted(pv)
        A = [pv[d] for d in arr_days]
        B = [pv.get(str(d), 0) for d in span]
        C = [cal[d] for d in arr_days]
        D = [cal[str(d)] for d in span]
        mism = [d for d in span if stored_D.get(str(d)) != cal[str(d)]]
        nobs = s["service_points"]
        rows.append({
            "site_id": sid, "n_obs": nobs,
            "default_D_mismatches": len(mism), "default_D_checked": len(span),
            "m_event": len(A), "m_span": len(D),
            "max_A": max(A), "max_D": max(D),
            "form_A": form(A, nobs), "form_C": form(C, nobs),
            "form_B": form(B, nobs), "form_D": form(D, nobs),
            "cert_A": {str(r): cert(A, r) for r in RHOS},
            "cert_B": {str(r): cert(B, r) for r in RHOS},
            "cert_C": {str(r): cert(C, r) for r in RHOS},
            "cert_D": {str(r): cert(D, r) for r in RHOS},
        })
    json.dump({"alpha": ALPHA, "default": "D", "variants": {
        "A": "arrival-day, event days (sensitivity, retained field)",
        "B": "arrival-day, all span days (zeros added)",
        "C": "calendar-day incl. carryover, event days",
        "D": "calendar-day incl. carryover, all span days (default)"}, "rows": rows},
        open(os.path.join(ROOT, "data", "demand", "peak_definition_sensitivity.json"), "w",
             encoding="utf-8"), ensure_ascii=False, indent=1)
    print("id        mEv mSp maxA maxD formA      formD      certA .10/.15/.20   certD(default) .10/.15/.20  Dchk")
    bad = 0
    for r in rows:
        ca = "/".join(str(r["cert_A"][str(x)]) for x in RHOS)
        cd = "/".join(str(r["cert_D"][str(x)]) for x in RHOS)
        bad += r["default_D_mismatches"]
        print(f"{r['site_id']:9s} {r['m_event']:3d} {r['m_span']:3d} {r['max_A']:4d} {r['max_D']:4d} "
              f"{r['form_A']:10s} {r['form_D']:10s} {ca:18s} {cd:28s} "
              f"{r['default_D_mismatches']}/{r['default_D_checked']}")
    print(f"default-D field vs recomputed calendar-day peaks: {bad} mismatched days")


if __name__ == "__main__":
    main()
