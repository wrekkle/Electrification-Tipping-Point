import json, os
BASE = r"C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
rows = []
for day in ["2026-10-30", "2026-10-31"]:
    with open(os.path.join(BASE, day, "connector_status_long.jsonl"), encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            if r.get("parking_id") == "TPE0151":
                rows.append((r["slot_start_utc"], r["spot_abrv"], r["status_raw"], r.get("duplicate_batch")))
rows.sort()
print("rows", len(rows), "connectors", len({r[1] for r in rows}))
for row in rows[:80]:
    print(row[0][11:19], row[1][-6:], row[2], row[3])
print("--- last 20 ---")
for row in rows[-20:]:
    print(row[0][11:19], row[1][-6:], row[2], row[3])
