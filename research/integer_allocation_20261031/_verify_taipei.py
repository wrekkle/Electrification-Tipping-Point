"""Lead 独立核对台北 372 场原始数据（只读）。不作为 traffic-gen 校准结果，仅作交叉验证基准。"""
import json, os, collections, datetime
BASE = "C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
OUT = os.path.join("C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs")
os.makedirs(OUT, exist_ok=True)

def hours(iso):
    dt = datetime.datetime.fromisoformat(iso)
    return dt.astimezone(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H")

summary = {"parking": {}, "connector": {}}
for day in ["2026-10-30", "2026-10-31"]:
    path = os.path.join(BASE, day, "parking_slots.jsonl")
    rows = 0; valid = 0; missing = 0
    slot_set = set(); lots = set(); dup = 0
    cap = {}; occ_by_hour = collections.defaultdict(lambda: [0.0, 0.0])
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            rows += 1
            if r.get("duplicate_batch"):
                dup += 1
                continue
            slot_set.add(r["slot_start_utc"]); lots.add(r["parking_id"])
            cap[r["parking_id"]] = r.get("baseline_totalcar")
            if r.get("data_missing") or not r.get("availablecar_valid"):
                missing += 1
                continue
            avail = r.get("availablecar_raw"); total = r.get("baseline_totalcar")
            if not isinstance(avail, (int, float)) or not isinstance(total, (int, float)) or total <= 0:
                missing += 1; continue
            valid += 1
            h = hours(r["slot_start_utc"])
            occ_by_hour[h][0] += total - avail
            occ_by_hour[h][1] += total
    summary["parking"][day] = {"rows": rows, "valid": valid, "missing": missing, "duplicate": dup,
                               "slots": len(slot_set), "lots": len(lots)}
    prof = {h: round(v[0]/v[1], 4) for h, v in sorted(occ_by_hour.items()) if v[1] > 0}
    summary["parking"][day]["mean_occupancy_ratio_by_cst_hour"] = prof

    cpath = os.path.join(BASE, day, "connector_status_long.jsonl")
    status = collections.Counter(); crows = 0; per_lot_sessions = collections.Counter()
    last = {}
    with open(cpath, encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            crows += 1
            s = r.get("status_raw")
            status[s] += 1
            key = (r["parking_id"], r["spot_abrv"])
            prev = last.get(key)
            if s == "充電中" and prev != "充電中":
                per_lot_sessions[r["parking_id"]] += 1
            last[key] = s
    summary["connector"][day] = {"rows": crows, "status_counts": dict(status.most_common(10)),
                                 "lots_with_charging_starts": len(per_lot_sessions),
                                 "total_charging_starts": int(sum(per_lot_sessions.values()))}

with open(os.path.join(OUT, "taipei_raw_verify.json"), "w", encoding="utf-8") as handle:
    json.dump(summary, handle, ensure_ascii=False, indent=2)
print(json.dumps(summary["parking"], ensure_ascii=False)[:1200])
for day in summary["connector"]:
    print(day, "connector:", json.dumps(summary["connector"][day], ensure_ascii=False)[:600])
