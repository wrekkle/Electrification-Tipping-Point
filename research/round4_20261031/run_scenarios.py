# -*- coding: utf-8 -*-
"""Round-4 source-scenario curve runner (thin subprocess driver).

Runs the existing integer-allocation runner once per (scenario, rule); every run loads the
catalogue through workbench.charge_sources and stores the full provenance block in rows
and document meta. No hidden-willingness inputs are added.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNNER = os.path.join(ROOT, "research", "integer_allocation_20261031", "run_cost_curve.py")
DEFAULT_PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
DEFAULT_COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
RULES = {"A": "dedicated_by_type", "B": "full_open_ice_first",
         "C": "protected_quota", "D": "predictive_shared_ice_first"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="来源充电概率情景曲线")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--scenarios", default="REF,M08-NEAR-BEV,M08-NEAR-COMBINED,M10-OUT-OF-HOME,M08-ALL-AWAY-REF")
    parser.add_argument("--rules", default="A,B,D")
    parser.add_argument("--lots", default="TPE0008,TPE0401,TPE0610,TPE0695,TPE0330")
    parser.add_argument("--seeds", default="1,2,3,4,5")
    parser.add_argument("--k-max", type=int, default=40)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true", help="重跑已存在的结果")
    parser.add_argument("--params", default=DEFAULT_PARAMS)
    parser.add_argument("--cost-file", default=DEFAULT_COST)
    parser.add_argument("--outdir", default=os.path.join(ROOT, "research", "round4_20261031", "results"))
    args = parser.parse_args(argv)
    os.makedirs(args.outdir, exist_ok=True)
    manifest = []
    for scenario in [s.strip() for s in args.scenarios.split(",") if s.strip()]:
        for tag in [r.strip() for r in args.rules.split(",") if r.strip()]:
            rule = RULES[tag]
            out = os.path.join(args.outdir, "scenario_%s_%s_s5.json" % (scenario, tag))
            if os.path.exists(out) and not args.force:
                try:
                    with open(out, encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if existing.get("rows") and not existing.get("failures"):
                        manifest.append({"scenario": scenario, "rule": tag, "out": out,
                                         "exit": 0, "seconds": 0.0, "skipped_existing": True})
                        print(json.dumps({"scenario": scenario, "rule": tag, "skipped": True}, ensure_ascii=False))
                        continue
                except (OSError, ValueError):
                    pass
            cmd = [sys.executable, RUNNER, "--params", args.params, "--cost-file", args.cost_file,
                   "--lots", args.lots, "--seeds", args.seeds,
                   "--rule", rule, "--scenario-model", "independent",
                   "--charge-catalog", args.catalog, "--charge-scenario", scenario,
                   "--k-max", str(args.k_max), "--workers", str(args.workers), "--out", out]
            started = time.time()
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            record = {"scenario": scenario, "rule": tag, "out": out, "exit": proc.returncode,
                      "seconds": round(time.time() - started, 2),
                      "stdout": proc.stdout.strip()[-2000:], "stderr": proc.stderr.strip()[-3000:]}
            manifest.append(record)
            print(json.dumps({k: record[k] for k in ("scenario", "rule", "exit", "seconds")}, ensure_ascii=False))
            if proc.returncode != 0:
                print(proc.stderr[-1500:], file=sys.stderr)
    with open(os.path.join(args.outdir, "scenario_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"command": sys.argv, "runs": manifest}, fh, ensure_ascii=False, indent=2)
    failed = [r for r in manifest if r["exit"] != 0]
    print(json.dumps({"runs": len(manifest), "failed": len(failed),
                      "catalog_sha256": __import__("hashlib").sha256(open(args.catalog, "rb").read()).hexdigest()},
                     ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
