"""Build machine-readable alignment evidence for the PREI Python baselines.

Reads the four fixed configs and their new run outputs, recomputes input hashes,
checks the 441-cell deterministic oracle against audit_numeric, and records
component/conservation residuals.  Writes one JSON evidence file; no prose
report and no writes outside experiments/prei.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

import compare_with_matlab as comparator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
AUDIT = ROOT / "research" / "electrification" / "matlab_audit_20261029"
RUNS = HERE / "runs"
EVIDENCE = HERE / "evidence"
CASES = [
    ("final_tvr_n40_legacy", "run2_v1_legacy"),
    ("final_tvr_n40_corrected", "run2_v1_corrected"),
    ("v2_n10786_legacy", "run2_v2_legacy"),
    ("v2_n10786_corrected", "run2_v2_corrected"),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_matrix(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def audit_module():
    spec = importlib.util.spec_from_file_location("audit_numeric", AUDIT / "audit_numeric.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def conservation(cfg, rows):
    max_component_error = 0.0
    max_capital_error = 0.0
    max_reject_over_demand = 0.0
    for row in rows:
        parts = sum(float(row[name]) for name in (
            "capital_daily_cost", "ev_fuel_cost", "ice_fuel_cost",
            "ev_time_cost", "ice_time_cost", "ev_complaint_cost",
            "ice_complaint_cost"))
        max_component_error = max(max_component_error,
                                  abs(parts - float(row["total_daily_cost"])))
        expected = (cfg["n_spaces"] * float(row["pile_ratio"])
                    * cfg["installation_cost_rmb_per_pile"]
                    / (365.0 * cfg["amortization_years"]))
        max_capital_error = max(max_capital_error,
                                abs(expected - float(row["capital_daily_cost"])))
        total = float(row["total_arrivals"])
        max_reject_over_demand = max(max_reject_over_demand,
                                     float(row["ev_rejected"]) - total,
                                     float(row["ice_rejected"]) - total)
    return {
        "rows": len(rows),
        "max_component_identity_abs_error_rmb": max_component_error,
        "max_capital_formula_abs_error_rmb": max_capital_error,
        "max_rejection_minus_total_arrivals": max_reject_over_demand,
        "all_rejections_within_total_arrivals": max_reject_over_demand <= 1e-9,
    }


def main():
    p, q = audit_module().parameters()
    oracle_cost, oracle_ev, oracle_ice = audit_module().deterministic_formula(p)
    cases = []
    run_names = {}
    for config_name, run_name in CASES:
        run_names[run_name] = config_name
        cfg_path = HERE / "configs" / f"{config_name}.json"
        run_dir = RUNS / run_name
        cfg = json.loads(cfg_path.read_text("utf-8"))
        meta = json.loads((run_dir / "metadata.json").read_text("utf-8"))
        rows = read_matrix(run_dir / "raw_cost_matrix.csv")
        fixture = (cfg_path.parent / cfg["fixture_file"]).resolve()
        fixture_meta = json.loads((fixture.parent / "fixture_meta.json").read_text("utf-8"))
        actual_config = sha256_file(cfg_path)
        actual_fixture = sha256_file(fixture)
        entry = {
            "config": str(cfg_path.relative_to(ROOT)),
            "run": str(run_dir.relative_to(ROOT)),
            "model_variant": cfg["model_variant"],
            "diagnostic_only": meta["diagnostic_only"],
            "input_hashes": {
                "config_actual": actual_config,
                "config_recorded": meta["input"]["config_sha256"],
                "config_matches": actual_config == meta["input"]["config_sha256"],
                "fixture_actual": actual_fixture,
                "fixture_recorded": meta["input"]["fixture_sha256"],
                "fixture_matches": actual_fixture == meta["input"]["fixture_sha256"],
                "fixture_meta_recorded": fixture_meta.get("fixture_sha256"),
                "fixture_meta_matches": fixture_meta.get("fixture_sha256") == actual_fixture,
            },
            "rows": len(rows),
            "days": len({(r["scenario_id"], r["ev_share_target"]) for r in rows}),
            "conservation": conservation(cfg, rows),
        }
        if run_name in ("run2_v1_legacy", "run2_v1_corrected"):
            n_t, n_r = len(cfg["ev_share_targets"]), len(cfg["pile_ratios"])
            matrix = [[0.0] * n_r for _ in range(n_t)]
            ev = [[0.0] * n_r for _ in range(n_t)]
            ice = [[0.0] * n_r for _ in range(n_t)]
            days = sorted({(r["scenario_id"], float(r["ev_share_target"])) for r in rows})
            day_index = {d: i for i, d in enumerate(days)}
            for row in rows:
                i = day_index[(row["scenario_id"], float(row["ev_share_target"]))]
                j = cfg["pile_ratios"].index(float(row["pile_ratio"]))
                matrix[i][j] = float(row["total_daily_cost"])
                ev[i][j] = float(row["ev_rejected"])
                ice[i][j] = float(row["ice_rejected"])
            diffs = []
            for i in range(n_t):
                for j in range(n_r):
                    diffs.append(abs(matrix[i][j] - float(oracle_cost[j, n_t - 1 - i])))
            ev_diffs = [abs(ev[i][j] - float(oracle_ev[j, n_t - 1 - i]))
                        for i in range(n_t) for j in range(n_r)]
            ice_diffs = [abs(ice[i][j] - float(oracle_ice[j, n_t - 1 - i]))
                         for i in range(n_t) for j in range(n_r)]
            entry["oracle"] = {
                "oracle": "research/electrification/matlab_audit_20261029/audit_numeric.py:deterministic_formula",
                "cells": n_t * n_r,
                "max_abs_cost_error_rmb": max(diffs),
                "max_abs_ev_rejection_error": max(ev_diffs),
                "max_abs_ice_rejection_error": max(ice_diffs),
                "within_atol_1e_9": max(max(diffs), max(ev_diffs), max(ice_diffs)) <= 1e-9,
            }
            if run_name == "run2_v1_corrected":
                full_cols = [j for j, r in enumerate(cfg["pile_ratios"]) if r == 1.0]
                full_diff = [abs(matrix[i][j] - float(oracle_cost[j, n_t - 1 - i]))
                             for i in range(n_t) for j in full_cols]
                entry["oracle"]["note"] = ("corrected_baseline is not a direct oracle copy: "
                                           "r=1 adds the EV complaint term the legacy oracle omits")
                entry["oracle"]["max_abs_full_install_difference_rmb"] = max(full_diff)
        cases.append(entry)

    candidate_by_run = {}
    matlab_runs = ROOT / "matlab" / "prei" / "runs"
    if matlab_runs.is_dir():
        for config_name, run_name in CASES:
            cfg_path = HERE / "configs" / f"{config_name}.json"
            cfg = json.loads(cfg_path.read_text("utf-8"))
            fixture = (cfg_path.parent / cfg["fixture_file"]).resolve()
            want = {"config": sha256_file(cfg_path), "fixture": sha256_file(fixture)}
            matches = []
            for meta_path in matlab_runs.glob("*/run_metadata.json"):
                _, hashes = comparator.read_metadata(meta_path.parent)
                if (hashes and hashes.get("config") == want["config"]
                        and hashes.get("fixture") == want["fixture"]
                        and (meta_path.parent / "raw_cost_matrix.csv").is_file()):
                    matches.append(meta_path.parent)
            if matches:
                candidate_by_run[run_name] = max(matches, key=lambda p: p.stat().st_mtime)
    verified = pending_count = 0
    for entry, run_name in zip(cases, [run for _, run in CASES]):
        candidate = candidate_by_run.get(run_name)
        reference = RUNS / run_name
        if candidate is None or not (candidate / "raw_cost_matrix.csv").is_file():
            entry["cross_language"] = {
                "status": "pending_matlab_output",
                "verdict": "NOT VERIFIED - no compliant M output for this config",
            }
            pending_count += 1
            continue
        code, report = comparator.compare_safe(reference, candidate)
        entry["cross_language"] = {
            "status": report.get("status"),
            "verdict": report.get("verdict"),
            "exit_code": code,
            "candidate": str(candidate.relative_to(ROOT)),
            "candidate_csv_sha256": report.get("candidate_csv_sha256"),
            "same_fixed_input": report.get("input_identity", {}).get("same_fixed_input"),
            "config_sha256": report.get("input_identity", {}).get("config_sha256"),
            "fixture_sha256": report.get("input_identity", {}).get("fixture_sha256"),
            "rows": report.get("rows"),
            "mismatch_count": report.get("mismatch_count"),
            "max_abs_error_by_column": report.get("max_abs_error_by_column"),
            "tie_mismatches": report.get("tie_mismatches"),
            "flag_errors": report.get("flag_errors"),
        }
        if code == 0:
            verified += 1
        else:
            pending_count += 1

    pending = {
        "status": f"verified_{verified}_of_{len(cases)}",
        "verified_configs": [c["run"] for c in cases
                             if c["cross_language"].get("exit_code") == 0],
        "pending_or_failed_configs": [c["run"] for c in cases
                                      if c["cross_language"].get("exit_code") != 0],
        "verdict": ("actual same-hash full-matrix pass where verified; remaining configs "
                    "are pending and NOT VERIFIED"),
        "note": "a copied-reference logic test is not counted as cross-language evidence",
    }
    evidence = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "four fixed Python baselines; fixed scenarios reused by every pile candidate",
        "environment": {"python": sys.version, "executable": sys.executable,
                        "platform": platform.platform()},
        "commands": {
            "fixtures": "python experiments/prei/sample_fixtures.py",
            "runs": "python experiments/prei/reference.py --config <config> --out <new run dir>",
            "tests": "python -m unittest discover -s experiments/prei/tests -v",
            "cross_language": ("python experiments/prei/compare_with_matlab.py "
                               "--reference experiments/prei/runs/run2_v1_legacy "
                               "--candidate matlab/prei/runs/<run>"),
        },
        "source_hashes": {
            "reference.py": sha256_file(HERE / "reference.py"),
            "schema.json": sha256_file(HERE / "schema.json"),
            "compare_with_matlab.py": sha256_file(HERE / "compare_with_matlab.py"),
            "sample_fixtures.py": sha256_file(HERE / "sample_fixtures.py"),
            "audit_numeric.py": sha256_file(AUDIT / "audit_numeric.py"),
            **{f"originals/{name}": sha256_file(AUDIT / "originals" / name)
               for name in ("final_tvr.m", "final_tvr_v2_fluc_re.m")},
        },
        "cases": cases,
        "cross_language": pending,
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "alignment_20261029.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({
        "out": str(out),
        "cases": len(cases),
        "oracle_legacy_max_error": cases[0]["oracle"]["max_abs_cost_error_rmb"],
        "all_hashes_match": all(c["input_hashes"]["config_matches"]
                                and c["input_hashes"]["fixture_matches"] for c in cases),
        "cross_language": pending["status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
