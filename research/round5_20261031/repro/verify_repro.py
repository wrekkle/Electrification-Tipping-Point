# -*- coding: utf-8 -*-
"""Round-5 P0 verification: explain the three stale round-3 demand hashes.

Checks (exit 1 on any failure):
 1. current code is deterministic: workers=1 two independent runs -> identical hashes
 2. worker-count invariant: workers=1 == workers=8 for all 25 (lot, seed) streams
 3. current code reproduces round-4 REF hashes 25/25
 4. round-3 file reproduces 22/25; the 3 differing streams are the known set
 5. generator/runner source hashes recorded in the two round metas differ
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
R4 = os.path.join(ROOT, "research", "round4_20261031", "results", "scenario_REF_A_s5.json")
R3 = os.path.join(ROOT, "research", "round3_20261031", "results", "main_A_pi0_ref_s10.json")
NEW = {
    "w1": os.path.join(ROOT, "research", "round5_20261031", "repro", "repro_r3params_s5_k0.json"),
    "w8": os.path.join(ROOT, "research", "round5_20261031", "repro", "repro_r3params_s5_k0_w8.json"),
    "rep2": os.path.join(ROOT, "research", "round5_20261031", "repro", "repro_r3params_s5_k0_rep2.json"),
}
STALE = {("TPE0330", 2), ("TPE0401", 2), ("TPE0695", 3)}

def load(path):
    with open(path, encoding="utf-8") as h:
        return json.load(h)

def hashes(doc):
    out = {}
    for row in doc["rows"]:
        out.setdefault((row["lot_id"], int(row["seed"])), row["demand_hash"])
    return out

def main():
    r3, r4 = hashes(load(R3)), hashes(load(R4))
    new = {k: hashes(load(p)) for k, p in NEW.items()}
    keys = sorted(new["w1"])
    failures = []
    if not (new["w1"] == new["w8"] == new["rep2"]):
        failures.append("determinism/worker-invariance")
    if sum(r4[k] == new["w1"][k] for k in keys) != 25:
        failures.append("round4 reproduction != 25/25")
    match3 = sum(r3[k] == new["w1"][k] for k in keys)
    if match3 != 22:
        failures.append("round3 reproduction != 22/25 (got %d)" % match3)
    diff3 = {k for k in keys if r3[k] != new["w1"][k]}
    if diff3 != STALE:
        failures.append("unexpected stale set: %r" % (diff3,))
    m3 = load(R3)["meta"]["source_sha256"]
    m4 = load(R4)["meta"]["source_sha256"]
    changed = {k for k in set(m3) | set(m4) if m3.get(k) != m4.get(k)}
    if "apps/parking_lab/workbench/traffic_gen.py" not in changed:
        failures.append("traffic_gen.py source hash did not change between rounds")
    print(json.dumps({
        "streams": len(keys), "deterministic": new["w1"] == new["w8"] == new["rep2"],
        "worker_invariant": new["w1"] == new["w8"], "r4_match": sum(r4[k] == new["w1"][k] for k in keys),
        "r3_match": match3, "stale_streams": sorted("%s/s%d" % k for k in diff3),
        "changed_sources": sorted(os.path.basename(p) for p in changed),
        "failures": failures,
    }, ensure_ascii=False, indent=1))
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
