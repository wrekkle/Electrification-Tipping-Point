# -*- coding: utf-8 -*-
"""Select fixed k on training seeds, then evaluate it on held-out seeds (round 4).

Selection uses only seeds 1..4 of the REF curves; evaluation uses seeds 5..10, which were
not used to choose the k. Two modes are produced:
  own_k    each rule uses its own training-selected median k;
  common_k every shared rule is evaluated at the dedicated rule's k (same device count).
The script never reuses an evaluation seed for selection.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "research", "round3_20261031"))
import analyze_round3 as R3  # noqa: E402

RUNNER = os.path.join(ROOT, "research", "integer_allocation_20261031", "run_cost_curve.py")
PARAMS = os.path.join(ROOT, "research", "traffic_generation_20261031", "fitted_parameters.json")
COST = os.path.join(ROOT, "research", "integer_allocation_20261031", "cost_scenario.json")
TRAIN = ["TPE0008", "TPE0401", "TPE0610", "TPE0695", "TPE0330"]
VALID = ["TPE0930", "TPE1376", "TPE1171", "TPE1380"]
LOTS = TRAIN + VALID
RULES = {"A": "dedicated_by_type", "B": "full_open_ice_first", "D": "predictive_shared_ice_first"}
FILE_TAG = {"A": "A_pi0", "B": "B_pi1", "D": "D_pi2"}
SEL_SEEDS = (1, 2, 3, 4)
EVAL_SEEDS = (5, 6, 7, 8, 9, 10)


def load(name):
    with open(os.path.join(R3.OUT, name), encoding="utf-8") as fh:
        return json.load(fh)


def select_k(tag):
    curve = load("main_%s_ref_s10.json" % FILE_TAG[tag])
    grouped = R3.group(curve["rows"])
    out = {}
    for lot in LOTS:
        achieved = []
        for seed in SEL_SEEDS:
            result = R3.joint_k(grouped.get((lot, seed), {}))
            if result["k"] is not None:
                achieved.append(result["k"])
        out[lot] = {"k": int(statistics.median(achieved)) if achieved else None,
                    "n_selection_cells": len(achieved), "achieved": achieved}
    return out


def run(rule, lot, k, outdir, catalog, tag):
    out = os.path.join(outdir, "fixedk_%s_%s_%s.json" % (tag, rule, lot))
    cmd = [sys.executable, RUNNER, "--params", PARAMS, "--cost-file", COST,
           "--lots", lot, "--seeds", ",".join(str(s) for s in EVAL_SEEDS),
           "--rule", RULES[rule], "--scenario-model", "independent",
           "--charge-catalog", catalog, "--charge-scenario", "REF",
           "--fixed-k", str(k), "--workers", "1", "--out", out]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {"rule": rule, "lot": lot, "mode": tag, "k": k, "out": out,
            "exit": proc.returncode, "stderr": proc.stderr[-2000:]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="训练选 k、独立种子评价")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--outdir", default=os.path.join(ROOT, "research", "round4_20261031", "results", "fixedk"))
    args = parser.parse_args(argv)
    os.makedirs(args.outdir, exist_ok=True)
    selection = {tag: select_k(tag) for tag in RULES}
    runs = []
    for lot in LOTS:
        for tag in RULES:
            k = selection[tag][lot]["k"]
            if k is not None:
                runs.append(run(tag, lot, k, args.outdir, args.catalog, "own"))
        k_a = selection["A"][lot]["k"]
        if k_a is not None:
            for tag in ("B", "D"):
                runs.append(run(tag, lot, k_a, args.outdir, args.catalog, "common"))
    payload = {"selection_seeds": list(SEL_SEEDS), "evaluation_seeds": list(EVAL_SEEDS),
               "selection": selection, "runs": runs}
    with open(os.path.join(args.outdir, "fixedk_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    failed = [r for r in runs if r["exit"] != 0]
    print(json.dumps({"runs": len(runs), "failed": len(failed), "outdir": args.outdir}, ensure_ascii=False))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
