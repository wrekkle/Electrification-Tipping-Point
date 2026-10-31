import json
c = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json", encoding="utf-8"))
for r in c["rows"]:
    if r["k"] == 0 and r["lot_id"] in ("TPE0610","TPE1011"):
        print(r["lot_id"], r["seed"], "total", r.get("cost_total"), "complete", r.get("cost_complete"), "missing", r.get("cost_missing_parameters"))
        print("  items", json.dumps(r.get("cost_items"), ensure_ascii=False)[:700])
        print("  unmet_nc", r.get("unmet_no_connector_events"), "charge_req", r.get("charge_requests"), "ev_arr", r.get("ev_arrivals"))
        break
# 统计 cost_complete=True 的分布
from collections import Counter
print(Counter((r["lot_id"], r["k"]) for r in c["rows"] if r.get("cost_complete")))
