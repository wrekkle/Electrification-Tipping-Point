#!/usr/bin/env python3
"""Acceptance validator for data/charger_sites/*/sites.jsonl + data/demand/<site_id>/.

Checks: field presence/types, provenance non-empty, charger_units>=1,
service_points>=charger_units, total_spaces>=charger_units when present,
unique site_id, and demand-directory/event-file agreement.
Prints a provenance-missing list and a coverage table, then "0 errors".
"""
import csv, glob, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REQ = ["site_id","site_name","city","district","site_type","charger_units","service_points",
       "operator","status","as_of_date","date_semantics","source_url","source_type",
       "fetched_date","raw_text","total_spaces","space_type"]
PROV = ["source_url","source_type","fetched_date","raw_text"]
errors, prov_missing, rows = [], [], []

files = sorted(glob.glob(os.path.join(ROOT,"data","charger_sites","*","sites.jsonl")))
if not files:
    print("no sites.jsonl found"); sys.exit(1)

for fp in files:
    for ln, line in enumerate(open(fp, encoding="utf-8"), 1):
        line = line.strip()
        if not line: continue
        try:
            r = json.loads(line)
        except Exception as e:
            errors.append(f"{os.path.basename(fp)}:{ln} invalid JSON: {e}"); continue
        rows.append(r)
        sid = r.get("site_id")
        for k in REQ:
            if k not in r: errors.append(f"{sid}: missing field {k}")
        for k in PROV:
            if not r.get(k) or (isinstance(r.get(k), str) and not r[k].strip()):
                prov_missing.append(f"{sid}: {k}")
        cu = r.get("charger_units"); sp = r.get("service_points"); ts = r.get("total_spaces")
        if not isinstance(cu, int) or cu < 1: errors.append(f"{sid}: charger_units must be int>=1 (got {cu!r})")
        if sp is not None and (not isinstance(sp, int) or (isinstance(cu, int) and sp < cu)):
            errors.append(f"{sid}: service_points {sp!r} < charger_units {cu!r}")
        if ts is not None:
            if not isinstance(ts, int): errors.append(f"{sid}: total_spaces must be int or null")
            elif isinstance(cu, int) and ts < cu: errors.append(f"{sid}: total_spaces {ts} < charger_units {cu}")
        ddir = os.path.join(ROOT, "data", "demand", str(sid))
        if not os.path.isdir(ddir):
            errors.append(f"{sid}: missing demand dir {ddir}")
            continue
        ev = os.path.join(ddir, "events.csv")
        if not os.path.exists(ev):
            errors.append(f"{sid}: missing events.csv"); continue
        n = 0; bad = 0
        with open(ev, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                n += 1
                a, d = row["arrival_ts"], row["departure_ts"]
                if not a or not d: bad += 1; continue
                if a[-6:] not in ("-04:00","-05:00") or d[-6:] not in ("-04:00","-05:00"): bad += 1; continue
                if a > d: bad += 1
        if bad: errors.append(f"{sid}: {bad}/{n} events with bad/unsorted timezone-aware timestamps")
        q = os.path.join(ddir, "quality.json")
        if not os.path.exists(q): errors.append(f"{sid}: missing quality.json")

ids = [r.get("site_id") for r in rows]
dups = {i for i in ids if ids.count(i) > 1}
for d in dups: errors.append(f"duplicate site_id {d}")

print(f"sites files: {len(files)}  records: {len(rows)}  unique site_id: {len(set(ids))}")
print(f"provenance gaps: {len(prov_missing)}")
for p in prov_missing: print("  MISSING", p)
print("\ncoverage table")
print(f"{'site_id':10} {'units':>5} {'points':>6} {'spaces':>6} {'events':>7} {'days':>5} {'cov%':>6} {'hourcov%':>8} {'full24d':>7}")
for r in sorted(rows, key=lambda z: z.get("site_id") or ""):
    sid = r.get("site_id"); q = os.path.join(ROOT,"data","demand",str(sid),"quality.json")
    if os.path.exists(q):
        j = json.load(open(q, encoding="utf-8"))
        print(f"{sid:10} {r.get('charger_units',0):5} {str(r.get('service_points')):>6} {str(r.get('total_spaces')):>6} "
              f"{j['event_count']:7} {j['days_with_events']:5} {j['day_coverage_pct']:6.1f} {j['hourly_coverage_mean_pct']:8.2f} {j['days_full_24h']:7}")
    else:
        print(f"{sid:10} {r.get('charger_units',0):5} {str(r.get('service_points')):>6} {str(r.get('total_spaces')):>6} {'-':>7} {'-':>5} {'-':>6} {'-':>6}")
print()
for e in errors: print("ERROR", e)
print(f"{len(errors)} errors")
sys.exit(1 if errors else 0)
