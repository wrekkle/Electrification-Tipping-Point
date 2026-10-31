import hashlib, json, os, subprocess, sys, urllib.request
ROOT = r"C:\Projects\停车场充电桩优化方案"
files = ["apps/parking_lab/workbench/costs.py", "apps/parking_lab/workbench/traffic_gen.py",
         "apps/parking_lab/workbench/rules.py", "apps/parking_lab/workbench/prediction.py",
         "apps/parking_lab/workbench/allocation.py", "apps/parking_lab/workbench/simulation.py",
         "apps/parking_lab/workbench/config.py", "research/traffic_generation_20261031/fitted_parameters.json",
         "research/integer_allocation_20261031/outputs/cost_curve_pi0_k40.json",
         "research/integer_allocation_20261031/cost_scenario.json",
         "research/cost_model_20261030/parameter_candidates_20261031.json",
         "research/calibration/charging_probability_20261030/model_20261031.json",
         "docs/reports/2026-10-31-整数配桩规则与仿真验证.md"]
rows = []
for rel in files:
    path = os.path.join(ROOT, rel)
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
    rows.append({"file": rel, "sha256": digest, "bytes": os.path.getsize(path)})
print(json.dumps({"python": sys.version, "executable": sys.executable, "files": rows}, ensure_ascii=False, indent=1))
def qwen(path):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8081" + path, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as error:
        return {"error": "%s: %s" % (type(error).__name__, error)}
print("QWEN_HEALTH", json.dumps(qwen("/health"), ensure_ascii=False)[:300])
print("QWEN_STATS", json.dumps(qwen("/stats"), ensure_ascii=False)[:600])
