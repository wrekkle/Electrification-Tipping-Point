import json, os, collections
BASE = r"C:/Projects/停车场充电桩优化方案/research/collection/taipei_372_polling_20261030/data"
params = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json", encoding="utf-8"))
lots = {row["lot_id"]: row for row in params.get("per_lot") or []}
target = set(lots)
starts = collections.Counter(); charging_slots = collections.Counter(); states = collections.defaultdict(dict)
connectors = collections.defaultdict(set)
for day in ["2026-10-30", "2026-10-31"]:
    path = os.path.join(BASE, day, "connector_status_long.jsonl")
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            r = json.loads(line)
            lot = r.get("parking_id")
            if lot not in target:
                # 需要全体计数时再放开；这里只统计 18 个候选场站
                continue
            key = (lot, r.get("spot_abrv"))
            connectors[lot].add(r.get("spot_abrv"))
            state = r.get("status_raw")
            prev = states[lot].get(key)
            if state == "充電中":
                charging_slots[lot] += 1
                if prev != "充電中":
                    starts[lot] += 1
            states[lot][key] = state
print("lot  spaces  connectors  my_starts  file_n_transitions  my_charging_min  observed_lambda_charge_per_hour")
for lot_id in sorted(lots):
    row = lots[lot_id]
    my_starts = starts.get(lot_id, 0)
    their = row.get("n_charge_transitions_observed")
    charge_min = charging_slots.get(lot_id, 0) * 5
    print("%s  %s  %s  %s  %s  %s  %s" % (lot_id, row.get("n_spaces"), len(connectors.get(lot_id, [])),
          my_starts, their, charge_min, round(my_starts/24.0, 2)))
