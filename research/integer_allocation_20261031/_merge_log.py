import json
log_path = r"C:/Projects/停车场充电桩优化方案/literature/reading-log.json"
add_path = r"C:/Projects/停车场充电桩优化方案/research/official_data_20261031/ev_behavior/reading_log_additions.json"
log = json.load(open(log_path, encoding="utf-8"))
add = json.load(open(add_path, encoding="utf-8"))
items = log.setdefault("items", {})
added = []
for key, value in add.get("items", {}).items():
    if key in items:
        continue
    items[key] = {"read_status": value["read_status"], "evidence": value["evidence"], "note": value["note"], "date": value["date"]}
    added.append(key)
log["items"] = dict(sorted(items.items()))
with open(log_path, "w", encoding="utf-8") as handle:
    json.dump(log, handle, ensure_ascii=False, indent=2)
print("added", added, "total", len(items))
size = len(open(r"C:/Projects/停车场充电桩优化方案/docs/TODO.md", encoding="utf-8").read())
print("TODO chars", size)
