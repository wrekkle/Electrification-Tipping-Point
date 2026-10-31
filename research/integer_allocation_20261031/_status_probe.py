import json, os, collections
BASE = "C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
status = collections.Counter()
lot_status = collections.defaultdict(collections.Counter)
with open(os.path.join(BASE, "2026-10-30", "connector_status_long.jsonl"), encoding="utf-8") as handle:
    for i, line in enumerate(handle):
        r = json.loads(line)
        status[r.get("status_raw")] += 1
        if i < 200000:
            lot_status[r["parking_id"]][r.get("status_raw")] += 1
out = {"status_counts": dict(status)}
with open("C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/status_values.json", "w", encoding="utf-8") as handle:
    json.dump(out, handle, ensure_ascii=False, indent=2)
print("done")
