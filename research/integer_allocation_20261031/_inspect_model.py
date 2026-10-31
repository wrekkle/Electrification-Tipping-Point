import json, sys
sys.path.insert(0, "C:/Projects/停车场充电桩优化方案")
p = "C:/Projects/停车场充电桩优化方案/research/calibration/charging_probability_20261030/model_20261031.json"
d = json.load(open(p, encoding="utf-8"))
print("top keys:", list(d.keys()))
for key in d:
    v = d[key]
    if isinstance(v, list):
        print(key, "list n=", len(v))
    elif isinstance(v, dict):
        print(key, "dict keys:", list(v.keys())[:12])
    else:
        print(key, "=", repr(v)[:200])
scen = d.get("q_need_scenarios") or []
for row in scen:
    keys = {k: row.get(k) for k in ("scenario_id", "q_need", "basis", "is_scenario", "applies_to", "source_id")}
    print(json.dumps(keys, ensure_ascii=False)[:300])
ident = d.get("identification")
print("identification:", json.dumps(ident, ensure_ascii=False)[:1500] if ident else None)
