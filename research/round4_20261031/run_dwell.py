# -*- coding: utf-8 -*-
"""Dwell-duration scenario sensitivity (±20%), fixed p_ev/q_need, capacity constraints."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNNER = os.path.join(ROOT, "research", "integer_allocation_20261031", "run_cost_curve.py")
PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
RULES = {"A": "dedicated_by_type", "B": "full_open_ice_first", "D": "predictive_shared_ice_first"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="停留情景敏感性")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--scales", default="0.8,1.0,1.2")
    parser.add_argument("--rules", default="A,B,D")
    parser.add_argument("--lots", default="TPE0008,TPE0401,TPE0610")
    parser.add_argument("--seeds", default="1,2,3")
    parser.add_argument("--outdir", default=os.path.join(ROOT, "research", "round4_20261031", "results", "dwell"))
    args = parser.parse_args(argv)
    os.makedirs(args.outdir, exist_ok=True)
    runs = []
    for scale in [float(s) for s in args.scales.split(",") if s.strip()]:
        for tag in [r.strip() for r in args.rules.split(",") if r.strip()]:
            out = os.path.join(args.outdir, "dwell_%s_%s_s3.json" % (scale, tag))
            cmd = [sys.executable, RUNNER, "--params", PARAMS, "--cost-file", COST,
                   "--lots", args.lots, "--seeds", args.seeds, "--rule", RULES[tag],
                   "--scenario-model", "independent", "--charge-catalog", args.catalog,
                   "--charge-scenario", "REF", "--dwell-scale", str(scale),
                   "--k-max", "40", "--workers", "1", "--out", out]
            started = time.time()
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            runs.append({"scale": scale, "rule": tag, "out": out, "exit": proc.returncode,
                         "seconds": round(time.time() - started, 2),
                         "stderr": proc.stderr[-2000:]})
            print(json.dumps({k: runs[-1][k] for k in ("scale", "rule", "exit", "seconds")}, ensure_ascii=False))
    with open(os.path.join(args.outdir, "dwell_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump({"runs": runs}, fh, ensure_ascii=False, indent=2)
    failed = [r for r in runs if r["exit"] != 0]
    print(json.dumps({"runs": len(runs), "failed": len(failed)}, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
