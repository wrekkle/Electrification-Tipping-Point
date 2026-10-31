import json
p = r"C:/Projects/停车场充电桩优化方案/research/cost_model_20261030/parameter_candidates_20261031.json"
d = json.load(open(p, encoding="utf-8"))
recs = d.get("records") or d.get("parameters") or []
if isinstance(recs, dict):
    fixed = []
    for k, v in recs.items():
        row = {"param_id": k}; row.update(v); fixed.append(row)
    recs = fixed
want = ("vot_per_hour_2026", "fuel_price_95_unleaded_2026_ytd", "electricity_tariff_ev_charging_2026", "carbon_fee_general", "co2_emission_factor_gasoline_mobile", "fuel_idle_consumption", "electricity_tariff_lowvoltage", "evse_annual_cost", "evse_capex_TWD_per_connector_2026", "evse_maintenance_TWD_per_connector_year_2026", "evse_lifetime_years_scenario", "cpi_index_base2021")
for r in recs:
    if any(r.get("param_id","") == w or r.get("param_id","").startswith(w) for w in want):
        print(json.dumps({k: r.get(k) for k in ("param_id","value","unit","region","period","price_year","status","source_class","is_scenario","locator","estimation_method","limitations")}, ensure_ascii=False)[:800])
        print()
