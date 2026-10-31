import json
p = r"C:/Projects/停车场充电桩优化方案/research/cost_model_20261030/parameter_candidates_20261031.json"
d = json.load(open(p, encoding="utf-8"))
recs = d.get("records") or d.get("parameters") or []
if isinstance(recs, dict):
    fixed = []
    for k, v in recs.items():
        row = {"param_id": k}
        row.update(v)
        fixed.append(row)
    recs = fixed
print("n params", len(recs))
want = ("evse", "capex", "depreciation", "maintenance", "fx", "exchange", "usd", "cpi", "annual")
for r in recs:
    pid = r.get("param_id", "")
    if any(w in pid.lower() for w in want):
        print("-", pid, "=", r.get("value"), "|", r.get("unit"), "| status", r.get("status"), "| class", r.get("source_class"), "| scenario", r.get("is_scenario"))
        lim = r.get("limitations") or []
        if lim:
            print("   lim:", str(lim)[:260])
