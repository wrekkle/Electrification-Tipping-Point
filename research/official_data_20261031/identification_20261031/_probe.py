
import os, json, collections
proj = r"C:\Projects\停车场充电桩优化方案"
root = os.path.join(proj,"research","collection","taipei_372_polling_20261030","data")
outdir = os.path.join(proj,"research","official_data_20261031","identification_20261031")
# inspect one parking row types
for line in open(os.path.join(root,"2026-10-30","parking_slots.jsonl"), encoding="utf-8"):
    r = json.loads(line)
    print("SAMPLE", {k: (r[k] if not isinstance(r[k], str) or len(str(r[k]))<60 else str(r[k])[:60]) for k in ["parking_id","slot_start_utc","baseline_totalcar","availablecar_raw","availablecar_valid","observed_connector_count","data_missing","duplicate_batch"]})
    break
