import json, os, collections, datetime
BASE = "C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
target = {"TPE0008": 76, "TPE0007": 105, "TPE0151": 151, "TPE0003": 457}
occ = {lot: collections.defaultdict(lambda: [0.0, 0.0]) for lot in target}
for day in ["2026-10-30", "2026-10-31"]:
    with open(os.path.join(BASE, day, "parking_slots.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            lot = r.get("parking_id")
            if lot not in target or r.get("duplicate_batch") or r.get("data_missing") or not r.get("availablecar_valid"):
                continue
            a, t = r.get("availablecar_raw"), r.get("baseline_totalcar")
            if not isinstance(a, (int, float)) or not isinstance(t, (int, float)) or t <= 0:
                continue
            h = datetime.datetime.fromisoformat(r["slot_start_utc"]).astimezone(datetime.timezone(datetime.timedelta(hours=8))).hour
            occ[lot][h][0] += t - a; occ[lot][h][1] += t
for lot in target:
    profile = {h: round(v[0]/v[1], 3) for h, v in sorted(occ[lot].items()) if v[1]}
    mean_ratio = sum(v[0] for v in occ[lot].values())/sum(v[1] for v in occ[lot].values()) if occ[lot] else None
    print(lot, "n_spaces=", target[lot], "mean_occ_ratio=", round(mean_ratio,3) if mean_ratio else None)
    print("   by hour:", profile)
print("--- sessions per lot ---")
sessions = collections.Counter(); last = {}
for day in ["2026-10-30", "2026-10-31"]:
    with open(os.path.join(BASE, day, "connector_status_long.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            lot = r.get("parking_id")
            key = (lot, r.get("spot_abrv")); s = r.get("status_raw")
            if key not in last:
                last[key] = s; continue
            if s != last[key] and s == "充電中":
                sessions[lot] += 1
            last[key] = s
for lot in target:
    print(lot, "sessions=", sessions.get(lot, 0))
print("total sessions all lots=", sum(sessions.values()), "lots=", len(sessions))
