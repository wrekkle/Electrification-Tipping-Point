# -*- coding: utf-8 -*-
"""R2-B v2 independent verification of traffic_gen-2.0.0 on the frozen fitted parameters.

Checks (read-only on old data/JSON; writes one new JSON under research/round2_20261031/traffic_fix/):
  1. meta distribution columns exist and the demand identity holds for every usable lot;
  2. true demand is not pre-cut by the stay/power (new demand >= in-stay deliverable, gaps exist);
  3. demand energy hash is invariant when the generator scenario power/efficiency changes;
  4. warm start is stationary length biased: sampled mean remaining vs E[D^2]/(2E[D]) and vs
     the removed uniform-residual method E[D]/2 (two-point {1,9} closed form 4.1 min);
  5. right censoring is marked and excluded from charge_shortfall_sessions;
  6. t=0 occupancy still matches the observed mean; 24 h occupancy RMSE vs the old verification
     is re-measured to quantify the impact on the old conclusions.
Supersedes research/traffic_generation_20261031/verify.py for energy/warm-start semantics
(the old script asserts energy <= power*dwell, which is exactly the defect being fixed).

Run (repo root):
    python research/traffic_generation_20261031/verify_v2.py
    python research/traffic_generation_20261031/verify_v2.py --out research/round2_20261031/traffic_fix/traffic_fix_verify.json
Exit code 0 = all checks pass, 1 = a check failed.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from apps.parking_lab.workbench import traffic_gen  # noqa: E402

SEED = 42
TZ = timezone(timedelta(hours=8))
GRID_MIN = 5
N_GRID = 1440 // GRID_MIN
PARAMS_PATH = HERE / "fitted_parameters.json"
PANEL_PATH = HERE / "data" / "panel_selected_lots.json"
OLD_VERIFY = HERE / "outputs" / "verify_report.json"
DEFAULT_OUT = ROOT / "research" / "round2_20261031" / "traffic_fix" / "traffic_fix_verify.json"


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def local_minute(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).hour * 60 + \
        datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ).minute


def occupancy_grid(arrivals):
    grid = [0.0] * N_GRID
    for a in arrivals:
        start = int(a.time_min // GRID_MIN)
        end = int(math.ceil((a.time_min + a.dwell_min) / GRID_MIN))
        for idx in range(max(0, start), min(N_GRID, end)):
            grid[idx] += 1.0
    return grid


def pearson(x, y):
    n = len(x)
    if n < 2:
        return None
    mx, my = sum(x) / n, sum(y) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    sxx = sum((a - mx) ** 2 for a in x)
    syy = sum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def _two_point_params():
    dwell = {"family": "two_point", "mean_min": 5.0, "components": [
        {"name": "one", "weight": 0.5, "family": "lognormal_scenario",
         "params": [math.log(1.0), 0.0], "mean_min": 1.0},
        {"name": "nine", "weight": 0.5, "family": "lognormal_scenario",
         "params": [math.log(9.0), 0.0], "mean_min": 9.0}]}
    params = traffic_gen.load_params(PARAMS_PATH) if PARAMS_PATH.exists() else None
    params = copy.deepcopy(params) if params else {}
    params["traffic_fit"] = {
        "train": {"arrival_rate_per_100_spaces_hour": [0.0] * 24, "dwell": dwell},
        "cohort_reference": {"arrival_rate_per_100_spaces_hour": [0.0] * 24}}
    params["ev"] = {"p_ev_default": 0.5, "product_required_mean": 0.0}
    params["energy"] = {"charger_power_kw": 7.0, "efficiency": 0.9,
                        "deficit_mean_kwh": 20.0, "deficit_sd_kwh": 5.0,
                        "deficit_clip_kwh": [4.0, 55.0]}
    params["generator"] = dict(params.get("generator") or {}, horizon_min=60, max_arrivals=40000)
    params["per_lot"] = [{
        "lot_id": "TWO-POINT", "n_spaces": 20000.0, "fit_split": "train",
        "lambda_hour_by_bin": [0.0] * 24, "lambda_bar_veh_per_hour": 0.0,
        "dwell_dist": dwell, "charge_session_rate_hour_by_bin": [0.0] * 24,
        "charge_session_rate_mean_hour": 0.0, "mean_occupancy_vehicles": 20000.0,
        "connector_availability": 1.0, "usable": True}]
    return params


def _old_style_energy(entry, params, rng, n=5000):
    """Old (1.1.0) per-session energy: duration from the observed hist, capped by dwell."""
    power = float(params["energy"]["charger_power_kw"])
    eff = float(params["energy"]["efficiency"])
    comps = traffic_gen._components(entry["dwell_dist"])
    hist = entry.get("charge_duration_hist_5min") or {}
    items = sorted((float(k), int(v)) for k, v in hist.items() if int(v) > 0)
    total = sum(v for _, v in items)
    samples = []
    for _ in range(n):
        dwell = min(1440.0, max(1.0, traffic_gen._sample_dwell(comps, rng)))
        if items:
            u = rng.random() * total
            acc = 0.0
            minutes = items[-1][0]
            for value, count in items:
                acc += count
                if u <= acc:
                    minutes = value
                    break
            wanted = minutes + rng.random() * 5.0
            samples.append(power * eff * min(wanted, dwell) / 60.0)
        else:
            samples.append(power * eff * dwell / 60.0)
    return sum(samples) / len(samples)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    params = traffic_gen.load_params(PARAMS_PATH)
    panel = json.loads(PANEL_PATH.read_text(encoding="utf-8"))
    slots = panel["slot_start_utc"]
    power = float(params["energy"]["charger_power_kw"])
    eff = float(params["energy"]["efficiency"])
    cap = power * eff
    results = []
    lots = []
    rng_old = random.Random(20261031)
    for entry in params["per_lot"]:
        if not entry.get("usable"):
            continue
        lot_id = entry["lot_id"]
        lot_panel = panel["lots"].get(lot_id)
        arrivals, meta = traffic_gen.generate_for_lot(params, lot_id, SEED)
        n_warm = int(meta["initial_occupancy_n"])
        needs = [a for a in arrivals if a.needs_charge]
        demand = sum(a.energy_kwh for a in needs)
        precut = sum(min(a.energy_kwh, cap * a.dwell_min / 60.0) for a in needs)
        # Independent censoring/shortfall recount from the arrival stream.
        short = censored = 0
        for a in needs:
            if a.time_min + a.dwell_min > meta["horizon_min"] + 1e-9:
                censored += 1
            elif a.energy_kwh > cap * a.dwell_min / 60.0 + 1e-9:
                short += 1
        residual = sum(a.dwell_min for a in arrivals[:n_warm]) / n_warm if n_warm else None
        grid = occupancy_grid(arrivals)
        obs_mean = float(entry.get("mean_occupancy_vehicles") or 0.0)
        obs_at, gen_at = [], []
        if lot_panel:
            cap_space = float(lot_panel["n_spaces"])
            obs = lot_panel["occupancy_vehicles"]
            for index, slot in enumerate(slots):
                if obs[index] is None:
                    continue
                minute = local_minute(slot)
                if not (720 <= minute <= 1430):
                    continue
                grid_idx = minute // GRID_MIN
                gen_at.append(100.0 * grid[grid_idx] / cap_space)
                obs_at.append(100.0 * obs[index] / cap_space)
        rmse = (math.sqrt(sum((a - b) ** 2 for a, b in zip(obs_at, gen_at)) / len(gen_at))
                if gen_at else None)
        rel_rmse = (rmse / (sum(obs_at) / len(obs_at))) if rmse else None
        row = {
            "lot_id": lot_id, "fit_split": entry.get("fit_split"),
            "n_spaces": entry["n_spaces"], "warm_start_n": n_warm,
            "n_arrivals": len(arrivals), "n_new_arrivals": meta["n_new_arrivals"],
            "n_charge_sessions": meta["n_charge_sessions"],
            "occupancy_t0": grid[0], "occupancy_t0_observed": obs_mean,
            "occupancy_t0_relative_error": (grid[0] - obs_mean) / max(1.0, obs_mean),
            "occupancy_mean_24h": sum(grid) / len(grid),
            "occupancy_relative_rmse": rel_rmse, "occupancy_r": pearson(obs_at, gen_at),
            "warm_residual_mean_min": residual,
            "warm_residual_expected_min": meta["expected_warm_residual_mean_min"],
            "warm_residual_old_uniform_method_min": entry["dwell_dist"].get("mean_min", 0.0) / 2.0,
            "demand_energy_kwh_total": meta["demand_energy_kwh_total"],
            "demand_mean_kwh_per_session": (demand / len(needs)) if needs else None,
            "theoretical_service_min_total": meta["theoretical_service_min_total"],
            "deliverable_energy_kwh_total": meta["deliverable_energy_kwh_total"],
            "departed_shortfall_kwh": meta["departed_shortfall_kwh"],
            "pending_energy_kwh": meta["pending_energy_kwh"],
            "charge_shortfall_sessions": meta["charge_shortfall_sessions"],
            "censored_charge_sessions": meta["censored_charge_sessions"],
            "shortfall_recount_independent": short,
            "censored_recount_independent": censored,
            "old_rule_precut_energy_kwh_total": precut,
            "precut_share_of_true_demand": (1.0 - precut / demand) if demand else None,
            "old_style_energy_mean_kwh": _old_style_energy(entry, params, rng_old, n=3000),
            "ledger_identity_error": abs(meta["deliverable_energy_kwh_total"]
                                         + meta["departed_shortfall_kwh"]
                                         + meta["pending_energy_kwh"]
                                         - meta["demand_energy_kwh_total"]),
        }
        lots.append(row)
    # 1) energy invariance under generator power/efficiency scenarios
    invariance = {}
    for lot_id in [row["lot_id"] for row in lots[:2]]:
        hashes = set()
        for scenario in ({"charger_power_kw": 7.0}, {"charger_power_kw": 22.0},
                         {"charger_power_kw": 50.0}, {"efficiency": 0.7}):
            changed = copy.deepcopy(params)
            changed["energy"].update(scenario)
            arrivals, _ = traffic_gen.generate_for_lot(changed, lot_id, SEED)
            hashes.add(traffic_gen.stream_hash(arrivals))
        invariance[lot_id] = sorted(hashes)
    # 1b) pooled warm-start residual over several seeds (small lots have too few initial vehicles)
    pooled_n = 0
    pooled_sum = 0.0
    pooled_expected = 0.0
    pooled_old = 0.0
    for row in lots:
        entry = next(item for item in params["per_lot"] if item["lot_id"] == row["lot_id"])
        for seed in (1, 2, 3, 4, 5):
            warm_arrivals, warm_meta = traffic_gen.generate_for_lot(params, row["lot_id"], seed)
            n0 = int(warm_meta["initial_occupancy_n"])
            if n0 <= 0:
                continue
            pooled_n += n0
            pooled_sum += sum(a.dwell_min for a in warm_arrivals[:n0])
            pooled_expected += n0 * warm_meta["expected_warm_residual_mean_min"]
            pooled_old += n0 * (entry["dwell_dist"].get("mean_min", 0.0) / 2.0)
    pooled_warm = {
        "n": pooled_n,
        "sampled_mean_remaining_min": (pooled_sum / pooled_n) if pooled_n else None,
        "expected_stationary_mean_min": (pooled_expected / pooled_n) if pooled_n else None,
        "removed_uniform_method_mean_min": (pooled_old / pooled_n) if pooled_n else None,
        "relative_error": (pooled_sum / pooled_expected - 1.0) if pooled_n else None,
    }
    # 2) two-point warm start closed form
    two_point_params = _two_point_params()
    tp_arrivals, tp_meta = traffic_gen.generate_for_lot(two_point_params, "TWO-POINT", 3)
    tp_n = int(tp_meta["initial_occupancy_n"])
    tp_mean = sum(a.dwell_min for a in tp_arrivals[:tp_n]) / tp_n
    # 3) checks
    checks = {
        "energy_hash_invariant_to_power_and_efficiency": all(
            len(values) == 1 for values in invariance.values()),
        "two_point_warm_residual_4_1": abs(tp_mean - 4.1) < 0.15,
        "ledger_identity_all_lots": all(row["ledger_identity_error"] <= 1e-6 for row in lots),
        "censored_excluded_from_shortfall_all_lots": all(
            row["charge_shortfall_sessions"] == row["shortfall_recount_independent"]
            and row["censored_charge_sessions"] == row["censored_recount_independent"]
            for row in lots),
        "true_demand_exceeds_in_stay_deliverable": (
            sum(1 for row in lots if row["n_charge_sessions"] > 0
                and row["departed_shortfall_kwh"] + row["pending_energy_kwh"] > 0.0) >= 5),
        "pooled_warm_residual_close_to_stationary_mean": (
            pooled_warm["relative_error"] is not None
            and abs(pooled_warm["relative_error"]) < 0.05),
        "t0_occupancy_matches_observed_within_1pct": all(
            abs(row["occupancy_t0_relative_error"]) < 0.01 for row in lots),
        "warm_residual_far_from_removed_uniform_method": all(
            row["warm_residual_mean_min"] > 1.2 * row["warm_residual_old_uniform_method_min"]
            for row in lots),
    }
    old_report = {}
    if OLD_VERIFY.exists():
        old = json.loads(OLD_VERIFY.read_text(encoding="utf-8"))
        old_report = {"path": str(OLD_VERIFY), "pooled": old.get("pooled", {}),
                      "note": "旧脚本按 energy<=power*dwell 断言，与 R2-D3 冲突；仅作对照"}
    payload = {
        "schema": "traffic_fix_verify/v2",
        "generator_version": traffic_gen.GENERATOR_VERSION,
        "warm_start_method": traffic_gen.WARM_START_METHOD,
        "seed": SEED,
        "params_file": str(PARAMS_PATH),
        "params_sha256": sha256_file(PARAMS_PATH),
        "source_sha256": sha256_file(ROOT / "apps" / "parking_lab" / "workbench" / "traffic_gen.py"),
        "command": "python research/traffic_generation_20261031/verify_v2.py --out " + str(args.out),
        "python": sys.version.split()[0],
        "checks": checks,
        "pooled_warm_start": pooled_warm,
        "two_point_warm": {"n": tp_n, "sampled_mean_remaining_min": tp_mean,
                           "closed_form_min": 4.1,
                           "removed_uniform_method_min": 2.5},
        "energy_invariance_hashes_by_lot": invariance,
        "lots": lots,
        "old_verify_report": old_report,
    }
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    failed = [name for name, ok in checks.items() if not ok]
    print(json.dumps({"out": str(out), "checks": checks, "failed": failed,
                      "n_lots": len(lots)}, ensure_ascii=False, indent=1))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())