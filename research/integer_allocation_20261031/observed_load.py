import json, os, collections, datetime
BASE = r"C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
PARAMS = r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json"
OUT = r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/observed_charging_load.json"
params = json.load(open(PARAMS, encoding="utf-8"))
lots_info = {row["lot_id"]: row for row in params.get("per_lot") or []}
target = set(lots_info)
rows = {}
for day in ["2026-10-30", "2026-10-31"]:
    with open(os.path.join(BASE, day, "connector_status_long.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r.get("parking_id") not in target or r.get("duplicate_batch"):
                continue
            rows[(r["parking_id"], r["spot_abrv"], r["slot_start_utc"])] = r["status_raw"]
by_conn = collections.defaultdict(list)
for (lot, spot, ts), status in rows.items():
    by_conn[(lot, spot)].append((ts, status))
def parse(ts):
    return datetime.datetime.fromisoformat(ts)
per_lot = collections.defaultdict(lambda: {"sessions": 0, "minutes": 0.0, "durations": [], "censored": 0, "connectors": set()})
for (lot, spot), seq in by_conn.items():
    seq.sort(key=lambda item: item[0])
    agg = per_lot[lot]
    agg["connectors"].add(spot)
    start = None; last = None; breaks = 0
    for ts, status in seq:
        if status == "充電中":
            if start is None:
                start = parse(ts)
            last = parse(ts)
        else:
            if start is not None:
                duration = (last - start).total_seconds()/60.0 + 5.0
                agg["sessions"] += 1; agg["minutes"] += duration; agg["durations"].append(duration)
                start = None
    if start is not None:
        duration = (last - start).total_seconds()/60.0 + 5.0
        agg["sessions"] += 1; agg["minutes"] += duration; agg["durations"].append(duration); agg["censored"] += 1
out = {"window_hours": 24.0, "method": "dedupe (parking_id,spot_abrv,slot_start_utc), skip duplicate_batch, sort by time, count 充電中 runs", "lots": {}}
for lot_id, agg in per_lot.items():
    info = lots_info[lot_id]
    durations = sorted(agg["durations"])
    out["lots"][lot_id] = {
        "n_spaces": info.get("n_spaces"), "n_connectors": len(agg["connectors"]),
        "sessions": agg["sessions"], "charging_minutes": round(agg["minutes"], 1),
        "mean_session_min": round(agg["minutes"]/agg["sessions"], 1) if agg["sessions"] else None,
        "p50_session_min": durations[len(durations)//2] if durations else None,
        "censored_sessions": agg["censored"],
        "observed_load_erlang": round(agg["minutes"]/1440.0, 4),
        "session_rate_per_day": agg["sessions"],
        "mean_occupancy_vehicles": info.get("mean_occupancy_vehicles"),
        "mean_dwell_min": (info.get("dwell_dist") or {}).get("mean_min"),
        "fit_split": info.get("fit_split"),
        "usable": info.get("usable"),
    }
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(json.dumps({k: {kk: v[kk] for kk in ("sessions","charging_minutes","observed_load_erlang","mean_session_min")} for k, v in out["lots"].items()}, ensure_ascii=False)[:1200])
