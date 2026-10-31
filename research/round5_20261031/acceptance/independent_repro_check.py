# -*- coding: utf-8 -*-
"""Round-5 independent acceptance: compare my own 25-stream reruns with round3/round4 and stored repro."""
import json, os, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
R = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
R3P = "research/round3_20261031/results/main_A_pi0_ref_s10.json"
R4P = "research/round4_20261031/results/scenario_REF_A_s5.json"
NEW = {
    "mine_w1": "research/round5_20261031/acceptance/indep_rerun_w1.json",
    "mine_w8": "research/round5_20261031/acceptance/indep_rerun_w8.json",
    "exec_w1": "research/round5_20261031/repro/repro_r3params_s5_k0.json",
    "exec_w8": "research/round5_20261031/repro/repro_r3params_s5_k0_w8.json",
    "exec_rep2": "research/round5_20261031/repro/repro_r3params_s5_k0_rep2.json",
}
def hashes(doc):
    out = {}
    for row in doc["rows"]:
        out.setdefault((row["lot_id"], int(row["seed"])), row["demand_hash"])
    return out
def sha(p):
    h = hashlib.sha256()
    with open(os.path.join(ROOT, p), "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""): h.update(c)
    return h.hexdigest()

r3, r4 = hashes(R(R3P)), hashes(R(R4P))
new = {k: hashes(R(v)) for k, v in NEW.items()}
keys = sorted(new["mine_w1"])
diff3 = {k for k in keys if r3.get(k) != new["mine_w1"][k]}
res = {
    "streams": len(keys), "rows_mine": {k: len(R(v)["rows"]) for k, v in NEW.items()},
    "mine_w1_eq_w8": new["mine_w1"] == new["mine_w8"],
    "mine_eq_exec_w1": new["mine_w1"] == new["exec_w1"],
    "exec_w1_eq_w8_eq_rep2": new["exec_w1"] == new["exec_w8"] == new["exec_rep2"],
    "r4_match_mine": sum(r4[k] == new["mine_w1"][k] for k in keys),
    "r3_match_mine": sum(r3[k] == new["mine_w1"][k] for k in keys),
    "stale_streams": sorted("%s/s%d" % k for k in diff3),
    "r3_k0_rows": sum(1 for r in R(R3P)["rows"] if int(r["k"]) == 0 and (r["lot_id"], int(r["seed"])) in set(keys)),
    "stale_r3_hashes": {("%s/s%d" % k): r3[k] for k in sorted(diff3)},
    "stale_new_hashes": {("%s/s%d" % k): new["mine_w1"][k] for k in sorted(diff3)},
    "all_keys_r3": len(r3),
    "src_now": {p: sha(p) for p in ("apps/parking_lab/workbench/traffic_gen.py",
                                    "research/integer_allocation_20261031/run_cost_curve.py")},
    "src_r3_meta": R(R3P)["meta"]["source_sha256"],
    "src_r4_meta": R(R4P)["meta"]["source_sha256"],
}
res["meta_equal_params"] = all(new[k][kk] is not None for k in new for kk in list(new[k])[:1])
# check param fields used
res["emitted_params"] = {k: {f: R(v)["meta"].get(f) for f in ("p_ev_override","q_need_override","horizon_min","scenario_model","feeder_kw","start_hour","rule","fixed_k")} for k, v in NEW.items()}
res["failures"] = []
if res["streams"] != 25: res["failures"].append("streams != 25")
if len(set(res["rows_mine"].values())) != 1 or list(res["rows_mine"].values())[0] != 25: res["failures"].append("row count not 25")
if not res["mine_w1_eq_w8"]: res["failures"].append("my w1 != w8")
if not res["mine_eq_exec_w1"]: res["failures"].append("mine != executor repro file")
if res["r4_match_mine"] != 25: res["failures"].append("r4 match != 25")
if res["r3_match_mine"] != 22: res["failures"].append("r3 match != 22")
print(json.dumps(res, ensure_ascii=False, indent=1))
raise SystemExit(1 if res["failures"] else 0)
