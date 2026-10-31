import json
p = r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json"
d = json.load(open(p, encoding="utf-8"))
print("CONSISTENCY:", json.dumps(d.get("consistency"), ensure_ascii=False)[:2200])
print()
print("VALIDATION:", json.dumps(d.get("validation"), ensure_ascii=False)[:2500])
print()
print("SPLIT:", json.dumps(d.get("split"), ensure_ascii=False)[:900])
print()
lots = {row["lot_id"]: row for row in d.get("per_lot") or []}
row = lots.get("TPE0151")
print("TPE0151 keys:", list(row.keys()))
print(json.dumps(row, ensure_ascii=False)[:2600])
