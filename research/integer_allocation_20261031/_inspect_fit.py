import json, os
p = "C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json"
data = json.load(open(p, encoding="utf-8"))
print("top keys:", list(data.keys()))
for key, value in data.items():
    if isinstance(value, dict):
        print(key, "dict keys:", list(value.keys())[:14])
    elif isinstance(value, list):
        print(key, "list n=", len(value))
    else:
        print(key, "=", repr(value)[:120])
lots = data.get("per_lot") or data.get("lots") or []
print("per_lot n=", len(lots))
if lots:
    print("per_lot[0] keys:", list(lots[0].keys()))
    print(json.dumps(lots[0], ensure_ascii=False)[:2500])
    ids = [(row.get("lot_id"), row.get("n_spaces"), row.get("fit_split") or row.get("split")) for row in lots]
    print("ids/capacity/split:", ids[:25])
    print("capacity range:", min(x[1] for x in ids if x[1]), max(x[1] for x in ids if x[1]))
