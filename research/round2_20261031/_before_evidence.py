import json, os
ROOT = r"C:\Projects\停车场充电桩优化方案"
OUT = os.path.join(ROOT, "research/integer_allocation_20261031/outputs")
curve = json.load(open(os.path.join(OUT, "cost_curve_pi0_k40.json"), encoding="utf-8"))
rows = curve["rows"]
# 1) 成本缺陷：k=0 仍有资本成本
k0 = [r for r in rows if r["k"] == 0 and (r.get("cost_items") or {}).get("operator_capital_depreciation")]
print("CAPITAL_AT_K0", len(k0), json.dumps(k0[:2], ensure_ascii=False)[:300])
# 2) 占位口径：π1 行里 costs 的 no_charging_demand vs rules 台账
pi1 = [r for r in rows if r["rule"] == "full_open_ice_first"]
bad = {"rows": 0, "max_gap": 0.0, "sample": None}
for r in pi1:
    cost_min = (r.get("occupancy_minutes_by_reason") or {}).get("no_charging_demand")
    rules_min = (r.get("type_occupancy") or {}).get("no_charging_demand_bay_min")
    ice_min = (r.get("type_occupancy") or {}).get("ice_blocking_connector_min") or 0.0
    if cost_min is None or rules_min is None:
        continue
    gap = cost_min - rules_min
    if abs(gap) > 1e-6:
        if bad["sample"] is None:
            bad["sample"] = {"lot": r["lot_id"], "k": r["k"], "seed": r["seed"], "cost": cost_min, "rules": rules_min, "ice": ice_min}
        bad["rows"] += 1
        bad["max_gap"] = max(bad["max_gap"], abs(gap))
print("OCCUPANCY_MIXING", json.dumps(bad, ensure_ascii=False))
# 3) 搜索上限返回：k=40 仍未达标的比例
analysis = json.load(open(os.path.join(OUT, "analysis_pi0.json"), encoding="utf-8"))
bad_status = []
for lot, rec in analysis["lots"].items():
    by_k = {int(k): v for k, v in rec["curve"].items()}
    if 0 not in by_k or 40 not in by_k:
        continue
    base = by_k[0].get("unmet_no_connector_events")
    at40 = by_k[40].get("unmet_no_connector_events")
    k5 = rec["service_level_k"].get("0.05")
    if base and at40 is not None and at40 > 0.05 * base and k5 == 40:
        bad_status.append({"lot": lot, "base": base, "at40": at40, "reported_k5": k5, "ratio": round(at40 / base, 3)})
print("FALSE_RECOMMEND_AT_UPPER", json.dumps(bad_status[:6], ensure_ascii=False), "count", len(bad_status))
# 4) 模型文件里 q>1 的 p_EV 情景
model = json.load(open(os.path.join(ROOT, "research/calibration/charging_probability_20261030/model_20261031.json"), encoding="utf-8"))
grid = (((model.get("q_need_scenarios") or {}) and None) or (((model.get("p_EV_arrival") or {}).get("q_need_by_p_ev"))))
print("MODEL_KEYS", list(model.keys())[:10])
print("P_EV_GRID", json.dumps(model.get("p_EV_arrival"), ensure_ascii=False)[:500])
# 5) 数据目录：是否有多日
data_root = os.path.join(ROOT, "research/collection/taipei_372_polling_20261030/data")
print("DATA_DIRS", sorted(os.listdir(data_root))[:10] if os.path.isdir(data_root) else "missing")
