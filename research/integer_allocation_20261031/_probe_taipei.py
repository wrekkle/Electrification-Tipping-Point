import json, os
base = "C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
for day in ["2026-10-30", "2026-10-31"]:
    for name in ["parking_slots.jsonl", "connector_status_long.jsonl"]:
        path = os.path.join(base, day, name)
        if not os.path.exists(path):
            print("MISSING", path); continue
        with open(path, encoding="utf-8") as handle:
            first = handle.readline()
        record = json.loads(first)
        print("==", day, name, "bytes=", os.path.getsize(path))
        print("keys=", list(record.keys()))
        print(json.dumps(record, ensure_ascii=False)[:700])
print("--- static cohort ---")
with open(os.path.join(base, "static", "cohort_static.json"), encoding="utf-8") as handle:
    static = json.load(handle)
if isinstance(static, dict):
    print("type=dict keys=", list(static.keys())[:10])
    entries = static.get("lots") or static.get("cohort") or static
else:
    entries = static
if isinstance(entries, dict):
    items = list(entries.items())[:1]
    print("sample entry:", json.dumps(items, ensure_ascii=False)[:800])
elif isinstance(entries, list):
    print("n=", len(entries))
    print("sample:", json.dumps(entries[0], ensure_ascii=False)[:900])
caps = []
if isinstance(entries, list):
    for row in entries:
        for key in ("capacity", "n_spaces", "total", "spaces", "car_total"):
            if isinstance(row, dict) and key in row and isinstance(row[key], (int, float)) and not isinstance(row[key], bool):
                caps.append(row[key]); break
if caps:
    caps.sort()
    print("capacity n=%d min=%s p25=%s p50=%s p75=%s max=%s sum=%s" % (len(caps), caps[0], caps[len(caps)//4], caps[len(caps)//2], caps[3*len(caps)//4], caps[-1], sum(caps)))
