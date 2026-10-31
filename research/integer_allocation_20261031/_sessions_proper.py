import json, os, collections, datetime
BASE = r"C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
params = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json", encoding="utf-8"))
lots = {row["lot_id"]: row for row in params.get("per_lot") or []}
target = set(lots)
rows = {}
for day in ["2026-10-30", "2026-10-31"]:
    with open(os.path.join(BASE, day, "connector_status_long.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r.get("parking_id") not in target or r.get("duplicate_batch"):
                continue
            key = (r["parking_id"], r["spot_abrv"], r["slot_start_utc"])
            if key in rows:
                continue
            rows[key] = r["status_raw"]
by_conn = collections.defaultdict(list)
for (lot, spot, ts), status in rows.items():
    by_conn[(lot, spot)].append((ts, status))
def parse(ts):
    return datetime.datetime.fromisoformat(ts)
per_lot = collections.defaultdict(lambda: {"sessions": 0, "minutes": 0.0, "durations": [], "censored": 0, "connectors": 0})
all_sessions = 0
for (lot, spot), seq in by_conn.items():
    seq.sort(key=lambda item: item[0])
    agg = per_lot[lot]
    agg["connectors"] += 1
    start = None
    last_charging_ts = None
    for ts, status in seq:
        if status == "充電中":
            if start is None:
                start = parse(ts)
            last_charging_ts = parse(ts)
        else:
            if start is not None:
                duration = (last_charging_ts - start).total_seconds()/60.0 + 5.0
                agg["sessions"] += 1
                agg["minutes"] += duration
                agg["durations"].append(duration)
                start = None
    if start is not None:
        duration = (last_charging_ts - start).total_seconds()/60.0 + 5.0
        agg["sessions"] += 1
        agg["minutes"] += duration
        agg["durations"].append(duration)
        agg["censored"] += 1
print("lot spaces conn sessions minutes mean_min file_n_transitions file_charge_min")
for lot_id in sorted(per_lot):
    agg = per_lot[lot_id]
    n = agg["sessions"]
    row = lots[lot_id]
    print("%s %s %s %s %.0f %.1f %s %s" % (lot_id, row.get("n_spaces"), agg["connectors"], n, agg["minutes"],
          (agg["minutes"]/n if n else 0), row.get("n_charge_transitions_observed"),
          (row.get("charge_duration_dist") or {}).get("n")))
print()
print("total sessions", sum(v["sessions"] for v in per_lot.values()), "over lots", len(per_lot))
