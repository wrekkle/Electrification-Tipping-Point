import sys, json
sys.path.insert(0, r"C:/Projects/停车场充电桩优化方案")
from apps.parking_lab.workbench import traffic_gen
params = json.load(open(r"C:/Projects/停车场充电桩优化方案/research/traffic_generation_20261031/fitted_parameters.json", encoding="utf-8"))
print("has generate_for_lot:", hasattr(traffic_gen, "generate_for_lot"))
arr, meta = traffic_gen.generate_for_lot(params, "TPE0151", 1)
print("n arrivals", len(arr), "meta", json.dumps(meta, ensure_ascii=False, default=str)[:600])
print("first", arr[0])
print("ev share", sum(a.is_ev for a in arr)/len(arr), "need share", sum(a.needs_charge for a in arr)/max(1,sum(a.is_ev for a in arr)))
import statistics
print("mean dwell", statistics.mean(a.dwell_min for a in arr), "mean energy", statistics.mean(a.energy_kwh for a in arr if a.needs_charge))
from apps.parking_lab.workbench.demand import stream_hash
print("stream_hash", stream_hash(arr)[:16])
