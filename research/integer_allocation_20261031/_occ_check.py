import json
d = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/test_curve_ws.json", encoding="utf-8"))
print(sorted(d["rows"][0].keys()))
for row in d["rows"][:3]:
    print("k", row["k"], "occ", row.get("mean_occupancy_rate"), "peak", row.get("peak_occupancy"))
